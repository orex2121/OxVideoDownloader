@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "python\pythonw.exe" (
    echo The portable Python environment is missing.
    choice /C YN /N /M "Run INSTALL.bat now? [Y/N] "
    if errorlevel 2 exit /b 1
    call "%~dp0INSTALL.bat"
    if errorlevel 1 exit /b 1
)

start "" "python\pythonw.exe" "%~dp0oxvideodownloader.py"
exit /b 0
