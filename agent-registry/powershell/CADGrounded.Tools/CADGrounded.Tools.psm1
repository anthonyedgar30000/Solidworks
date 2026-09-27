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

    if ($Arguments.Count -eq 1 -and $Arguments[0] -ceq 'status') {
        return Invoke-CGStatusProbe
    }

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

function Invoke-CGStatusProcess {
    param([Parameter(Mandatory=$true)][int]$TimeoutMilliseconds)

    Assert-CGWorkerAvailable
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $script:WorkerExe
    $startInfo.Arguments = 'status'
    $startInfo.WorkingDirectory = $script:WorkerRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
        # Drain both streams while waiting so a full pipe cannot block exit.
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            # Kill only the short-lived read-only worker, never SOLIDWORKS.
            # Do not retry if the old worker cannot be confirmed terminated.
            try { $process.Kill() }
            catch { throw "STALE_STATE: timed-out status worker could not be terminated: $($_.Exception.Message)" }
            if (-not $process.WaitForExit(5000)) {
                throw 'STALE_STATE: timed-out status worker is still running; retry blocked.'
            }
            return [pscustomobject]@{
                outcome = 'TIMEOUT_TERMINATED'
                process_id = $process.Id
                exit_code = $null
                stdout = $null
                stderr = $null
            }
        }
        return [pscustomobject]@{
            outcome = 'EXITED'
            process_id = $process.Id
            exit_code = $process.ExitCode
            stdout = $stdoutTask.GetAwaiter().GetResult()
            stderr = $stderrTask.GetAwaiter().GetResult()
        }
    }
    finally {
        $process.Dispose()
    }
}

function Invoke-CGStatusProbe {
    param([ValidateRange(1000,60000)][int]$TimeoutMilliseconds = 15000)

    for ($attempt = 1; $attempt -le 2; $attempt++) {
        $run = Invoke-CGStatusProcess -TimeoutMilliseconds $TimeoutMilliseconds
        if ([string]$run.outcome -ceq 'TIMEOUT_TERMINATED') {
            Write-Verbose "sw.status attempt $attempt timed out; worker PID $($run.process_id) terminated."
            if ($attempt -eq 2) {
                throw 'STALE_STATE: sw.status timed out twice; no current CAD identity established.'
            }
            continue
        }
        if ([string]$run.outcome -cne 'EXITED') {
            throw "STALE_STATE: sw.status worker outcome '$($run.outcome)' is not a completed read; retry blocked."
        }
        if ([string]::IsNullOrWhiteSpace([string]$run.stdout)) {
            throw 'STALE_STATE: sw.status returned no JSON; retry blocked.'
        }
        try { $status = [string]$run.stdout | ConvertFrom-Json -ErrorAction Stop }
        catch { throw "STALE_STATE: sw.status returned invalid JSON; retry blocked: $($_.Exception.Message)" }
        if ($null -eq $status -or $status -isnot [pscustomobject] -or
            -not (@($status.PSObject.Properties.Name) -contains 'ok')) {
            throw 'STALE_STATE: sw.status returned an invalid envelope; retry blocked.'
        }
        if ([int]$run.exit_code -ne 0 -or -not [bool]$status.ok) {
            $code = if ((@($status.PSObject.Properties.Name) -contains 'error') -and
                $null -ne $status.error -and
                (@($status.error.PSObject.Properties.Name) -contains 'type')) { [string]$status.error.type } else { 'worker_failure' }
            throw "STALE_STATE: sw.status failed with '$code' (exit $($run.exit_code)); retry blocked."
        }
        if (-not (@($status.PSObject.Properties.Name) -contains 'command_id') -or
            -not (@($status.PSObject.Properties.Name) -contains 'data') -or
            $null -eq $status.data -or
            -not (@($status.data.PSObject.Properties.Name) -contains 'document') -or
            -not (@($status.data.PSObject.Properties.Name) -contains 'solidworks_process_id') -or
            -not (@($status.data.PSObject.Properties.Name) -contains 'write_authority') -or
            -not (@($status.PSObject.Properties.Name) -contains 'source_classification') -or
            $null -eq $status.data.document) {
            throw 'STALE_STATE: sw.status lacks an exact active document or SOLIDWORKS process identity; retry blocked.'
        }
        $documentFields = @($status.data.document.PSObject.Properties.Name)
        if (-not ($documentFields -contains 'title') -or -not ($documentFields -contains 'path') -or
            -not ($documentFields -contains 'active_configuration')) {
            throw 'STALE_STATE: sw.status omitted a required document identity field; retry blocked.'
        }
        if ([string]$status.command_id -cne 'sw.status' -or $null -eq $status.data -or $null -eq $status.data.document -or
            [string]::IsNullOrWhiteSpace([string]$status.data.document.title) -or
            [string]::IsNullOrWhiteSpace([string]$status.data.document.path) -or
            [string]::IsNullOrWhiteSpace([string]$status.data.document.active_configuration) -or
            [string]::IsNullOrWhiteSpace([string]$status.data.solidworks_process_id)) {
            throw 'STALE_STATE: sw.status lacks an exact active document, configuration, or SOLIDWORKS process identity; retry blocked.'
        }
        if ([string]$status.data.write_authority -cne 'NONE' -or
            [string]$status.source_classification -cne 'verified_from_solidworks_api') {
            throw 'STALE_STATE: sw.status returned untrusted authority or source classification; retry blocked.'
        }
        Assert-CGReadOnlyEnvelope -Envelope $status
        $status | Add-Member -NotePropertyName status_probe -NotePropertyValue ([pscustomobject]@{
            outcome = if ($attempt -eq 2) { 'RECOVERED_AFTER_TIMEOUT' } else { 'COMPLETED' }
            attempts = $attempt
            timeout_ms_per_attempt = $TimeoutMilliseconds
            worker_process_id = $run.process_id
        })
        return $status
    }
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

    $propertyNames = @($Envelope.data.PSObject.Properties.Name)
    if ($propertyNames -contains 'write_authority' -and [string]$Envelope.data.write_authority -cne 'NONE') {
        throw "Worker command '$($Envelope.command_id)' did not report write_authority NONE."
    }
    if ($propertyNames -contains 'model_mutation' -and $Envelope.data.model_mutation -ne $false) {
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
            parent_name = if ($row.PSObject.Properties.Name -contains 'parent_name') { $row.parent_name } else { $null }
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
    $fileBefore = Get-CGFileState -Path ([string]$status.data.document.path)
    $statusAfter = Invoke-CGWorkerCli -Arguments @('status')
    Assert-CGReadOnlyEnvelope -Envelope $statusAfter
    Assert-CGExpectedState -StatusEnvelope $statusAfter -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration
    $fileAfter = Get-CGFileState -Path ([string]$statusAfter.data.document.path)

    $identityBefore = Get-CGDocumentState -StatusEnvelope $status
    $identityAfter = Get-CGDocumentState -StatusEnvelope $statusAfter
    if (($identityBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($identityAfter | ConvertTo-Json -Depth 10 -Compress) -or
        ($fileBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($fileAfter | ConvertTo-Json -Depth 10 -Compress)) {
        throw 'STALE_STATE: active document/process/configuration or assembly file changed during status readback.'
    }

    $result = New-CGEnvelope -CapabilityId 'cg.state.read' -Result 'PASS' -Data ([ordered]@{
        worker_version = $statusAfter.data.worker_version
        solidworks_process_id = $statusAfter.data.solidworks_process_id
        document = $statusAfter.data.document
        file_state = $fileAfter
        status_probes = @($status.status_probe,$statusAfter.status_probe)
    }) -Establishes @(
        'exact active SOLIDWORKS document identity at this read',
        'active configuration at this read',
        'stable assembly file SHA-256 across status readback',
        'worker read-only authority state'
    ) -DoesNotEstablish @(
        'that an unsaved in-memory SOLIDWORKS model matches the on-disk assembly SHA-256',
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

function Get-CGRequiredBottleDOF {
    [CmdletBinding()]
    param(
        [string]$BottleName2 = 'BENCH_BOTTLE_D48_H180-2',
        [string]$ConveyorName2 = 'BENCH_CONVEYOR_L900_W82_H950-1',
        [string]$ExpectedDocumentTitle = 'IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE',
        [string]$ExpectedDocumentPath = 'C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM',
        [string]$ExpectedConfiguration = 'V43_WRAP',
        [switch]$AsJson
    )

    $requirementsPath = Join-Path $script:RepositoryRoot 'agent-registry\reasoning\requirements\function-first-bottle-dof.v1.json'
    if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
        throw "Function-first bottle DOF requirements file not found: $requirementsPath"
    }
    $requirements = Get-Content -LiteralPath $requirementsPath -Raw | ConvertFrom-Json

    $status = Invoke-CGWorkerCli -Arguments @('status')
    Assert-CGReadOnlyEnvelope -Envelope $status
    Assert-CGExpectedState -StatusEnvelope $status -ExpectedDocumentTitle $ExpectedDocumentTitle -ExpectedDocumentPath $ExpectedDocumentPath -ExpectedConfiguration $ExpectedConfiguration

    $components = Invoke-CGWorkerCli -Arguments @('components','--all')
    Assert-CGReadOnlyEnvelope -Envelope $components
    $bottle = Get-CGExactComponentFromEnvelope -ComponentsEnvelope $components -Name2 $BottleName2
    $conveyor = Get-CGExactComponentFromEnvelope -ComponentsEnvelope $components -Name2 $ConveyorName2

    if ([bool]$bottle.suppressed) { throw "Bottle component '$BottleName2' is suppressed." }
    if ([bool]$conveyor.suppressed) { throw "Conveyor component '$ConveyorName2' is suppressed." }

    $result = [pscustomobject][ordered]@{
        schema_version = 1
        capability_id = 'cg.product.required-dof'
        result = 'PASS'
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        source_authority = 'DETERMINISTIC_CALCULATION'
        source_classification = 'function_first_requirement_derivation_v1'
        live_binding = [ordered]@{
            document = Get-CGDocumentState -StatusEnvelope $status
            bottle = [ordered]@{
                name2 = [string]$bottle.name2
                path = [string]$bottle.path
                fixed_component = $bottle.fixed_component
                fixed = $bottle.fixed
                suppressed = $bottle.suppressed
                rotation9 = @($bottle.rotation9)
                translation_mm = @($bottle.translation_mm)
            }
            conveyor = [ordered]@{
                name2 = [string]$conveyor.name2
                path = [string]$conveyor.path
                fixed_component = $conveyor.fixed_component
                fixed = $conveyor.fixed
                suppressed = $conveyor.suppressed
                rotation9 = @($conveyor.rotation9)
                translation_mm = @($conveyor.translation_mm)
            }
        }
        requirement_model_id = [string]$requirements.requirement_model_id
        functional_axes = $requirements.functional_axes
        state_requirements = @($requirements.state_requirements)
        cross_state_invariants = @($requirements.cross_state_invariants)
        establishes = @(
            'mechanism-neutral required or intentionally permitted bottle rigid-body DOF behavior by scoped operating state',
            'fresh exact live identity binding for the benchmark bottle and conveyor at this read',
            'explicit unresolved DOF choices where the functional requirement does not force a mechanism behavior'
        )
        does_not_establish = @($requirements.explicitly_not_established)
        ambiguity_bucket = 'MEASUREMENT_REQUIRED'
        mechanical_acceptance_granted = $false
        model_mutation = $false
        write_authority = 'NONE'
    }

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Get-CGBottleContactConstraintMap {
    [CmdletBinding()]
    param(
        [string]$EvidencePath = 'agent-registry\reasoning\runtime\function-first-bottle-contact-normal-map-evidence-20260927T082707281Z.json',
        [double]$Tolerance = 1e-6,
        [switch]$EvidenceOnly,
        [switch]$AsJson
    )

    if ($Tolerance -le 0) { throw 'Tolerance must be greater than zero.' }

    if ([IO.Path]::IsPathRooted($EvidencePath)) {
        $resolvedEvidencePath = [IO.Path]::GetFullPath($EvidencePath)
    } else {
        $resolvedEvidencePath = [IO.Path]::GetFullPath((Join-Path $script:RepositoryRoot $EvidencePath))
    }

    $repoPrefix = [IO.Path]::GetFullPath($script:RepositoryRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedEvidencePath.StartsWith($repoPrefix,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Constraint-map evidence path escaped the repository root.'
    }
    if (-not (Test-Path -LiteralPath $resolvedEvidencePath -PathType Leaf)) {
        throw "Constraint-map evidence file not found: $resolvedEvidencePath"
    }

    $evidence = Get-Content -LiteralPath $resolvedEvidencePath -Raw | ConvertFrom-Json
    if ([string]$evidence.evidence_id -cne 'E.FUNCTION_FIRST.BOTTLE_CONTACT_NORMAL_MAP.20260927T082707281Z') {
        throw "Unexpected contact-normal evidence id '$($evidence.evidence_id)'."
    }
    if ([string]$evidence.evidence_state -cne 'VERIFIED') {
        throw "Contact-normal evidence is not VERIFIED. Actual='$($evidence.evidence_state)'."
    }
    if ([string]$evidence.source_authority -cne 'SOLIDWORKS_LIVE_STATE') {
        throw "Unexpected source authority '$($evidence.source_authority)'."
    }

    $document = $evidence.payload.document
    $freshness = [ordered]@{
        mode = if ($EvidenceOnly) { 'ADMITTED_SNAPSHOT_ONLY' } else { 'LIVE_ASSEMBLY_FILE_MATCH_REQUIRED' }
        live_match = $null
        observed_file_sha256 = $null
        expected_file_sha256 = [string]$evidence.payload.assembly_file_sha256_after
    }

    if (-not $EvidenceOnly) {
        $status = Invoke-CGWorkerCli -Arguments @('status')
        Assert-CGReadOnlyEnvelope -Envelope $status
        Assert-CGExpectedState -StatusEnvelope $status -ExpectedDocumentTitle ([string]$document.title) -ExpectedDocumentPath ([string]$document.path) -ExpectedConfiguration ([string]$document.active_configuration_exact)

        $fileState = Get-CGFileState -Path ([string]$document.path)
        $freshness.observed_file_sha256 = [string]$fileState.sha256
        if ([string]$fileState.sha256 -cne [string]$evidence.payload.assembly_file_sha256_after) {
            throw "STALE_STATE: active assembly file hash does not match admitted contact-normal evidence. Expected='$($evidence.payload.assembly_file_sha256_after)' Actual='$($fileState.sha256)'."
        }
        $freshness.live_match = $true
    }

    function Get-Cross2Local {
        param([double[]]$A,[double[]]$B)
        return ([double]$A[0] * [double]$B[1]) - ([double]$A[1] * [double]$B[0])
    }

    function Get-Dot3Local {
        param([double[]]$A,[double[]]$B)
        return ([double]$A[0] * [double]$B[0]) + ([double]$A[1] * [double]$B[1]) + ([double]$A[2] * [double]$B[2])
    }

    function Get-Normalized2Local {
        param([double[]]$A)
        $mag = [Math]::Sqrt(([double]$A[0] * [double]$A[0]) + ([double]$A[1] * [double]$A[1]))
        if ($mag -le $Tolerance) { throw 'Cannot normalize near-zero in-plane vector.' }
        $nx = ([double]$A[0]) / ([double]$mag)
        $ny = ([double]$A[1]) / ([double]$mag)
        return @($nx,$ny)
    }

    function Get-BestOpposedCandidateLocal {
        param([double[]]$BottleNormal,$Candidates,[string]$PairId)
        $best = $null
        $bestDot = [double]::PositiveInfinity
        foreach ($candidate in @($Candidates)) {
            $n = @($candidate.unit_normal_assembly | ForEach-Object { [double]$_ })
            if ($n.Count -ne 3) { continue }
            $dot = Get-Dot3Local -A $BottleNormal -B $n
            if ($dot -lt $bestDot) {
                $bestDot = $dot
                $best = $candidate
            }
        }
        if ($null -eq $best) { throw "No opposing face-normal candidate found for '$PairId'." }
        if ($bestDot -gt -0.999) {
            throw "Best opposing face-normal candidate for '$PairId' is not antiparallel enough. dot=$bestDot"
        }
        return [pscustomobject]@{ candidate = $best; dot = $bestDot }
    }

    $pairs = @($evidence.payload.pairs)
    if ($pairs.Count -ne 4) { throw "Expected exactly four touching-pair observations. Actual=$($pairs.Count)." }

    $lateral = @()
    $axial = @()

    foreach ($pair in $pairs) {
        $bottleCandidates = @($pair.bottle_face_candidates)
        if ($bottleCandidates.Count -ne 1) {
            throw "Expected exactly one bottle-side face-normal candidate for '$($pair.pair_id)'. Actual=$($bottleCandidates.Count)."
        }

        $bn = @($bottleCandidates[0].unit_normal_assembly | ForEach-Object { [double]$_ })
        if ($bn.Count -ne 3) { throw "Bottle normal for '$($pair.pair_id)' is not 3D." }

        $opposed = Get-BestOpposedCandidateLocal -BottleNormal $bn -Candidates $pair.other_face_candidates -PairId ([string]$pair.pair_id)
        $on = @($opposed.candidate.unit_normal_assembly | ForEach-Object { [double]$_ })
        $p = @($pair.contact_point_mm | ForEach-Object { [double]$_ })

        $row = [pscustomobject][ordered]@{
            pair_id = [string]$pair.pair_id
            component_b = [string]$pair.component_b
            role_candidate = [string]$pair.role_candidate
            contact_point_mm = $p
            bottle_normal_assembly = $bn
            selected_opposing_normal_assembly = $on
            opposed_dot = [double]$opposed.dot
            minimum_distance_mm = [double]$pair.minimum_distance_mm
            intersection_volume_mm3 = [double]$pair.intersection_volume_mm3
        }

        if ([Math]::Abs([double]$bn[2]) -le $Tolerance) {
            $lateral += $row
        } else {
            $axial += $row
        }
    }

    if ($lateral.Count -ne 3) { throw "Expected exactly three lateral bottle contacts. Actual=$($lateral.Count)." }
    if ($axial.Count -ne 1) { throw "Expected exactly one non-lateral bottle contact. Actual=$($axial.Count)." }

    $lateralRows = @()
    foreach ($row in $lateral) {
        $n2 = Get-Normalized2Local -A @([double]$row.bottle_normal_assembly[0],[double]$row.bottle_normal_assembly[1])
        $reaction = @(-[double]$n2[0],-[double]$n2[1])
        $lateralRows += [pscustomobject][ordered]@{
            pair_id = $row.pair_id
            component_b = $row.component_b
            role_candidate = $row.role_candidate
            contact_point_xy_mm = @([double]$row.contact_point_mm[0],[double]$row.contact_point_mm[1])
            contact_point_z_mm = [double]$row.contact_point_mm[2]
            bottle_normal_xy = $n2
            compressive_reaction_direction_xy = $reaction
            opposed_dot = $row.opposed_dot
        }
    }

    $intersections = @()
    for ($i = 0; $i -lt $lateralRows.Count; $i++) {
        for ($j = $i + 1; $j -lt $lateralRows.Count; $j++) {
            $a = $lateralRows[$i]
            $b = $lateralRows[$j]
            $pa = @([double]$a.contact_point_xy_mm[0],[double]$a.contact_point_xy_mm[1])
            $pb = @([double]$b.contact_point_xy_mm[0],[double]$b.contact_point_xy_mm[1])
            $na = @([double]$a.bottle_normal_xy[0],[double]$a.bottle_normal_xy[1])
            $nb = @([double]$b.bottle_normal_xy[0],[double]$b.bottle_normal_xy[1])
            $den = Get-Cross2Local -A $na -B $nb
            if ([Math]::Abs($den) -le $Tolerance) {
                throw "Lateral normal lines '$($a.pair_id)' and '$($b.pair_id)' are parallel/degenerate."
            }
            $delta = @(([double]$pb[0]-[double]$pa[0]),([double]$pb[1]-[double]$pa[1]))
            $tLine = (Get-Cross2Local -A $delta -B $nb) / $den
            $point = @(([double]$pa[0] + $tLine * [double]$na[0]),([double]$pa[1] + $tLine * [double]$na[1]))
            $intersections += [pscustomobject][ordered]@{
                pair_a = $a.pair_id
                pair_b = $b.pair_id
                point_xy_mm = $point
            }
        }
    }

    $sumCx = 0.0
    $sumCy = 0.0
    foreach ($item in $intersections) {
        $sumCx += [double]$item.point_xy_mm[0]
        $sumCy += [double]$item.point_xy_mm[1]
    }
    $intersectionCount = [double]$intersections.Count
    $commonX = ([double]$sumCx) / $intersectionCount
    $commonY = ([double]$sumCy) / $intersectionCount
    $commonPoint = @($commonX,$commonY)

    $maxIntersectionSpread = 0.0
    foreach ($item in $intersections) {
        $dx = [double]$item.point_xy_mm[0] - [double]$commonPoint[0]
        $dy = [double]$item.point_xy_mm[1] - [double]$commonPoint[1]
        $d = [Math]::Sqrt($dx*$dx + $dy*$dy)
        if ($d -gt $maxIntersectionSpread) { $maxIntersectionSpread = $d }
    }

    $maxLineResidual = 0.0
    $radii = @()
    $torques = @()
    foreach ($row in $lateralRows) {
        $p = @([double]$row.contact_point_xy_mm[0],[double]$row.contact_point_xy_mm[1])
        $n = @([double]$row.bottle_normal_xy[0],[double]$row.bottle_normal_xy[1])
        $reaction = @([double]$row.compressive_reaction_direction_xy[0],[double]$row.compressive_reaction_direction_xy[1])
        $delta = @(([double]$commonPoint[0]-[double]$p[0]),([double]$commonPoint[1]-[double]$p[1]))
        $lineResidual = [Math]::Abs((Get-Cross2Local -A $n -B $delta))
        if ($lineResidual -gt $maxLineResidual) { $maxLineResidual = $lineResidual }

        $rx = [double]$p[0]-[double]$commonPoint[0]
        $ry = [double]$p[1]-[double]$commonPoint[1]
        $radii += [Math]::Sqrt($rx*$rx + $ry*$ry)
        $torques += $rx * [double]$reaction[1] - $ry * [double]$reaction[0]
    }

    $reaction0 = @([double]$lateralRows[0].compressive_reaction_direction_xy[0],[double]$lateralRows[0].compressive_reaction_direction_xy[1])
    $reaction1 = @([double]$lateralRows[1].compressive_reaction_direction_xy[0],[double]$lateralRows[1].compressive_reaction_direction_xy[1])
    $reaction2 = @([double]$lateralRows[2].compressive_reaction_direction_xy[0],[double]$lateralRows[2].compressive_reaction_direction_xy[1])

    $coefficients = @(
        (Get-Cross2Local -A $reaction1 -B $reaction2),
        (Get-Cross2Local -A $reaction2 -B $reaction0),
        (Get-Cross2Local -A $reaction0 -B $reaction1)
    )
    $nonPositiveCount = @($coefficients | Where-Object { [double]$_ -le $Tolerance }).Count
    $nonNegativeCount = @($coefficients | Where-Object { [double]$_ -ge -$Tolerance }).Count
    $allPositive = ($nonPositiveCount -eq 0)
    $allNegative = ($nonNegativeCount -eq 0)
    if ($allNegative) {
        $coefficients = @($coefficients | ForEach-Object { -[double]$_ })
        $allPositive = $true
    }

    $positiveSpan = $allPositive
    $normalizedCoefficients = @()
    $equilibriumResidual = @($null,$null)
    if ($positiveSpan) {
        $minCoefficient = ($coefficients | Measure-Object -Minimum).Minimum
        $normalizedCoefficients = @($coefficients | ForEach-Object {
            $numerator = [double]$_
            $denominator = [double]$minCoefficient
            $numerator / $denominator
        })
        $sumX = 0.0
        $sumY = 0.0
        for ($i = 0; $i -lt 3; $i++) {
            $sumX += [double]$normalizedCoefficients[$i] * [double]$lateralRows[$i].compressive_reaction_direction_xy[0]
            $sumY += [double]$normalizedCoefficients[$i] * [double]$lateralRows[$i].compressive_reaction_direction_xy[1]
        }
        $equilibriumResidual = @($sumX,$sumY)
    }

    $radiusMin = ($radii | Measure-Object -Minimum).Minimum
    $radiusMax = ($radii | Measure-Object -Maximum).Maximum
    $maxAbsTorque = ($torques | ForEach-Object { [Math]::Abs([double]$_) } | Measure-Object -Maximum).Maximum

    $axialRow = $axial[0]
    $axialBottleNormal = @($axialRow.bottle_normal_assembly | ForEach-Object { [double]$_ })
    $axialOtherNormal = @($axialRow.selected_opposing_normal_assembly | ForEach-Object { [double]$_ })

    $data = [ordered]@{
        evidence_id = [string]$evidence.evidence_id
        evidence_path = $resolvedEvidencePath
        evidence_sha256 = (Get-FileHash -LiteralPath $resolvedEvidencePath -Algorithm SHA256).Hash.ToLowerInvariant()
        freshness = $freshness
        lateral_contacts = $lateralRows
        pairwise_normal_line_intersections = $intersections
        common_axis_candidate = [ordered]@{
            point_xy_mm = $commonPoint
            direction_assembly = @(0.0,0.0,1.0)
            derivation = 'perpendicular to the plane of three concurrent lateral bottle-side contact normals'
            max_pairwise_intersection_spread_mm = $maxIntersectionSpread
            max_normal_line_residual_mm = $maxLineResidual
        }
        radial_geometry = [ordered]@{
            radii_mm = $radii
            min_radius_mm = [double]$radiusMin
            max_radius_mm = [double]$radiusMax
            radius_spread_mm = [double]$radiusMax - [double]$radiusMin
        }
        lateral_normal_closure = [ordered]@{
            state = if ($positiveSpan) { 'SUPPORTED_CURRENT_POSE_FRICTIONLESS_NORMAL_MODEL' } else { 'NOT_SUPPORTED' }
            positive_span = $positiveSpan
            normalized_positive_equilibrium_coefficients = $normalizedCoefficients
            equilibrium_residual_xy = $equilibriumResidual
            interpretation = 'Positive compressive normal reactions can balance first-order translation directions in the assembly XY plane at this recorded pose.'
        }
        normal_reaction_moment_about_common_axis = [ordered]@{
            torque_per_unit_reaction_mm = $torques
            max_abs_torque_per_unit_reaction_mm = [double]$maxAbsTorque
            state = if ([double]$maxAbsTorque -le 1e-6) { 'APPROX_ZERO_CURRENT_POSE' } else { 'NONZERO' }
            interpretation = 'The selected frictionless normal reaction lines pass through the common axis candidate, so normal reactions alone do not resist rotation about that axis.'
        }
        non_lateral_contact = [ordered]@{
            pair_id = [string]$axialRow.pair_id
            bottle_normal_assembly = $axialBottleNormal
            selected_opposing_normal_assembly = $axialOtherNormal
            contact_point_mm = @($axialRow.contact_point_mm)
            interpretation = 'An opposed assembly-Z contact direction is observed. Gravity/up semantics and load capacity remain unresolved.'
        }
        functional_projection = [ordered]@{
            assembly_xy_translation = if ($positiveSpan) { 'NORMAL_CLOSURE_SUPPORTED_CURRENT_POSE' } else { 'UNRESOLVED' }
            rotation_about_common_axis = if ([double]$maxAbsTorque -le 1e-6) { 'NOT_RESTRAINED_BY_FRICTIONLESS_NORMAL_REACTIONS_CURRENT_POSE' } else { 'NORMAL_REACTION_MOMENT_OBSERVED' }
            assembly_z_contact_direction = 'OPPOSED_NORMAL_CONTACT_OBSERVED'
            tilt_restraint = 'UNRESOLVED'
            frictional_wrap_torque = 'UNRESOLVED'
            preload_and_contact_maintenance = 'UNRESOLVED'
            interval_wide_validity = 'UNRESOLVED_POINT_POSE_ONLY'
        }
    }

    $result = New-CGEnvelope -CapabilityId 'cg.product.contact-constraint-map' -Result 'PASS' -Data $data -SourceAuthority 'DETERMINISTIC_CALCULATION' -SourceClassification 'measured_calculated_from_admitted_solidworks_observation' -AmbiguityBucket 'KINEMATIC_STATE_UNRESOLVED' -Establishes @(
        'the three selected lateral bottle-side normal lines are concurrent at the recorded pose',
        'the three compressive lateral normal directions positively span the assembly XY plane at the recorded pose',
        'frictionless normal reactions about the derived common-axis candidate have approximately zero moment at the recorded pose',
        'one opposed assembly-Z contact-normal pair is observed for the bottle-to-conveyor contact'
    ) -DoesNotEstablish @(
        'that the derived common-axis candidate is yet authoritatively bound to the functional wrap axis',
        'gravity/up-axis semantics or vertical load capacity',
        'tilt restraint or full six-DOF restraint rank',
        'friction, traction, preload, compliance, pressure, force, stiffness, or reaction capacity',
        'that any current V43 component is required in the final mechanism',
        'interval-wide contact maintenance or reachable motion',
        'mechanism selection or mechanical acceptance'
    )

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Get-CGBottleContactWrenchRank {
    [CmdletBinding()]
    param(
        [double]$Tolerance = 1e-9,
        [switch]$EvidenceOnly,
        [switch]$AsJson
    )

    if ($Tolerance -le 0) { throw 'Tolerance must be greater than zero.' }

    $constraint = if ($EvidenceOnly) {
        Get-CGBottleContactConstraintMap -EvidenceOnly
    } else {
        Get-CGBottleContactConstraintMap
    }

    if ([string]$constraint.result -cne 'PASS') {
        throw "Bottle contact constraint map did not PASS. Actual='$($constraint.result)'."
    }

    $common = @($constraint.data.common_axis_candidate.point_xy_mm | ForEach-Object { [double]$_ })
    $axialPoint = @($constraint.data.non_lateral_contact.contact_point_mm | ForEach-Object { [double]$_ })
    if ($common.Count -ne 2 -or $axialPoint.Count -ne 3) {
        throw 'Constraint-map common-axis or axial contact point shape is invalid.'
    }

    $referencePoint = @([double]$common[0],[double]$common[1],[double]$axialPoint[2])

    function Get-Cross3Local {
        param([double[]]$A,[double[]]$B)
        $ax = [double]$A[0]
        $ay = [double]$A[1]
        $az = [double]$A[2]
        $bx = [double]$B[0]
        $by = [double]$B[1]
        $bz = [double]$B[2]
        $cx = ($ay * $bz) - ($az * $by)
        $cy = ($az * $bx) - ($ax * $bz)
        $cz = ($ax * $by) - ($ay * $bx)
        return @($cx,$cy,$cz)
    }

    function New-ConstraintRowLocal {
        param(
            [string]$PairId,
            [double[]]$Point,
            [double[]]$Reaction
        )

        if ($Point.Count -ne 3 -or $Reaction.Count -ne 3) {
            throw "Pair '$PairId' point/reaction must be 3D."
        }

        $px = [double]$Point[0]
        $py = [double]$Point[1]
        $pz = [double]$Point[2]
        $rx0 = [double]$referencePoint[0]
        $ry0 = [double]$referencePoint[1]
        $rz0 = [double]$referencePoint[2]
        $armX = $px - $rx0
        $armY = $py - $ry0
        $armZ = $pz - $rz0
        $arm = @($armX,$armY,$armZ)
        $moment = Get-Cross3Local -A $arm -B $Reaction
        return [pscustomobject][ordered]@{
            pair_id = $PairId
            contact_point_mm = @($Point)
            compressive_normal_direction = @($Reaction)
            moment_arm_mm = @($arm)
            moment_per_unit_normal_mm = @($moment)
            row = @(
                [double]$Reaction[0],
                [double]$Reaction[1],
                [double]$Reaction[2],
                [double]$moment[0],
                [double]$moment[1],
                [double]$moment[2]
            )
        }
    }

    $rows = @()

    $axialReaction = @($constraint.data.non_lateral_contact.selected_opposing_normal_assembly | ForEach-Object { [double]$_ })
    $rows += New-ConstraintRowLocal -PairId ([string]$constraint.data.non_lateral_contact.pair_id) -Point $axialPoint -Reaction $axialReaction

    foreach ($lateral in @($constraint.data.lateral_contacts)) {
        $point = @(
            [double]$lateral.contact_point_xy_mm[0],
            [double]$lateral.contact_point_xy_mm[1],
            [double]$lateral.contact_point_z_mm
        )
        $reaction = @(
            [double]$lateral.compressive_reaction_direction_xy[0],
            [double]$lateral.compressive_reaction_direction_xy[1],
            0.0
        )
        $rows += New-ConstraintRowLocal -PairId ([string]$lateral.pair_id) -Point $point -Reaction $reaction
    }

    if ($rows.Count -ne 4) {
        throw "Expected four maintained point-normal constraints. Actual=$($rows.Count)."
    }

    $rowCount = $rows.Count
    $columnCount = 6
    $matrix = New-Object 'double[,]' $rowCount,$columnCount
    for ($r = 0; $r -lt $rowCount; $r++) {
        for ($col = 0; $col -lt $columnCount; $col++) {
            $matrix[$r,$col] = [double]($rows[$r].row[$col])
        }
    }

    $rref = New-Object 'double[,]' $rowCount,$columnCount
    for ($r = 0; $r -lt $rowCount; $r++) {
        for ($col = 0; $col -lt $columnCount; $col++) {
            $rref[$r,$col] = $matrix[$r,$col]
        }
    }

    $pivotColumns = @()
    $pivotRow = 0
    for ($col = 0; $col -lt $columnCount -and $pivotRow -lt $rowCount; $col++) {
        $bestRow = -1
        $bestAbs = 0.0
        for ($r = $pivotRow; $r -lt $rowCount; $r++) {
            $candidateAbs = [Math]::Abs([double]($rref[$r,$col]))
            if ($candidateAbs -gt $bestAbs) {
                $bestAbs = $candidateAbs
                $bestRow = $r
            }
        }

        if ($bestRow -lt 0 -or $bestAbs -le $Tolerance) {
            continue
        }

        if ($bestRow -ne $pivotRow) {
            for ($j = 0; $j -lt $columnCount; $j++) {
                $tmp = [double]($rref[$pivotRow,$j])
                $rref[$pivotRow,$j] = [double]($rref[$bestRow,$j])
                $rref[$bestRow,$j] = $tmp
            }
        }

        $pivotValue = [double]($rref[$pivotRow,$col])
        for ($j = 0; $j -lt $columnCount; $j++) {
            $rref[$pivotRow,$j] = [double]($rref[$pivotRow,$j]) / $pivotValue
        }

        for ($r = 0; $r -lt $rowCount; $r++) {
            if ($r -eq $pivotRow) { continue }
            $factor = [double]($rref[$r,$col])
            if ([Math]::Abs($factor) -le $Tolerance) { continue }
            for ($j = 0; $j -lt $columnCount; $j++) {
                $currentValue = [double]($rref[$r,$j])
                $pivotValueForColumn = [double]($rref[$pivotRow,$j])
                $rref[$r,$j] = $currentValue - ($factor * $pivotValueForColumn)
            }
        }

        $pivotColumns += $col
        $pivotRow++
    }

    $rank = $pivotColumns.Count
    $nullity = $columnCount - $rank
    $freeColumns = @(0..($columnCount-1) | Where-Object { $pivotColumns -notcontains $_ })

    $nullspaceBasis = @()
    foreach ($free in $freeColumns) {
        $vector = New-Object double[] $columnCount
        $vector[$free] = 1.0

        for ($i = 0; $i -lt $pivotColumns.Count; $i++) {
            $pivotCol = [int]$pivotColumns[$i]
            $vector[$pivotCol] = -[double]($rref[$i,$free])
        }

        $nullspaceBasis += ,@($vector)
    }

    $wrapTwist = @(0.0,0.0,0.0,0.0,0.0,1.0)
    $wrapResiduals = @()
    foreach ($row in $rows) {
        $sum = 0.0
        for ($j = 0; $j -lt $columnCount; $j++) {
            $rowValue = [double]$row.row[$j]
            $twistValue = [double]$wrapTwist[$j]
            $sum += $rowValue * $twistValue
        }
        $wrapResiduals += $sum
    }
    $maxWrapResidual = ($wrapResiduals | ForEach-Object { [Math]::Abs([double]$_) } | Measure-Object -Maximum).Maximum
    $wrapRotationIsNullMode = ([double]$maxWrapResidual -le $Tolerance)

    $requiredRankForOnlyWrapRotationFree = 5
    $additionalNullModes = if ($wrapRotationIsNullMode) { [Math]::Max(0,$nullity - 1) } else { $nullity }

    $rrefRows = @()
    for ($r = 0; $r -lt $rowCount; $r++) {
        $rowValues = @()
        for ($col = 0; $col -lt $columnCount; $col++) {
            $value = [double]($rref[$r,$col])
            if ([Math]::Abs($value) -le $Tolerance) { $value = 0.0 }
            $rowValues += $value
        }
        $rrefRows += ,$rowValues
    }

    $data = [ordered]@{
        source_constraint_map = [ordered]@{
            capability_id = [string]$constraint.capability_id
            evidence_id = [string]$constraint.data.evidence_id
            freshness = $constraint.data.freshness
        }
        model = [ordered]@{
            name = 'CURRENT_POSE_MAINTAINED_FRICTIONLESS_POINT_NORMAL_CONSTRAINT_MODEL'
            twist_coordinate_order = @('vx','vy','vz','omega_x','omega_y','omega_z')
            wrench_row_order = @('Fx','Fy','Fz','Mx','My','Mz')
            reference_point_mm = $referencePoint
            note = 'Each touching pair contributes one maintained frictionless point-normal constraint. This is an optimistic linearized point-contact model; real unilateral contact maintenance and finite contact manifolds require separate evidence.'
        }
        constraint_rows = $rows
        matrix_rank = $rank
        nullity = $nullity
        pivot_columns_zero_based = $pivotColumns
        free_columns_zero_based = $freeColumns
        rref = $rrefRows
        nullspace_basis_free_variable_one = $nullspaceBasis
        wrap_axis_rotation_test = [ordered]@{
            twist = $wrapTwist
            residuals = $wrapResiduals
            max_abs_residual = [double]$maxWrapResidual
            is_null_mode = $wrapRotationIsNullMode
        }
        restraint_projection = [ordered]@{
            required_rank_to_leave_only_one_free_twist = $requiredRankForOnlyWrapRotationFree
            observed_rank = $rank
            observed_nullity = $nullity
            additional_independent_null_modes_beyond_common_axis_rotation = $additionalNullModes
            five_dof_restraint_excluding_common_axis_rotation = if ($rank -ge $requiredRankForOnlyWrapRotationFree -and $wrapRotationIsNullMode) { 'SUPPORTED_BY_POINT_NORMAL_RANK_MODEL' } else { 'NOT_SUPPORTED_BY_CURRENT_FOUR_POINT_NORMAL_MODEL' }
            interpretation = if ($rank -lt $requiredRankForOnlyWrapRotationFree) {
                'Even under the optimistic maintained frictionless point-normal model, the four observed contacts do not provide five independent normal constraints. At least one additional independent instantaneous mode remains beyond common-axis rotation.'
            } else {
                'The maintained point-normal rank is sufficient to leave at most one independent twist; additional unilateral/contact-maintenance checks are still required.'
            }
        }
    }

    $result = New-CGEnvelope -CapabilityId 'cg.product.contact-wrench-rank' -Result 'PASS' -Data $data -SourceAuthority 'DETERMINISTIC_CALCULATION' -SourceClassification 'measured_calculated_from_contact_constraint_map' -AmbiguityBucket 'KINEMATIC_STATE_UNRESOLVED' -Establishes @(
        'rank and nullity of the current four-contact maintained frictionless point-normal constraint matrix',
        'whether pure rotation about the derived common axis is a null mode of that matrix',
        'whether the current four point-normal constraints can provide five independent constraint directions while leaving only common-axis rotation free'
    ) -DoesNotEstablish @(
        'finite line/surface contact constraint effects beyond the sampled point normals',
        'unilateral contact maintenance, preload, compliance, or force closure',
        'friction or traction and driven wrap torque',
        'gravity/up semantics or load capacity',
        'interval-wide restraint or reachable-state behavior',
        'that any current V43 component is required in the final mechanism',
        'mechanism selection or mechanical acceptance'
    )

    Write-CGOutput -Value $result -AsJson:$AsJson
}

function Get-CGContactMaintenanceRequirements {
    [CmdletBinding()]
    param([switch]$AsJson)

    $requirementsPath = Join-Path $script:RepositoryRoot 'agent-registry\reasoning\requirements\function-first-contact-maintenance.v1.json'
    $sourceEvidencePath = Join-Path $script:RepositoryRoot 'agent-registry\reasoning\runtime\function-first-contact-maintenance-source-probe-20260927T150842223Z.json'

    if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
        throw "Contact-maintenance requirement model not found: $requirementsPath"
    }
    if (-not (Test-Path -LiteralPath $sourceEvidencePath -PathType Leaf)) {
        throw "Contact-maintenance source-probe evidence not found: $sourceEvidencePath"
    }

    $requirements = Get-Content -LiteralPath $requirementsPath -Raw | ConvertFrom-Json
    $sourceEvidence = Get-Content -LiteralPath $sourceEvidencePath -Raw | ConvertFrom-Json

    if ([string]$requirements.requirement_model_id -cne 'CADGROUNDED.IXOR.CONTACT_MAINTENANCE.V1') {
        throw "Unexpected contact-maintenance requirement model id '$($requirements.requirement_model_id)'."
    }
    if ([string]$sourceEvidence.evidence_id -cne 'E.FUNCTION_FIRST.CONTACT_MAINTENANCE_SOURCE_PROBE.20260927T150842223Z') {
        throw "Unexpected contact-maintenance source-probe evidence id '$($sourceEvidence.evidence_id)'."
    }
    if ([string]$sourceEvidence.evidence_state -cne 'VERIFIED' -or
        [string]$sourceEvidence.source_authority -cne 'SOLIDWORKS_LIVE_STATE') {
        throw 'Contact-maintenance source-probe evidence is not an admitted verified SOLIDWORKS observation.'
    }

    $data = [ordered]@{
        requirement_model_id = [string]$requirements.requirement_model_id
        basis_evidence_ids = @($requirements.basis_evidence_ids)
        scope_states = @($requirements.scope_states)
        transition_scope = @($requirements.transition_scope)
        requirements = @($requirements.requirements)
        unresolved_quantities = @($requirements.unresolved_quantities)
        candidate_selection_status = [string]$requirements.candidate_selection_status
        candidate_family_status = $requirements.candidate_family_status
        source_probe = [ordered]@{
            evidence_id = [string]$sourceEvidence.evidence_id
            validity_state = [string]$sourceEvidence.temporal_scope.validity_state
            component_inventory_count = [int]$sourceEvidence.payload.component_inventory_count
            explicit_name_classification = $sourceEvidence.payload.explicit_name_classification
            tested_targets = @($sourceEvidence.payload.targets | ForEach-Object {
                [ordered]@{
                    name2 = [string]$_.name2
                    fixed_component = $_.fixed_component
                    suppressed = $_.suppressed
                    incident_active_assembly_mate_count = [int]$_.incident_active_assembly_mate_count
                }
            })
        }
    }

    $result = New-CGEnvelope -CapabilityId 'cg.requirements.contact-maintenance' -Result 'PASS' -Data $data -SourceAuthority 'DETERMINISTIC_CALCULATION' -SourceClassification 'function_first_contact_maintenance_requirement_projection_v1' -AmbiguityBucket 'OEM_SOURCE_REQUIRED' -Establishes @(
        'mechanism-neutral contact-maintenance requirements derived from admitted bottle DOF and finite-contact evidence',
        'current V43 fit-check assembly does not bind an exact active-assembly mate chain or explicitly named spring/pneumatic maintenance element among the tested closure candidates',
        'candidate mechanism families remain eligibility classes rather than selected architecture',
        'quantitative force/travel/stiffness/friction values remain explicitly UNKNOWN'
    ) -DoesNotEstablish @(
        'which candidate mechanism family should be selected',
        'closure travel or stroke',
        'preload, force, pressure, stiffness, compliance magnitude, or friction',
        'interval-wide contact maintenance',
        'reaction load capacity',
        'mechanical acceptance'
    )

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
    'Get-CGRequiredBottleDOF',
    'Get-CGBottleContactConstraintMap',
    'Get-CGBottleContactWrenchRank',
    'Get-CGContactMaintenanceRequirements',
    'Get-CGCurrentPlan',
    'Get-CGInvestigationFrontier',
    'Invoke-CGRegisteredVerifier'
)
