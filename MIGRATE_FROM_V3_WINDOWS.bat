@echo off
setlocal
cd /d "%~dp0"
echo MIGRATION: Close both older and newer servers FIRST.
echo Migration does not overwrite an existing new inventory.db.
echo.
set /p "OLD=Enter full path to your previous project folder: "
if "%OLD%"=="" exit /b 1
where py >nul 2>nul
if errorlevel 1 (
  python migrate_from_v3.py "%OLD%"
) else (
  py -3 migrate_from_v3.py "%OLD%"
)
pause
