<h1 align="center">NanoKVM Pro Mirror</h1>

<p align="center">
  <img src="https://visitor-badge.laobi.icu/badge?page_id=vadlike.nanokvmpro-NanoKVM-Mirror" alt="visitors">
  <img src="https://img.shields.io/badge/license-GPL--3.0-blue.svg" alt="license GPL-3.0">
  <img src="https://img.shields.io/github/last-commit/vadlike/nanokvmpro-NanoKVM-Mirror" alt="last commit">
  <a href="https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_Pro/introduction.html">
    <img src="https://img.shields.io/badge/NanoKVM%20Pro-Official%20Device%20Page-red" alt="NanoKVM Pro device">
  </a>
</p>

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

## License

This project is licensed under the [GNU GPL v3.0](LICENSE).

## About

NanoKVM Mirror was made as a simple desktop companion for controlling the small NanoKVM screen more comfortably from Windows.
