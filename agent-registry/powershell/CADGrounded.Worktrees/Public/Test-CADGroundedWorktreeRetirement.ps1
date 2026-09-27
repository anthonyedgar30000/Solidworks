function Test-CADGroundedWorktreeRetirement {
    [CmdletBinding()]
    param(
        [string]$RepositoryRoot = 'C:\ChatGPT\Solidworks',
        [Parameter(Mandatory = $true)][string]$WorktreePath,
        [string[]]$ProtectedWorktreeNames = $script:DefaultProtectedWorktreeNames
    )

    $RepositoryRoot = Resolve-CGWTFullPath -Path $RepositoryRoot
    $WorktreePath = Resolve-CGWTFullPath -Path $WorktreePath

    $records = @(Get-CGWTWorktreeRecords -RepositoryRoot $RepositoryRoot)
    $registered = @($records | Where-Object { Test-CGWTPathEqual -A $_.Path -B $WorktreePath })
    if ($registered.Count -ne 1) {
        throw "Worktree is not registered exactly once: $WorktreePath"
    }

    $head = ((Invoke-CGWTGit -RepositoryRoot $WorktreePath -ArgumentList @('rev-parse', 'HEAD')).Output | Select-Object -First 1)
    $statusLines = @(Get-CGWTStatusLines -WorktreePath $WorktreePath)
    $untracked = @(Get-CGWTUntrackedFiles -WorktreePath $WorktreePath)
    $ignored = @(Get-CGWTIgnoredFiles -WorktreePath $WorktreePath)
    $tracked = @($statusLines | Where-Object { $_ -notlike '?? *' })
    $refs = @(Get-CGWTContainingRefs -RepositoryRoot $RepositoryRoot -HEAD $head)
    $protected = Test-CGWTProtected -RepositoryRoot $RepositoryRoot -WorktreePath $WorktreePath -ProtectedWorktreeNames $ProtectedWorktreeNames

    $blockers = @()
    if ($protected) { $blockers += 'PROTECTED_WORKTREE' }
    if ($tracked.Count -gt 0) { $blockers += 'TRACKED_CHANGES_REQUIRE_MANUAL_REVIEW' }
    if ($untracked.Count -gt 0) { $blockers += 'UNTRACKED_FILES_REQUIRE_ARCHIVE' }
    if ($ignored.Count -gt 0) { $blockers += 'IGNORED_FILES_REQUIRE_EXPLICIT_DISPOSITION' }
    if ($refs.Count -eq 0) { $blockers += 'HEAD_NOT_REACHABLE_FROM_BRANCH_REF' }

    [pscustomobject]@{
        WorktreePath = $WorktreePath
        HEAD = $head
        Protected = $protected
        TrackedChanges = $tracked.Count
        UntrackedFiles = $untracked.Count
        IgnoredFiles = $ignored.Count
        ContainingRefs = @($refs)
        CommitReachable = ($refs.Count -gt 0)
        ReadyWithoutArchive = ($blockers.Count -eq 0)
        Blockers = @($blockers)
    }
}
