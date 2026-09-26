param(
    [string]$StepPath = 'C:\ChatGPT\Solidworks\IXOR\6130648_01_Carriage_Schlitten_AL (2)\6130648_01_Carriage_Schlitten_AL.stp',
    [string]$ExpectedSha256 = 'bfcd381045f4e115be81ea22a349dfeccc6453ae49a00acab25c547205b50c5b',
    [string]$PackageVersion = '0.6.1',
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'verification-output\al-carriage-6130648-v1')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-JsonFileUtf8NoBom {
    param(
        [Parameter(Mandatory=$true)] [string]$Path,
        [Parameter(Mandatory=$true)] [object]$Value
    )

    $json = $Value | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText(
        $Path,
        $json,
        [System.Text.UTF8Encoding]::new($false)
    )
}

if (-not (Test-Path -LiteralPath $StepPath -PathType Leaf)) {
    throw "Pilot STEP artifact is missing: $StepPath"
}

$hash = (Get-FileHash -LiteralPath $StepPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -cne $ExpectedSha256.ToLowerInvariant()) {
    throw "Pilot STEP SHA256 mismatch. expected=$ExpectedSha256 actual=$hash"
}

$node = Get-Command node -ErrorAction Stop
$nodeVersionText = (& $node.Source --version).Trim()
if ($nodeVersionText -notmatch '^v(?<major>\d+)\.') {
    throw "Could not parse Node.js version: $nodeVersionText"
}

$nodeMajor = [int]$Matches.major
if ($nodeMajor -lt 24) {
    throw "Node.js 24+ is required by the selected cad-mcp-server. Found $nodeVersionText"
}

$npx = Get-Command npx -ErrorAction Stop
$npxVersionText = (& $npx.Source --version).Trim()

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$preparedAt = [DateTimeOffset]::UtcNow.ToString('o')
$manifest = [ordered]@{
    schema_version = 1
    pilot_id = 'opencascade-al-carriage-6130648-v1'
    state = 'PREFLIGHT_PASS'
    prepared_at_utc = $preparedAt
    input = [ordered]@{
        path = $StepPath
        sha256 = $hash
        size_bytes = (Get-Item -LiteralPath $StepPath).Length
    }
    host = [ordered]@{
        node_path = $node.Source
        node_version = $nodeVersionText
        npx_path = $npx.Source
        npx_version = $npxVersionText
    }
    sidecar = [ordered]@{
        package = 'cad-mcp-server'
        package_version = $PackageVersion
        proposed_launch = "npx -y cad-mcp-server@$PackageVersion"
        launch_performed = $false
        install_performed = $false
    }
    authority = [ordered]@{
        source_authority_ceiling = 'DETERMINISTIC_CALCULATION'
        solidworks_access = $false
        solidworks_write = $false
        mechanical_acceptance_granted = $false
    }
}

$outPath = Join-Path $OutputDirectory 'preflight-manifest.json'
Write-JsonFileUtf8NoBom -Path $outPath -Value $manifest

Write-Host 'PASS: Open CASCADE STEP pilot host preflight'
Write-Host "Input SHA256: $hash"
Write-Host "Node: $nodeVersionText"
Write-Host "Prepared manifest: $outPath"
Write-Host 'No package was installed or launched.'
