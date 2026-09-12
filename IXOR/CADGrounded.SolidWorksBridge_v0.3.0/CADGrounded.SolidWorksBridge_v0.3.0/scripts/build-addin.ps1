$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Project = Join-Path $RepoRoot "src\CADGrounded.SolidWorksAddin\CADGrounded.SolidWorksAddin.csproj"
$OutputDll = Join-Path $RepoRoot "src\CADGrounded.SolidWorksAddin\bin\Release\net48\CADGrounded.SolidWorksAddin.dll"

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    throw "vswhere.exe not found. Install Visual Studio/Build Tools with MSBuild and .NET Framework 4.8 development tools."
}

$msbuild = & $vswhere -latest -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe | Select-Object -First 1
if (-not $msbuild) {
    throw "MSBuild not found through vswhere."
}

$SolidWorksApiDir = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist"
if (-not (Test-Path $SolidWorksApiDir)) {
    throw "SOLIDWORKS API redistributable directory not found: $SolidWorksApiDir`nEdit scripts/build-addin.ps1 if SOLIDWORKS is installed elsewhere."
}

$RequiredInterop = @(
    "SolidWorks.Interop.sldworks.dll",
    "SolidWorks.Interop.swconst.dll",
    "SolidWorks.Interop.swpublished.dll"
)
foreach ($name in $RequiredInterop) {
    $candidate = Join-Path $SolidWorksApiDir $name
    if (-not (Test-Path $candidate)) {
        throw "Required SOLIDWORKS interop assembly not found: $candidate"
    }
}

Write-Host "MSBuild: $msbuild"
Write-Host "SOLIDWORKS API: $SolidWorksApiDir"
Write-Host "Project style: classic .NET Framework 4.8 (no Microsoft.NET.Sdk dependency)"

& $msbuild $Project /t:Build /p:Configuration=Release /p:Platform=x64 /p:SolidWorksApiDir="$SolidWorksApiDir" /m
if ($LASTEXITCODE -ne 0) {
    throw "Add-in build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $OutputDll)) {
    throw "MSBuild returned success but output DLL was not found: $OutputDll"
}

Write-Host "Build complete."
Write-Host $OutputDll
