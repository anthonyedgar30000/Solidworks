Set-StrictMode -Version Latest

function Write-JsonFileUtf8NoBom {
    <#
    .SYNOPSIS
    Writes a machine-readable JSON artifact as UTF-8 without a BOM.

    .DESCRIPTION
    Windows PowerShell 5.1 treats Set-Content -Encoding UTF8 differently from
    PowerShell 7.  This explicit .NET writer keeps CADGrounded JSON evidence
    files deterministic for strict UTF-8 consumers.  It only writes the named
    evidence artifact; it has no SOLIDWORKS or Remote Queue authority.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]$Value,
        [Parameter(Mandatory=$true)][string]$LiteralPath,
        [Parameter(Mandatory=$true)][ValidateRange(1, 100)][int]$Depth
    )

    if ([string]::IsNullOrWhiteSpace($LiteralPath)) {
        throw 'JSON evidence artifact path must be non-empty.'
    }

    $json = $Value | ConvertTo-Json -Depth $Depth
    $utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($LiteralPath, $json, $utf8WithoutBom)
}
