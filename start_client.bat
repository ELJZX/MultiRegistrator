@echo off
rem Запуск клиента MultiRegistrator (из exe).
rem Пример: start_client.bat --autoconnect --server 192.168.1.54:8120
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist "MultiRegistratorClient.exe" (
    "MultiRegistratorClient.exe" %*
    goto :end
)
if exist "dist\MultiRegistratorClient.exe" (
    "dist\MultiRegistratorClient.exe" %*
    goto :end
)
echo exe не найден, запускаю через Python...
python run_client.py %*

:end
endlocal
