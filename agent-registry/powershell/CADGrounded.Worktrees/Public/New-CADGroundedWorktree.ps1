function New-CADGroundedWorktree {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
    param(
        [string]$RepositoryRoot = 'C:\ChatGPT\Solidworks',
        [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9._-]+$')][string]$Name,
        [string]$BaseRef = 'main',
        [string]$BranchName,
        [string]$DestinationPath,
        [string[]]$SparsePaths = $script:DefaultSparsePaths,
        [int]$MaxTemporaryWorktrees = $script:DefaultMaxTemporaryWorktrees,
        [double]$MinimumFreeGB = $script:DefaultMinimumFreeGB,
        [string[]]$ProtectedWorktreeNames = $script:DefaultProtectedWorktreeNames
    )

    $RepositoryRoot = Resolve-CGWTFullPath -Path $RepositoryRoot
    if (-not (Test-Path -LiteralPath $RepositoryRoot -PathType Container)) {
        throw "Repository root does not exist: $RepositoryRoot"
    }

    if ([string]::IsNullOrWhiteSpace($BranchName)) {
        $BranchName = "cadgrounded-worktree/$Name"
    }

    if ([string]::IsNullOrWhiteSpace($DestinationPath)) {
        $parent = Split-Path $RepositoryRoot -Parent
        $repoLeaf = Split-Path $RepositoryRoot -Leaf
        $DestinationPath = Join-Path $parent ($repoLeaf + '-' + $Name)
    }
    $DestinationPath = Resolve-CGWTFullPath -Path $DestinationPath

    if (Test-Path -LiteralPath $DestinationPath) {
        throw "Destination already exists: $DestinationPath"
    }

    $records = @(Get-CGWTWorktreeRecords -RepositoryRoot $RepositoryRoot)
    $temporary = @($records | Where-Object {
        -not (Test-CGWTProtected -RepositoryRoot $RepositoryRoot -WorktreePath $_.Path -ProtectedWorktreeNames $ProtectedWorktreeNames)
    })

    if ($temporary.Count -ge $MaxTemporaryWorktrees) {
        throw "Temporary worktree limit reached ($($temporary.Count)/$MaxTemporaryWorktrees). Retire or explicitly raise the limit before creating another worktree."
    }

    $freeGB = Get-CGWTFreeGB -Path $RepositoryRoot
    if (($null -ne $freeGB) -and ($freeGB -lt $MinimumFreeGB)) {
        throw "Free space gate blocked worktree creation: $freeGB GB available, minimum is $MinimumFreeGB GB."
    }

    if (($null -eq $SparsePaths) -or ($SparsePaths.Count -eq 0)) {
        throw 'At least one sparse path is required. Full temporary worktrees are not created by this command.'
    }

    $target = "$DestinationPath on branch $BranchName from $BaseRef"
    if (-not $PSCmdlet.ShouldProcess($target, 'Create sparse CADGrounded temporary worktree')) {
        return
    }

    try {
        Invoke-CGWTGit -RepositoryRoot $RepositoryRoot -ArgumentList @('worktree', 'add', '--no-checkout', '-b', $BranchName, $DestinationPath, $BaseRef) | Out-Null
        Invoke-CGWTGit -RepositoryRoot $DestinationPath -ArgumentList @('sparse-checkout', 'init', '--cone') | Out-Null
        $setArgs = @('sparse-checkout', 'set', '--cone') + @($SparsePaths)
        Invoke-CGWTGit -RepositoryRoot $DestinationPath -ArgumentList $setArgs | Out-Null
        Invoke-CGWTGit -RepositoryRoot $DestinationPath -ArgumentList @('checkout') | Out-Null

        $head = ((Invoke-CGWTGit -RepositoryRoot $DestinationPath -ArgumentList @('rev-parse', 'HEAD')).Output | Select-Object -First 1)
        $metadataRoot = Get-CGWTMetadataRoot -RepositoryRoot $RepositoryRoot
        New-Item -ItemType Directory -Force -Path $metadataRoot | Out-Null
        $metadataPath = Get-CGWTMetadataPath -RepositoryRoot $RepositoryRoot -WorktreePath $DestinationPath

        [ordered]@{
            schema_version = 'cadgrounded.worktree-metadata.v1'
            name = $Name
            purpose = 'temporary_sparse_engineering_worktree'
            repository_root = $RepositoryRoot
            worktree_path = $DestinationPath
            branch = $BranchName
            base_ref = $BaseRef
            head = $head
            sparse_paths = @($SparsePaths)
            created_utc = [DateTime]::UtcNow.ToString('o')
            protected = $false
        } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $metadataPath -Encoding UTF8

        [pscustomobject]@{
            Name = $Name
            Path = $DestinationPath
            Branch = $BranchName
            HEAD = $head
            SparsePaths = @($SparsePaths)
            FreeGBBefore = $freeGB
            MetadataPath = $metadataPath
        }
    }
    catch {
        if (Test-Path -LiteralPath $DestinationPath) {
            Invoke-CGWTGit -RepositoryRoot $RepositoryRoot -ArgumentList @('worktree', 'remove', '--force', $DestinationPath) -AllowFailure | Out-Null
        }
        throw
    }
}
