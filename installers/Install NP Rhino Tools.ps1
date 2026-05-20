# NP Rhino Tools Installer (Windows)
# Right-click -> Run with PowerShell

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force | Out-Null
$ErrorActionPreference = "Stop"

$InstallRoot = Join-Path $env:USERPROFILE "Documents\NP Rhino Scripts"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# --- Configuration: edit before distributing ---
$GitHubRepo = if ($env:NP_GITHUB_REPO) { $env:NP_GITHUB_REPO } else { "oliveoi1/np-rhino-scripts" }
$Branch = if ($env:NP_GITHUB_BRANCH) { $env:NP_GITHUB_BRANCH } else { "main" }

Write-Host "=========================================="
Write-Host "  NP Rhino Tools - Installer (Windows)"
Write-Host "=========================================="
Write-Host ""
Write-Host "This downloads and installs tools to:"
Write-Host "  $InstallRoot"
Write-Host ""
Write-Host "No GitHub account needed."
Write-Host ""

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
foreach ($dir in @("_user_data", "_logs", "_temp", "_backup", "_staging")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot $dir) | Out-Null
}

function Install-FromFolder {
    param([string]$SourceRoot, [string]$RepoSlug)
    $manifestPath = Join-Path $SourceRoot "manifest.json"
    $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
    $items = @("manifest.json", "README.md", "run_np_launcher.py") + $manifest.appFolders
    foreach ($item in $items) {
        $src = Join-Path $SourceRoot $item
        $dst = Join-Path $InstallRoot $item
        if (Test-Path $src -PathType Container) {
            if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
            Copy-Item $src $dst -Recurse -Force
        } elseif (Test-Path $src -PathType Leaf) {
            $parent = Split-Path $dst -Parent
            if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
            Copy-Item $src $dst -Force
        }
    }
    $configPath = Join-Path $InstallRoot "_user_data\github_config.json"
    if (-not (Test-Path $configPath)) {
        @{ repo = $RepoSlug; branch = $manifest.branch } | ConvertTo-Json | Set-Content $configPath -Encoding UTF8
    }
}

if ($GitHubRepo -like "*YOUR_GITHUB*") {
    Write-Host "Installing from local developer folder..."
    Install-FromFolder -SourceRoot $RepoRoot -RepoSlug $GitHubRepo
} else {
    $ZipUrl = "https://github.com/$GitHubRepo/archive/refs/heads/$Branch.zip"
    $TempZip = Join-Path $env:TEMP ("np_rhino_" + [guid]::NewGuid().ToString() + ".zip")
    $TempDir = Join-Path $env:TEMP ("np_rhino_extract_" + [guid]::NewGuid().ToString())
    Write-Host "Downloading $ZipUrl ..."
    Invoke-WebRequest -Uri $ZipUrl -OutFile $TempZip -UseBasicParsing
    Expand-Archive -Path $TempZip -DestinationPath $TempDir -Force
    $packageDir = Get-ChildItem $TempDir -Directory | Select-Object -First 1
    if (-not $packageDir -or -not (Test-Path (Join-Path $packageDir.FullName "manifest.json"))) {
        throw "Could not find package in downloaded ZIP."
    }
    Install-FromFolder -SourceRoot $packageDir.FullName -RepoSlug $GitHubRepo
    Remove-Item $TempZip -Force -ErrorAction SilentlyContinue
    Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
}

$AliasCmd = '-_RunPythonScript "' + (Join-Path $InstallRoot "run_np_launcher.py") + '"'
Write-Host ""
Write-Host "SUCCESS: NP Rhino Scripts installed."
Write-Host ""
Write-Host "NEXT STEP - Rhino (one time):"
Write-Host "  1. Open Rhino 8"
Write-Host "  2. Tools -> Options -> Aliases"
Write-Host "  3. Create alias: NP"
Write-Host "  4. Paste this command:"
Write-Host ""
Write-Host $AliasCmd
Write-Host ""
Set-Clipboard -Value $AliasCmd
Write-Host "(Copied to clipboard - paste into Rhino alias NP)"
Write-Host ""
Write-Host "Then type NP in Rhino and press Enter for the tool menu."
Read-Host "Press Enter to close"
