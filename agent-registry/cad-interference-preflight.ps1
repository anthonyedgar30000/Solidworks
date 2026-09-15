#Requires -Version 5.1
<#
.SYNOPSIS
    Compatibility wrapper for the fixed local pair-interference read.
.DESCRIPTION
    Submits sw.check_interference_pair through the local CAD Agent Registry by
    forwarding to cad.ps1. The worker performs native SOLIDWORKS minimum-distance
    and interference reads without enabling MaxControl or arbitrary code execution.

    Despite the historical filename, this script now performs the complete
    read-only measurement rather than only compiling a MaxControl preflight.
.EXAMPLE
    .\cad-interference-preflight.ps1 `
      -ANameContains AR60 `
      -BNameContains 6130649_01_Carriage
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateLength(1, 128)]
    [string]$ANameContains,

    [Parameter(Mandatory = $true)]
    [ValidateLength(1, 128)]
    [string]$BNameContains,

    [ValidateRange(1, 120)]
    [int]$WaitSeconds = 30,

    [switch]$Json,

    # Retained so previous invocations fail safely rather than at parameter binding.
    [string]$McpUrl
)

$ErrorActionPreference = 'Stop'

if ($PSBoundParameters.ContainsKey('McpUrl')) {
    Write-Warning '-McpUrl is ignored; this read now uses the local registry worker.'
}

$cadScript = Join-Path $PSScriptRoot 'cad.ps1'

if (-not (Test-Path -LiteralPath $cadScript)) {
    throw "Required helper was not found: $cadScript"
}

$arguments = @(
    'interference',
    '-ANameContains', $ANameContains,
    '-BNameContains', $BNameContains,
    '-WaitSeconds', $WaitSeconds
)

if ($Json) {
    $arguments += '-Json'
}

& $cadScript @arguments
