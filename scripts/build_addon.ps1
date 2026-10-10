# Packs the Blender add-on into an installable extension zip: dist\image_to_game_asset-<version>.zip
#   powershell -ExecutionPolicy Bypass -File scripts\build_addon.ps1
# Then in Blender: Edit > Preferences > Get Extensions > (top-right menu) > Install from Disk...
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root "addon\image_to_game_asset"
$Version = (Select-String -Path (Join-Path $Src "blender_manifest.toml") -Pattern '^version\s*=\s*"(.+)"').Matches[0].Groups[1].Value
$Dist = Join-Path $Root "dist"
$Out = Join-Path $Dist "image_to_game_asset-$Version.zip"
New-Item -ItemType Directory -Force $Dist | Out-Null
if (Test-Path $Out) { Remove-Item $Out }

# Stage a clean copy (no __pycache__), plus the user guide.
$Stage = Join-Path $env:TEMP "i23d_build_$PID"
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
Copy-Item -Recurse $Src $Stage
Get-ChildItem $Stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Copy-Item (Join-Path $Root "addon\README.md") (Join-Path $Stage "README.md")

# Zip entries must use "/" (Compress-Archive in Windows PowerShell 5.1 writes "\", which Blender rejects).
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($Out, "Create")
try {
    foreach ($f in Get-ChildItem $Stage -Recurse -File) {
        $rel = $f.FullName.Substring($Stage.Length + 1).Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $rel) | Out-Null
    }
} finally {
    $zip.Dispose()
    Remove-Item -Recurse -Force $Stage
}
Write-Host "Built: $Out"
