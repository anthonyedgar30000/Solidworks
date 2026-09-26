Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot '..\workers\CadGrounded.SolidWorksWorker\Verify-QueryMates-V43-Prism.ps1'
$scriptPath = [System.IO.Path]::GetFullPath($scriptPath)
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Verifier script is missing: $scriptPath"
}

$text = [System.IO.File]::ReadAllText($scriptPath)
$requiredLiterals = @(
    'IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE',
    'FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1',
    'FITCHECK_PRISM_LINK_15x10x25_V43-1',
    'FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1',
    "Invoke-WorkerJson -Arguments @('status')",
    "Invoke-WorkerJson -Arguments @('components','--all')",
    'Invoke-WorkerJson -Arguments @(''mates'',''--component'',$name)',
    "write_authority -cne 'NONE'",
    'model_mutation -ne $false',
    'Get-FileEvidence -Path $ExpectedDocumentPath',
    'Get-TargetState -ComponentsEnvelope $componentsBefore',
    'Get-TargetState -ComponentsEnvelope $componentsAfter',
    'Write-JsonFileUtf8NoBom'
)

foreach ($literal in $requiredLiterals) {
    if (-not $text.Contains($literal)) {
        throw "Verifier source contract is missing required literal: $literal"
    }
}

$forbiddenPatterns = @(
    '(?im)\.\s*Save(?:As|3|Silent)?\s*\(',
    '(?im)\bRebuild(?:3)?\b',
    '(?im)\bAddMate\b',
    '(?im)\bSetSuppression\b',
    '(?im)\bSelectByID2\b',
    '(?im)\.Transform2\s*=',
    '(?im)\bSetTransform\b',
    '(?im)\bRemote\s*Queue\b'
)

foreach ($pattern in $forbiddenPatterns) {
    if ([regex]::IsMatch($text, $pattern)) {
        throw "Verifier source contract contains forbidden mutation/control surface: $pattern"
    }
}

Write-Host 'PASS: V43 Prism mate-read verifier source contract'
