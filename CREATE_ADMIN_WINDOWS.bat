@echo off
setlocal
cd /d "%~dp0"
title Aegean Robotics - Create first Administrator
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" auth.py init-admin
) else (
  py -3 auth.py init-admin
)
if errorlevel 1 (
  echo Could not create administrator. Read the message above.
  pause
  exit /b 1
)
echo Login account created successfully.
exit /b 0
