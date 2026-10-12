@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 migrate_from_v4.py
) else (
  python migrate_from_v4.py
)
if errorlevel 1 echo IMPORT not completed. Existing files were not replaced.
pause
