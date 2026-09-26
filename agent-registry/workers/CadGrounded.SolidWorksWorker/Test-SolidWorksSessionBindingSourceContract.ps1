Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SourcePath = Join-Path $PSScriptRoot 'Program.cs'
$Source = Get-Content -LiteralPath $SourcePath -Raw

function Assert-SourceContains {
    param(
        [Parameter(Mandatory=$true)][string]$Pattern,
        [Parameter(Mandatory=$true)][string]$Message
    )

    if ($Source -notmatch $Pattern) {
        throw $Message
    }
}

Assert-SourceContains 'using System\.Runtime\.InteropServices\.ComTypes;' 'COM Running Object Table types must remain explicitly imported.'
Assert-SourceContains 'Version\s*=\s*"0\.4\.4"' 'Worker version must identify the session-binding hardening build as 0.4.4.'
Assert-SourceContains 'GetRunningObjectTable' 'Session binding must enumerate the Windows Running Object Table.'
Assert-SourceContains 'GetRunningSolidWorksApplications' 'Session binding must enumerate candidate SOLIDWORKS automation objects.'
Assert-SourceContains 'GetProcessID\(\)' 'SOLIDWORKS candidates must be identity-bound through ISldWorks.GetProcessID().'
Assert-SourceContains 'activeCandidates\.Count\s*>\s*1' 'Session binding must explicitly detect multiple active-document candidates.'
Assert-SourceContains '"solidworks_instance_ambiguous"' 'Multiple active SOLIDWORKS sessions must fail closed with a typed ambiguity error.'
Assert-SourceContains 'byProcessId' 'ROT results must be deduplicated by SOLIDWORKS process identity.'

if ($Source -match 'ComRot\.GetActiveObject\("SldWorks\.Application"\)') {
    throw 'Generic GetActiveObject attachment must not be reintroduced; it can bind to the wrong SOLIDWORKS process.'
}

Write-Host 'PASS: fail-closed SOLIDWORKS session-binding source contract'
