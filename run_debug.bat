@echo off
rem ---------------------------------------------------------------------------
rem  Same as run.bat, but keeps a console window open so start-up errors and the
rem  log output stay visible.  Use this when the GUI does not appear.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist "python\python.exe" (
    echo [ERROR] Portable Python not found: python\python.exe
    echo         Build it once with:  python tools\make_portable_python.py
    pause
    exit /b 1
)

"python\python.exe" "NokovBroadcaster.py" %*

echo.
echo ---------------------------------------------------------------
echo Exit code: %ERRORLEVEL%
echo ---------------------------------------------------------------
pause
