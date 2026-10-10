# Runs the add-on's automatic tests without a real ComfyUI or graphics card (a fake ComfyUI stands in).
#
#   powershell -ExecutionPolicy Bypass -File tests\run_tests.ps1 [-Blender "C:\...\blender.exe"]
#
# Needs Python 3.10+ on PATH (for the runner tests) and Blender 4.2+ (for the add-on tests).
# Everything is written into tests\_work (deleted and re-made on each run).
param(
    [string]$Blender = $env:BLENDER,
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$W = if ($env:I23D_TEST_WORK) { $env:I23D_TEST_WORK } else { Join-Path $Here "_work" }
$env:I23D_TEST_WORK = $W

if (-not $Blender) {
    $Blender = Get-ChildItem "C:\Program Files\Blender Foundation\Blender*\blender.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [version]($_.Directory.Name -replace '[^\d.]', '') } | Select-Object -Last 1 -ExpandProperty FullName
}
if (-not $Blender -or -not (Test-Path $Blender)) { throw "Blender not found. Pass -Blender <path to blender.exe>." }

function Invoke-Blender([string]$Script, [string[]]$More = @()) {
    # Blender prints warnings on stderr; Windows PowerShell would treat them as errors.
    $ErrorActionPreference = "Continue"
    $out = & $Blender -b --factory-startup --python-exit-code 1 -P (Join-Path $Here $Script) -- @More 2>&1 |
        ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($code -ne 0) { $out | Select-Object -Last 30 | Write-Host; throw "$Script failed" }
    $out | Where-Object { $_ -match "PASSED|error|clean:|re-imported|mean colour|exported" -and $_ -notmatch "Warning" } |
        Select-Object -Last 6 | Write-Host
}

if (Test-Path $W) { Remove-Item -Recurse -Force $W }
New-Item -ItemType Directory -Force $W | Out-Null
Copy-Item (Join-Path $Here "fixtures\brown_photo.png") (Join-Path $W "picture.png")

Write-Host "== 1. Runner against a fake ComfyUI (no Blender needed)"
Invoke-Blender "make_messy.py" @((Join-Path $W "messy.glb"))   # a deliberately messy "AI" model
& $Python -I (Join-Path $Here "test_runner.py") $W
if ($LASTEXITCODE -ne 0) { throw "test_runner.py failed" }

Write-Host "== 2. Add-on inside Blender ($Blender)"
foreach ($t in "test_ui_bpy", "test_quality_bpy", "test_addon_bpy", "test_colours_bpy", "test_texture_colours_bpy",
             "test_surface_maps_bpy") {
    Write-Host "-- $t"
    Invoke-Blender "$t.py"
}
Write-Host ""
Write-Host "ALL TESTS PASSED"
