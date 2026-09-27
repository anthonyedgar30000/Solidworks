$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Assert-Equal {
    param(
        $Actual,
        $Expected,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if ($Actual -ne $Expected) {
        throw "ASSERTION FAILED: $Message. Expected '$Expected', got '$Actual'."
    }
}

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$modulePath = Join-Path $repoRoot 'agent-registry\powershell\CADGrounded.Worktrees\CADGrounded.Worktrees.psd1'
Import-Module $modulePath -Force

$base = Join-Path ([IO.Path]::GetTempPath()) ('cadgrounded-worktree-test-' + [Guid]::NewGuid().ToString('N'))
$repo = Join-Path $base 'repo'
$worktree = Join-Path $base 'repo-pilot'
$archive = Join-Path $base 'evidence'

try {
    New-Item -ItemType Directory -Force -Path $repo | Out-Null
    & git init -b main $repo | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
    & git -C $repo config user.email 'cadgrounded-tests@example.invalid'
    & git -C $repo config user.name 'CADGrounded Tests'

    New-Item -ItemType Directory -Force -Path (Join-Path $repo 'agent-registry') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $repo '.github\workflows') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $repo 'IXOR') | Out-Null
    Set-Content -LiteralPath (Join-Path $repo 'agent-registry\sample.txt') -Value 'code'
    Set-Content -LiteralPath (Join-Path $repo '.github\workflows\sample.yml') -Value 'name: sample'
    Set-Content -LiteralPath (Join-Path $repo 'IXOR\large-cad-placeholder.bin') -Value ('x' * 4096)
    & git -C $repo add .
    & git -C $repo commit -m 'test fixture' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'fixture commit failed' }

    $created = New-CADGroundedWorktree `
        -RepositoryRoot $repo `
        -Name 'pilot' `
        -BaseRef 'main' `
        -DestinationPath $worktree `
        -SparsePaths @('agent-registry', '.github') `
        -MinimumFreeGB 0 `
        -MaxTemporaryWorktrees 5 `
        -Confirm:$false

    Assert-True (Test-Path -LiteralPath (Join-Path $worktree 'agent-registry\sample.txt') -PathType Leaf) 'sparse worktree must contain agent-registry'
    Assert-True (Test-Path -LiteralPath (Join-Path $worktree '.github\workflows\sample.yml') -PathType Leaf) 'sparse worktree must contain .github'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $worktree 'IXOR\large-cad-placeholder.bin') -PathType Leaf)) 'sparse worktree must not materialize IXOR by default'
    Assert-Equal $created.Branch 'cadgrounded-worktree/pilot' 'default temporary branch name'

    $status = @(Get-CADGroundedWorktreeStatus -RepositoryRoot $repo -MinimumFreeGB 0)
    Assert-Equal $status.Count 2 'status should report root plus temporary worktree'
    $pilotStatus = @($status | Where-Object { $_.Path -eq (Resolve-Path $worktree).Path })
    Assert-Equal $pilotStatus.Count 1 'temporary worktree should appear once'
    Assert-True $pilotStatus[0].Temporary 'pilot must be classified temporary'

    $protected = Test-CADGroundedWorktreeRetirement -RepositoryRoot $repo -WorktreePath $repo
    Assert-True $protected.Protected 'repository root must always be protected'

    $evidenceRel = 'agent-registry\verification-output\verification-summary.json'
    $evidenceSource = Join-Path $worktree $evidenceRel
    New-Item -ItemType Directory -Force -Path (Split-Path $evidenceSource -Parent) | Out-Null
    Set-Content -LiteralPath $evidenceSource -Value '{"result":"verified-test-artifact"}' -Encoding UTF8

    $preflight = Test-CADGroundedWorktreeRetirement -RepositoryRoot $repo -WorktreePath $worktree
    Assert-Equal $preflight.TrackedChanges 0 'fixture should have no tracked changes'
    Assert-Equal $preflight.UntrackedFiles 1 'fixture should expose one untracked evidence file'
    Assert-True $preflight.CommitReachable 'temporary branch should keep HEAD reachable'

    $blocked = $false
    try {
        Remove-CADGroundedWorktree `
            -RepositoryRoot $repo `
            -WorktreePath $worktree `
            -ApproveRemoval `
            -Confirm:$false
    }
    catch {
        $blocked = $true
    }
    Assert-True $blocked 'removal without evidence archive must be blocked when untracked files exist'
    Assert-True (Test-Path -LiteralPath $worktree -PathType Container) 'blocked retirement must leave worktree intact'

    $removed = Remove-CADGroundedWorktree `
        -RepositoryRoot $repo `
        -WorktreePath $worktree `
        -ApproveRemoval `
        -EvidenceArchiveRoot $archive `
        -Confirm:$false

    Assert-True $removed.Removed 'governed retirement should report removal'
    Assert-Equal $removed.ArchivedUntrackedFiles 1 'retirement should archive the evidence file'
    Assert-True (-not (Test-Path -LiteralPath $worktree)) 'retired worktree path should be gone'
    Assert-True (Test-Path -LiteralPath $removed.EvidenceArchivePath -PathType Container) 'evidence archive directory should exist'

    $manifestPath = Join-Path $removed.EvidenceArchivePath 'EVIDENCE_MANIFEST_SHA256.json'
    Assert-True (Test-Path -LiteralPath $manifestPath -PathType Leaf) 'SHA-256 evidence manifest should exist'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Assert-Equal $manifest.file_count 1 'manifest should record one archived artifact'
    Assert-True $manifest.files[0].hash_verified 'manifest must record verified hash equality'

    $remaining = @(& git -C $repo worktree list --porcelain | Where-Object { $_ -like 'worktree *' })
    Assert-Equal $remaining.Count 1 'only the protected root should remain after test retirement'

    Write-Host 'CADGrounded.Worktrees contract tests passed.'
}
finally {
    if (Test-Path -LiteralPath $base) {
        Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
    }
}
