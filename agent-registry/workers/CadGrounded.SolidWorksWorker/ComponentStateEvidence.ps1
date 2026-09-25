function Get-RequiredObservationPropertyValue {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$Context
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        throw "Required component observation field is absent. Context='$Context' Field='$Name'."
    }
    return $property.Value
}

function Get-OptionalObservationPropertyValue {
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

function Get-TargetState {
    param(
        [Parameter(Mandatory=$true)]$ComponentsEnvelope,
        [Parameter(Mandatory=$true)][string[]]$TargetComponents
    )

    $data = Get-RequiredObservationPropertyValue -Object $ComponentsEnvelope -Name 'data' -Context 'components envelope'
    if ($null -eq $data) {
        throw "Required component observation field is null. Context='components envelope' Field='data'."
    }
    $components = Get-RequiredObservationPropertyValue -Object $data -Name 'components' -Context 'components envelope data'
    if ($null -eq $components) {
        throw "Required component observation field is null. Context='components envelope data' Field='components'."
    }

    $state = [ordered]@{}
    foreach ($name in $TargetComponents) {
        $matches = @($components | Where-Object {
            [string](Get-RequiredObservationPropertyValue -Object $_ -Name 'name2' -Context 'component inventory row') -ceq $name
        })
        if ($matches.Count -ne 1) {
            throw "Exact Component2.Name2 must resolve uniquely. name='$name' matches=$($matches.Count)."
        }

        $component = $matches[0]
        $context = "component '$name'"
        $isTopLevel = [bool](Get-RequiredObservationPropertyValue -Object $component -Name 'is_top_level' -Context $context)
        $parentName = Get-OptionalObservationPropertyValue -Object $component -Name 'parent_name'

        # The worker omits nullable JSON properties. parent_name is optional only
        # for a top-level component; is_top_level remains the explicit parentage
        # observation instead of inferring topology from an omitted field.
        if ($isTopLevel -and $null -ne $parentName) {
            throw "Contradictory parentage observation. Context='$context' reports is_top_level=true with parent_name='$parentName'."
        }
        if (-not $isTopLevel -and [string]::IsNullOrWhiteSpace([string]$parentName)) {
            throw "Required nested-component parentage observation is absent. Context='$context' reports is_top_level=false but parent_name is null or omitted."
        }

        $state[$name] = [ordered]@{
            name2 = [string](Get-RequiredObservationPropertyValue -Object $component -Name 'name2' -Context $context)
            path = [string](Get-RequiredObservationPropertyValue -Object $component -Name 'path' -Context $context)
            suppression_state = Get-RequiredObservationPropertyValue -Object $component -Name 'suppression_state' -Context $context
            fixed_component = Get-RequiredObservationPropertyValue -Object $component -Name 'fixed_component' -Context $context
            is_top_level = $isTopLevel
            parent_name = $parentName
            rotation9 = @(Get-RequiredObservationPropertyValue -Object $component -Name 'rotation9' -Context $context)
            translation_mm = @(Get-RequiredObservationPropertyValue -Object $component -Name 'translation_mm' -Context $context)
            transform_source = [string](Get-RequiredObservationPropertyValue -Object $component -Name 'transform_source' -Context $context)
        }
    }
    return $state
}
