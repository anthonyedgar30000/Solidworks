#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [Parameter(Mandatory=$true)][bool]$Condition,
        [Parameter(Mandatory=$true)][string]$Message
    )
    if (-not $Condition) { throw $Message }
}

$root = $PSScriptRoot
$projectPath = Join-Path $root 'CadGrounded.SolidWorksWorker.csproj'
$programPath = Join-Path $root 'Program.cs'
$exePath = Join-Path $root 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'
$outputRoot = Split-Path -Parent $exePath

Assert-True (Test-Path -LiteralPath $projectPath -PathType Leaf) 'Worker project file is missing.'
Assert-True (Test-Path -LiteralPath $programPath -PathType Leaf) 'Worker Program.cs is missing.'
Assert-True (Test-Path -LiteralPath $exePath -PathType Leaf) "Worker executable is missing: $exePath"

[xml]$project = Get-Content -LiteralPath $projectPath -Raw
$propertyGroups = @($project.Project.PropertyGroup)
$targetFramework = @($propertyGroups.TargetFramework | Where-Object { $_ }) | Select-Object -First 1
$runtimeIdentifier = @($propertyGroups.RuntimeIdentifier | Where-Object { $_ }) | Select-Object -First 1
$selfContained = @($propertyGroups.SelfContained | Where-Object { $_ }) | Select-Object -First 1

Assert-True ([string]$targetFramework -ceq 'net8.0-windows') "Unexpected TargetFramework '$targetFramework'."
Assert-True ([string]$runtimeIdentifier -ceq 'win-x64') "Unexpected RuntimeIdentifier '$runtimeIdentifier'."
Assert-True ([string]$selfContained -ceq 'true') 'Worker project must set SelfContained=true.'

foreach ($runtimeFile in @(
    'coreclr.dll',
    'hostfxr.dll',
    'hostpolicy.dll',
    'PresentationFramework.dll'
)) {
    $path = Join-Path $outputRoot $runtimeFile
    Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "Self-contained runtime file is missing: $runtimeFile"
}

$programSource = Get-Content -LiteralPath $programPath -Raw
$versionMatch = [regex]::Match(
    $programSource,
    'internal\s+const\s+string\s+Version\s*=\s*"(?<version>[^"]+)"'
)
Assert-True $versionMatch.Success 'Could not resolve worker version from Program.cs.'
$workerVersion = [string]$versionMatch.Groups['version'].Value

$verifiers = @(Get-ChildItem -LiteralPath $root -Filter 'Verify-*.ps1' -File)
Assert-True ($verifiers.Count -gt 0) 'No verifier scripts were found.'

foreach ($verifier in $verifiers) {
    $source = Get-Content -LiteralPath $verifier.FullName -Raw
    $pin = [regex]::Match(
        $source,
        '\$ExpectedWorkerVersion\s*=\s*''(?<version>[^'']+)'''
    )

    if (-not $pin.Success) {
        continue
    }

    $expected = [string]$pin.Groups['version'].Value
    Assert-True (
        $expected -ceq $workerVersion
    ) "Verifier '$($verifier.Name)' pins worker '$expected' but Program.cs is '$workerVersion'."
}

$oldDotnetRoot = $env:DOTNET_ROOT
$oldDotnetRootX64 = $env:DOTNET_ROOT_X64
$oldMultilevel = $env:DOTNET_MULTILEVEL_LOOKUP

try {
    $env:DOTNET_ROOT = 'C:\__cadgrounded_no_global_dotnet__'
    $env:DOTNET_ROOT_X64 = 'C:\__cadgrounded_no_global_dotnet__'
    $env:DOTNET_MULTILEVEL_LOOKUP = '0'

    $versionText = (& $exePath version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Self-contained worker launch failed with exit code $LASTEXITCODE."
    }

    Assert-True (
        $versionText -ceq "CadGrounded.SolidWorksWorker $workerVersion"
    ) "Unexpected worker version output '$versionText'."
}
finally {
    $env:DOTNET_ROOT = $oldDotnetRoot
    $env:DOTNET_ROOT_X64 = $oldDotnetRootX64
    $env:DOTNET_MULTILEVEL_LOOKUP = $oldMultilevel
}

Write-Host "PASS: self-contained net8 win-x64 worker build and verifier version pins match $workerVersion"
