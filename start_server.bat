@echo off
rem Запуск сервера MultiRegistrator (из exe).
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist "MultiRegistratorServer.exe" (
    "MultiRegistratorServer.exe" %*
    goto :end
)
if exist "dist\MultiRegistratorServer.exe" (
    "dist\MultiRegistratorServer.exe" %*
    goto :end
)
echo exe не найден, запускаю через Python...
python run_server.py %*

:end
endlocal
