param(
    [Parameter(Mandatory = $true)]
    [string]$RolloutPath,

    [Parameter(Mandatory = $true)]
    [string]$Out,

    [string]$Match = "",

    [int]$Width = 0,

    [int]$Height = 0
)

$fs = [System.IO.File]::Open($RolloutPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
$sr = New-Object System.IO.StreamReader($fs)
$selected = $null

try {
    while (($line = $sr.ReadLine()) -ne $null) {
        if (-not $line.Contains('"image_generation_end"') -or -not $line.Contains('"result"')) {
            continue
        }
        if ($Match -and -not $line.Contains($Match)) {
            continue
        }
        $selected = $line
    }
}
finally {
    $sr.Close()
    $fs.Close()
}

if (-not $selected) {
    throw "No matching image_generation_end line found."
}

$obj = $selected | ConvertFrom-Json
$payload = $obj.payload
$b64 = $payload.result
if (-not $b64 -and $payload.item) {
    $b64 = $payload.item.result
}
if (-not $b64) {
    throw "Matching image line did not contain a result field."
}

$outDir = [System.IO.Path]::GetDirectoryName($Out)
if ($outDir) {
    [System.IO.Directory]::CreateDirectory($outDir) | Out-Null
}

$bytes = [System.Convert]::FromBase64String($b64)
[System.IO.File]::WriteAllBytes($Out, $bytes)

if ($Width -gt 0 -and $Height -gt 0) {
    Add-Type -AssemblyName System.Drawing
    $img = [System.Drawing.Image]::FromFile($Out)
    $bmp = New-Object System.Drawing.Bitmap $Width, $Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.DrawImage($img, 0, 0, $Width, $Height)
    $img.Dispose()
    $g.Dispose()
    $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

Get-Item -LiteralPath $Out | Select-Object FullName, Length, LastWriteTime
