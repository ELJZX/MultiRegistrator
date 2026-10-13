# Build standalone Windows executables for MultiRegistrator.
#
# Requires: python -m pip install -r requirements-dev.txt
# Output:   dist\MultiRegistratorServer.exe, dist\MultiRegistratorClient.exe

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Building MultiRegistratorServer.exe ..."
python -m PyInstaller --noconfirm --clean --onefile --windowed `
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
    run_server.py

Write-Host "Building MultiRegistratorClient.exe ..."
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name MultiRegistratorClient `
    --collect-submodules pyqtgraph `
    --collect-submodules requests `
    run_client.py

Write-Host "Building MultiRegistratorTestDevice.exe ..."
python -m PyInstaller --noconfirm --clean --onefile --console `
    --name MultiRegistratorTestDevice `
    test_device.py

Write-Host "Done. Executables are in the 'dist' folder."
