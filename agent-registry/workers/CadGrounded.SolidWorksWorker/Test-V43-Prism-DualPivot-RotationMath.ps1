Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Verifier = Join-Path $PSScriptRoot 'Verify-Pop-V43-Prism-DualPivot-ExactHypotheticalSweep.ps1'
if (-not (Test-Path -LiteralPath $Verifier -PathType Leaf)) {
    throw "Verifier missing: $Verifier"
}

$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $Verifier,
    [ref]$tokens,
    [ref]$errors
)
if (@($errors).Count -ne 0) {
    throw ("Verifier parser errors: " + (@($errors | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine))
}

foreach ($functionName in @('Multiply-Rotation3RowMajor','Get-RotationZRowMajor')) {
    $fn = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -ceq $functionName
    }, $true)
    if ($null -eq $fn) {
        throw "Function not found in verifier: $functionName"
    }
    . ([ScriptBlock]::Create($fn.Extent.Text))
}

function Assert-NearVector {
    param(
        [Parameter(Mandatory=$true)]$Actual,
        [Parameter(Mandatory=$true)][double[]]$Expected,
        [double]$Tolerance = 1e-12,
        [string]$Label = 'vector'
    )
    $actualValues = @($Actual)
    if ($actualValues.Count -ne $Expected.Count) {
        throw "$Label count mismatch. Expected=$($Expected.Count) Actual=$($actualValues.Count)"
    }
    for ($index=0; $index -lt $Expected.Count; $index++) {
        if ([Math]::Abs([double]$actualValues[$index] - $Expected[$index]) -gt $Tolerance) {
            throw "$Label mismatch at index $index. Expected=$($Expected[$index]) Actual=$($actualValues[$index])"
        }
    }
}

$identity = [double[]]@(
    1.0,0.0,0.0,
    0.0,1.0,0.0,
    0.0,0.0,1.0
)
Assert-NearVector -Actual @(Multiply-Rotation3RowMajor -A $identity -B $identity) -Expected $identity -Label 'identity multiply'

$rz90 = [double[]]@(Get-RotationZRowMajor -AngleDeg 90.0)
$expectedRz90 = [double[]]@(
    0.0,1.0,0.0,
    -1.0,0.0,0.0,
    0.0,0.0,1.0
)
Assert-NearVector -Actual $rz90 -Expected $expectedRz90 -Tolerance 1e-12 -Label 'Rz(90)'
Assert-NearVector -Actual @(Multiply-Rotation3RowMajor -A $identity -B $rz90) -Expected $expectedRz90 -Tolerance 1e-12 -Label 'identity times Rz(90)'

Write-Host 'PASS: v43 PRISM dual-pivot rotation math regression'
