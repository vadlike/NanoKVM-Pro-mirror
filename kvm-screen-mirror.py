import argparse
import io
import json
import os
import sys
import threading
import time
import tkinter as tk

import numpy as np
import paramiko
from PIL import Image, ImageTk


PHYSICAL_WIDTH = 172
PHYSICAL_HEIGHT = 320
FRAME_SIZE = PHYSICAL_WIDTH * PHYSICAL_HEIGHT * 2


def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(get_app_dir(), "kvm-screen-mirror.json")
REMOTE_READER = r"""
import sys
import time

FRAME_SIZE = 172 * 320 * 2

with open('/dev/fb0', 'rb', buffering=0) as fb:
    while True:
        fb.seek(0)
        frame = fb.read(FRAME_SIZE)
        if len(frame) != FRAME_SIZE:
            time.sleep(0.005)
            continue
        sys.stdout.buffer.write(frame)
        sys.stdout.flush()
        time.sleep(0.016)
"""


def rgb565_to_image(frame_bytes):
    pixels = np.frombuffer(frame_bytes, dtype=np.uint16).reshape((PHYSICAL_HEIGHT, PHYSICAL_WIDTH))
    r = ((pixels >> 11) & 0x1F).astype(np.uint8) << 3
    g = ((pixels >> 5) & 0x3F).astype(np.uint8) << 2
    b = (pixels & 0x1F).astype(np.uint8) << 3
    rgb = np.dstack((r, g, b))
    return Image.fromarray(rgb, "RGB").rotate(-90, expand=True)


def load_connection_config(default_host, default_username, default_password):
    config = {
        "host": default_host,
        "username": default_username,
        "password": default_password,
    }
    if not os.path.exists(CONFIG_PATH):
        return config
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            config["host"] = payload.get("host") or config["host"]
            config["username"] = payload.get("username") or config["username"]
            config["password"] = payload.get("password") or config["password"]
    except Exception:
        pass
    return config


def save_connection_config(host, username, password):
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump({"host": host, "username": username, "password": password}, handle, indent=2)


class MirrorApp:
    def __init__(self, host, username, password, scale):
        config = load_connection_config(host, username, password)
        self.host = config["host"]
        self.username = config["username"]
        self.password = config["password"]
        self.scale = max(1, int(scale))
        self.base_image_size = (320, 172)
        self.client = None
        self.channel = None
        self.running = True
        self.connected = False
        self.connecting = False
        self.last_frame = None
        self.latest_frame_bytes = None
        self.latest_frame_serial = 0
        self.rendered_frame_serial = -1
        self.last_error = None
        self.display_width = 320
        self.display_height = 172
        self.render_width = self.display_width * self.scale
        self.render_height = self.display_height * self.scale
        self.render_offset_x = 0
        self.render_offset_y = 0
        self.drag_start = None
        self.window_drag = None
        self.resize_drag = None
        self.is_minimized = False
        self.titlebar_height = 34
        self.connection_height = 40
        self.controls_height = 46
        self.status_height = 28
        self.connection_generation = 0
        self.connection_lock = threading.Lock()

        self.root = tk.Tk()
        self.root.title("NanoKVM Screen Mirror")
        self.root.configure(bg="black")
        self.root.overrideredirect(True)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.bind("+", lambda _event: self.change_scale(1))
        self.root.bind("=", lambda _event: self.change_scale(1))
        self.root.bind("-", lambda _event: self.change_scale(-1))
        self.root.bind("_", lambda _event: self.change_scale(-1))
        self.root.bind("0", lambda _event: self.reset_scale())
        self.root.bind("<Left>", lambda _event: self.send_knob(-1))
        self.root.bind("<Right>", lambda _event: self.send_knob(1))
        self.root.bind("<Return>", lambda _event: self.send_press())
        self.root.bind("<space>", lambda _event: self.send_press())
        self.root.bind("l", lambda _event: self.send_long_press())
        self.root.bind("L", lambda _event: self.send_long_press())
        self.root.bind("f", lambda _event: self.fit_window())
        self.root.bind("F", lambda _event: self.fit_window())
        self.root.bind("<Control-s>", lambda _event: self.save_current_config())
        self.root.bind("<Map>", self.on_map)

        self.status_var = tk.StringVar(value="Ready")
        self.host_badge_var = tk.StringVar(value="Offline")
        self.host_var = tk.StringVar(value=self.host)
        self.username_var = tk.StringVar(value=self.username)
        self.password_var = tk.StringVar(value=self.password)
        titlebar = tk.Frame(self.root, bg="#0d1117", height=self.titlebar_height)
        titlebar.grid(row=0, column=0, sticky="ew")
        titlebar.pack_propagate(False)
        self.bind_drag_widget(titlebar)
        title_label = tk.Label(
            titlebar,
            text="NanoKVM Mirror",
            bg="#0d1117",
            fg="#f8fafc",
            padx=10,
            font=("Segoe UI Semibold", 11),
        )
        title_label.pack(side="left")
        self.bind_drag_widget(title_label)
        host_badge = tk.Label(
            titlebar,
            textvariable=self.host_badge_var,
            bg="#18202b",
            fg="#8fd3ff",
            padx=8,
            pady=2,
            font=("Segoe UI", 9),
        )
        host_badge.pack(side="left", padx=(0, 8), pady=5)
        self.bind_drag_widget(host_badge)
        self.close_button = self.make_button(titlebar, "X", self.close, width=3, bg="#3a1116")
        self.close_button.pack(side="right", padx=(0, 8), pady=4)
        self.min_button = self.make_button(titlebar, "—", self.minimize_window, width=3, bg="#111827")
        self.min_button.pack(side="right", padx=(0, 4), pady=4)
        self.about_button = self.make_button(titlebar, "About", self.show_about, width=6, bg="#18202b")
        self.about_button.pack(side="right", padx=(0, 6), pady=4)

        connection = tk.Frame(self.root, bg="#111827", height=self.connection_height)
        connection.grid(row=1, column=0, sticky="ew")
        connection.pack_propagate(False)
        tk.Label(connection, text="IP", bg="#111827", fg="#9fb0c3").pack(side="left", padx=(10, 4), pady=7)
        self.host_entry = self.make_entry(connection, self.host_var, 16)
        self.host_entry.pack(side="left", padx=(0, 8), pady=6)
        tk.Label(connection, text="Login", bg="#111827", fg="#9fb0c3").pack(side="left", padx=(0, 4), pady=7)
        self.username_entry = self.make_entry(connection, self.username_var, 10)
        self.username_entry.pack(side="left", padx=(0, 8), pady=6)
        tk.Label(connection, text="Password", bg="#111827", fg="#9fb0c3").pack(side="left", padx=(0, 4), pady=7)
        self.password_entry = self.make_entry(connection, self.password_var, 12, show="*")
        self.password_entry.pack(side="left", padx=(0, 8), pady=6)
        self.connect_button = self.make_button(connection, "Connect", self.start_connect, width=8, bg="#163047")
        self.connect_button.pack(side="left", padx=(0, 6), pady=5)
        self.save_button = self.make_button(connection, "Save", self.save_current_config, width=6, bg="#1f2937")
        self.save_button.pack(side="left", padx=(0, 6), pady=5)
        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0, bd=0)
        self.canvas.grid(row=2, column=0, sticky="nsew")
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", lambda _event: self.change_scale(1))
        self.canvas.bind("<Button-5>", lambda _event: self.change_scale(-1))
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Button-2>", lambda _event: self.send_back_tap())
        self.canvas.bind("<Button-3>", lambda _event: self.send_close_tap())
        controls = tk.Frame(self.root, bg="#0b1220", height=self.controls_height)
        controls.grid(row=3, column=0, sticky="ew")
        controls.pack_propagate(False)
        self.make_button(controls, "Knob -", lambda: self.send_knob(-1), width=8).pack(side="left", padx=(10, 6), pady=6)
        self.make_button(controls, "Knob +", lambda: self.send_knob(1), width=8).pack(side="left", padx=6, pady=6)
        self.make_button(controls, "OK", self.send_press, width=6).pack(side="left", padx=6, pady=6)
        self.make_button(controls, "Hold", self.send_long_press, width=6).pack(side="left", padx=6, pady=6)
        self.make_button(controls, "Right", self.send_swipe_right, width=7).pack(side="left", padx=6, pady=6)
        self.make_button(controls, "Left", self.send_swipe_left, width=7).pack(side="left", padx=6, pady=6)
        self.make_button(controls, "Back", self.send_back_tap, width=7).pack(side="right", padx=(6, 10), pady=6)
        self.make_button(controls, "Close", self.send_close_tap, width=7, bg="#3a1116").pack(side="right", padx=6, pady=6)
        self.make_button(controls, "Fit", self.fit_window, width=5).pack(side="right", padx=6, pady=6)
        status_frame = tk.Frame(self.root, bg="#0d1117", height=self.status_height)
        status_frame.grid(row=4, column=0, sticky="ew")
        status_frame.pack_propagate(False)
        self.status = tk.Label(
            status_frame,
            textvariable=self.status_var,
            anchor="w",
            bg="#0d1117",
            fg="#9fb0c3",
            padx=8,
            pady=3,
            font=("Segoe UI", 9),
        )
        self.status.pack(side="left", fill="x", expand=True)
        self.resize_grip = tk.Label(
            status_frame,
            text="◢",
            bg="#0d1117",
            fg="#5b6b80",
            padx=8,
            font=("Segoe UI", 9),
            cursor="bottom_right_corner",
        )
        self.resize_grip.pack(side="right")
        self.resize_grip.bind("<ButtonPress-1>", self.start_resize)
        self.resize_grip.bind("<B1-Motion>", self.on_resize_drag)
        self.fit_window()
        self.start_connect()
        self.root.after(16, self.repaint)

    def make_button(self, parent, text, command, width=8, bg="#17202b"):
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=bg,
            fg="#f8fafc",
            activebackground="#264158",
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            padx=6,
            pady=4,
            cursor="hand2",
        )

    def make_entry(self, parent, variable, width, show=None):
        return tk.Entry(
            parent,
            textvariable=variable,
            width=width,
            show=show,
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg="#1f2937",
            fg="#f8fafc",
            insertbackground="#f8fafc",
            font=("Segoe UI", 9),
        )

    def bind_drag_widget(self, widget):
        widget.bind("<ButtonPress-1>", self.start_window_drag)
        widget.bind("<B1-Motion>", self.on_window_drag)

    def start_window_drag(self, event):
        self.window_drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def on_window_drag(self, event):
        if not self.window_drag:
            return
        offset_x, offset_y = self.window_drag
        self.root.geometry("+{0}+{1}".format(event.x_root - offset_x, event.y_root - offset_y))

    def start_resize(self, event):
        self.resize_drag = (
            event.x_root,
            event.y_root,
            self.root.winfo_width(),
            self.root.winfo_height(),
        )

    def on_resize_drag(self, event):
        if not self.resize_drag:
            return
        start_x, start_y, start_w, start_h = self.resize_drag
        new_w = max(360, start_w + (event.x_root - start_x))
        new_h = max(240, start_h + (event.y_root - start_y))
        self.root.geometry("{0}x{1}".format(new_w, new_h))

    def minimize_window(self):
        self.is_minimized = True
        self.root.overrideredirect(False)
        self.root.update_idletasks()
        self.root.iconify()

    def on_map(self, _event):
        if self.root.state() == "normal":
            self.is_minimized = False
            self.root.after(10, lambda: self.root.overrideredirect(True))

    def show_about(self):
        about = tk.Toplevel(self.root)
        about.overrideredirect(True)
        about.configure(bg="#0d1117")
        panel = tk.Frame(about, bg="#111827", padx=14, pady=12)
        panel.pack()
        tk.Label(panel, text="NanoKVM Mirror", bg="#111827", fg="#f8fafc", font=("Segoe UI Semibold", 11)).pack()
        author = tk.Label(
            panel,
            text="Author: VADLIKE",
            bg="#111827",
            fg="#8fd3ff",
            font=("Segoe UI", 10),
            cursor="hand2",
        )
        author.pack(pady=(6, 0))
        author.bind("<Button-1>", lambda _event: self.open_url("https://github.com/vadlike"))
        repo = tk.Label(
            panel,
            text="Repo: vadlike/nanokvmpro-NanoKVM-Mirror",
            bg="#111827",
            fg="#8fd3ff",
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        repo.pack(pady=(4, 0))
        repo.bind("<Button-1>", lambda _event: self.open_url("https://github.com/vadlike/nanokvmpro-NanoKVM-Mirror"))
        tk.Label(panel, text="Minimal LCD mirror for NanoKVM", bg="#111827", fg="#9fb0c3", font=("Segoe UI", 9)).pack(pady=(4, 0))
        self.make_button(panel, "Close", about.destroy, width=8).pack(pady=(10, 0))
        about.update_idletasks()
        x = self.root.winfo_x() + ((self.root.winfo_width() - about.winfo_width()) // 2)
        y = self.root.winfo_y() + ((self.root.winfo_height() - about.winfo_height()) // 2)
        about.geometry("+{0}+{1}".format(max(0, x), max(0, y)))

    def open_url(self, url):
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception as exc:
            self.set_status("Open URL failed: {0}".format(exc))

    def set_status(self, message):
        try:
            self.status_var.set(message)
        except tk.TclError:
            pass

    def save_current_config(self):
        try:
            save_connection_config(self.host_var.get().strip(), self.username_var.get().strip(), self.password_var.get())
            self.set_status("Saved connection settings")
        except Exception as exc:
            self.set_status("Save failed: {0}".format(exc))

    def disconnect_transport(self):
        old_channel = self.channel
        old_client = self.client
        self.channel = None
        self.client = None
        self.connected = False
        if old_channel is not None:
            try:
                old_channel.close()
            except Exception:
                pass
        if old_client is not None:
            try:
                old_client.close()
            except Exception:
                pass

    def start_connect(self):
        if self.connecting or not self.running:
            return
        host = self.host_var.get().strip()
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not host or not username:
            self.set_status("IP and Login are required")
            return
        self.connecting = True
        self.connection_generation += 1
        generation = self.connection_generation
        self.host_badge_var.set("Connecting")
        self.set_status("Connecting to {0}...".format(host))
        threading.Thread(
            target=self.connect_worker,
            args=(generation, host, username, password),
            daemon=True,
        ).start()

    def connect_worker(self, generation, host, username, password):
        client = None
        channel = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, username=username, password=password, timeout=15)
            channel = client.get_transport().open_session()
            channel.exec_command("python3 - <<'PY'\n{0}\nPY".format(REMOTE_READER.strip()))
            with self.connection_lock:
                if generation != self.connection_generation or not self.running:
                    channel.close()
                    client.close()
                    return
                self.disconnect_transport()
                self.client = client
                self.channel = channel
                self.host = host
                self.username = username
                self.password = password
                self.connected = True
                self.connecting = False
                self.latest_frame_bytes = None
                self.latest_frame_serial = 0
                self.rendered_frame_serial = -1
                self.last_frame = None
                self.last_error = None
            self.root.after(
                0,
                lambda: (self.host_badge_var.set(host), self.set_status(
                    "Connected to {0} | click/drag screen | Right click X | Middle click Back".format(host)
                )),
            )
            threading.Thread(target=self.reader_loop, args=(generation, channel), daemon=True).start()
        except Exception as exc:
            if channel is not None:
                try:
                    channel.close()
                except Exception:
                    pass
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            with self.connection_lock:
                if generation == self.connection_generation:
                    self.connecting = False
                    self.connected = False
                    self.last_error = str(exc)
            self.root.after(0, lambda: (self.host_badge_var.set("Offline"), self.set_status("Connect failed: {0}".format(exc))))

    def read_exact(self, channel, size, generation):
        buffer = io.BytesIO()
        while buffer.tell() < size and self.running:
            if generation != self.connection_generation:
                return b""
            if channel.exit_status_ready():
                raise RuntimeError("Remote reader stopped")
            chunk = channel.recv(size - buffer.tell())
            if not chunk:
                time.sleep(0.01)
                continue
            buffer.write(chunk)
        return buffer.getvalue()

    def reader_loop(self, generation, channel):
        try:
            while self.running and generation == self.connection_generation:
                frame = self.read_exact(channel, FRAME_SIZE, generation)
                if len(frame) == FRAME_SIZE:
                    self.latest_frame_bytes = frame
                    self.latest_frame_serial += 1
        except Exception as exc:
            with self.connection_lock:
                if generation == self.connection_generation and self.running:
                    self.connected = False
                    self.last_error = str(exc)
            if generation == self.connection_generation and self.running:
                self.root.after(0, lambda: self.set_status("Mirror stopped: {0}".format(exc)))
        finally:
            if generation == self.connection_generation and self.running:
                self.connecting = False

    def change_scale(self, step):
        self.scale = max(1, min(8, self.scale + step))
        self.status_var.set(
            "Connected to {0} | scale x{1} | click screen = touch".format(self.host, self.scale)
        )
        self.fit_window()
        self.repaint()

    def reset_scale(self):
        self.scale = 2
        self.status_var.set(
            "Connected to {0} | scale x{1} | click screen = touch".format(self.host, self.scale)
        )
        self.fit_window()
        self.repaint()

    def fit_window(self):
        width = self.base_image_size[0] * self.scale
        height = (
            (self.base_image_size[1] * self.scale)
            + self.titlebar_height
            + self.connection_height
            + self.controls_height
            + self.status_height
        )
        self.canvas.configure(width=width, height=self.base_image_size[1] * self.scale)
        min_canvas_height = 120
        min_width = 640
        min_height = (
            self.titlebar_height
            + self.connection_height
            + self.controls_height
            + self.status_height
            + min_canvas_height
        )
        self.root.minsize(min_width, min_height)
        self.root.geometry("{0}x{1}".format(width, height))

    def on_mousewheel(self, event):
        if event.delta > 0:
            self.change_scale(1)
        elif event.delta < 0:
            self.change_scale(-1)

    def run_remote_command(self, command):
        if self.client is None or not self.connected:
            raise RuntimeError("Not connected")
        stdin, stdout, stderr = self.client.exec_command(command, timeout=10)
        stdout.read()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        if error:
            raise RuntimeError(error)

    def send_touch_tap(self, logical_x, logical_y):
        logical_x = max(0, min(self.display_width - 1, int(logical_x)))
        logical_y = max(0, min(self.display_height - 1, int(logical_y)))
        raw_x = max(0, min(171, logical_y))
        raw_y = max(0, min(319, (self.display_width - 1) - logical_x))
        command = (
            "python3 - <<'PY'\n"
            "import subprocess, time\n"
            "events = [\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_SLOT','0'),\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_TRACKING_ID','1'),\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_POSITION_X','{0}'),\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_POSITION_Y','{1}'),\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_TOUCH_MAJOR','20'),\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_WIDTH_MAJOR','10'),\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_PRESSURE','90'),\n"
            "('/dev/input/event2','EV_KEY','BTN_TOUCH','1'),\n"
            "('/dev/input/event2','EV_KEY','BTN_TOOL_FINGER','1'),\n"
            "]\n"
            "for dev, typ, code, value in events:\n"
            "    subprocess.run(['evemu-event','--sync',dev,'--type',typ,'--code',code,'--value',value], check=False)\n"
            "time.sleep(0.05)\n"
            "release = [\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_SLOT','0'),\n"
            "('/dev/input/event2','EV_ABS','ABS_MT_TRACKING_ID','-1'),\n"
            "('/dev/input/event2','EV_KEY','BTN_TOUCH','0'),\n"
            "('/dev/input/event2','EV_KEY','BTN_TOOL_FINGER','0'),\n"
            "]\n"
            "for dev, typ, code, value in release:\n"
            "    subprocess.run(['evemu-event','--sync',dev,'--type',typ,'--code',code,'--value',value], check=False)\n"
            "PY"
        ).format(raw_x, raw_y)
        self.run_remote_command(command)

    def logical_to_raw(self, logical_x, logical_y):
        logical_x = max(0, min(self.display_width - 1, int(logical_x)))
        logical_y = max(0, min(self.display_height - 1, int(logical_y)))
        raw_x = max(0, min(171, logical_y))
        raw_y = max(0, min(319, (self.display_width - 1) - logical_x))
        return raw_x, raw_y

    def send_touch_swipe(self, start_x, start_y, end_x, end_y, steps=8):
        start_raw_x, start_raw_y = self.logical_to_raw(start_x, start_y)
        end_raw_x, end_raw_y = self.logical_to_raw(end_x, end_y)
        points = []
        for index in range(steps):
            t = index / max(1, steps - 1)
            x = round(start_raw_x + ((end_raw_x - start_raw_x) * t))
            y = round(start_raw_y + ((end_raw_y - start_raw_y) * t))
            points.append((x, y))

        command = ["python3 - <<'PY'", "import subprocess, time"]
        command.append(
            "def emit(typ, code, value):\n"
            "    subprocess.run(['evemu-event','--sync','/dev/input/event2','--type',typ,'--code',code,'--value',str(value)], check=False)"
        )
        command.append("emit('EV_ABS','ABS_MT_SLOT',0)")
        command.append("emit('EV_ABS','ABS_MT_TRACKING_ID',1)")
        first_x, first_y = points[0]
        command.append("emit('EV_ABS','ABS_MT_POSITION_X',{0})".format(first_x))
        command.append("emit('EV_ABS','ABS_MT_POSITION_Y',{0})".format(first_y))
        command.append("emit('EV_ABS','ABS_MT_TOUCH_MAJOR',20)")
        command.append("emit('EV_ABS','ABS_MT_WIDTH_MAJOR',10)")
        command.append("emit('EV_ABS','ABS_MT_PRESSURE',90)")
        command.append("emit('EV_KEY','BTN_TOUCH',1)")
        command.append("emit('EV_KEY','BTN_TOOL_FINGER',1)")
        command.append("time.sleep(0.03)")
        for raw_x, raw_y in points[1:]:
            command.append("emit('EV_ABS','ABS_MT_POSITION_X',{0})".format(raw_x))
            command.append("emit('EV_ABS','ABS_MT_POSITION_Y',{0})".format(raw_y))
            command.append("time.sleep(0.02)")
        command.append("emit('EV_ABS','ABS_MT_TRACKING_ID',-1)")
        command.append("emit('EV_KEY','BTN_TOUCH',0)")
        command.append("emit('EV_KEY','BTN_TOOL_FINGER',0)")
        command.append("PY")
        self.run_remote_command("\n".join(command))

    def send_close_tap(self):
        try:
            self.send_touch_tap(20, 20)
            self.status_var.set("Sent touch tap to close button")
        except Exception as exc:
            self.status_var.set("Close tap failed: {0}".format(exc))

    def send_back_tap(self):
        try:
            self.send_touch_swipe(18, 86, 150, 86)
            self.status_var.set("Sent back swipe")
        except Exception as exc:
            self.status_var.set("Back swipe failed: {0}".format(exc))

    def send_swipe_left(self):
        try:
            self.send_touch_swipe(250, 86, 70, 86)
            self.status_var.set("Sent swipe left")
        except Exception as exc:
            self.status_var.set("Swipe left failed: {0}".format(exc))

    def send_swipe_right(self):
        try:
            self.send_touch_swipe(70, 86, 250, 86)
            self.status_var.set("Sent swipe right")
        except Exception as exc:
            self.status_var.set("Swipe right failed: {0}".format(exc))

    def send_knob(self, delta):
        if not self.running or self.client is None:
            return
        value = 1 if delta > 0 else -1
        try:
            self.run_remote_command(
                "evemu-event --sync /dev/input/event0 --type EV_REL --code REL_X --value {0}".format(value)
            )
            self.status_var.set("Sent knob {0:+d}".format(value))
        except Exception as exc:
            self.status_var.set("Knob failed: {0}".format(exc))

    def send_press(self):
        if not self.running or self.client is None:
            return
        try:
            self.run_remote_command(
                "evemu-event --sync /dev/input/event1 --type EV_KEY --code KEY_ENTER --value 1 && "
                "evemu-event --sync /dev/input/event1 --type EV_KEY --code KEY_ENTER --value 0"
            )
            self.status_var.set("Sent press")
        except Exception as exc:
            self.status_var.set("Press failed: {0}".format(exc))

    def send_long_press(self):
        if not self.running or self.client is None:
            return
        try:
            self.run_remote_command(
                "evemu-event --sync /dev/input/event1 --type EV_KEY --code KEY_ENTER --value 1 && "
                "sleep 0.8 && "
                "evemu-event --sync /dev/input/event1 --type EV_KEY --code KEY_ENTER --value 0"
            )
            self.status_var.set("Sent long press")
        except Exception as exc:
            self.status_var.set("Long press failed: {0}".format(exc))

    def canvas_to_logical(self, event_x, event_y):
        x = event_x - self.render_offset_x
        y = event_y - self.render_offset_y
        if x < 0 or y < 0 or x >= self.render_width or y >= self.render_height:
            return None
        logical_x = int((x / max(1, self.render_width)) * self.display_width)
        logical_y = int((y / max(1, self.render_height)) * self.display_height)
        return logical_x, logical_y

    def on_canvas_press(self, event):
        point = self.canvas_to_logical(event.x, event.y)
        self.drag_start = point

    def on_canvas_release(self, event):
        if not self.running or self.client is None:
            return
        start = self.drag_start
        self.drag_start = None
        end = self.canvas_to_logical(event.x, event.y)
        if not start or not end:
            return
        start_x, start_y = start
        end_x, end_y = end
        dx = end_x - start_x
        dy = end_y - start_y
        try:
            if abs(dx) >= 18 or abs(dy) >= 18:
                self.send_touch_swipe(start_x, start_y, end_x, end_y)
                self.status_var.set("Swipe {0},{1} -> {2},{3}".format(start_x, start_y, end_x, end_y))
            else:
                self.send_touch_tap(end_x, end_y)
                self.status_var.set("Touch tap {0},{1}".format(end_x, end_y))
        except Exception as exc:
            self.status_var.set("Touch failed: {0}".format(exc))

    def repaint(self):
        if self.latest_frame_serial != self.rendered_frame_serial and self.latest_frame_bytes is not None:
            self.last_frame = rgb565_to_image(self.latest_frame_bytes)
            self.rendered_frame_serial = self.latest_frame_serial

        if self.last_frame is not None:
            image = self.last_frame
            canvas_width = max(1, self.canvas.winfo_width())
            canvas_height = max(1, self.canvas.winfo_height())
            preferred_width = self.base_image_size[0] * self.scale
            preferred_height = self.base_image_size[1] * self.scale
            render_width = min(canvas_width, preferred_width)
            render_height = min(canvas_height, preferred_height)
            scale_factor = min(render_width / image.width, render_height / image.height)
            target_width = max(1, int(image.width * scale_factor))
            target_height = max(1, int(image.height * scale_factor))
            if target_width != image.width or target_height != image.height:
                image = image.resize(
                    (target_width, target_height),
                    Image.Resampling.NEAREST,
                )
            photo = ImageTk.PhotoImage(image)
            self.canvas.delete("all")
            self.render_width = image.width
            self.render_height = image.height
            self.render_offset_x = (canvas_width - image.width) // 2
            self.render_offset_y = (canvas_height - image.height) // 2
            self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=photo, anchor="center")
            self.canvas.image = photo
        if self.last_error:
            self.status_var.set(self.last_error)
        if self.running:
            self.root.after(16, self.repaint)
        else:
            self.root.after(500, self.close)

    def close(self):
        if not self.running:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
            return
        self.running = False
        self.disconnect_transport()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self):
        self.root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(description="Mirror NanoKVM local LCD to this PC over SSH")
    parser.add_argument("--host", default="192.168.27.159")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--scale", type=int, default=2)
    return parser.parse_args()


def main():
    args = parse_args()
    app = MirrorApp(args.host, args.username, args.password, args.scale)
    app.run()


if __name__ == "__main__":
    main()
