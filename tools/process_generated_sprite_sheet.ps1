param(
    [Parameter(Mandatory = $true)]
    [string]$RolloutPath,

    [Parameter(Mandatory = $true)]
    [string]$Match,

    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Alpha,

    [Parameter(Mandatory = $true)]
    [string]$Out,

    [Parameter(Mandatory = $true)]
    [int]$Width,

    [Parameter(Mandatory = $true)]
    [int]$Height,

    [int]$Frames = 0
)

$ErrorActionPreference = "Stop"

powershell -ExecutionPolicy Bypass -File tools\extract_latest_image_from_rollout.ps1 `
    -RolloutPath $RolloutPath `
    -Out $Source `
    -Match $Match

python C:\Users\ilank\.codex\skills\.system\imagegen\scripts\remove_chroma_key.py `
    --input $Source `
    --out $Alpha `
    --auto-key border `
    --soft-matte `
    --transparent-threshold 12 `
    --opaque-threshold 220 `
    --despill

if ($Frames -gt 0) {
    $FrameWidth = [int]($Width / $Frames)
    python tools\normalize_sprite_frames.py `
        --input $Alpha `
        --out $Out `
        --frames $Frames `
        --frame-width $FrameWidth `
        --frame-height $Height
}
else {
    python tools\normalize_sprite_sheet.py `
        --input $Alpha `
        --out $Out `
        --width $Width `
        --height $Height
}
