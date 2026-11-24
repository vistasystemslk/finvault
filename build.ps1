# Build a portable, single-file FinVault.exe
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# PyInstaller's --clean can fail on OneDrive/antivirus-locked files, so clean
# what we can and keep going instead of aborting the whole build.
function Remove-BuildPath([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        try {
            Remove-Item $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            Start-Sleep -Milliseconds 400
        }
    }
    Write-Host "Warning: could not fully remove $Path (file in use); reusing it." -ForegroundColor Yellow
}

if (-not (Test-Path "assets\FinVault.ico")) {
    python tools\make_icon.py
}

Remove-BuildPath "build"
Remove-BuildPath "dist\FinVault.exe"
if (Test-Path "FinVault.spec") { Remove-Item "FinVault.spec" -Force -ErrorAction SilentlyContinue }

python -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name FinVault `
    --icon "assets\FinVault.ico" `
    --add-data "web;web" `
    --add-data "assets\FinVault.ico;assets" `
    --collect-submodules finvault `
    launcher.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path "dist\FinVault.exe")) {
    throw "PyInstaller finished but dist\FinVault.exe was not created."
}

Write-Host ""
Write-Host "Built dist\FinVault.exe" -ForegroundColor Green
Write-Host "Copy that single file to any folder; FinVault.db is created beside it on first run."
exit 0
