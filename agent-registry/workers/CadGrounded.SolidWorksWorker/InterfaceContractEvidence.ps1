Set-StrictMode -Version Latest

function Get-RequiredInterfaceObservationPropertyValue {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$Context
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        throw "Required interface observation field is absent. Context='$Context' Field='$Name'."
    }
    if ($null -eq $property.Value) {
        throw "Required interface observation field is null. Context='$Context' Field='$Name'."
    }
    return $property.Value
}

function Get-ExactInterfaceObservationRow {
    param(
        [Parameter(Mandatory=$true)]$Rows,
        [Parameter(Mandatory=$true)][string]$NameField,
        [Parameter(Mandatory=$true)][string]$ExpectedName,
        [Parameter(Mandatory=$true)][string]$Context
    )

    $matches = @($Rows | Where-Object {
        [string](Get-RequiredInterfaceObservationPropertyValue -Object $_ -Name $NameField -Context $Context) -ceq $ExpectedName
    })
    if ($matches.Count -ne 1) {
        throw "Exact interface feature matching must be unique. Context='$Context' Name='$ExpectedName' Matches=$($matches.Count)."
    }
    return $matches[0]
}

function Assert-InterfaceContractObservation {
    param(
        [Parameter(Mandatory=$true)]$Envelope,
        [Parameter(Mandatory=$true)][string[]]$ExpectedCoordinateSystems,
        [Parameter(Mandatory=$true)][string[]]$ExpectedConnectors
    )

    $envelopeContext = 'interface contract envelope'
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'command_id' -Context $envelopeContext) -cne 'sw.query_interface_contract') {
        throw 'Expected sw.query_interface_contract envelope.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'source_classification' -Context $envelopeContext) -cne 'verified_from_solidworks_api') {
        throw 'Interface observation source_classification must be verified_from_solidworks_api.'
    }

    $data = Get-RequiredInterfaceObservationPropertyValue -Object $Envelope -Name 'data' -Context $envelopeContext
    $dataContext = 'interface contract envelope data'
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'write_authority' -Context $dataContext) -cne 'NONE') {
        throw 'Interface observation write_authority must be NONE.'
    }
    if ((Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'model_mutation' -Context $dataContext) -ne $false) {
        throw 'Interface observation model_mutation must be false.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'result_scope' -Context $dataContext) -cne 'EXACT_NAMED_FEATURES_ONLY') {
        throw 'Interface observation result_scope must be EXACT_NAMED_FEATURES_ONLY.'
    }
    if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'evidence' -Context $dataContext) -cne 'verified_from_solidworks_api') {
        throw 'Interface observation data.evidence must be verified_from_solidworks_api.'
    }

    $document = Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'document' -Context $dataContext
    $documentContext = 'interface contract document'
    foreach ($field in @('title', 'path', 'type', 'active_configuration', 'save_flag')) {
        $value = Get-RequiredInterfaceObservationPropertyValue -Object $document -Name $field -Context $documentContext
        if ($field -in @('title', 'path', 'type', 'active_configuration') -and [string]::IsNullOrWhiteSpace([string]$value)) {
            throw "Required interface document field is empty. Field='$field'."
        }
    }

    $coordinateSystems = @(
        Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'coordinate_systems' -Context $dataContext
    )
    if ($coordinateSystems.Count -ne $ExpectedCoordinateSystems.Count) {
        throw "Interface coordinate-system result count mismatch. Expected=$($ExpectedCoordinateSystems.Count) Actual=$($coordinateSystems.Count)."
    }
    $coordinateSummary = [ordered]@{}
    foreach ($name in $ExpectedCoordinateSystems) {
        $row = Get-ExactInterfaceObservationRow -Rows $coordinateSystems -NameField 'feature_name' -ExpectedName $name -Context 'coordinate-system row'
        if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'feature_type' -Context "coordinate system '$name'") -cne 'CoordSys') {
            throw "Coordinate system '$name' did not report feature_type CoordSys."
        }
        $transform16 = @(
            Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'transform16' -Context "coordinate system '$name'"
        )
        if ($transform16.Count -ne 16) {
            throw "Coordinate system '$name' transform16 must contain exactly 16 values. Actual=$($transform16.Count)."
        }
        $originMm = @(
            Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'origin_mm' -Context "coordinate system '$name'"
        )
        if ($originMm.Count -ne 3) {
            throw "Coordinate system '$name' origin_mm must contain exactly 3 values. Actual=$($originMm.Count)."
        }
        $transformSource = [string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'transform_source' -Context "coordinate system '$name'")
        if ([string]::IsNullOrWhiteSpace($transformSource)) {
            throw "Coordinate system '$name' transform_source must be non-empty."
        }
        $coordinateSummary[$name] = [ordered]@{
            feature_type = 'CoordSys'
            transform16 = $transform16
            origin_mm = $originMm
            transform_source = $transformSource
        }
    }

    $connectors = @(
        Get-RequiredInterfaceObservationPropertyValue -Object $data -Name 'published_reference_features' -Context $dataContext
    )
    if ($connectors.Count -ne $ExpectedConnectors.Count) {
        throw "Published Reference connector result count mismatch. Expected=$($ExpectedConnectors.Count) Actual=$($connectors.Count)."
    }
    $connectorSummary = [ordered]@{}
    foreach ($name in $ExpectedConnectors) {
        $row = Get-ExactInterfaceObservationRow -Rows $connectors -NameField 'connector_name' -ExpectedName $name -Context 'Published Reference connector row'
        if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $row -Name 'feature_type' -Context "Published Reference connector '$name'") -cne 'MagneticConnectRef') {
            throw "Published Reference connector '$name' did not report feature_type MagneticConnectRef."
        }
        $connectorSummary[$name] = [ordered]@{ feature_type = 'MagneticConnectRef' }
    }

    return [ordered]@{
        document = [ordered]@{
            title = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'title' -Context $documentContext)
            path = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'path' -Context $documentContext)
            type = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'type' -Context $documentContext)
            active_configuration = [string](Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'active_configuration' -Context $documentContext)
            save_flag = Get-RequiredInterfaceObservationPropertyValue -Object $document -Name 'save_flag' -Context $documentContext
        }
        coordinate_systems = $coordinateSummary
        published_reference_features = $connectorSummary
    }
}
