#Requires -Version 5.1
<#
.SYNOPSIS
    Build PnLClaw Desktop (Tauri + Python Sidecar) for Windows.
.DESCRIPTION
    1. Checks prerequisites (Python 3.11+, Node 20+, Rust)
    2. Installs Python packages and runs PyInstaller
    3. Copies sidecar to Tauri resources location
    4. Runs Tauri build to produce the installer
#>
param(
    [switch]$SkipPyInstaller,
    [switch]$SkipFrontend
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot

function Check-Command($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Error "$name is required but not found in PATH."
        exit 1
    }
}

function Get-SemVer($cmd, $args_list) {
    $raw = & $cmd @args_list 2>&1 | Select-Object -First 1
    if ($raw -match '(\d+\.\d+)') { return [version]$Matches[1] }
    return $null
}

Write-Host "=== PnLClaw Desktop Build ===" -ForegroundColor Cyan
Write-Host "Root: $ROOT"
Write-Host ""

# --- Step 1: Prerequisites ---
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow

Check-Command "python"
Check-Command "node"
Check-Command "cargo"

$pyVer = Get-SemVer "python" @("--version")
if ($pyVer -and $pyVer -lt [version]"3.11") {
    Write-Error "Python 3.11+ required, got $pyVer"
    exit 1
}
Write-Host "  Python: $pyVer"

$nodeVer = Get-SemVer "node" @("--version")
if ($nodeVer -and $nodeVer -lt [version]"20.0") {
    Write-Error "Node 20+ required, got $nodeVer"
    exit 1
}
Write-Host "  Node: $nodeVer"

$rustVer = & rustc --version 2>&1 | Select-Object -First 1
Write-Host "  Rust: $rustVer"
Write-Host ""

# --- Step 2: Install Python packages ---
if (-not $SkipPyInstaller) {
    Write-Host "[2/6] Installing Python packages..." -ForegroundColor Yellow
    Push-Location $ROOT

    pip install pyinstaller --quiet 2>&1 | Out-Null

    $communityPkgs = @(
        "packages/shared-types",
        "packages/core",
        "packages/exchange-sdk",
        "packages/market-data",
        "packages/security-gateway",
        "packages/strategy-engine",
        "packages/backtest-engine",
        "packages/paper-engine",
        "packages/risk-engine",
        "packages/agent-runtime",
        "packages/llm-adapter",
        "packages/storage",
        "packages/openclaw-compat",
        "services/local-api"
    )

    $editableArgs = @()
    foreach ($pkg in $communityPkgs) {
        $editableArgs += "-e"
        $editableArgs += $pkg
    }

    pip install @editableArgs --quiet 2>&1 | Out-Null
    Write-Host "  All community packages installed."
    Pop-Location

    # --- Step 3: PyInstaller build ---
    Write-Host "[3/6] Running PyInstaller..." -ForegroundColor Yellow
    Push-Location $ROOT

    if (Test-Path "dist/pnlclaw-server") {
        Remove-Item -Recurse -Force "dist/pnlclaw-server"
    }
    if (Test-Path "build/pnlclaw-server") {
        Remove-Item -Recurse -Force "build/pnlclaw-server"
    }

    pyinstaller scripts/pyinstaller/pnlclaw-server.spec --noconfirm
    if ($LASTEXITCODE -ne 0) {
        Write-Error "PyInstaller build failed."
        exit 1
    }

    $serverExe = "dist/pnlclaw-server/pnlclaw-server.exe"
    if (-not (Test-Path $serverExe)) {
        Write-Error "Expected $serverExe not found."
        exit 1
    }
    Write-Host "  Sidecar built: $serverExe"
    Pop-Location
} else {
    Write-Host "[2/6] Skipping Python packages (--SkipPyInstaller)" -ForegroundColor DarkGray
    Write-Host "[3/6] Skipping PyInstaller (--SkipPyInstaller)" -ForegroundColor DarkGray
}

# --- Step 4: Zip sidecar for Tauri bundling ---
Write-Host "[4/6] Zipping sidecar for Tauri resources..." -ForegroundColor Yellow
$sidecarSrc = Join-Path $ROOT "dist/pnlclaw-server"
$sidecarDir = Join-Path $ROOT "apps/desktop/src-tauri/sidecar"
$sidecarZip = Join-Path $sidecarDir "pnlclaw-server.zip"

if (-not (Test-Path $sidecarSrc)) {
    Write-Error "Sidecar directory not found: $sidecarSrc"
    exit 1
}

New-Item -ItemType Directory -Path $sidecarDir -Force | Out-Null
if (Test-Path $sidecarZip) {
    Remove-Item -Force $sidecarZip
}

Write-Host "  Compressing sidecar (this may take a minute)..."
Compress-Archive -Path "$sidecarSrc\*" -DestinationPath $sidecarZip -CompressionLevel Optimal
$zipSize = [math]::Round((Get-Item $sidecarZip).Length / 1MB, 1)
Write-Host "  Zip created: $sidecarZip ($zipSize MB)"

# --- Step 5: npm install + Tauri build ---
Write-Host "[5/6] Building Tauri desktop app..." -ForegroundColor Yellow
Push-Location (Join-Path $ROOT "apps/desktop")

if (-not $SkipFrontend) {
    npm install --prefer-offline 2>&1 | Out-Null
}

npm run tauri build 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Tauri build failed."
    Pop-Location
    exit 1
}
Pop-Location

# --- Step 6: Report ---
Write-Host ""
Write-Host "[6/6] Build complete!" -ForegroundColor Green
$bundleDir = Join-Path $ROOT "apps/desktop/src-tauri/target/release/bundle"
Write-Host "Bundle output: $bundleDir"

if (Test-Path "$bundleDir/nsis") {
    Get-ChildItem "$bundleDir/nsis" -Filter "*.exe" | ForEach-Object {
        Write-Host "  NSIS: $($_.Name) ($([math]::Round($_.Length / 1MB, 1)) MB)" -ForegroundColor Green
    }
}
if (Test-Path "$bundleDir/msi") {
    Get-ChildItem "$bundleDir/msi" -Filter "*.msi" | ForEach-Object {
        Write-Host "  MSI:  $($_.Name) ($([math]::Round($_.Length / 1MB, 1)) MB)" -ForegroundColor Green
    }
}
