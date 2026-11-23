# Installs (or repairs) PhoneCast: Python environment, icon, and shortcuts.
# Run it from this folder:  powershell -ExecutionPolicy Bypass -File .\install.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv"
$py = Join-Path $venv "Scripts\python.exe"
$pyw = Join-Path $venv "Scripts\pythonw.exe"

if (-not (Test-Path $py)) {
    Write-Host "Creating the Python environment..."
    python -m venv $venv
}
Write-Host "Installing libraries..."
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r (Join-Path $root "requirements.txt")

Write-Host "Making the icon..."
Push-Location $root
& $py -m app.make_icon
Pop-Location

$icon = Join-Path $root "assets\phonecast.ico"
$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "PhoneCast.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "PhoneCast.lnk"),
    (Join-Path $root "PhoneCast.lnk")
)
foreach ($path in $targets) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "-m app"
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = "See and control your Android phone on this computer"
    $lnk.Save()
    Write-Host "Shortcut: $path"
}
Write-Host "Done. Open PhoneCast from the desktop or the Start menu."
