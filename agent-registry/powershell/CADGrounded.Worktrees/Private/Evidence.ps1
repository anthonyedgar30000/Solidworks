function Export-CGWTEvidenceArchive {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$WorktreePath,
        [Parameter(Mandatory = $true)][string]$EvidenceArchiveRoot,
        [Parameter(Mandatory = $true)][string[]]$RelativeFiles,
        [Parameter(Mandatory = $true)][string]$HEAD
    )

    $leaf = Split-Path $WorktreePath -Leaf
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $archivePath = Join-Path (Resolve-CGWTFullPath -Path $EvidenceArchiveRoot) ($leaf + '-' + $stamp)
    New-Item -ItemType Directory -Force -Path $archivePath | Out-Null

    $manifest = @()
    foreach ($relative in $RelativeFiles) {
        $source = Join-Path $WorktreePath $relative
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Expected untracked evidence file is missing: $source"
        }

        $destination = Join-Path $archivePath $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force

        $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
        $archiveHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
        if ($sourceHash -ne $archiveHash) {
            throw "Evidence hash verification failed for $relative"
        }

        $manifest += [pscustomobject]@{
            file = $relative
            size_bytes = (Get-Item -LiteralPath $source).Length
            sha256 = $sourceHash
            hash_verified = $true
        }
    }

    [ordered]@{
        schema_version = 'cadgrounded.worktree-evidence-archive.v1'
        repository_root = $RepositoryRoot
        worktree_path = $WorktreePath
        worktree_head = $HEAD
        archived_utc = [DateTime]::UtcNow.ToString('o')
        file_count = $manifest.Count
        files = @($manifest)
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $archivePath 'EVIDENCE_MANIFEST_SHA256.json') -Encoding UTF8

    return $archivePath
}
