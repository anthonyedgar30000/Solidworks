function Remove-CADGroundedWorktree {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
    param(
        [string]$RepositoryRoot = 'C:\ChatGPT\Solidworks',
        [Parameter(Mandatory = $true)][string]$WorktreePath,
        [Parameter(Mandatory = $true)][switch]$ApproveRemoval,
        [string]$EvidenceArchiveRoot,
        [switch]$DiscardIgnored,
        [string]$PreserveRefName,
        [string[]]$ProtectedWorktreeNames = $script:DefaultProtectedWorktreeNames
    )

    if (-not $ApproveRemoval) {
        throw 'Explicit -ApproveRemoval is required.'
    }

    $RepositoryRoot = Resolve-CGWTFullPath -Path $RepositoryRoot
    $WorktreePath = Resolve-CGWTFullPath -Path $WorktreePath
    $preflight = Test-CADGroundedWorktreeRetirement -RepositoryRoot $RepositoryRoot -WorktreePath $WorktreePath -ProtectedWorktreeNames $ProtectedWorktreeNames

    if ($preflight.Protected) {
        throw "Protected worktree cannot be removed by this command: $WorktreePath"
    }
    if ($preflight.TrackedChanges -gt 0) {
        throw 'Tracked changes are present. Retirement is blocked until they are committed, restored, or separately preserved by a human-reviewed process.'
    }
    if (($preflight.IgnoredFiles -gt 0) -and (-not $DiscardIgnored)) {
        throw 'Ignored files are present. Supply -DiscardIgnored only after explicitly deciding they are disposable.'
    }

    if (-not $preflight.CommitReachable) {
        if ([string]::IsNullOrWhiteSpace($PreserveRefName)) {
            throw 'HEAD is not reachable from a branch ref. Supply -PreserveRefName to create an archive branch before removal.'
        }
        Invoke-CGWTGit -RepositoryRoot $RepositoryRoot -ArgumentList @('branch', $PreserveRefName, $preflight.HEAD) | Out-Null
        $refsAfter = @(Get-CGWTContainingRefs -RepositoryRoot $RepositoryRoot -HEAD $preflight.HEAD)
        if ($refsAfter.Count -eq 0) {
            throw 'Preservation branch was requested but HEAD is still not reachable from a branch ref.'
        }
    }

    $untracked = @(Get-CGWTUntrackedFiles -WorktreePath $WorktreePath)
    $archivePath = $null
    if ($untracked.Count -gt 0) {
        if ([string]::IsNullOrWhiteSpace($EvidenceArchiveRoot)) {
            throw 'Untracked files are present. Supply -EvidenceArchiveRoot so they can be copied and SHA-256 verified before removal.'
        }
        $archivePath = Export-CGWTEvidenceArchive -RepositoryRoot $RepositoryRoot -WorktreePath $WorktreePath -EvidenceArchiveRoot $EvidenceArchiveRoot -RelativeFiles $untracked -HEAD $preflight.HEAD
    }

    $action = "Remove governed worktree; archived untracked=$($untracked.Count); discarded ignored=$($preflight.IgnoredFiles)"
    if (-not $PSCmdlet.ShouldProcess($WorktreePath, $action)) {
        return
    }

    $removeArgs = @('worktree', 'remove')
    if (($untracked.Count -gt 0) -or ($preflight.IgnoredFiles -gt 0)) {
        $removeArgs += '--force'
    }
    $removeArgs += $WorktreePath
    Invoke-CGWTGit -RepositoryRoot $RepositoryRoot -ArgumentList $removeArgs | Out-Null

    if (Test-Path -LiteralPath $WorktreePath) {
        throw "Worktree removal command returned but path still exists: $WorktreePath"
    }

    $metadataPath = Get-CGWTMetadataPath -RepositoryRoot $RepositoryRoot -WorktreePath $WorktreePath
    if (Test-Path -LiteralPath $metadataPath -PathType Leaf) {
        Remove-Item -LiteralPath $metadataPath -Force
    }

    [pscustomobject]@{
        WorktreePath = $WorktreePath
        HEAD = $preflight.HEAD
        Removed = $true
        ArchivedUntrackedFiles = $untracked.Count
        EvidenceArchivePath = $archivePath
        DiscardedIgnoredFiles = if ($DiscardIgnored) { $preflight.IgnoredFiles } else { 0 }
        MechanicalAcceptanceGranted = $false
        CADModelMutation = $false
    }
}
