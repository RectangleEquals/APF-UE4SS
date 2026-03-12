# =============================================================================
# build.ps1  --  Build APF Manifesto and install to a user-selected folder
#
# Usage:
#   .\build.ps1           # Normal build + install
#   .\build.ps1 -Clean    # Wipe venv + dist + build cache first
#
# NOTE: APFManifesto.spec is hand-crafted and source-controlled.
#       Do NOT delete it or let PyInstaller auto-regenerate it --
#       the auto-generated spec omits all kivy/kivymd datas and hiddenimports.
# =============================================================================
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$Root     = $PSScriptRoot
$AppDir   = Join-Path $Root "app"
$SpecFile = Join-Path $AppDir "APFManifesto.spec"
$DistDir  = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build_cache"
$VenvDir  = Join-Path $Root ".venv"
$ExeName  = "APFManifesto.exe"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  APF Manifesto Builder"                               -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# -- 0. Clean (optional) -----------------------------------------------------
if ($Clean) {
    Write-Host "[0/5] Cleaning previous build artifacts..." -ForegroundColor Yellow
    # NOTE: $SpecFile is intentionally NOT deleted -- it is source-controlled.
    foreach ($d in @($VenvDir, $DistDir, $BuildDir)) {
        if (Test-Path $d) { Remove-Item -Recurse -Force $d }
    }
    Write-Host "  Cleaned (venv, dist, build_cache)." -ForegroundColor Green
}

# -- 1. Python check ---------------------------------------------------------
Write-Host "[1/5] Checking Python..." -ForegroundColor Cyan
$PythonExe = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonExe) {
    Write-Error "Python not found on PATH. Install Python 3.11-3.13 and add it to PATH."
}
$PyVersion = & python --version 2>&1
Write-Host "  Found: $PyVersion"

# -- 2. Virtual environment --------------------------------------------------
Write-Host "[2/5] Setting up virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path $VenvDir)) {
    & python -m venv $VenvDir
    Write-Host "  Created venv at $VenvDir"
} else {
    Write-Host "  Reusing existing venv."
}

$VenvPy = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "  Upgrading pip..."
& $VenvPy -m pip install --no-cache-dir --quiet --upgrade pip

Write-Host "  Installing requirements..."
& $VenvPy -m pip install --no-cache-dir --quiet -r (Join-Path $AppDir "requirements.txt")

if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed (exit $LASTEXITCODE). See output above."
}
Write-Host "  Dependencies installed." -ForegroundColor Green

# -- 3. Verify spec exists ---------------------------------------------------
Write-Host "[3/5] Checking spec file..." -ForegroundColor Cyan
if (-not (Test-Path $SpecFile)) {
    Write-Error "Spec file not found: $SpecFile`nThis file should be source-controlled. Do not delete it."
}
Write-Host "  Using spec: $SpecFile" -ForegroundColor Green

# -- 4. Build executable -----------------------------------------------------
Write-Host "[4/5] Building executable (this may take a few minutes)..." -ForegroundColor Cyan
Push-Location $AppDir
& $VenvPy -m PyInstaller $SpecFile `
    --distpath $DistDir `
    --workpath $BuildDir `
    --noconfirm
Pop-Location

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed (exit $LASTEXITCODE)."
}

$BuiltExe = Join-Path $DistDir $ExeName
if (-not (Test-Path $BuiltExe)) {
    Write-Error "Build failed -- $ExeName was not produced in $DistDir"
}
$sizeMB = [string][math]::Round((Get-Item $BuiltExe).Length / 1MB, 1) + " MB"
Write-Host "  Built: $BuiltExe  ($sizeMB)" -ForegroundColor Green

# -- 5. Install to user-selected folder --------------------------------------
Write-Host "[5/5] Select install location..." -ForegroundColor Cyan
Add-Type -AssemblyName System.Windows.Forms

$FolderBrowser = New-Object System.Windows.Forms.FolderBrowserDialog
$FolderBrowser.Description         = "Choose where to install APF Manifesto"
$FolderBrowser.RootFolder          = [System.Environment+SpecialFolder]::MyComputer
$FolderBrowser.ShowNewFolderButton = $true

$result = $FolderBrowser.ShowDialog()
if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
    Write-Warning "Install cancelled. The built exe is at: $BuiltExe"
    exit 0
}

$InstallDir = $FolderBrowser.SelectedPath
$Dest       = Join-Path $InstallDir $ExeName
Copy-Item -Force $BuiltExe $Dest

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "  APF Manifesto installed successfully!"               -ForegroundColor Green
Write-Host "  Location: $Dest"                                     -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
