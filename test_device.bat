@echo off
rem MultiRegistrator test device launcher.
rem Keeps running until you close this console window.
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist "dist\MultiRegistratorTestDevice.exe" (
    "dist\MultiRegistratorTestDevice.exe" %*
    goto :end
)

where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Соберите устройство: powershell -File packaging\build.ps1
    pause
    goto :end
)

python test_device.py %*

:end
endlocal
