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
$requiredDofPath = Join-Path $repoRoot 'agent-registry\reasoning\requirements\function-first-bottle-dof.v1.json'

Assert-True (Test-Path -LiteralPath $manifestPath -PathType Leaf) 'Module manifest is missing.'
Assert-True (Test-Path -LiteralPath $modulePath -PathType Leaf) 'Module source is missing.'
Assert-True (Test-Path -LiteralPath $registryPath -PathType Leaf) 'Capability registry is missing.'
Assert-True (Test-Path -LiteralPath $requiredDofPath -PathType Leaf) 'Function-first bottle DOF requirement model is missing.'

Import-Module $manifestPath -Force

$dofModel = Get-Content -LiteralPath $requiredDofPath -Raw | ConvertFrom-Json
Assert-True ([string]$dofModel.requirement_model_id -ceq 'CADGROUNDED.IXOR.FUNCTION_FIRST_BOTTLE_DOF.V1') 'Bottle DOF requirement model id is incorrect.'
$axisNames = @($dofModel.functional_axes.PSObject.Properties.Name)
foreach ($axis in @('translation_flow','translation_cross_flow','translation_vertical','rotation_wrap_axis','rotation_tilt_flow','rotation_tilt_cross_flow')) {
    Assert-True ($axisNames -contains $axis) "Bottle DOF requirement model is missing axis '$axis'."
}
$stateIds = @($dofModel.state_requirements | ForEach-Object { [string]$_.state_id })
foreach ($state in @('INDEXED','CAPTURE_AND_ROTATION','LABEL_TRANSFER_INTERVAL','WRAP_ACTIVE','RELEASE')) {
    Assert-True ($stateIds -contains $state) "Bottle DOF requirement model is missing state '$state'."
}
$wrap = @($dofModel.state_requirements | Where-Object { [string]$_.state_id -ceq 'WRAP_ACTIVE' })
Assert-True ($wrap.Count -eq 1) 'WRAP_ACTIVE bottle DOF row must resolve uniquely.'
Assert-True ([string]$wrap[0].dof.rotation_wrap_axis.requirement -ceq 'INTENTIONALLY_PERMIT_AND_CONTROL') 'WRAP_ACTIVE must intentionally permit and control wrap-axis rotation.'
$modelText = Get-Content -LiteralPath $requiredDofPath -Raw
foreach ($forbiddenMechanismToken in @('FITCHECK_PRISM_CARRIER','FITCHECK_PRISM_LINK','FITCHECK_PRISM_ARM','translating roller carrier is required','pivoting roller arm is required')) {
    Assert-True (-not $modelText.Contains($forbiddenMechanismToken)) "Bottle DOF requirements improperly hard-code mechanism token '$forbiddenMechanismToken'."
}


$expectedCommands = @(
    'Get-CGCapabilityCatalog',
    'Get-CGCapability',
    'Get-CGState',
    'Get-CGComponentBinding',
    'Test-CGContactPair',
    'Test-CGTopologyChain',
    'Get-CGMateBinding',
    'Get-CGRequiredBottleDOF',
    'Get-CGBottleContactConstraintMap',
    'Get-CGBottleContactWrenchRank',
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
    'cg.product.required-dof',
    'cg.product.contact-constraint-map',
    'cg.product.contact-wrench-rank',
    'cg.frontier.read',
    'cg.verifier.v43.full-chain-mates',
    'cg.verifier.function-first.bottle-support-contact',
    'cg.verifier.function-first.lateral-contact-manifold'
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
    'cg.contact.surface-normal',
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
    'cg.visualization.gate',
    'cg.requirements.functional',
    'cg.requirements.rotation',
    'cg.mechanism.candidates',
    'cg.mechanism.screen'
)
foreach ($id in $requiredPlanned) {
    $matches = @($catalog | Where-Object { [string]$_.id -ceq $id -and [string]$_.status -ceq 'PLANNED' })
    Assert-True ($matches.Count -eq 1) "Planned engineering capability '$id' is missing or has the wrong maturity state."
    Assert-True ($matches[0].PSObject.Properties.Name -contains 'future_command') "Planned capability '$id' must name its future semantic command."
    Assert-True (-not ($matches[0].PSObject.Properties.Name -contains 'command')) "Planned capability '$id' must not masquerade as an implemented command."
}


$requiredDof = Get-CGCapability -Id 'cg.product.required-dof'
Assert-True ([string]$requiredDof.status -ceq 'IMPLEMENTED') 'Bottle DOF capability must be IMPLEMENTED.'
Assert-True ([string]$requiredDof.command -ceq 'Get-CGRequiredBottleDOF') 'Bottle DOF capability command binding is incorrect.'
Assert-True ([string]$requiredDof.execution_kind -ceq 'deterministic_requirement_derivation') 'Bottle DOF capability execution kind is incorrect.'
Assert-True ([string]$requiredDof.write_authority -ceq 'NONE') 'Bottle DOF capability must remain read-only.'


$bottleSupportVerifier = Get-CGCapability -Id 'cg.verifier.function-first.bottle-support-contact'
Assert-True ([string]$bottleSupportVerifier.status -ceq 'IMPLEMENTED') 'Bottle support/contact verifier must be IMPLEMENTED.'
Assert-True ([string]$bottleSupportVerifier.execution_kind -ceq 'registered_verifier') 'Bottle support/contact verifier execution kind is incorrect.'
Assert-True ([string]$bottleSupportVerifier.write_authority -ceq 'NONE') 'Bottle support/contact verifier must remain read-only.'
Assert-True ([string]$bottleSupportVerifier.verifier_path -ceq 'agent-registry/workers/CadGrounded.SolidWorksWorker/Verify-ClassifyContact-FunctionFirst-BottleSupport.ps1') 'Bottle support/contact verifier path is incorrect.'

$lateralManifoldVerifier = Get-CGCapability -Id 'cg.verifier.function-first.lateral-contact-manifold'
Assert-True ([string]$lateralManifoldVerifier.status -ceq 'IMPLEMENTED') 'Lateral contact manifold verifier must be IMPLEMENTED.'
Assert-True ([string]$lateralManifoldVerifier.execution_kind -ceq 'registered_verifier') 'Lateral contact manifold verifier execution kind is incorrect.'
Assert-True ([string]$lateralManifoldVerifier.write_authority -ceq 'NONE') 'Lateral contact manifold verifier must remain read-only.'
Assert-True ([string]$lateralManifoldVerifier.verifier_path -ceq 'agent-registry/workers/CadGrounded.SolidWorksWorker/Verify-ContactManifold-FunctionFirst-LateralContacts.ps1') 'Lateral contact manifold verifier path is incorrect.'

$constraintMap = Get-CGBottleContactConstraintMap -EvidenceOnly
Assert-True ([string]$constraintMap.capability_id -ceq 'cg.product.contact-constraint-map') 'Constraint-map capability id is incorrect.'
Assert-True ($constraintMap.data.lateral_normal_closure.positive_span -eq $true) 'Three lateral normal reactions must positively span assembly XY in the admitted fixture.'
Assert-True ([string]$constraintMap.data.lateral_normal_closure.state -ceq 'SUPPORTED_CURRENT_POSE_FRICTIONLESS_NORMAL_MODEL') 'Constraint-map lateral closure state is incorrect.'
Assert-True ([Math]::Abs([double]$constraintMap.data.common_axis_candidate.point_xy_mm[0] - (-153.42061528267112)) -lt 1e-6) 'Constraint-map common-axis X is incorrect.'
Assert-True ([Math]::Abs([double]$constraintMap.data.common_axis_candidate.point_xy_mm[1] - (-214.0)) -lt 1e-6) 'Constraint-map common-axis Y is incorrect.'
Assert-True ([double]$constraintMap.data.radial_geometry.radius_spread_mm -lt 1e-6) 'Constraint-map lateral radii should agree to numerical precision.'
Assert-True ([double]$constraintMap.data.normal_reaction_moment_about_common_axis.max_abs_torque_per_unit_reaction_mm -lt 1e-6) 'Constraint-map normal reactions should have near-zero moment about the common axis.'
Assert-True ([string]$constraintMap.data.functional_projection.tilt_restraint -ceq 'UNRESOLVED') 'Constraint map must preserve unresolved tilt restraint.'
Assert-True ([string]$constraintMap.data.functional_projection.frictional_wrap_torque -ceq 'UNRESOLVED') 'Constraint map must preserve unresolved frictional wrap torque.'
Assert-True ($constraintMap.mechanical_acceptance_granted -eq $false) 'Constraint map must not grant mechanical acceptance.'

$wrenchRank = Get-CGBottleContactWrenchRank -EvidenceOnly
Assert-True ([string]$wrenchRank.capability_id -ceq 'cg.product.contact-wrench-rank') 'Wrench-rank capability id is incorrect.'
Assert-True ([int]$wrenchRank.data.matrix_rank -eq 4) 'Expected four independent maintained point-normal constraints.'
Assert-True ([int]$wrenchRank.data.nullity -eq 2) 'Expected two instantaneous null modes in the four-point normal model.'
Assert-True ($wrenchRank.data.wrap_axis_rotation_test.is_null_mode -eq $true) 'Pure bound wrap-axis rotation should be a null mode.'
Assert-True ([int]$wrenchRank.data.restraint_projection.additional_independent_null_modes_beyond_common_axis_rotation -eq 1) 'Expected one additional independent null mode beyond wrap-axis rotation.'
Assert-True ([string]$wrenchRank.data.restraint_projection.five_dof_restraint_excluding_common_axis_rotation -ceq 'NOT_SUPPORTED_BY_CURRENT_FOUR_POINT_NORMAL_MODEL') 'Four-point normal model must not claim five-DOF restraint.'
Assert-True ($wrenchRank.mechanical_acceptance_granted -eq $false) 'Wrench-rank calculation must not grant mechanical acceptance.'

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
