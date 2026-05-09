param([string]$InnoSetupPath = "D:\Programs\Inno Setup 7")

# 1. Verify Inno Setup is available at the given path before starting the build
if (-not (Test-Path "$InnoSetupPath\ISCC.exe")) {
    Write-Error "Inno Setup not found at '$InnoSetupPath\ISCC.exe'."
    Write-Error "Install Inno Setup 7 or pass -InnoSetupPath to override."
    exit 1
}

# 2. Force Python and PowerShell to use UTF-8 (Fixes the Arrow crash)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# 3. Define a regex to strip ANSI color codes (Fixes the [INFO] gibberish)
$ansiRegex = "$([char]27)\[[0-9;]*[mK]"

New-Item -ItemType Directory -Path "$PSScriptRoot\Output" -Force | Out-Null
Start-Transcript -Path "$PSScriptRoot\Output\setup.log"
Write-Host "Setup started at $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")"
conda activate apf_manager 2>&1 | ForEach-Object { ($_ -replace $ansiRegex, "") }
python setup/setup.py build_exe 2>&1 | ForEach-Object { ($_ -replace $ansiRegex, "") }
Write-Host "Setup completed at $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")"
Stop-Transcript

Write-Host "Installer Setup beginning in 15 seconds..."
Start-Sleep -Seconds 15

Start-Transcript -Path "$PSScriptRoot\Output\install.log"
Write-Host "Installer Setup started at $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")"
& "$PSScriptRoot\build\build_installer.ps1" -IsccPath $InnoSetupPath 2>&1 | ForEach-Object { ($_ -replace $ansiRegex, "") }
Write-Host "Installer Setup completed at $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")"
Stop-Transcript