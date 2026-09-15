param(
    [string]$OutputPath = "C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\LIVE_CAD_SNAPSHOT.json"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# This relay intentionally reuses the existing validated CAD intent boundary.
# It does not call SOLIDWORKS, the registry, or the worker directly.
$CadAskPath = "C:\ChatGPT\Solidworks\agent-registry\cad-ask.ps1"
$WaitSeconds = 30
$AllowedCommands = @("sw.status", "sw.query_components")

function Invoke-ValidatedCadRead {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt,

        [Parameter(Mandatory = $true)]
        [ValidateSet("sw.status", "sw.query_components")]
        [string]$ExpectedCommand
    )

    if (-not (Test-Path -LiteralPath $CadAskPath -PathType Leaf)) {
        throw "Validated CAD intent script not found at '$CadAskPath'."
    }

    # One attempt only. No retry or fallback to a broader CAD path.
    $raw = & powershell.exe `
        -NoLogo `
        -NoProfile `
        -NonInteractive `
        -File $CadAskPath `
        -Prompt $Prompt `
        -WaitSeconds $WaitSeconds `
        -Json 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "cad-ask.ps1 failed for '$ExpectedCommand' with exit code $LASTEXITCODE. No automatic retry was attempted. Output: $($raw -join [Environment]::NewLine)"
    }

    $text = ($raw -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "cad-ask.ps1 returned no JSON snapshot for '$ExpectedCommand'."
    }

    try {
        $snapshot = $text | ConvertFrom-Json
    }
    catch {
        throw "Rejected malformed cad-ask.ps1 JSON for '$ExpectedCommand': $($_.Exception.Message)"
    }

    if ($null -eq $snapshot -or $snapshot -is [System.Array]) {
        throw "Rejected CAD result for '$ExpectedCommand': expected one JSON object."
    }

    if ($AllowedCommands -notcontains [string]$snapshot.command) {
        throw "Rejected CAD result command '$($snapshot.command)': outside read-only allowlist."
    }

    if ([string]$snapshot.command -ne $ExpectedCommand) {
        throw "Rejected CAD result: expected '$ExpectedCommand' but received '$($snapshot.command)'."
    }

    if ([string]$snapshot.state -ne "completed" -or $null -eq $snapshot.data) {
        throw "Rejected CAD result for '$ExpectedCommand': snapshot is not completed with data."
    }

    return $snapshot
}

$status = Invoke-ValidatedCadRead `
    -Prompt "What assembly is active?" `
    -ExpectedCommand "sw.status"

$components = Invoke-ValidatedCadRead `
    -Prompt "List the top-level components." `
    -ExpectedCommand "sw.query_components"

$payload = [ordered]@{
    schema_version = "cadgrounded-live-snapshot-v0.1"
    snapshot_id = [Guid]::NewGuid().ToString("D")
    published_at_utc = [DateTime]::UtcNow.ToString("o")
    source_authority = "SOLIDWORKS_LIVE_SNAPSHOT"
    transport = "SYNCED_FILE"
    mechanical_acceptance = "NOT_EVALUATED"
    safety = [ordered]@{
        allowed_commands = $AllowedCommands
        writes_enabled = $false
        max_control_enabled = $false
        arbitrary_code_enabled = $false
        retries_enabled = $false
        note = "Snapshot transport only. API/read success is not mechanical acceptance."
    }
    snapshots = [ordered]@{
        status = $status
        components = $components
    }
}

$directory = Split-Path -Parent $OutputPath
if ([string]::IsNullOrWhiteSpace($directory)) {
    throw "OutputPath must include a parent directory."
}
if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$json = $payload | ConvertTo-Json -Depth 100
$tempPath = Join-Path $directory (".{0}.{1}.tmp" -f ([IO.Path]::GetFileName($OutputPath)), [Guid]::NewGuid().ToString("N"))
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

try {
    [IO.File]::WriteAllText($tempPath, $json, $utf8NoBom)
    Move-Item -LiteralPath $tempPath -Destination $OutputPath -Force
}
finally {
    if (Test-Path -LiteralPath $tempPath) {
        Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Published read-only CAD snapshot: $OutputPath"
Write-Host "Snapshot ID: $($payload.snapshot_id)"
Write-Host "Mechanical acceptance: NOT_EVALUATED"
