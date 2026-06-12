<#
.SYNOPSIS
    Build a stable, versioned JasperVoice release: PyInstaller bundle -> Inno
    Setup installer -> SHA256SUMS. Produces exactly the artifacts the in-app
    updater expects from a GitHub Release.

.DESCRIPTION
    Steps:
      1. Read the single-source version from src/jaspervoice/__init__.py.
      2. Build the PyInstaller one-folder bundle (dist/JasperVoice/).
      3. Compile installer/JasperVoice.iss with Inno Setup (ISCC) into
         dist/installer/JasperVoice-Setup-<version>.exe.
      4. Write dist/installer/SHA256SUMS over the installer (the updater reads
         this to verify integrity before running an update).

    Upload the two files in dist/installer/ (the Setup .exe and SHA256SUMS) as
    assets on a GitHub Release tagged v<version>. That's the whole release flow.

.PARAMETER SkipBuild
    Reuse an existing dist/JasperVoice bundle instead of rebuilding it.

.PARAMETER Iscc
    Path to the Inno Setup compiler (ISCC.exe). Auto-detected if omitted.

.EXAMPLE
    .\scripts\build_release.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [string]$Iscc
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Repo root = parent of this script's directory.
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $RepoRoot ".venv\Scripts\pyinstaller.exe"

function Get-AppVersion {
    $initPath = Join-Path $RepoRoot "src\jaspervoice\__init__.py"
    $line = Select-String -LiteralPath $initPath -Pattern '^\s*__version__\s*=' | Select-Object -First 1
    if (-not $line) { throw "Could not find __version__ in $initPath" }
    if ($line.Line -match '"([^"]+)"' -or $line.Line -match "'([^']+)'") {
        return $Matches[1]
    }
    throw "Could not parse version from: $($line.Line)"
}

function Find-Iscc {
    if ($Iscc -and (Test-Path -LiteralPath $Iscc)) { return $Iscc }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 or pass -Iscc <path>."
}

$Version = Get-AppVersion
Write-Host "JasperVoice version: $Version" -ForegroundColor Cyan

# --- 1. PyInstaller bundle ---
if (-not $SkipBuild) {
    if (-not (Test-Path -LiteralPath $PyInstaller)) {
        throw "PyInstaller not found at $PyInstaller. Run: pip install -r requirements-dev.txt"
    }
    Write-Host "Building PyInstaller bundle..." -ForegroundColor Cyan
    & $PyInstaller "jaspervoice.spec" --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }
} else {
    Write-Host "Skipping PyInstaller build (-SkipBuild)." -ForegroundColor Yellow
}

$BundleDir = Join-Path $RepoRoot "dist\JasperVoice"
$BundleExe = Join-Path $BundleDir "JasperVoice.exe"
if (-not (Test-Path -LiteralPath $BundleExe)) {
    throw "Bundle missing: $BundleExe. Build it first (omit -SkipBuild)."
}

# --- 2. Inno Setup installer ---
$IsccPath = Find-Iscc
Write-Host "Using Inno Setup: $IsccPath" -ForegroundColor Cyan

$OutDir = Join-Path $RepoRoot "dist\installer"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

$IssPath = Join-Path $RepoRoot "installer\JasperVoice.iss"
& $IsccPath "/DAppVersion=$Version" "/DSourceDir=$BundleDir" $IssPath
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed (exit $LASTEXITCODE)" }

$SetupExe = Join-Path $OutDir "JasperVoice-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $SetupExe)) {
    throw "Installer not produced at $SetupExe"
}

# --- 3. SHA256SUMS ---
Write-Host "Writing SHA256SUMS..." -ForegroundColor Cyan
$hash = (Get-FileHash -LiteralPath $SetupExe -Algorithm SHA256).Hash.ToLower()
$setupName = Split-Path -Leaf $SetupExe
# coreutils-style: "<hex>  <filename>" (two spaces). The updater parser is
# lenient about spacing but this is the canonical form.
$line = "$hash  $setupName"
$sumsPath = Join-Path $OutDir "SHA256SUMS"
# Write without a BOM so the updater's UTF-8 parse is clean.
[System.IO.File]::WriteAllText($sumsPath, "$line`n", (New-Object System.Text.UTF8Encoding($false)))

Write-Host ""
Write-Host "Release artifacts ready in $OutDir" -ForegroundColor Green
Write-Host "  $setupName" -ForegroundColor Green
Write-Host "  SHA256SUMS" -ForegroundColor Green
Write-Host ""
Write-Host "Next: create a GitHub Release tagged 'v$Version' and upload both files as assets." -ForegroundColor Cyan
