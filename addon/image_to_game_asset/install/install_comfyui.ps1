# =============================================================================
# install_comfyui.ps1 - sets up ComfyUI + TRELLIS.2 for the Image to Game Asset add-on (Windows)
#
# Easiest: in Blender, the add-on's preferences > Install ComfyUI + TRELLIS.2 (runs this script).
# By hand (from the add-on folder, or scripts\install_comfyui.ps1 in the I23D_win repo):
#   powershell -ExecutionPolicy Bypass -File install_comfyui.ps1 -Check   # checks this PC only
#   powershell -ExecutionPolicy Bypass -File install_comfyui.ps1          # check + install
#
# Everything goes into %USERPROFILE%\I23D (change it with -InstallDir):
#   ComfyUI_windows_portable\   ComfyUI with its own Python, and the TRELLIS.2 model files
#   output\                     generated models and logs (the add-on's default output folder)
#   install_log.txt             log of this script
#
# Downloads about 2 GB (ComfyUI) + 9 GB (models). Nothing needs a Hugging Face account.
# Safe to re-run: finished files are skipped, half-finished downloads continue.
# This file ships inside the add-on (image_to_game_asset\install\), so the add-on zip is all you need.
# =============================================================================
param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE "I23D"),
    [string]$ComfyVersion = "v0.39.0",   # the version the add-on's workflow was made and tested with
    [switch]$Check,
    [switch]$Pause                       # wait for Enter at the end (the add-on's button uses this)
)
$ErrorActionPreference = "Stop"
try { $Host.UI.RawUI.WindowTitle = "Install ComfyUI + TRELLIS.2" } catch {}
# The add-on's workflow lists the model files to download. It sits next to this folder: install\..\workflows
$Workflow = Join-Path (Split-Path -Parent $PSScriptRoot) "workflows\trellis2_image_to_glb.json"
$Comfy = Join-Path $InstallDir "ComfyUI_windows_portable"

function Ok($t)   { Write-Host "  OK    $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  WARN  $t" -ForegroundColor Yellow }
function Stop($t) { Write-Host "  STOP  $t" -ForegroundColor Red; exit 1 }
function Step($t) { Write-Host ""; Write-Host "=== $t ===" }

New-Item -ItemType Directory -Force $InstallDir | Out-Null
Start-Transcript -Append -Path (Join-Path $InstallDir "install_log.txt") | Out-Null
try {

# -----------------------------------------------------------------------------
Step "1. Checking this PC"
if (-not (Test-Path $Workflow)) { Stop "Add-on workflow not found: $Workflow (keep this script inside the add-on's install folder)." }
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) { Stop "No NVIDIA graphics driver found (nvidia-smi). TRELLIS.2 needs an NVIDIA card." }
$gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits | Select-Object -First 1).Split(",") |
    ForEach-Object { $_.Trim() }
$vramGB = [math]::Round([int]$gpu[1] / 1024)
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$drive = (Get-Item $InstallDir).PSDrive
$freeGB = [math]::Round((Get-PSDrive $drive.Name).Free / 1GB)
Write-Host "  Graphics:  $($gpu[0]), $vramGB GB, driver $($gpu[2])"
Write-Host "  Memory:    $ramGB GB"
Write-Host "  Free disk: $freeGB GB on $($drive.Name):"
Write-Host "  Folder:    $InstallDir"
Write-Host ""
if     ($vramGB -ge 16) { Ok "Graphics memory is enough ($vramGB GB; tested on 16 GB: peak 11.5 GB)" }
elseif ($vramGB -ge 12) { Warn "Graphics memory is tight ($vramGB GB). Standard detail may just fit; close other apps." }
else                    { Stop "Under 12 GB graphics memory is too little for TRELLIS.2." }
if ($ramGB -ge 32) { Ok "Memory is enough ($ramGB GB)" } else { Warn "Under 32 GB memory: close other apps while generating." }
$haveComfy = Test-Path (Join-Path $Comfy "python_embeded\python.exe")
$needGB = if ($haveComfy) { 10 } else { 25 }
if ($freeGB -ge $needGB) { Ok "Disk space is enough" } else { Stop "Need about $needGB GB free (you have $freeGB GB)." }
$tar = Join-Path $env:SystemRoot "System32\tar.exe"
if ((Test-Path $tar) -and ((& $tar --version) -match "libarchive")) { Ok "Windows can unpack .7z files" }
else { Stop "Windows' tar.exe (with 7z support) is missing. Update Windows 10/11, or install 7-Zip and unpack by hand." }
if (Get-Command curl.exe -ErrorAction SilentlyContinue) { Ok "curl found" } else { Stop "curl.exe is missing (it comes with Windows 10/11)." }
$models = (Get-Content $Workflow -Raw | ConvertFrom-Json).models
$missing = @($models | Where-Object { -not (Test-Path (Join-Path $Comfy "ComfyUI\models\$($_.folder)\$($_.file)")) })
if ($haveComfy) { Ok "ComfyUI already installed" }
if ($missing.Count -eq 0) { Ok "TRELLIS.2 model files already there ($($models.Count) files)" }
else { Write-Host "  To download: $($missing.Count) of $($models.Count) TRELLIS.2 model files" }

if ($Check) { Write-Host ""; Write-Host "Check finished. Nothing was installed."; return }

# -----------------------------------------------------------------------------
Step "2. ComfyUI $ComfyVersion (portable, NVIDIA)"
if ($haveComfy) {
    Ok "Already there: $Comfy"
} else {
    $archive = Join-Path $InstallDir "ComfyUI_windows_portable_nvidia.7z"
    $url = "https://github.com/Comfy-Org/ComfyUI/releases/download/$ComfyVersion/ComfyUI_windows_portable_nvidia.7z"
    Write-Host "  Downloading (about 2 GB)..."
    & curl.exe -fL -C - --retry 5 -o $archive $url
    if ($LASTEXITCODE -ne 0) { Stop "Download failed (curl code $LASTEXITCODE). Re-run to continue." }
    Write-Host "  Unpacking..."
    & $tar -xf $archive -C $InstallDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $Comfy "python_embeded\python.exe"))) { Stop "Unpacking failed." }
    Remove-Item $archive
    Ok "Installed: $Comfy"
}
$torch = & (Join-Path $Comfy "python_embeded\python.exe") -s -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
if ($torch -match "True") { Ok "PyTorch sees the graphics card: $torch" } else { Stop "PyTorch can't use the graphics card ($torch). Update the NVIDIA driver." }

# -----------------------------------------------------------------------------
Step "3. TRELLIS.2 model files (about 9 GB, first time only)"
foreach ($m in $models) {
    $dir = Join-Path $Comfy "ComfyUI\models\$($m.folder)"
    $file = Join-Path $dir $m.file
    if (Test-Path $file) { Ok "$($m.folder)\$($m.file)"; continue }
    New-Item -ItemType Directory -Force $dir | Out-Null
    Write-Host "  Downloading $($m.folder)\$($m.file)..."
    & curl.exe -fL -C - --retry 5 -o "$file.part" $m.url
    if ($LASTEXITCODE -ne 0) { Stop "Download failed (curl code $LASTEXITCODE). Re-run to continue." }
    Move-Item -Force "$file.part" $file
    Ok "$($m.folder)\$($m.file)"
}

New-Item -ItemType Directory -Force (Join-Path $InstallDir "output") | Out-Null

# -----------------------------------------------------------------------------
Step "Done"
Write-Host @"
  Everything is installed. Next:
    1. In Blender: Edit > Preferences > Add-ons > Image to Game Asset.
       (Add-on not installed yet? Get Extensions > top-right menu > Install from Disk...
        and pick image_to_game_asset-<version>.zip)
    2. The ComfyUI folder should read:
         $Comfy
       Press Check Setup.
    3. 3D View > press N > Image->3D tab > pick a picture > Generate.
       The add-on starts ComfyUI by itself (offline, this PC only).
"@

} finally {
    Stop-Transcript | Out-Null
    if ($Pause) { Write-Host ""; Read-Host "You can close this window (or press Enter)" | Out-Null }
}
