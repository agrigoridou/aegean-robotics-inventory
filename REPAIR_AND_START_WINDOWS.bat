@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Aegean Robotics - Repair and Start
if not exist "server.py" (
  echo ERROR: Put this file in the same folder as server.py first.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating the missing isolated Python environment...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 (
    echo Could not create the virtual environment. Install Python 3.10+ first.
    pause
    exit /b 1
  )
)
echo Installing/updating Pillow and QR support in this app's Python environment...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check "Pillow>=10.4,<13" "qrcode[pil]>=7.4,<9"
if errorlevel 1 (
  echo Package install failed. Check the output above and your Internet connection.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import PIL, qrcode; print('OK: Pillow and qrcode are installed')"
if errorlevel 1 (
  echo The installation could not be verified.
  pause
  exit /b 1
)
echo Starting with the correct Python environment...
".venv\Scripts\python.exe" server.py --host 127.0.0.1 --port 8765 --open
if errorlevel 1 echo Server could not start. Please share the error above.
pause
