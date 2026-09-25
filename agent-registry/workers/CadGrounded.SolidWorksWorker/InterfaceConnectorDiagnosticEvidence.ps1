Set-StrictMode -Version Latest

function Get-OptionalInterfaceConnectorDiagnosticPropertyValue {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Name
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Assert-InterfaceConnectorDiagnosticObservation {
    param(
        [Parameter(Mandatory=$true)]$Envelope,
        [Parameter(Mandatory=$true)][string[]]$ExpectedConnectors
    )

    $envelopeContext = 'interface connector diagnostic envelope'
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'command_id' -Context $envelopeContext) -cne 'sw.diagnose_interface_connectors') {
        throw 'Expected sw.diagnose_interface_connectors envelope.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'source_classification' -Context $envelopeContext) -cne 'verified_from_solidworks_api') {
        throw 'Interface connector diagnostic source_classification must be verified_from_solidworks_api.'
    }

    $data = Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'data' -Context $envelopeContext
    $dataContext = 'interface connector diagnostic data'
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'write_authority' -Context $dataContext) -cne 'NONE') {
        throw 'Interface connector diagnostic write_authority must be NONE.'
    }
    if ((Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'model_mutation' -Context $dataContext) -ne $false) {
        throw 'Interface connector diagnostic model_mutation must be false.'
    }
    if ((Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'remote_queue_authorized' -Context $dataContext) -ne $false) {
        throw 'Interface connector diagnostic remote_queue_authorized must be false.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'result_scope' -Context $dataContext) -cne 'EXACT_CONNECTOR_NAMES_PLUS_CONNECT_REF_MANAGER') {
        throw 'Interface connector diagnostic result_scope must remain bounded.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'evidence' -Context $dataContext) -cne 'verified_from_solidworks_api') {
        throw 'Interface connector diagnostic evidence must be verified_from_solidworks_api.'
    }

    $document = Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'document' -Context $dataContext
    foreach ($field in @('title', 'path', 'type', 'active_configuration', 'save_flag')) {
        $value = Get-RequiredInterfaceObservationPropertyValue -Object $document -Name $field -Context 'interface connector diagnostic document'
        if ($field -in @('title', 'path', 'type', 'active_configuration') -and [string]::IsNullOrWhiteSpace([string]$value)) {
            throw "Required interface connector diagnostic document field is empty. Field='$field'."
        }
    }

    $directLookup = @(
        Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'direct_lookup' -Context $dataContext
    )
    if ($directLookup.Count -ne $ExpectedConnectors.Count) {
        throw "Direct connector lookup count mismatch. Expected=$($ExpectedConnectors.Count) Actual=$($directLookup.Count)."
    }
    $directSummary = [ordered]@{}
    foreach ($name in $ExpectedConnectors) {
        $row = Get-ExactInterfaceObservationRow -Rows $directLookup -NameField 'requested_name' -ExpectedName $name -Context 'direct connector lookup row'
        $found = Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'found' -Context "direct connector lookup '$name'"
        if ($found -isnot [bool]) {
            throw "Direct connector lookup '$name' found must be boolean."
        }
        if ($found) {
            foreach ($field in @('feature_name', 'feature_type')) {
                $value = Get-RequiredInterfaceObservationPropertyValue -Object $row -Name $field -Context "direct connector lookup '$name'"
                if ([string]::IsNullOrWhiteSpace([string]$value)) {
                    throw "Direct connector lookup '$name' field '$field' must be non-empty when found=true."
                }
            }
        }
        $directSummary[$name] = [ordered]@{
            found = $found
            feature_name = Get-OptionalInterfaceConnectorDiagnosticPropertyValue -Object $row -Name 'feature_name'
            feature_type = Get-OptionalInterfaceConnectorDiagnosticPropertyValue -Object $row -Name 'feature_type'
            lookup_error = Get-OptionalInterfaceConnectorDiagnosticPropertyValue -Object $row -Name 'lookup_error'
        }
    }

    $traversal = @(
        Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'traversal_observations' -Context $dataContext
    )
    foreach ($row in $traversal) {
        $name = [string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'feature_name' -Context 'traversal observation')
        $type = [string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'feature_type' -Context "traversal observation '$name'")
        if ([string]::IsNullOrWhiteSpace($name) -or [string]::IsNullOrWhiteSpace($type)) {
            throw 'Traversal observation name/type must be non-empty.'
        }
        $depth = [int](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'tree_depth' -Context "traversal observation '$name'")
        if ($depth -lt 0) {
            throw "Traversal observation '$name' tree_depth must be non-negative."
        }
        $isTopLevel = Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'is_top_level' -Context "traversal observation '$name'"
        if ($isTopLevel -isnot [bool] -or (($depth -eq 0) -ne $isTopLevel)) {
            throw "Traversal observation '$name' is_top_level must agree with tree_depth."
        }
        $treePath = [string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'tree_path' -Context "traversal observation '$name'")
        if ([string]::IsNullOrWhiteSpace($treePath)) {
            throw "Traversal observation '$name' tree_path must be non-empty."
        }
        if ($depth -gt 0) {
            $parentName = [string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'parent_feature_name' -Context "traversal observation '$name'")
            if ([string]::IsNullOrWhiteSpace($parentName)) {
                throw "Traversal observation '$name' parent_feature_name must be non-empty below the top level."
            }
        }
    }

    $connectorDiagnostics = @(
        Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'connector_diagnostics' -Context $dataContext
    )
    if ($connectorDiagnostics.Count -ne $ExpectedConnectors.Count) {
        throw "Connector diagnostic count mismatch. Expected=$($ExpectedConnectors.Count) Actual=$($connectorDiagnostics.Count)."
    }
    $diagnosticSummary = [ordered]@{}
    foreach ($name in $ExpectedConnectors) {
        $row = Get-ExactInterfaceObservationRow -Rows $connectorDiagnostics -NameField 'requested_name' -ExpectedName $name -Context 'connector diagnostic row'
        foreach ($field in @('direct_lookup_state', 'traversal_match_count', 'traversal_expected_type_match_count', 'classification')) {
            $value = Get-RequiredInterfaceObservationPropertyValue -Object $row -Name $field -Context "connector diagnostic '$name'"
            if ($field -in @('direct_lookup_state', 'classification') -and [string]::IsNullOrWhiteSpace([string]$value)) {
                throw "Connector diagnostic '$name' field '$field' must be non-empty."
            }
        }
        $diagnosticSummary[$name] = [ordered]@{
            direct_lookup_state = [string]$row.direct_lookup_state
            traversal_match_count = [int]$row.traversal_match_count
            traversal_expected_type_match_count = [int]$row.traversal_expected_type_match_count
            classification = [string]$row.classification
        }
    }

    $diagnosticState = [string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'diagnostic_state' -Context $dataContext)
    if ([string]::IsNullOrWhiteSpace($diagnosticState)) {
        throw 'Interface connector diagnostic diagnostic_state must be non-empty.'
    }

    return [ordered]@{
        document = [ordered]@{
            title = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'title' -Context 'interface connector diagnostic document')
            path = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'path' -Context 'interface connector diagnostic document')
            type = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'type' -Context 'interface connector diagnostic document')
            active_configuration = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'active_configuration' -Context 'interface connector diagnostic document')
            save_flag = Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'save_flag' -Context 'interface connector diagnostic document'
        }
        direct_lookup = $directSummary
        traversal_observations = $traversal
        traversal_error = Get-OptionalInterfaceConnectorDiagnosticPropertyValue -Object $data -Name 'traversal_error'
        connector_diagnostics = $diagnosticSummary
        diagnostic_state = $diagnosticState
    }
}
