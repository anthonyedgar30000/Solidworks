function Get-CADGroundedWorktreeStatus {
    [CmdletBinding()]
    param(
        [string]$RepositoryRoot = 'C:\ChatGPT\Solidworks',
        [switch]$MeasureSize,
        [int]$StaleAfterDays = $script:DefaultStaleAfterDays,
        [double]$MinimumFreeGB = $script:DefaultMinimumFreeGB,
        [string[]]$ProtectedWorktreeNames = $script:DefaultProtectedWorktreeNames
    )

    $RepositoryRoot = Resolve-CGWTFullPath -Path $RepositoryRoot
    $records = @(Get-CGWTWorktreeRecords -RepositoryRoot $RepositoryRoot)
    $freeGB = Get-CGWTFreeGB -Path $RepositoryRoot

    foreach ($record in $records) {
        $path = Resolve-CGWTFullPath -Path $record.Path
        $statusLines = @(Get-CGWTStatusLines -WorktreePath $path)
        $untracked = @(Get-CGWTUntrackedFiles -WorktreePath $path)
        $ignored = @(Get-CGWTIgnoredFiles -WorktreePath $path)
        $tracked = @($statusLines | Where-Object { $_ -notlike '?? *' })
        $protected = Test-CGWTProtected -RepositoryRoot $RepositoryRoot -WorktreePath $path -ProtectedWorktreeNames $ProtectedWorktreeNames

        $metadataPath = Get-CGWTMetadataPath -RepositoryRoot $RepositoryRoot -WorktreePath $path
        $createdUtc = $null
        if (Test-Path -LiteralPath $metadataPath -PathType Leaf) {
            try {
                $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
                if ($metadata.created_utc) {
                    $createdUtc = [DateTime]::Parse($metadata.created_utc).ToUniversalTime()
                }
            }
            catch {
                $createdUtc = $null
            }
        }

        if ($null -eq $createdUtc) {
            try { $createdUtc = (Get-Item -LiteralPath $path).CreationTimeUtc } catch { $createdUtc = $null }
        }

        $ageDays = if ($null -ne $createdUtc) { [math]::Floor(([DateTime]::UtcNow - $createdUtc).TotalDays) } else { $null }
        $warnings = @()
        if ((-not $protected) -and ($null -ne $ageDays) -and ($ageDays -ge $StaleAfterDays)) { $warnings += 'STALE_TEMPORARY_WORKTREE' }
        if (($null -ne $freeGB) -and ($freeGB -lt $MinimumFreeGB)) { $warnings += 'LOW_DISK_SPACE' }
        if ($tracked.Count -gt 0) { $warnings += 'TRACKED_CHANGES_PRESENT' }
        if ($untracked.Count -gt 0) { $warnings += 'UNTRACKED_FILES_PRESENT' }
        if ($ignored.Count -gt 0) { $warnings += 'IGNORED_FILES_PRESENT' }

        [pscustomobject]@{
            Name = Split-Path $path -Leaf
            Path = $path
            HEAD = $record.HEAD
            Branch = if ($record.Detached) { '(detached)' } else { $record.Branch }
            Protected = $protected
            Temporary = (-not $protected)
            DirtyItems = $statusLines.Count
            TrackedChanges = $tracked.Count
            UntrackedFiles = $untracked.Count
            IgnoredFiles = $ignored.Count
            SizeGB = if ($MeasureSize) { Get-CGWTDirectorySizeGB -Path $path } else { $null }
            CreatedUtc = if ($null -ne $createdUtc) { $createdUtc.ToString('o') } else { $null }
            AgeDays = $ageDays
            FreeGB = $freeGB
            Warnings = @($warnings)
        }
    }
}
