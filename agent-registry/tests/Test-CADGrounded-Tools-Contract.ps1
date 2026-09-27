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

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$moduleRoot = Join-Path $repoRoot 'agent-registry\powershell\CADGrounded.Tools'
$manifestPath = Join-Path $moduleRoot 'CADGrounded.Tools.psd1'
$modulePath = Join-Path $moduleRoot 'CADGrounded.Tools.psm1'
$registryPath = Join-Path $moduleRoot 'capability-registry.v1.json'

Assert-True (Test-Path -LiteralPath $manifestPath -PathType Leaf) 'Module manifest is missing.'
Assert-True (Test-Path -LiteralPath $modulePath -PathType Leaf) 'Module source is missing.'
Assert-True (Test-Path -LiteralPath $registryPath -PathType Leaf) 'Capability registry is missing.'

Import-Module $manifestPath -Force

$expectedCommands = @(
    'Get-CGCapabilityCatalog',
    'Get-CGCapability',
    'Get-CGState',
    'Get-CGComponentBinding',
    'Test-CGContactPair',
    'Test-CGTopologyChain',
    'Get-CGMateBinding',
    'Get-CGCurrentPlan',
    'Get-CGInvestigationFrontier',
    'Invoke-CGRegisteredVerifier'
)

foreach ($name in $expectedCommands) {
    $cmd = Get-Command -Name $name -Module CADGrounded.Tools -ErrorAction Stop
    Assert-True ($null -ne $cmd) "Expected exported command '$name' is missing."
}

$catalog = @(Get-CGCapabilityCatalog)
$ids = @($catalog | ForEach-Object { [string]$_.id })
Assert-True ($ids.Count -eq (@($ids | Select-Object -Unique)).Count) 'Capability ids are not unique.'

$requiredImplemented = @(
    'cg.state.read',
    'cg.component.bind',
    'cg.contact.pair',
    'cg.topology.chain',
    'cg.mates.bind',
    'cg.frontier.read',
    'cg.verifier.v43.full-chain-mates'
)
foreach ($id in $requiredImplemented) {
    $matches = @($catalog | Where-Object { [string]$_.id -ceq $id -and [string]$_.status -ceq 'IMPLEMENTED' })
    Assert-True ($matches.Count -eq 1) "Implemented capability '$id' is missing or duplicated."
}

$implemented = @($catalog | Where-Object { [string]$_.status -ceq 'IMPLEMENTED' })
foreach ($capability in $implemented) {
    Assert-True ([string]$capability.write_authority -ceq 'NONE') "Implemented capability '$($capability.id)' is not read-only."
    Assert-True ($capability.remote_queue_authorized -eq $false) "Implemented capability '$($capability.id)' unexpectedly authorizes Remote Queue."
}

$requiredPlanned = @(
    'cg.product.support',
    'cg.product.restraint',
    'cg.product.entry-path',
    'cg.product.exit-path',
    'cg.wrap.contact',
    'cg.label.peel-edge',
    'cg.label.transfer-path',
    'cg.index.hardstop',
    'cg.reaction.path',
    'cg.mount.integrity',
    'cg.provenance.kinematic-source',
    'cg.motion.candidate',
    'cg.motion.sweep',
    'cg.acceptance.check',
    'cg.visualization.gate'
)
foreach ($id in $requiredPlanned) {
    $matches = @($catalog | Where-Object { [string]$_.id -ceq $id -and [string]$_.status -ceq 'PLANNED' })
    Assert-True ($matches.Count -eq 1) "Planned engineering capability '$id' is missing or has the wrong maturity state."
    Assert-True ($matches[0].PSObject.Properties.Name -contains 'future_command') "Planned capability '$id' must name its future semantic command."
    Assert-True (-not ($matches[0].PSObject.Properties.Name -contains 'command')) "Planned capability '$id' must not masquerade as an implemented command."
}

$currentPlan = Get-CGCurrentPlan
Assert-True (-not [string]::IsNullOrWhiteSpace([string]$currentPlan.current_plan_id)) 'CURRENT_PLAN has no current_plan_id.'
Assert-True (-not [string]::IsNullOrWhiteSpace([string]$currentPlan.current_architecture_id)) 'CURRENT_PLAN has no current_architecture_id.'

$frontier = Get-CGInvestigationFrontier
Assert-True ([string]$frontier.capability_id -ceq 'cg.frontier.read') 'Investigation frontier returned the wrong capability id.'
Assert-True (@($frontier.next_tests).Count -gt 0) 'Investigation frontier returned no registered next tests.'
Assert-True ($frontier.mechanical_acceptance_granted -eq $false) 'Investigation frontier must not grant mechanical acceptance.'

$source = Get-Content -LiteralPath $modulePath -Raw
foreach ($forbidden in @(
    'sw.set_transform',
    'sw.insert_component',
    'AddMate',
    'CreateMate',
    'EditRebuild',
    'ForceRebuild',
    'SaveAs'
)) {
    Assert-True (-not $source.Contains($forbidden)) "PowerShell command surface contains forbidden CAD write token '$forbidden'."
}

foreach ($requiredGuard in @(
    "execution_kind -cne 'registered_verifier'",
    "write_authority -cne 'NONE'",
    'Verify-*.ps1',
    'escaped the repository root.',
    'mechanical_acceptance_granted = $false'
)) {
    Assert-True ($source.Contains($requiredGuard)) "PowerShell command surface is missing required guard '$requiredGuard'."
}

Write-Host 'PASS: CADGrounded.Tools capability/authority contract'
