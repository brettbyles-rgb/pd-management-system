@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\run-kimi-resume-stage3-all-high-gui.ps1"
