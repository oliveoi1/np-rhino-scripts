# NP Rhino Scripts Installer (Windows)
# Right-click -> Run with PowerShell

$ErrorActionPreference = "Stop"

$InstallRoot = Join-Path $env:USERPROFILE "Documents\NP Rhino Scripts"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# --- Configuration: edit before distributing ---
$GitHubRepo = if ($env:NP_GITHUB_REPO) { $env:NP_GITHUB_REPO } else { "oliveoi1/np-rhino-scripts" }
$Branch = if ($env:NP_GITHUB_BRANCH) { $env:NP_GITHUB_BRANCH } else { "main" }

Write-Host "NP Rhino Scripts Installer (Windows)"
Write-Host "Install location: $InstallRoot"
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
Write-Host "In Rhino, create an alias named NP with this command:"
Write-Host $AliasCmd
Write-Host ""
Set-Clipboard -Value $AliasCmd
Write-Host "(Command copied to clipboard.)"
Write-Host ""
Write-Host "Then type NP in Rhino and press Enter."
Read-Host "Press Enter to close"
