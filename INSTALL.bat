@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_VERSION=3.12.11"
set "PBS_TAG=20250612"
set "PYTHON_DIR=%CD%\python"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "ARCHIVE=%TEMP%\oxvideodownloader-python-%PYTHON_VERSION%.tar.gz"
set "PYTHON_URL=https://github.com/astral-sh/python-build-standalone/releases/download/%PBS_TAG%/cpython-%PYTHON_VERSION%+%PBS_TAG%-x86_64-pc-windows-msvc-install_only.tar.gz"

echo.
echo OxVideoDownloader portable environment setup
echo Target: "%PYTHON_DIR%"
echo.

if exist "%PYTHON_EXE%" goto install_packages

echo [1/3] Downloading portable Python %PYTHON_VERSION% x64...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%PYTHON_URL%' -OutFile '%ARCHIVE%'"
if errorlevel 1 goto download_failed

rem The archive is a self-contained CPython: extract it as-is, no installer,
rem no registry. (The python.org setup .exe is a registered system bundle:
rem a second run is a no-op that silently places no files in a new folder.)
echo [2/3] Extracting Python into the application folder...
tar.exe -xzf "%ARCHIVE%" -C "%CD%"
if errorlevel 1 goto python_failed
if not exist "%PYTHON_EXE%" goto python_failed
del /q "%ARCHIVE%" >nul 2>&1
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath '%PYTHON_DIR%' -Recurse -Filter *.pdb -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue" >nul 2>&1

:install_packages
echo [3/3] Installing application dependencies...
"%PYTHON_EXE%" -m pip install --disable-pip-version-check --upgrade -r requirements.txt
if errorlevel 1 goto packages_failed

echo Verifying the portable environment...
"%PYTHON_EXE%" -c "import tkinter, yt_dlp, PIL, curl_cffi; print('Python and dependencies: OK')"
if errorlevel 1 goto verify_failed

echo.
echo Setup completed successfully.
echo FFmpeg will be downloaded into ffmpeg\ on the first application start.
echo You can now run "OxVideo Downloader.exe" or "OxVideo Downloader.bat".
echo.
pause
exit /b 0

:download_failed
echo.
echo ERROR: Could not download Python from:
echo %PYTHON_URL%
echo Check the internet connection and try again.
goto failed

:python_failed
echo.
echo ERROR: Python could not be extracted into "%PYTHON_DIR%".
goto failed

:packages_failed
echo.
echo ERROR: Could not install packages from requirements.txt.
goto failed

:verify_failed
echo.
echo ERROR: The environment was created, but its verification failed.

:failed
echo Setup was not completed.
pause
exit /b 1
