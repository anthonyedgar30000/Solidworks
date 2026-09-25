Set-StrictMode -Version Latest

function Get-OptionalFeatureManagerTreeDiagnosticPropertyValue {
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

function Assert-FeatureManagerTreeDiagnosticObservation {
    param(
        [Parameter(Mandatory=$true)]$Envelope,
        [Parameter(Mandatory=$true)][string[]]$ExpectedTreeTexts
    )

    $envelopeContext = 'FeatureManager tree diagnostic envelope'
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'command_id' -Context $envelopeContext) -cne 'sw.diagnose_feature_manager_tree') {
        throw 'Expected sw.diagnose_feature_manager_tree envelope.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'source_classification' -Context $envelopeContext) -cne 'verified_from_solidworks_api') {
        throw 'FeatureManager tree diagnostic source_classification must be verified_from_solidworks_api.'
    }

    $data = Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'data' -Context $envelopeContext
    $dataContext = 'FeatureManager tree diagnostic data'
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'write_authority' -Context $dataContext) -cne 'NONE') {
        throw 'FeatureManager tree diagnostic write_authority must be NONE.'
    }
    if ((Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'model_mutation' -Context $dataContext) -ne $false) {
        throw 'FeatureManager tree diagnostic model_mutation must be false.'
    }
    if ((Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'remote_queue_authorized' -Context $dataContext) -ne $false) {
        throw 'FeatureManager tree diagnostic remote_queue_authorized must be false.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'result_scope' -Context $dataContext) -cne 'EXACT_DISPLAYED_TREE_TEXTS_ONLY') {
        throw 'FeatureManager tree diagnostic result_scope must remain bounded.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'evidence' -Context $dataContext) -cne 'verified_from_solidworks_api') {
        throw 'FeatureManager tree diagnostic evidence must be verified_from_solidworks_api.'
    }
    if ((Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'feature_manager_tree_root_available' -Context $dataContext) -ne $true) {
        throw 'FeatureManager tree diagnostic must explicitly confirm a non-null tree root.'
    }

    $document = Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'document' -Context $dataContext
    foreach ($field in @('title', 'path', 'type', 'active_configuration', 'save_flag')) {
        $value = Get-RequiredInterfaceObservationPropertyValue -Object $document -Name $field -Context 'FeatureManager tree diagnostic document'
        if ($field -in @('title', 'path', 'type', 'active_configuration') -and [string]::IsNullOrWhiteSpace([string]$value)) {
            throw "Required FeatureManager tree diagnostic document field is empty. Field='$field'."
        }
    }

    $request = Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'request' -Context $dataContext
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $request -Name 'feature_manager_pane' -Context 'FeatureManager tree diagnostic request') -cne 'swFeatMgrPaneBottom') {
        throw 'FeatureManager tree diagnostic must use swFeatMgrPaneBottom.'
    }
    $requestedTexts = @(
        Get-RequiredInterfaceObservationPropertyValue -Object $request -Name 'displayed_tree_texts' -Context 'FeatureManager tree diagnostic request'
    )
    if ($requestedTexts.Count -ne $ExpectedTreeTexts.Count) {
        throw "FeatureManager tree diagnostic requested text count mismatch. Expected=$($ExpectedTreeTexts.Count) Actual=$($requestedTexts.Count)."
    }
    foreach ($text in $ExpectedTreeTexts) {
        $matches = @($requestedTexts | Where-Object { [string]$_ -ceq $text })
        if ($matches.Count -ne 1) {
            throw "FeatureManager tree diagnostic did not request exact displayed text '$text' exactly once."
        }
    }

    $treeObservations = @(
        Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'tree_observations' -Context $dataContext
    )
    $treeSummary = @()
    foreach ($row in $treeObservations) {
        $text = [string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'displayed_tree_text' -Context 'FeatureManager tree observation')
        if ([string]::IsNullOrWhiteSpace($text)) {
            throw 'FeatureManager tree observation displayed_tree_text must be non-empty.'
        }
        if (@($ExpectedTreeTexts | Where-Object { $_ -ceq $text }).Count -ne 1) {
            throw "FeatureManager tree observation is outside the exact requested-text scope. Text='$text'."
        }
        $depth = [int](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'tree_depth' -Context "FeatureManager tree observation '$text'")
        if ($depth -lt 0) {
            throw "FeatureManager tree observation '$text' tree_depth must be non-negative."
        }
        $treePath = [string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'tree_path' -Context "FeatureManager tree observation '$text'")
        if ([string]::IsNullOrWhiteSpace($treePath)) {
            throw "FeatureManager tree observation '$text' tree_path must be non-empty."
        }
        $objectType = Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'object_type' -Context "FeatureManager tree observation '$text'"
        if ($objectType -isnot [int] -and $objectType -isnot [long]) {
            throw "FeatureManager tree observation '$text' object_type must be an integer."
        }
        $objectIsNull = Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'object_is_null' -Context "FeatureManager tree observation '$text'"
        if ($objectIsNull -isnot [bool]) {
            throw "FeatureManager tree observation '$text' object_is_null must be boolean."
        }

        $runtimeType = Get-OptionalFeatureManagerTreeDiagnosticPropertyValue -Object $row -Name 'object_runtime_dotnet_type'
        $isComObject = Get-OptionalFeatureManagerTreeDiagnosticPropertyValue -Object $row -Name 'object_is_com_object'
        $featureName = Get-OptionalFeatureManagerTreeDiagnosticPropertyValue -Object $row -Name 'feature_name'
        $featureType = Get-OptionalFeatureManagerTreeDiagnosticPropertyValue -Object $row -Name 'feature_type'
        if ($objectIsNull) {
            if ($null -ne $runtimeType -or $null -ne $isComObject -or $null -ne $featureName -or $null -ne $featureType) {
                throw "FeatureManager tree observation '$text' cannot report object or feature metadata when Object is null."
            }
        }
        else {
            if ([string]::IsNullOrWhiteSpace([string]$runtimeType)) {
                throw "FeatureManager tree observation '$text' must report Object runtime .NET type when Object is non-null."
            }
            if ($isComObject -isnot [bool]) {
                throw "FeatureManager tree observation '$text' Object COM classification must be boolean when Object is non-null."
            }
            if (($null -eq $featureName) -xor ($null -eq $featureType)) {
                throw "FeatureManager tree observation '$text' must report both IFeature name and type or neither."
            }
            if ($null -ne $featureName -and ([string]::IsNullOrWhiteSpace([string]$featureName) -or [string]::IsNullOrWhiteSpace([string]$featureType))) {
                throw "FeatureManager tree observation '$text' IFeature metadata must be non-empty when present."
            }
        }

        $treeSummary += [ordered]@{
            displayed_tree_text = $text
            tree_depth = $depth
            tree_path = $treePath
            object_type = [int]$objectType
            object_is_null = $objectIsNull
            object_runtime_dotnet_type = $runtimeType
            object_is_com_object = $isComObject
            feature_name = $featureName
            feature_type = $featureType
        }
    }

    $textDiagnostics = @(
        Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'tree_text_diagnostics' -Context $dataContext
    )
    if ($textDiagnostics.Count -ne $ExpectedTreeTexts.Count) {
        throw "FeatureManager tree diagnostic count mismatch. Expected=$($ExpectedTreeTexts.Count) Actual=$($textDiagnostics.Count)."
    }
    $diagnosticSummary = [ordered]@{}
    foreach ($text in $ExpectedTreeTexts) {
        $row = Get-ExactInterfaceObservationRow -Rows $textDiagnostics -NameField 'requested_displayed_tree_text' -ExpectedName $text -Context 'FeatureManager tree text diagnostic row'
        $matchCount = [int](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'exact_match_count' -Context "FeatureManager tree text diagnostic '$text'")
        if ($matchCount -lt 0) {
            throw "FeatureManager tree text diagnostic '$text' exact_match_count must be non-negative."
        }
        $classification = [string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'classification' -Context "FeatureManager tree text diagnostic '$text'")
        $expectedClassification = if ($matchCount -eq 0) { 'NOT_OBSERVED' } elseif ($matchCount -eq 1) { 'OBSERVED' } else { 'MATCH_NOT_UNIQUE' }
        if ($classification -cne $expectedClassification) {
            throw "FeatureManager tree text diagnostic '$text' classification does not match exact_match_count."
        }
        $actualRows = @($treeObservations | Where-Object {
            [string](Get-RequiredInterfaceObservationPropertyValue -Object $_ -Name 'displayed_tree_text' -Context 'FeatureManager tree observation') -ceq $text
        })
        if ($actualRows.Count -ne $matchCount) {
            throw "FeatureManager tree text diagnostic '$text' exact_match_count does not match tree observations."
        }
        $diagnosticSummary[$text] = [ordered]@{
            exact_match_count = $matchCount
            classification = $classification
        }
    }

    $diagnosticState = [string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'diagnostic_state' -Context $dataContext)
    $classifications = @($diagnosticSummary.Values | ForEach-Object { [string]$_.classification })
    $hasNonUnique = @($classifications | Where-Object { $_ -eq 'MATCH_NOT_UNIQUE' }).Count -gt 0
    $observedCount = @($classifications | Where-Object { $_ -eq 'OBSERVED' }).Count
    $notObservedCount = @($classifications | Where-Object { $_ -eq 'NOT_OBSERVED' }).Count
    $expectedState = if ($hasNonUnique) {
        'TREE_TEXT_MATCH_NOT_UNIQUE'
    }
    elseif ($observedCount -eq $classifications.Count) {
        'ALL_REQUESTED_TREE_TEXTS_OBSERVED'
    }
    elseif ($notObservedCount -eq $classifications.Count) {
        'NO_REQUESTED_TREE_TEXTS_OBSERVED'
    }
    else {
        'PARTIAL_REQUESTED_TREE_TEXTS_OBSERVED'
    }
    if ($diagnosticState -cne $expectedState) {
        throw "FeatureManager tree diagnostic_state does not agree with target classifications. Expected='$expectedState' Actual='$diagnosticState'."
    }

    return [ordered]@{
        document = [ordered]@{
            title = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'title' -Context 'FeatureManager tree diagnostic document')
            path = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'path' -Context 'FeatureManager tree diagnostic document')
            type = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'type' -Context 'FeatureManager tree diagnostic document')
            active_configuration = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'active_configuration' -Context 'FeatureManager tree diagnostic document')
            save_flag = Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'save_flag' -Context 'FeatureManager tree diagnostic document'
        }
        feature_manager_pane = 'swFeatMgrPaneBottom'
        tree_observations = $treeSummary
        tree_text_diagnostics = $diagnosticSummary
        diagnostic_state = $diagnosticState
    }
}
