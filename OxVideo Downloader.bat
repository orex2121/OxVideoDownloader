@echo off
rem OxVideoDownloader launcher. The app is fully portable: this folder ships
rem its own Python (python\), the yt-dlp engine, tkinter and ffmpeg (ffmpeg\).
rem Copy the whole folder to another Windows x64 PC and it runs as-is.
cd /d "%~dp0"
if not exist "python\pythonw.exe" (
    echo Error: the bundled Python interpreter in the "python" folder is missing.
    pause
    exit /b 1
)
start "" "python\pythonw.exe" oxvideodownloader.py
exit /b 0
