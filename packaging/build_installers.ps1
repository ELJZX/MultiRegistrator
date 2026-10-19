# Build the Windows installers with Inno Setup.
#
# Requires: Inno Setup 6 (https://jrsoftware.org/isinfo.php) and the exes built
# by build.ps1.  Output: ..\installers\MultiRegistrator*-Setup-*.exe

$ErrorActionPreference = "Stop"

$candidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "ISCC.exe not found. Install Inno Setup 6 first."
}

Write-Host "Building server installer ..."
& $iscc "$PSScriptRoot\installer_server.iss"
if ($LASTEXITCODE -ne 0) { throw "server installer failed" }

Write-Host "Building client installer ..."
& $iscc "$PSScriptRoot\installer_client.iss"
if ($LASTEXITCODE -ne 0) { throw "client installer failed" }

Write-Host "Done. Installers are in the 'installers' folder."
