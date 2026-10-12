@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Aegean Robotics Smart Inventory 4.2

if not exist ".venv\Scripts\python.exe" (
  echo First launch: Installing dependencies in the project environment...
  call "INSTALL_WINDOWS.bat"
  if errorlevel 1 (
    echo Setup failed. Read the error above.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import PIL, qrcode" >nul 2>nul
if errorlevel 1 (
  echo Missing Python libraries. Running repair...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo Could not install dependencies. Check your Internet connection.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -c "import PIL, qrcode" >nul 2>nul
if errorlevel 1 (
  echo The Python environment still cannot import Pillow or qrcode.
  pause
  exit /b 1
)

echo Checking first administrator...
".venv\Scripts\python.exe" auth.py status >nul 2>nul
if errorlevel 1 (
  call CREATE_ADMIN_WINDOWS.bat
  if errorlevel 1 (
    echo Administrator creation was not completed.
    pause
    exit /b 1
  )
)
echo Starting protected inventory: http://127.0.0.1:8989
".venv\Scripts\python.exe" server.py --host 127.0.0.1 --port 8989 --open
if errorlevel 1 echo Startup error. See the message above.
pause
