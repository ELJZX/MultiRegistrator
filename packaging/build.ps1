# Build standalone Windows executables for MultiRegistrator.
#
# Requires: python -m pip install -r requirements-dev.txt
# Output:   dist\MultiRegistratorServer.exe, dist\MultiRegistratorClient.exe

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Building MultiRegistratorServer.exe ..."
python -m PyInstaller --noconfirm --clean --onefile --windowed --specpath build `
    --name MultiRegistratorServer `
    --collect-submodules uvicorn `
    --collect-submodules pymodbus `
    --collect-all fastapi `
    --collect-all starlette `
    --collect-all anyio `
    --collect-all pydantic `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.lifespan.on `
    packaging\entry_server.py

Write-Host "Building MultiRegistratorClient.exe ..."
python -m PyInstaller --noconfirm --clean --onefile --windowed --specpath build `
    --name MultiRegistratorClient `
    --collect-submodules pyqtgraph `
    --collect-submodules requests `
    packaging\entry_client.py

Write-Host "Building MultiRegistratorTestDevice.exe ..."
python -m PyInstaller --noconfirm --clean --onefile --console --specpath build `
    --name MultiRegistratorTestDevice `
    packaging\entry_test_device.py

Write-Host "Copying executables to the project root ..."
Copy-Item "dist\MultiRegistratorServer.exe" -Destination $root -Force
Copy-Item "dist\MultiRegistratorClient.exe" -Destination $root -Force
Copy-Item "dist\MultiRegistratorTestDevice.exe" -Destination $root -Force

Write-Host "Done. Executables are in 'dist' and in the project root."
