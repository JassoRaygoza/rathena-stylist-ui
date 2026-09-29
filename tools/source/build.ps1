# Builds tools\StylistTools.exe with the C# compiler included in .NET Framework 4.
# -Server refreshes reference.txt (job constants and item names) from a patched rAthena tree.
param([string]$Server)
$ErrorActionPreference = 'Stop'
$package = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
}
$sources = @('Program.cs', 'MainForm.cs', 'Catalogue.cs', 'Verify.cs') | ForEach-Object { Join-Path $PSScriptRoot $_ }
$reference = Join-Path $PSScriptRoot 'reference.txt'
$outputExe = Join-Path $package 'tools\StylistTools.exe'

function Compile([string]$Target, [string[]]$Resources) {
    $arguments = @('/nologo', '/target:exe', '/optimize+', '/platform:anycpu',
        '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll', '/reference:System.Web.Extensions.dll',
        "/out:$Target") + ($Resources | ForEach-Object { "/resource:$_" }) + $sources
    & $compiler @arguments
    if ($LASTEXITCODE -ne 0) { throw 'StylistTools compilation failed.' }
}

if ($Server) {
    $bootstrap = Join-Path ([IO.Path]::GetTempPath()) ('StylistTools-' + [Guid]::NewGuid().ToString('N') + '.exe')
    Compile $bootstrap @()
    try {
        & $bootstrap --export-reference $Server (Join-Path $package 'client\source\stylingshopinfo.lub') $reference
        if ($LASTEXITCODE -ne 0) { throw 'Reference export failed.' }
    } finally { Remove-Item -LiteralPath $bootstrap -ErrorAction SilentlyContinue }
}
if (-not (Test-Path -LiteralPath $reference)) { throw 'reference.txt is missing; run build.ps1 -Server <patched rAthena folder>.' }

# Built-in copies let the EXE generate catalogues without Python or a server tree.
Compile $outputExe @(
    "$reference,StylistTools.reference",
    ((Join-Path $package 'server\src\map\stylist.hpp') + ',StylistTools.stylist_hpp'),
    ((Join-Path $package 'client\source\stylingshopinfo.lub') + ',StylistTools.stylingshopinfo'),
    ((Join-Path $package 'server\conf\battle\stylist.conf') + ',StylistTools.stylist_conf'))
Write-Output "Built $outputExe"
