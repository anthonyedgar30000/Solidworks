#Requires -Version 5.1
<#
.SYNOPSIS
    Deterministic read-only geometry report for components in the active SOLIDWORKS assembly.
.DESCRIPTION
    Calls only the existing cad.ps1 component-read route. No LLM is used and no
    write operation is exposed. The script filters the returned structured CAD
    snapshot locally and normalizes Component2.Transform2 / GetBox fields into a
    compact report.

    Transform translation is reported in millimetres from the bridge-provided
    translation_mm field. Bounding-box size and centre are derived locally from
    bounding_box_mm_approx.min/max. GetBox data remains approximate by definition.
.EXAMPLE
    .\cad-geometry.ps1 -NameContains AR60
.EXAMPLE
    .\cad-geometry.ps1 -NameContains 6120069
.EXAMPLE
    .\cad-geometry.ps1 -NameContains AR60 -Json
.EXAMPLE
    .\cad-geometry.ps1 -NameContains AR60 -AllLevels
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateLength(1, 128)]
    [string]$NameContains,

    [ValidateRange(1, 120)]
    [int]$WaitSeconds = 30,

    [switch]$AllLevels,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$cadHelper = Join-Path $PSScriptRoot 'cad.ps1'

if (-not (Test-Path -LiteralPath $cadHelper -PathType Leaf)) {
    throw 'cad-geometry.ps1 must be beside cad.ps1.'
}

function Convert-ToNumberArray {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) { return @() }
    $items = @($Value)
    $out = @()
    foreach ($item in $items) {
        $number = 0.0
        if (-not [double]::TryParse(
            [string]$item,
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$number
        )) {
            return @()
        }
        $out += $number
    }
    return @($out)
}

function New-Vector3 {
    param([double[]]$Values)
    if ($null -eq $Values -or $Values.Count -lt 3) { return $null }
    return [pscustomobject][ordered]@{
        x = $Values[0]
        y = $Values[1]
        z = $Values[2]
    }
}

$rawSnapshot = & $cadHelper -Command 'components' -AllLevels:$AllLevels.IsPresent `
    -WaitSeconds $WaitSeconds -Json

if ($rawSnapshot -is [System.Array]) {
    $rawSnapshot = ($rawSnapshot -join "`n")
}
if ($rawSnapshot -isnot [string] -or [string]::IsNullOrWhiteSpace($rawSnapshot)) {
    throw 'cad.ps1 returned no JSON snapshot.'
}

try {
    $snapshot = ConvertFrom-Json -InputObject $rawSnapshot -ErrorAction Stop
} catch {
    throw 'cad.ps1 returned data that was not valid JSON.'
}

if ($snapshot.state -cne 'completed' -or $null -eq $snapshot.data -or
    $null -eq $snapshot.data.components) {
    throw 'The CAD component snapshot is incomplete.'
}

$components = @($snapshot.data.components)
$matches = @($components | Where-Object {
    ([string]$_.name2).IndexOf($NameContains, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
})

$reports = @()
foreach ($component in $matches) {
    $translation = Convert-ToNumberArray -Value $component.translation_mm
    $rotation = Convert-ToNumberArray -Value $component.rotation9

    $boxMin = @()
    $boxMax = @()
    $boxSource = $null
    $boxClassification = $null
    if ($null -ne $component.bounding_box_mm_approx) {
        $boxMin = Convert-ToNumberArray -Value $component.bounding_box_mm_approx.min
        $boxMax = Convert-ToNumberArray -Value $component.bounding_box_mm_approx.max
        $boxSource = $component.bounding_box_mm_approx.source
        $boxClassification = $component.bounding_box_mm_approx.source_classification
    }

    $boxSize = @()
    $boxCenter = @()
    if ($boxMin.Count -ge 3 -and $boxMax.Count -ge 3) {
        $boxSize = @(
            $boxMax[0] - $boxMin[0],
            $boxMax[1] - $boxMin[1],
            $boxMax[2] - $boxMin[2]
        )
        $boxCenter = @(
            ($boxMin[0] + $boxMax[0]) / 2.0,
            ($boxMin[1] + $boxMax[1]) / 2.0,
            ($boxMin[2] + $boxMax[2]) / 2.0
        )
    }

    $rotationRows = $null
    if ($rotation.Count -ge 9) {
        $rotationRows = @(
            @($rotation[0], $rotation[1], $rotation[2]),
            @($rotation[3], $rotation[4], $rotation[5]),
            @($rotation[6], $rotation[7], $rotation[8])
        )
    }

    $reports += [pscustomobject][ordered]@{
        name = $component.name2
        path = $component.path
        fixed = [bool]$component.fixed
        suppressed = [bool]$component.suppressed
        transform_source = $component.transform_source
        transform_classification = $component.source_classification
        translation_mm = (New-Vector3 -Values $translation)
        rotation9 = @($rotation)
        rotation_rows = $rotationRows
        bounding_box_min_mm = (New-Vector3 -Values $boxMin)
        bounding_box_max_mm = (New-Vector3 -Values $boxMax)
        bounding_box_size_mm = (New-Vector3 -Values $boxSize)
        bounding_box_center_mm = (New-Vector3 -Values $boxCenter)
        bounding_box_source = $boxSource
        bounding_box_classification = $boxClassification
    }
}

$result = [pscustomobject][ordered]@{
    job_id = $snapshot.job_id
    state = $snapshot.state
    worker = $snapshot.worker
    recorded_at = $snapshot.recorded_at
    document = $snapshot.data.document_title
    scope = $(if ($AllLevels) { 'all_levels' } else { 'top_level' })
    source_component_count = $components.Count
    name_contains = $NameContains
    match_count = $reports.Count
    components = $reports
}

if ($Json) {
    $result | ConvertTo-Json -Depth 30
    return
}

[pscustomobject][ordered]@{
    Job = $result.job_id
    State = $result.state
    Worker = $result.worker
    RecordedAt = $result.recorded_at
    Document = $result.document
    Scope = $result.scope
    SourceComponents = $result.source_component_count
    Matches = $result.match_count
} | Format-List

if ($reports.Count -eq 0) {
    Write-Output "No component name contains '$NameContains'."
    return
}

foreach ($report in $reports) {
    Write-Host ('=' * 72)
    Write-Host $report.name
    Write-Host ('=' * 72)

    [pscustomobject][ordered]@{
        Path = $report.path
        Fixed = $report.fixed
        Suppressed = $report.suppressed
        TransformSource = $report.transform_source
        TransformClassification = $report.transform_classification
        TranslationX_mm = $report.translation_mm.x
        TranslationY_mm = $report.translation_mm.y
        TranslationZ_mm = $report.translation_mm.z
        BoxMinX_mm = $report.bounding_box_min_mm.x
        BoxMinY_mm = $report.bounding_box_min_mm.y
        BoxMinZ_mm = $report.bounding_box_min_mm.z
        BoxMaxX_mm = $report.bounding_box_max_mm.x
        BoxMaxY_mm = $report.bounding_box_max_mm.y
        BoxMaxZ_mm = $report.bounding_box_max_mm.z
        BoxSizeX_mm = $report.bounding_box_size_mm.x
        BoxSizeY_mm = $report.bounding_box_size_mm.y
        BoxSizeZ_mm = $report.bounding_box_size_mm.z
        BoxCenterX_mm = $report.bounding_box_center_mm.x
        BoxCenterY_mm = $report.bounding_box_center_mm.y
        BoxCenterZ_mm = $report.bounding_box_center_mm.z
        BoxSource = $report.bounding_box_source
        BoxClassification = $report.bounding_box_classification
    } | Format-List

    if ($null -ne $report.rotation_rows) {
        Write-Host 'Rotation9 (API order, grouped 3x3):'
        foreach ($row in $report.rotation_rows) {
            Write-Host ('  {0,14:G9}  {1,14:G9}  {2,14:G9}' -f $row[0], $row[1], $row[2])
        }
    } else {
        Write-Host 'Rotation9 unavailable or incomplete.'
    }
}
