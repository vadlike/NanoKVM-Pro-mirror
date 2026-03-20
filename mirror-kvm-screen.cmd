@echo off
setlocal
cd /d "%~dp0"
wscript.exe //nologo "%~dp0mirror-kvm-screen.vbs"
endlocal
