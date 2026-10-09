# Build get-update-pl.exe (PyInstaller, onefile, GUI without console)
$ErrorActionPreference = "Stop"
$venv = Join-Path $PSScriptRoot ".venv\Scripts"

$ErrorActionPreference = "Continue"
& "$venv\python.exe" -m pip show pyinstaller > $null 2> $null
if ($LASTEXITCODE -ne 0) {
    & "$venv\python.exe" -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
}
$ErrorActionPreference = "Stop"

& "$venv\pyinstaller.exe" --onefile --windowed --name get-update-pl `
    --icon (Join-Path $PSScriptRoot "assets\icon.ico") `
    --clean --noconfirm `
    (Join-Path $PSScriptRoot "main.py")

Write-Host ""
Write-Host "Done: $(Join-Path $PSScriptRoot 'dist\get-update-pl.exe')"
