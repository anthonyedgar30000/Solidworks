#Requires -Version 5.1
<#
.SYNOPSIS
    Compare approximate axis-aligned geometry between components in the active SOLIDWORKS assembly.
.DESCRIPTION
    Calls only the existing cad.ps1 component-read route. No LLM and no CAD write
    operation are used. Components are filtered locally by name substring.

    Translation values come from Component2.Transform2 through the bridge and are
    treated as verified SOLIDWORKS API data. Bounding boxes come from
    Component2.GetBox(false,false) and are approximate. Axis gaps/overlaps and
    Euclidean AABB separation are derived locally from those approximate boxes.

    This is a spatial screening tool, not an interference/contact/mechanical
    approval test.
.EXAMPLE
    .\cad-relative-geometry.ps1 -ANameContains AR60 -BNameContains BENCH_BOTTLE
.EXAMPLE
    .\cad-relative-geometry.ps1 -ANameContains AR60 -BNameContains BENCH_CONVEYOR
.EXAMPLE
    .\cad-relative-geometry.ps1 -ANameContains 6120069 -BNameContains SP100 -Json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateLength(1,128)]
    [string]$ANameContains,

    [Parameter(Mandatory = $true)]
    [ValidateLength(1,128)]
    [string]$BNameContains,

    [ValidateRange(1,120)]
    [int]$WaitSeconds = 30,

    [switch]$AllLevels,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$cadHelper = Join-Path $PSScriptRoot 'cad.ps1'
if (-not (Test-Path -LiteralPath $cadHelper -PathType Leaf)) {
    throw 'cad-relative-geometry.ps1 must be beside cad.ps1.'
}

function Convert-ToDoubleArray {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return ,@() }
    $items = @($Value)
    $numbers = New-Object System.Collections.Generic.List[double]
    foreach ($item in $items) {
        [double]$n = 0.0
        if (-not [double]::TryParse(
            [string]$item,
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$n
        )) { return ,@() }
        $numbers.Add($n)
    }
    return ,([double[]]$numbers.ToArray())
}

function Get-ComponentGeometry {
    param([Parameter(Mandatory=$true)][object]$Component)

    [double[]]$t = Convert-ToDoubleArray -Value $Component.translation_mm
    [double[]]$mn = @()
    [double[]]$mx = @()
    if ($null -ne $Component.bounding_box_mm_approx) {
        [double[]]$mn = Convert-ToDoubleArray -Value $Component.bounding_box_mm_approx.min
        [double[]]$mx = Convert-ToDoubleArray -Value $Component.bounding_box_mm_approx.max
    }

    if ($mn.Count -lt 3 -or $mx.Count -lt 3) {
        throw "Component '$($Component.name2)' has no complete approximate GetBox bounds."
    }

    [double]$minX = $mn[0]; [double]$minY = $mn[1]; [double]$minZ = $mn[2]
    [double]$maxX = $mx[0]; [double]$maxY = $mx[1]; [double]$maxZ = $mx[2]

    $translation = $null
    if ($t.Count -ge 3) {
        $translation = [pscustomobject][ordered]@{ x=$t[0]; y=$t[1]; z=$t[2] }
    }

    return [pscustomobject][ordered]@{
        name = $Component.name2
        path = $Component.path
        fixed = [bool]$Component.fixed
        suppressed = [bool]$Component.suppressed
        translation_mm = $translation
        transform_source = $Component.transform_source
        transform_classification = $Component.source_classification
        min = [pscustomobject][ordered]@{ x=$minX; y=$minY; z=$minZ }
        max = [pscustomobject][ordered]@{ x=$maxX; y=$maxY; z=$maxZ }
        center = [pscustomobject][ordered]@{
            x=($minX+$maxX)/2.0; y=($minY+$maxY)/2.0; z=($minZ+$maxZ)/2.0
        }
        size = [pscustomobject][ordered]@{
            x=$maxX-$minX; y=$maxY-$minY; z=$maxZ-$minZ
        }
        box_source = $Component.bounding_box_mm_approx.source
        box_classification = $Component.bounding_box_mm_approx.source_classification
    }
}

function Get-AxisRelation {
    param(
        [double]$AMin,
        [double]$AMax,
        [double]$BMin,
        [double]$BMax
    )

    if ($AMax -lt $BMin) {
        [double]$gap = $BMin - $AMax
        return [pscustomobject][ordered]@{ separated=$true; gap_mm=$gap; overlap_mm=0.0; relation='A_before_B' }
    }
    if ($BMax -lt $AMin) {
        [double]$gap = $AMin - $BMax
        return [pscustomobject][ordered]@{ separated=$true; gap_mm=$gap; overlap_mm=0.0; relation='B_before_A' }
    }

    [double]$overlap = [Math]::Min($AMax,$BMax) - [Math]::Max($AMin,$BMin)
    return [pscustomobject][ordered]@{ separated=$false; gap_mm=0.0; overlap_mm=$overlap; relation='overlap_or_touch' }
}

$rawSnapshot = & $cadHelper -Command 'components' -AllLevels:$AllLevels.IsPresent -WaitSeconds $WaitSeconds -Json
if ($rawSnapshot -is [System.Array]) { $rawSnapshot = ($rawSnapshot -join "`n") }
if ($rawSnapshot -isnot [string] -or [string]::IsNullOrWhiteSpace($rawSnapshot)) {
    throw 'cad.ps1 returned no JSON snapshot.'
}

try { $snapshot = ConvertFrom-Json -InputObject $rawSnapshot -ErrorAction Stop }
catch { throw 'cad.ps1 returned data that was not valid JSON.' }

if ($snapshot.state -cne 'completed' -or $null -eq $snapshot.data -or $null -eq $snapshot.data.components) {
    throw 'The CAD component snapshot is incomplete.'
}

$components = @($snapshot.data.components)
$aMatches = @($components | Where-Object {
    ([string]$_.name2).IndexOf($ANameContains,[System.StringComparison]::OrdinalIgnoreCase) -ge 0
})
$bMatches = @($components | Where-Object {
    ([string]$_.name2).IndexOf($BNameContains,[System.StringComparison]::OrdinalIgnoreCase) -ge 0
})

if ($aMatches.Count -eq 0) { throw "No component name contains '$ANameContains'." }
if ($bMatches.Count -eq 0) { throw "No component name contains '$BNameContains'." }

$comparisons = @()
foreach ($a in $aMatches) {
    $ag = Get-ComponentGeometry -Component $a
    foreach ($b in $bMatches) {
        if ([object]::ReferenceEquals($a,$b) -or $a.name2 -ceq $b.name2) { continue }
        $bg = Get-ComponentGeometry -Component $b

        $x = Get-AxisRelation -AMin $ag.min.x -AMax $ag.max.x -BMin $bg.min.x -BMax $bg.max.x
        $y = Get-AxisRelation -AMin $ag.min.y -AMax $ag.max.y -BMin $bg.min.y -BMax $bg.max.y
        $z = Get-AxisRelation -AMin $ag.min.z -AMax $ag.max.z -BMin $bg.min.z -BMax $bg.max.z

        [double]$aabbDistance = [Math]::Sqrt(
            ($x.gap_mm*$x.gap_mm) + ($y.gap_mm*$y.gap_mm) + ($z.gap_mm*$z.gap_mm)
        )
        [double]$centerDx = $bg.center.x - $ag.center.x
        [double]$centerDy = $bg.center.y - $ag.center.y
        [double]$centerDz = $bg.center.z - $ag.center.z
        [double]$centerDistance = [Math]::Sqrt(
            ($centerDx*$centerDx) + ($centerDy*$centerDy) + ($centerDz*$centerDz)
        )

        $comparisons += [pscustomobject][ordered]@{
            a = $ag
            b = $bg
            x = $x
            y = $y
            z = $z
            aabb_separation_mm = $aabbDistance
            boxes_overlap_all_axes = (-not $x.separated -and -not $y.separated -and -not $z.separated)
            center_delta_mm = [pscustomobject][ordered]@{ x=$centerDx; y=$centerDy; z=$centerDz }
            center_distance_mm = $centerDistance
            interpretation = 'Approximate AABB screening only; GetBox is not an interference/contact proof.'
        }
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
    a_name_contains = $ANameContains
    b_name_contains = $BNameContains
    a_match_count = $aMatches.Count
    b_match_count = $bMatches.Count
    comparison_count = $comparisons.Count
    comparisons = $comparisons
}

if ($Json) {
    $result | ConvertTo-Json -Depth 40
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
    AMatches = $result.a_match_count
    BMatches = $result.b_match_count
    Comparisons = $result.comparison_count
} | Format-List

foreach ($c in $comparisons) {
    Write-Host ('=' * 78)
    Write-Host ("A: {0}" -f $c.a.name)
    Write-Host ("B: {0}" -f $c.b.name)
    Write-Host ('=' * 78)

    [pscustomobject][ordered]@{
        AABB_Separation_mm = $c.aabb_separation_mm
        BoxesOverlapAllAxes = $c.boxes_overlap_all_axes
        X_Relation = $c.x.relation
        X_Gap_mm = $c.x.gap_mm
        X_Overlap_mm = $c.x.overlap_mm
        Y_Relation = $c.y.relation
        Y_Gap_mm = $c.y.gap_mm
        Y_Overlap_mm = $c.y.overlap_mm
        Z_Relation = $c.z.relation
        Z_Gap_mm = $c.z.gap_mm
        Z_Overlap_mm = $c.z.overlap_mm
        CenterDeltaX_mm = $c.center_delta_mm.x
        CenterDeltaY_mm = $c.center_delta_mm.y
        CenterDeltaZ_mm = $c.center_delta_mm.z
        CenterDistance_mm = $c.center_distance_mm
        A_BoxClassification = $c.a.box_classification
        B_BoxClassification = $c.b.box_classification
    } | Format-List

    Write-Host 'NOTE: approximate AABB screening only; not a contact/interference proof.'
}
