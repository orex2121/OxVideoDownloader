@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_VERSION=3.12.10"
set "PYTHON_DIR=%CD%\python"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "INSTALLER=%TEMP%\oxvideodownloader-python-%PYTHON_VERSION%-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe"

echo.
echo OxVideoDownloader portable environment setup
echo Target: "%PYTHON_DIR%"
echo.

if exist "%PYTHON_EXE%" goto install_packages

echo [1/3] Downloading Python %PYTHON_VERSION% x64...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%PYTHON_URL%' -OutFile '%INSTALLER%'"
if errorlevel 1 goto download_failed

echo [2/3] Installing Python into the application folder...
start "" /wait "%INSTALLER%" /quiet InstallAllUsers=0 TargetDir="%PYTHON_DIR%" ^
  AssociateFiles=0 Shortcuts=0 Include_doc=0 Include_debug=0 Include_dev=0 ^
  Include_launcher=0 Include_pip=1 Include_test=0 Include_tools=0 ^
  Include_tcltk=1 Include_symbols=0 PrependPath=0
if errorlevel 1 goto python_failed
if not exist "%PYTHON_EXE%" goto python_failed
del /q "%INSTALLER%" >nul 2>&1

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
echo ERROR: Python could not be installed into "%PYTHON_DIR%".
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
