# NanoKVM Pro Mirror ![visitors](https://visitor-badge.laobi.icu/badge?page_id=vadlike.nanokvmpro-NanoKVM-Mirror)

Portable Windows viewer for mirroring the local NanoKVM LCD over SSH.

It shows the built-in NanoKVM screen on your PC, supports mouse tap and swipe control, and includes extra buttons for knob-style actions.

Author: [VADLIKE](https://github.com/vadlike)  
Repository: [vadlike/nanokvmpro-NanoKVM-Mirror](https://github.com/vadlike/nanokvmpro-NanoKVM-Mirror)

![NanoKVM Mirror Demo](gif.gif)

## Features

- mirrors the NanoKVM LCD in a standalone Windows app
- portable `.exe` build without a console window
- click to tap, drag to swipe
- extra controls: `Knob -`, `Knob +`, `OK`, `Hold`, `Left`, `Right`, `Back`, `Close`
- editable connection settings: `IP`, `Login`, `Password`
- saves settings next to the app in `kvm-screen-mirror.json`
- includes `kvm-screen-mirror.example.json` for quick setup

## Portable App

Portable build:

- [NanoKVM-Mirror.exe](NanoKVM-Mirror.exe)

Source code:

- [kvm-screen-mirror.py](kvm-screen-mirror.py)

Optional launchers:

- [mirror-kvm-screen.vbs](mirror-kvm-screen.vbs)
- [mirror-kvm-screen.cmd](mirror-kvm-screen.cmd)

Config template:

- [kvm-screen-mirror.example.json](kvm-screen-mirror.example.json)

## Controls

- left click: tap
- left drag: swipe
- right click: top-left action / close area
- middle click: back action
- `Left` / `Right` / `Enter`: knob control
- `L`: long press
- `F`: fit window

## Notes

- the app connects to NanoKVM over SSH
- touch injection is done through available input event tools on the device
- the portable app stores its config beside the `.exe`

## About

NanoKVM Mirror was made as a simple desktop companion for controlling the small NanoKVM screen more comfortably from Windows.

## Star History

[![Star History Chart](https://api.star-history.com/image?repos=vadlike/nanokvmpro-NanoKVM-Mirror&type=date&legend=top-left)](https://www.star-history.com/?repos=vadlike%2Fnanokvmpro-NanoKVM-Mirror&type=date&legend=top-left)
