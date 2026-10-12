# Sets up ComfyUI + TRELLIS.2 from the I23D_win repo. The real installer ships inside the add-on
# (addon\image_to_game_asset\install\install_comfyui.ps1); this just runs it with the same options.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_comfyui.ps1 -Check   # checks this PC only
#   powershell -ExecutionPolicy Bypass -File scripts\install_comfyui.ps1          # check + install
#
# Options: -InstallDir <folder> (default %USERPROFILE%\I23D), -ComfyVersion, -Check, -Pause
param(
    [string]$InstallDir,
    [string]$ComfyVersion,
    [switch]$Check,
    [switch]$Pause
)
& (Join-Path (Split-Path -Parent $PSScriptRoot) "addon\image_to_game_asset\install\install_comfyui.ps1") @PSBoundParameters
exit $LASTEXITCODE
