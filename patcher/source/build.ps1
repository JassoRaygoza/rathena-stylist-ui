param([Parameter(Mandatory=$true)][string]$Client)
$ErrorActionPreference = 'Stop'
python "$PSScriptRoot/generate_patch.py" $Client
if ($LASTEXITCODE -ne 0) { throw 'Patch recipe generation failed.' }
# Selector box textures, rendered from the native box in the client's GRFs.
$textures = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'generated\textures.bin'))
python "$PSScriptRoot/client_assets.py" resource (Split-Path -Parent ([IO.Path]::GetFullPath($Client))) $textures
if ($LASTEXITCODE -ne 0) { throw 'Texture generation failed.' }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
}
$recipe = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'generated\patch.bin'))
$outputExe = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\StylistUIPatcher.exe'))
$sourceFile = Join-Path $PSScriptRoot 'StylistUIPatcher.cs'
& $compiler /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll /reference:System.Drawing.dll `
    "/resource:$recipe,StylistUI.patch" "/resource:$textures,StylistUI.textures" "/out:$outputExe" $sourceFile
if ($LASTEXITCODE -ne 0) { throw 'Patcher compilation failed.' }
Write-Output "Built $PSScriptRoot/../StylistUIPatcher.exe"
