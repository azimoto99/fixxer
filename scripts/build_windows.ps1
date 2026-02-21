param(
    [switch]$Clean,
    [switch]$RunTests,
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Clean) {
    Write-Host "Cleaning previous build artifacts..."
    foreach ($path in @("build", "dist", "release\Fixer-Windows", "release\Fixer-Windows.zip")) {
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
        }
    }
}

Write-Host "Installing dependencies..."
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt

if ($RunTests) {
    Write-Host "Running test suite..."
    python -m pytest -q
}

Write-Host "Building FixerCLI.exe..."
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name FixerCLI `
    --paths . `
    --collect-submodules win32timezone `
    launchers/fixer_cli.py

Write-Host "Building FixerTray.exe..."
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name FixerTray `
    --paths . `
    --collect-submodules win32timezone `
    launchers/fixer_tray.py

Write-Host "Embedding default config in dist folders..."
New-Item -ItemType Directory -Path "dist\FixerCLI\config" -Force | Out-Null
New-Item -ItemType Directory -Path "dist\FixerTray\config" -Force | Out-Null
Copy-Item -Path "config\default.json" -Destination "dist\FixerCLI\config\default.json" -Force
Copy-Item -Path "config\default.json" -Destination "dist\FixerTray\config\default.json" -Force

Write-Host "Assembling release layout..."
$ReleaseRoot = Join-Path $Root "release\Fixer-Windows"
$CliOut = Join-Path $ReleaseRoot "FixerCLI"
$TrayOut = Join-Path $ReleaseRoot "FixerTray"

New-Item -ItemType Directory -Path $CliOut -Force | Out-Null
New-Item -ItemType Directory -Path $TrayOut -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $ReleaseRoot "config") -Force | Out-Null

Copy-Item -Path "dist\FixerCLI\*" -Destination $CliOut -Recurse -Force
Copy-Item -Path "dist\FixerTray\*" -Destination $TrayOut -Recurse -Force
Copy-Item -Path "config\default.json" -Destination (Join-Path $ReleaseRoot "config\default.json") -Force
Copy-Item -Path "README.md" -Destination (Join-Path $ReleaseRoot "README.md") -Force
Copy-Item -Path "installer\fixer.iss" -Destination (Join-Path $ReleaseRoot "fixer.iss") -Force

if ($Zip) {
    Write-Host "Creating zip archive..."
    if (Test-Path "release\Fixer-Windows.zip") {
        Remove-Item "release\Fixer-Windows.zip" -Force
    }
    Compress-Archive -Path "release\Fixer-Windows\*" -DestinationPath "release\Fixer-Windows.zip"
}

Write-Host "Build complete. Outputs:"
Write-Host "- dist\\FixerCLI"
Write-Host "- dist\\FixerTray"
Write-Host "- release\\Fixer-Windows"
if ($Zip) {
    Write-Host "- release\\Fixer-Windows.zip"
}
