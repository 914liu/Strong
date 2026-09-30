@echo off
chcp 65001 >nul 2>&1
title JianYing AI Editor
cd /d "C:\Users\Administrator.SCPC\Documents\Qoder\2026-09-30"
set PATH=C:\Users\Administrator.SCPC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin;%PATH%
set PYTHONIOENCODING=utf-8
"C:\Users\Administrator.SCPC\AppData\Local\Programs\Python\Python311\python.exe" launcher.py
if errorlevel 1 (
    echo.
    echo Launcher failed. Press any key to close.
    pause >nul
)
