@echo off
REM ============================================================
REM PDO Dashboard — DEMO Launcher (Windows)
REM Runs the DEMO version only. Does NOT touch WIP or production.
REM ============================================================

cd /d "%~dp0"
set APP_DIR=%~dp0app
set DB_PATH=%APP_DIR%\pune_do.db

echo ================================================
echo  PDO Dashboard -- DEMO VERSION
echo ================================================

if not exist "%DB_PATH%" (
    echo ERROR: Demo database not found at %DB_PATH%
    pause
    exit /b 1
)

echo Checking requirements...
python -m pip install -r "%APP_DIR%\requirements.txt" -q

echo Running DB integrity check...
cd "%APP_DIR%"
python verify.py
if errorlevel 1 (
    echo ERROR: DB integrity check failed. Aborting.
    pause
    exit /b 1
)

echo.
echo Launching Demo Dashboard at http://localhost:8502
echo (Port 8502 - separate from any WIP instance on 8501)
echo.

set PUNE_DO_DB=%DB_PATH%
python -m streamlit run "%APP_DIR%\app.py" --server.port 8502
pause
