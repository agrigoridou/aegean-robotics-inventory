@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Install dependencies using RUN_ME_WINDOWS.bat first.
  pause
  exit /b 1
)
echo Authenticated mode on PRIVATE Wi-Fi ONLY. This does NOT make the service safe for public Internet.
echo Do not forward this port from your router. Use HTTPS reverse proxy for hosting.
".venv\Scripts\python.exe" server.py --host 0.0.0.0 --port 8989
pause
