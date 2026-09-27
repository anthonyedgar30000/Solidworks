#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ModuleRoot = $PSScriptRoot
$script:RegistryPath = Join-Path $script:ModuleRoot 'capability-registry.v1.json'
$script:RepositoryRoot = (Resolve-Path (Join-Path $script:ModuleRoot '..\..\..')).Path
$script:WorkerRoot = Join-Path $script:RepositoryRoot 'agent-registry\workers\CadGrounded.SolidWorksWorker'
$script:WorkerExe = Join-Path $script:WorkerRoot 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'

$fileEvidenceHelper = Join-Path $script:WorkerRoot 'FileEvidence.ps1'
if (Test-Path -LiteralPath $fileEvidenceHelper -PathType Leaf) {
    . $fileEvidenceHelper
}

function Write-CGOutput {
    param(
        [Parameter(Mandatory=$true)]$Value,
        [switch]$AsJson
    )
    if ($AsJson) {
        $Value | ConvertTo-Json -Depth 100
    } else {
        $Value
    }
}

function Get-CGRegistryRaw {
    if (-not (Test-Path -LiteralPath $script:RegistryPath -PathType Leaf)) {
        throw "CADGrounded capability registry not found: $script:RegistryPath"
    }
    return (Get-Content -LiteralPath $script:RegistryPath -Raw | ConvertFrom-Json)
}

function Assert-CGWorkerAvailable {
    if (-not (Test-Path -LiteralPath $script:WorkerExe -PathType Leaf)) {
        throw "CADGrounded native worker executable not found: $script:WorkerExe. Build the reviewed worker first."
    }
}

function Invoke-CGWorkerCli {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)

    Assert-CGWorkerAvailable
    $text = (& $script:WorkerExe @Arguments | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "CADGrounded worker failed. ExitCode=$exitCode Arguments=$($Arguments -join ' ')"
    }
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "CADGrounded worker returned no JSON. Arguments=$($Arguments -join ' ')"
    }

    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) {
        $message = if ($null -ne $envelope.error) { [string]$envelope.error.message } else { 'unknown worker error' }
        throw "CADGrounded worker returned ok=false. Command=$($envelope.command_id) Error=$message"
    }
    return $envelope
}

function Invoke-CGWorkerRequest {
    param([Parameter(Mandatory=$true)]$Request)

    Assert-CGWorkerAvailable
    $requestJson = $Request | ConvertTo-Json -Depth 30 -Compress
    $text = ($requestJson | & $script:WorkerExe execute-json | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "CADGrounded worker execute-json failed. ExitCode=$exitCode"
    }
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw 'CADGrounded worker execute-json returned no JSON.'
    }

    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) {
        $message = if ($null -ne $envelope.error) { [string]$envelope.error.message } else { 'unknown worker error' }
        throw "CADGrounded worker returned ok=false. Command=$($envelope.command_id) Error=$message"
    }
    return $envelope
}

function Get-CGDocumentState {
    param([Parameter(Mandatory=$true)]$StatusEnvelope)

    return [ordered]@{
        solidworks_process_id = [string]$StatusEnvelope.data.solidworks_process_id
        title = [string]$StatusEnvelope.data.document.title
        path = [string]$StatusEnvelope.data.document.path
        type = [string]$StatusEnvelope.data.document.type
        active_configuration = [string]$StatusEnvelope.data.document.active_configuration
        save_flag = $StatusEnvelope.data.document.save_flag
    }
}

function Assert-CGReadOnlyEnvelope {
    param([Parameter(Mandatory=$true)]$Envelope)

    if ([string]$Envelope.data.write_authority -cne 'NONE') {
        throw "Worker command '$($Envelope.command_id)' did not report write_authority NONE."
    }
    if ($Envelope.data.PSObject.Properties.Name -contains 'model_mutation' -and $Envelope.data.model_mutation -ne $false) {
        throw "Worker command '$($Envelope.command_id)' reported model_mutation other than false."
    }
}

function Assert-CGExpectedState {
    param(
        [Parameter(Mandatory=$true)]$StatusEnvelope,
        [string]$ExpectedDocumentTitle,
        [string]$ExpectedDocumentPath,
        [string]$ExpectedConfiguration
    )

    if (-not [string]::IsNullOrWhiteSpace($ExpectedDocumentTitle) -and
        [string]$StatusEnvelope.data.document.title -cne $ExpectedDocumentTitle) {
        throw "Active document title mismatch. Expected='$ExpectedDocumentTitle' Actual='$($StatusEnvelope.data.document.title)'."
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedDocumentPath) -and
        -not [string]::Equals([string]$StatusEnvelope.data.document.path,$ExpectedDocumentPath,[StringComparison]::OrdinalIgnoreCase)) {
        throw "Active document path mismatch. Expected='$ExpectedDocumentPath' Actual='$($StatusEnvelope.data.document.path)'."
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedConfiguration) -and
        [string]$StatusEnvelope.data.document.active_configuration -cne $ExpectedConfiguration) {
        throw "Active configuration mismatch. Expected='$ExpectedConfiguration' Actual='$($StatusEnvelope.data.document.active_configuration)'."
    }
}

function Get-CGExactComponentFromEnvelope {
    param(
        [Parameter(Mandatory=$true)]$ComponentsEnvelope,
        [Parameter(Mandatory=$true)][string]$Name2
    )

    $matches = @($ComponentsEnvelope.data.components | Where-Object { [string]$_.name2 -ceq $Name2 })
    if ($matches.Count -ne 1) {
        throw "Exact Component2.Name2 must resolve uniquely. Name2='$Name2' Matches=$($matches.Count)."
    }
    return $matches[0]
}

function Get-CGTargetState {
    param(
        [Parameter(Mandatory=$true)]$ComponentsEnvelope,
        [Parameter(Mandatory=$true)][string[]]$Names
    )

    $state = [ordered]@{}
    foreach ($name in $Names) {
        $row = Get-CGExactComponentFromEnvelope -ComponentsEnvelope $ComponentsEnvelope -Name2 $name
        $state[$name] = [ordered]@{
            name2 = [string]$row.name2
            path = [string]$row.path
            suppression_state = $row.suppression_state
            suppressed = $row.suppressed
            fixed_component = $row.fixed_component
            fixed = $row.fixed
            is_top_level = $row.is_top_level
            parent_name = $row.parent_name
            rotation9 = @($row.rotation9)
            translation_mm = @($row.translation_mm)
            transform_source = $row.transform_source
        }
    }
    return $state
}

function Get-CGFileState {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (Get-Command Get-FileEvidence -ErrorAction SilentlyContinue) {
        return Get-FileEvidence -Path $Path
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Active SOLIDWORKS file not found for evidence snapshot: $Path"
    }
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        length = $item.Length
        last_write_time_utc = $item.LastWriteTimeUtc.ToString('o')
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function New-CGEnvelope {
    param(
        [Parameter(Mandatory=$true)][string]$CapabilityId,
        [Parameter(Mandatory=$true)][string]$Result,
        [Parameter(Mandatory=$true)]$Data,
        [string[]]$Establishes = @(),
        [string[]]$DoesNotEstablish = @(),
        [string]$AmbiguityBucket = 'INSUFFICIENT_EVIDENCE',
        [string]$SourceAuthority = 'SOLIDWORKS_LIVE_STATE',
        [string]$SourceClassification = 'verified_from_solidworks_api'
    )

    return [pscustomobject][ordered]@{
        schema_version = 1
        capability_id = $CapabilityId
        result = $Result
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        source_authority = $SourceAuthority
        source_classification = $SourceClassification
        data = $Data
        establishes = @($Establishes)
        does_not_establish = @($DoesNotEstablish)
        ambiguity_bucket = $AmbiguityBucket
        mechanical_acceptance_granted = $false
        model_mutation = $false
        write_authority = 'NONE'
    }
}

function Get-CGCapabilityCatalog {
    [CmdletBinding()]
    param(
        [ValidateSet('IMPLEMENTED','PLANNED','BLOCKED','ALL')]
        [string]$Status = 'ALL',
        [switch]$AsJson
    )

    $registry = Get-CGRegistryRaw
    $items = @($registry.capabilities)
    if ($Status -ne 'ALL') {
        $items = @($items | Where-Object { [string]$_.status -ceq $Status })
    }
    Write-CGOutput -Value $items -AsJson:$AsJson
}

function Get-CGCapability {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Id,
        [switch]$AsJson
    )

    $items = @((Get-CGRegistryRaw).capabilities | Where-Object { [string]$_.id -ceq $Id })
    if ($items.Count -ne 1) {
        throw "Capability id must resolve uniquely. Id='$Id' Matches=$($items.Count)."
    }
    Write-CGOutput -Value $items[0] -AsJson:$AsJson
}

function Get-CGState {
    [CmdletBinding()]
    param(
        [string]$ExpectedDocumentTitle,
        [string]$ExpectedDocumentPath,
        [string]$ExpectedConfiguration,
        [switch]$AsJson
    )

    $status = Invoke-CGWorkerCli -Arguments @('status')
    Assert-CGReadOnlyEnvelope -Envelope $status
    Assert-CGExpectedState -StatusEnvelope $status -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration

    $result = New-CGEnvelope -CapabilityId 'cg.state.read' -Result 'PASS' -Data ([ordered]@{
        worker_version = $status.data.worker_version
        solidworks_process_id = $status.data.solidworks_process_id
        document = $status.data.document
    }) -Establishes @(
        'exact active SOLIDWORKS document identity at this read',
        'active configuration at this read',
        'worker read-only authority state'
    ) -DoesNotEstablish @(
        'mechanical correctness',
        'geometry acceptance',
        'operating sequence'
    ) -AmbiguityBucket 'INSUFFICIENT_EVIDENCE'

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Get-CGComponentBinding {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Name2,
        [string]$ExpectedDocumentTitle,
        [string]$ExpectedDocumentPath,
        [string]$ExpectedConfiguration,
        [switch]$AsJson
    )

    $status = Invoke-CGWorkerCli -Arguments @('status')
    Assert-CGReadOnlyEnvelope -Envelope $status
    Assert-CGExpectedState -StatusEnvelope $status -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration
    $components = Invoke-CGWorkerCli -Arguments @('components','--all')
    Assert-CGReadOnlyEnvelope -Envelope $components
    $row = Get-CGExactComponentFromEnvelope -ComponentsEnvelope $components -Name2 $Name2

    $result = New-CGEnvelope -CapabilityId 'cg.component.bind' -Result 'PASS' -Data ([ordered]@{
        document = Get-CGDocumentState -StatusEnvelope $status
        component = $row
    }) -Establishes @(
        'exact Component2.Name2 identity',
        'current component path/state/transform returned by SOLIDWORKS'
    ) -DoesNotEstablish @(
        'component function',
        'joint relationship',
        'mechanical acceptance'
    ) -AmbiguityBucket 'KINEMATIC_STATE_UNRESOLVED'

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Test-CGContactPair {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$AName2,
        [Parameter(Mandatory=$true)][string]$BName2,
        [string]$ExpectedDocumentTitle,
        [string]$ExpectedDocumentPath,
        [string]$ExpectedConfiguration,
        [switch]$AsJson
    )

    if ($AName2 -ceq $BName2) { throw 'AName2 and BName2 must identify different components.' }

    $statusBefore = Invoke-CGWorkerCli -Arguments @('status')
    Assert-CGReadOnlyEnvelope -Envelope $statusBefore
    Assert-CGExpectedState -StatusEnvelope $statusBefore -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration
    $documentBefore = Get-CGDocumentState -StatusEnvelope $statusBefore
    $fileBefore = Get-CGFileState -Path ([string]$statusBefore.data.document.path)

    $componentsBefore = Invoke-CGWorkerCli -Arguments @('components','--all')
    Assert-CGReadOnlyEnvelope -Envelope $componentsBefore
    $targetBefore = Get-CGTargetState -ComponentsEnvelope $componentsBefore -Names @($AName2,$BName2)

    $contact = Invoke-CGWorkerRequest -Request @{
        command_id = 'sw.classify_contact_pair'
        payload = @{
            a_name_exact = $AName2
            b_name_exact = $BName2
        }
    }

    if ([string]$contact.command_id -cne 'sw.classify_contact_pair') { throw 'Unexpected worker command id.' }
    if ([string]$contact.data.component_a.name2 -cne $AName2 -or [string]$contact.data.component_b.name2 -cne $BName2) {
        throw 'Contact query returned the wrong exact component pair.'
    }
    Assert-CGReadOnlyEnvelope -Envelope $contact
    if ($null -eq $contact.data.minimum_distance_mm -or [string]::IsNullOrWhiteSpace([string]$contact.data.classification)) {
        throw 'Contact query omitted minimum distance or classification.'
    }

    $componentsAfter = Invoke-CGWorkerCli -Arguments @('components','--all')
    Assert-CGReadOnlyEnvelope -Envelope $componentsAfter
    $targetAfter = Get-CGTargetState -ComponentsEnvelope $componentsAfter -Names @($AName2,$BName2)
    $statusAfter = Invoke-CGWorkerCli -Arguments @('status')
    Assert-CGReadOnlyEnvelope -Envelope $statusAfter
    Assert-CGExpectedState -StatusEnvelope $statusAfter -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration
    $documentAfter = Get-CGDocumentState -StatusEnvelope $statusAfter
    $fileAfter = Get-CGFileState -Path ([string]$statusAfter.data.document.path)

    if (($targetBefore | ConvertTo-Json -Depth 30 -Compress) -cne ($targetAfter | ConvertTo-Json -Depth 30 -Compress)) {
        throw 'Target component state changed during read-only contact classification.'
    }
    if (($documentBefore | ConvertTo-Json -Depth 20 -Compress) -cne ($documentAfter | ConvertTo-Json -Depth 20 -Compress)) {
        throw 'SOLIDWORKS document/process/configuration/save state changed during read-only contact classification.'
    }
    if (($fileBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($fileAfter | ConvertTo-Json -Depth 10 -Compress)) {
        throw 'Assembly file evidence changed during read-only contact classification.'
    }

    $result = New-CGEnvelope -CapabilityId 'cg.contact.pair' -Result 'PASS' -Data ([ordered]@{
        document = $documentAfter
        pair = [ordered]@{ a_name2 = $AName2; b_name2 = $BName2 }
        observation = $contact.data
        target_state_before = $targetBefore
        target_state_after = $targetAfter
        file_before = $fileBefore
        file_after = $fileAfter
    }) -Establishes @(
        'exact current-pose component-pair identity',
        'minimum distance and returned current-pose contact/interference classification',
        'B-rep intersection evidence when the worker executes it',
        'pre/post no-mutation comparison'
    ) -DoesNotEstablish @(
        'joint type',
        'bearing function',
        'force or preload',
        'motion or reachable-state behavior',
        'mechanical acceptance'
    ) -AmbiguityBucket 'KINEMATIC_STATE_UNRESOLVED'

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Test-CGTopologyChain {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateCount(2,64)][string[]]$Name2,
        [string]$ExpectedDocumentTitle,
        [string]$ExpectedDocumentPath,
        [string]$ExpectedConfiguration,
        [switch]$AsJson
    )

    $pairs = @()
    $allContact = $true
    $anyUnresolved = $false

    for ($i = 0; $i -lt ($Name2.Count - 1); $i++) {
        $pair = Test-CGContactPair -AName2 $Name2[$i] -BName2 $Name2[$i + 1] -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration
        $classification = [string]$pair.data.observation.classification
        if ($classification -cne 'contact_or_coincidence_within_tolerance') {
            $allContact = $false
        }
        if ([string]::IsNullOrWhiteSpace($classification)) {
            $anyUnresolved = $true
        }
        $pairs += [ordered]@{
            a_name2 = $Name2[$i]
            b_name2 = $Name2[$i + 1]
            minimum_distance_mm = $pair.data.observation.minimum_distance_mm
            classification = $classification
            intersection_volume_mm3 = $pair.data.observation.intersection_volume_mm3
        }
    }

    $topologyState = if ($anyUnresolved) {
        'UNRESOLVED'
    } elseif ($allContact) {
        'ALL_ADJACENT_CONTACT_AT_RECORDED_POSE'
    } else {
        'NOT_CONTIGUOUS_AT_RECORDED_POSE'
    }

    $result = New-CGEnvelope -CapabilityId 'cg.topology.chain' -Result 'PASS' -Data ([ordered]@{
        ordered_components = @($Name2)
        adjacent_pairs = $pairs
        topology_state = $topologyState
    }) -Establishes @(
        'current-pose classification of every explicitly ordered adjacent pair'
    ) -DoesNotEstablish @(
        'mechanism DOF',
        'motion law',
        'force path',
        'retention through motion',
        'mechanical acceptance'
    ) -AmbiguityBucket 'KINEMATIC_STATE_UNRESOLVED'

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Get-CGMateBinding {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateCount(1,64)][string[]]$Name2,
        [string]$ExpectedDocumentTitle,
        [string]$ExpectedDocumentPath,
        [string]$ExpectedConfiguration,
        [switch]$AsJson
    )

    $uniqueNames = @($Name2 | Select-Object -Unique)
    if ($uniqueNames.Count -ne $Name2.Count) { throw 'Name2 contains duplicate component identities.' }

    $statusBefore = Invoke-CGWorkerCli -Arguments @('status')
    Assert-CGReadOnlyEnvelope -Envelope $statusBefore
    Assert-CGExpectedState -StatusEnvelope $statusBefore -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration
    $documentBefore = Get-CGDocumentState -StatusEnvelope $statusBefore
    $fileBefore = Get-CGFileState -Path ([string]$statusBefore.data.document.path)

    $componentsBefore = Invoke-CGWorkerCli -Arguments @('components','--all')
    Assert-CGReadOnlyEnvelope -Envelope $componentsBefore
    $targetBefore = Get-CGTargetState -ComponentsEnvelope $componentsBefore -Names $uniqueNames

    $mateResults = [ordered]@{}
    $coverage = [ordered]@{}
    foreach ($name in $uniqueNames) {
        $mate = Invoke-CGWorkerCli -Arguments @('mates','--component',$name)
        if ([string]$mate.command_id -cne 'sw.query_mates') { throw "Unexpected mate command id for '$name'." }
        Assert-CGReadOnlyEnvelope -Envelope $mate
        if ([string]$mate.data.component.name2 -cne $name) { throw "Mate query returned wrong exact component for '$name'." }

        $rows = @($mate.data.mates)
        $mateResults[$name] = $mate.data
        $coverage[$name] = [ordered]@{
            incident_mate_count = $rows.Count
            variation_values_observed = @(
                $rows | Where-Object { $null -ne $_.minimum_variation -or $null -ne $_.maximum_variation }
            ).Count
            fixed_component = $mate.data.component.fixed_component
            referenced_configuration = $mate.data.component.referenced_configuration
            parent_chain = @($mate.data.component.parent_chain)
            parentage_errors = @($mate.data.component.parentage_errors)
        }
    }

    $componentsAfter = Invoke-CGWorkerCli -Arguments @('components','--all')
    Assert-CGReadOnlyEnvelope -Envelope $componentsAfter
    $targetAfter = Get-CGTargetState -ComponentsEnvelope $componentsAfter -Names $uniqueNames
    $statusAfter = Invoke-CGWorkerCli -Arguments @('status')
    Assert-CGReadOnlyEnvelope -Envelope $statusAfter
    Assert-CGExpectedState -StatusEnvelope $statusAfter -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration
    $documentAfter = Get-CGDocumentState -StatusEnvelope $statusAfter
    $fileAfter = Get-CGFileState -Path ([string]$statusAfter.data.document.path)

    if (($targetBefore | ConvertTo-Json -Depth 30 -Compress) -cne ($targetAfter | ConvertTo-Json -Depth 30 -Compress)) {
        throw 'Target component state changed during read-only mate queries.'
    }
    if (($documentBefore | ConvertTo-Json -Depth 20 -Compress) -cne ($documentAfter | ConvertTo-Json -Depth 20 -Compress)) {
        throw 'SOLIDWORKS document/process/configuration/save state changed during read-only mate queries.'
    }
    if (($fileBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($fileAfter | ConvertTo-Json -Depth 10 -Compress)) {
        throw 'Assembly file evidence changed during read-only mate queries.'
    }

    $result = New-CGEnvelope -CapabilityId 'cg.mates.bind' -Result 'PASS' -Data ([ordered]@{
        document = $documentAfter
        target_components = $uniqueNames
        mate_results = $mateResults
        coverage = $coverage
        target_state_before = $targetBefore
        target_state_after = $targetAfter
        file_before = $fileBefore
        file_after = $fileAfter
    }) -Establishes @(
        'exact incident active-assembly mate observations for the named components',
        'mate suppression/type/variation evidence when exposed by SOLIDWORKS',
        'explicit zero incident mate counts as negative evidence',
        'pre/post no-mutation comparison'
    ) -DoesNotEstablish @(
        'physical closure ownership',
        'force or preload',
        'operating motion',
        'reachable envelope',
        'mechanical acceptance'
    ) -AmbiguityBucket 'KINEMATIC_STATE_UNRESOLVED'

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Get-CGCurrentPlan {
    [CmdletBinding()]
    param([switch]$AsJson)

    $path = Join-Path $script:RepositoryRoot 'agent-registry\planning\CURRENT_PLAN.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "CURRENT_PLAN.json not found: $path"
    }
    $plan = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    Write-CGOutput -Value $plan -AsJson:$AsJson
}

function Get-CGInvestigationFrontier {
    [CmdletBinding()]
    param([switch]$AsJson)

    $current = Get-CGCurrentPlan
    $referenceRoot = Join-Path $script:RepositoryRoot 'agent-registry\reasoning\reference_cases'
    $matches = @()

    foreach ($file in Get-ChildItem -LiteralPath $referenceRoot -Filter '*.json' -File -Recurse) {
        try {
            $candidate = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
            if ([string]$candidate.architecture_id -ceq [string]$current.current_architecture_id) {
                $matches += [pscustomobject]@{ path = $file.FullName; model = $candidate }
            }
        } catch {
            continue
        }
    }

    if ($matches.Count -ne 1) {
        throw "Current architecture id must resolve to exactly one reference case. Id='$($current.current_architecture_id)' Matches=$($matches.Count)."
    }

    $architecture = $matches[0].model
    $activeHypotheses = @(
        $architecture.hypotheses | Where-Object {
            [string]$_.investigation_state -in @('ACTIVE','ELIGIBLE')
        }
    )

    $result = [pscustomobject][ordered]@{
        schema_version = 1
        capability_id = 'cg.frontier.read'
        result = 'PASS'
        source_authority = 'GITHUB_VERSIONED_PROJECT_STATE'
        current_plan = $current
        architecture_id = $architecture.architecture_id
        architecture_path = $matches[0].path
        next_tests = @($architecture.next_tests)
        active_or_eligible_hypotheses = $activeHypotheses
        mechanical_acceptance_granted = $false
        write_authority = 'NONE'
    }

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Invoke-CGRegisteredVerifier {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$CapabilityId,
        [string[]]$ArgumentList = @(),
        [switch]$AsJson
    )

    $capability = @(Get-CGCapabilityCatalog | Where-Object { [string]$_.id -ceq $CapabilityId })
    if ($capability.Count -ne 1) { throw "Registered verifier capability not found: $CapabilityId" }
    $capability = $capability[0]

    if ([string]$capability.status -cne 'IMPLEMENTED' -or [string]$capability.execution_kind -cne 'registered_verifier') {
        throw "Capability '$CapabilityId' is not an implemented registered verifier."
    }
    if ([string]$capability.write_authority -cne 'NONE') {
        throw "Registered verifier '$CapabilityId' is not read-only."
    }

    $relativePath = [string]$capability.verifier_path
    if ([string]::IsNullOrWhiteSpace($relativePath)) { throw "Verifier path is missing for '$CapabilityId'." }
    if ([IO.Path]::IsPathRooted($relativePath)) { throw 'Registered verifier path must be repository-relative.' }

    $fullPath = [IO.Path]::GetFullPath((Join-Path $script:RepositoryRoot $relativePath))
    $repoPrefix = [IO.Path]::GetFullPath($script:RepositoryRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($repoPrefix,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Registered verifier escaped the repository root.'
    }
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) { throw "Registered verifier not found: $fullPath" }
    if ([IO.Path]::GetFileName($fullPath) -notlike 'Verify-*.ps1') { throw 'Registered verifier filename is outside the reviewed Verify-*.ps1 surface.' }

    $text = (& $fullPath @ArgumentList | Out-String).Trim()
    $result = [pscustomobject][ordered]@{
        schema_version = 1
        capability_id = $CapabilityId
        result = 'EXECUTED'
        verifier_path = $relativePath
        output = $text
        mechanical_acceptance_granted = $false
        write_authority = 'NONE'
    }
    Write-CGOutput -Value $result -AsJson:$AsJson
}

Export-ModuleMember -Function @(
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
