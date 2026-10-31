@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo OxVideoDownloader updater
echo Close OxVideoDownloader before continuing.
echo Local Python, FFmpeg, settings, tasks and thumbnails will be preserved.
echo.
pause

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
set "UPDATE_RESULT=%ERRORLEVEL%"

echo.
if "%UPDATE_RESULT%"=="0" (
    echo Update completed successfully.
) else (
    echo Update failed. Existing portable files were preserved where possible.
)
echo.
pause
exit /b %UPDATE_RESULT%
