@echo off
rem ---------------------------------------------------------------------------
rem  Launch NokovBroadcaster with the portable Python bundled in this folder.
rem  No Python, PySide2 or pip installation is required.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist "python\pythonw.exe" (
    echo [ERROR] Portable Python not found: python\pythonw.exe
    echo         Build it once with:  python tools\make_portable_python.py
    pause
    exit /b 1
)

start "" "python\pythonw.exe" "NokovBroadcaster.py" %*
exit /b 0
