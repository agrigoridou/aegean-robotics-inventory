@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 was not found. Install Python 3.10+ from python.org.
    pause
    exit /b 1
  )
  set "PY=python"
)
%PY% -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo Python 3.10 or newer is required.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating an isolated Python environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Virtual environment creation failed.
    pause
    exit /b 1
  )
) else (
  echo [1/3] Reusing the existing Python environment...
)
echo [2/3] Installing required libraries...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Library installation failed. Check the pip error above.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import PIL, qrcode; print('Pillow and QR code libraries OK')"
if errorlevel 1 (
  echo Could not import installed libraries.
  pause
  exit /b 1
)
if not exist ".env" (
  echo [3/3] Add your Gemini API key in the file that opens.
  copy ".env.example" ".env" >nul
  notepad ".env"
) else (
  echo [3/3] Existing Gemini .env settings preserved.
)
echo.
echo Installation completed successfully. Run START_WINDOWS.bat.
pause
