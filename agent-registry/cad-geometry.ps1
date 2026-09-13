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

function Convert-ToDoubleArray {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return ,@()
    }

    $items = @($Value)
    $numbers = New-Object System.Collections.Generic.List[double]

    foreach ($item in $items) {
        $number = 0.0
        if (-not [double]::TryParse(
            [string]$item,
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$number
        )) {
            return ,@()
        }
        $numbers.Add($number)
    }

    return ,([double[]]$numbers.ToArray())
}

function New-Vector3 {
    param(
        [double]$X,
        [double]$Y,
        [double]$Z
    )

    return [pscustomobject][ordered]@{
        x = $X
        y = $Y
        z = $Z
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
    [double[]]$translation = Convert-ToDoubleArray -Value $component.translation_mm
    [double[]]$rotation = Convert-ToDoubleArray -Value $component.rotation9

    [double[]]$boxMin = @()
    [double[]]$boxMax = @()
    $boxSource = $null
    $boxClassification = $null

    if ($null -ne $component.bounding_box_mm_approx) {
        [double[]]$boxMin = Convert-ToDoubleArray -Value $component.bounding_box_mm_approx.min
        [double[]]$boxMax = Convert-ToDoubleArray -Value $component.bounding_box_mm_approx.max
        $boxSource = $component.bounding_box_mm_approx.source
        $boxClassification = $component.bounding_box_mm_approx.source_classification
    }

    $translationVector = $null
    if ($translation.Count -ge 3) {
        $translationVector = New-Vector3 `
            -X ([double]$translation[0]) `
            -Y ([double]$translation[1]) `
            -Z ([double]$translation[2])
    }

    $boxMinVector = $null
    $boxMaxVector = $null
    $boxSizeVector = $null
    $boxCenterVector = $null

    if ($boxMin.Count -ge 3 -and $boxMax.Count -ge 3) {
        # Force each coordinate to a scalar before arithmetic. In Windows
        # PowerShell, comma-separated arithmetic expressions can otherwise bind
        # as Object[] operands and produce an op_Subtraction error.
        [double]$minX = $boxMin[0]
        [double]$minY = $boxMin[1]
        [double]$minZ = $boxMin[2]
        [double]$maxX = $boxMax[0]
        [double]$maxY = $boxMax[1]
        [double]$maxZ = $boxMax[2]

        [double]$sizeX = $maxX - $minX
        [double]$sizeY = $maxY - $minY
        [double]$sizeZ = $maxZ - $minZ
        [double]$centerX = ($minX + $maxX) / 2.0
        [double]$centerY = ($minY + $maxY) / 2.0
        [double]$centerZ = ($minZ + $maxZ) / 2.0

        $boxMinVector = New-Vector3 -X $minX -Y $minY -Z $minZ
        $boxMaxVector = New-Vector3 -X $maxX -Y $maxY -Z $maxZ
        $boxSizeVector = New-Vector3 -X $sizeX -Y $sizeY -Z $sizeZ
        $boxCenterVector = New-Vector3 -X $centerX -Y $centerY -Z $centerZ
    }

    $rotationRows = $null
    if ($rotation.Count -ge 9) {
        $rotationRows = @(
            ,([double[]]@($rotation[0], $rotation[1], $rotation[2]))
            ,([double[]]@($rotation[3], $rotation[4], $rotation[5]))
            ,([double[]]@($rotation[6], $rotation[7], $rotation[8]))
        )
    }

    $reports += [pscustomobject][ordered]@{
        name = $component.name2
        path = $component.path
        fixed = [bool]$component.fixed
        suppressed = [bool]$component.suppressed
        transform_source = $component.transform_source
        transform_classification = $component.source_classification
        translation_mm = $translationVector
        rotation9 = $rotation
        rotation_rows = $rotationRows
        bounding_box_min_mm = $boxMinVector
        bounding_box_max_mm = $boxMaxVector
        bounding_box_size_mm = $boxSizeVector
        bounding_box_center_mm = $boxCenterVector
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
        TranslationX_mm = $(if ($null -ne $report.translation_mm) { $report.translation_mm.x } else { $null })
        TranslationY_mm = $(if ($null -ne $report.translation_mm) { $report.translation_mm.y } else { $null })
        TranslationZ_mm = $(if ($null -ne $report.translation_mm) { $report.translation_mm.z } else { $null })
        BoxMinX_mm = $(if ($null -ne $report.bounding_box_min_mm) { $report.bounding_box_min_mm.x } else { $null })
        BoxMinY_mm = $(if ($null -ne $report.bounding_box_min_mm) { $report.bounding_box_min_mm.y } else { $null })
        BoxMinZ_mm = $(if ($null -ne $report.bounding_box_min_mm) { $report.bounding_box_min_mm.z } else { $null })
        BoxMaxX_mm = $(if ($null -ne $report.bounding_box_max_mm) { $report.bounding_box_max_mm.x } else { $null })
        BoxMaxY_mm = $(if ($null -ne $report.bounding_box_max_mm) { $report.bounding_box_max_mm.y } else { $null })
        BoxMaxZ_mm = $(if ($null -ne $report.bounding_box_max_mm) { $report.bounding_box_max_mm.z } else { $null })
        BoxSizeX_mm = $(if ($null -ne $report.bounding_box_size_mm) { $report.bounding_box_size_mm.x } else { $null })
        BoxSizeY_mm = $(if ($null -ne $report.bounding_box_size_mm) { $report.bounding_box_size_mm.y } else { $null })
        BoxSizeZ_mm = $(if ($null -ne $report.bounding_box_size_mm) { $report.bounding_box_size_mm.z } else { $null })
        BoxCenterX_mm = $(if ($null -ne $report.bounding_box_center_mm) { $report.bounding_box_center_mm.x } else { $null })
        BoxCenterY_mm = $(if ($null -ne $report.bounding_box_center_mm) { $report.bounding_box_center_mm.y } else { $null })
        BoxCenterZ_mm = $(if ($null -ne $report.bounding_box_center_mm) { $report.bounding_box_center_mm.z } else { $null })
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
