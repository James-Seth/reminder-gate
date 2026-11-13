@echo off
REM Build reminder-gate.exe with PyInstaller
cd /d "%~dp0"

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name reminder-gate ^
    --hidden-import pystray._win32 ^
    --add-data "screenshots\tray-icon.png;screenshots" ^
    run_remindergate.pyw

if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Done: dist\reminder-gate.exe
