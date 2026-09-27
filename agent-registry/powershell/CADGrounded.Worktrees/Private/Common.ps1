Set-StrictMode -Version Latest

$script:DefaultProtectedWorktreeNames = @('Solidworks', 'Solidworks-main-current')
$script:DefaultSparsePaths = @('agent-registry', '.github')
$script:DefaultMaxTemporaryWorktrees = 3
$script:DefaultMinimumFreeGB = 100
$script:DefaultStaleAfterDays = 7

function Invoke-CGWTGit {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [switch]$AllowFailure
    )

    $output = @(& git -C $RepositoryRoot @ArgumentList 2>&1)
    $exitCode = $LASTEXITCODE
    $text = @($output | ForEach-Object { [string]$_ })

    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
        $joined = ($text -join [Environment]::NewLine)
        throw "git -C '$RepositoryRoot' $($ArgumentList -join ' ') failed with exit code $exitCode.`n$joined"
    }

    [pscustomobject]@{
        ExitCode = $exitCode
        Output = $text
    }
}

function Resolve-CGWTFullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        return (Resolve-Path -LiteralPath $Path).Path
    }

    return [IO.Path]::GetFullPath($Path)
}

function Test-CGWTPathEqual {
    param(
        [Parameter(Mandatory = $true)][string]$A,
        [Parameter(Mandatory = $true)][string]$B
    )

    $aFull = (Resolve-CGWTFullPath -Path $A).TrimEnd('\', '/')
    $bFull = (Resolve-CGWTFullPath -Path $B).TrimEnd('\', '/')
    return [string]::Equals($aFull, $bFull, [StringComparison]::OrdinalIgnoreCase)
}

function Get-CGWTWorktreeRecords {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)

    $result = Invoke-CGWTGit -RepositoryRoot $RepositoryRoot -ArgumentList @('worktree', 'list', '--porcelain')
    $records = @()
    $current = $null

    foreach ($line in $result.Output) {
        if ($line -like 'worktree *') {
            if ($null -ne $current) {
                $records += [pscustomobject]$current
            }
            $current = [ordered]@{
                Path = $line.Substring(9)
                HEAD = $null
                Branch = $null
                Detached = $false
            }
        }
        elseif (($null -ne $current) -and ($line -like 'HEAD *')) {
            $current.HEAD = $line.Substring(5)
        }
        elseif (($null -ne $current) -and ($line -like 'branch *')) {
            $branchRef = $line.Substring(7)
            $current.Branch = $branchRef -replace '^refs/heads/', ''
        }
        elseif (($null -ne $current) -and ($line -eq 'detached')) {
            $current.Detached = $true
        }
    }

    if ($null -ne $current) {
        $records += [pscustomobject]$current
    }

    return $records
}

function Get-CGWTCommonGitDir {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)

    $result = Invoke-CGWTGit -RepositoryRoot $RepositoryRoot -ArgumentList @('rev-parse', '--git-common-dir')
    $value = ($result.Output | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw 'Unable to resolve git common directory.'
    }

    if ([IO.Path]::IsPathRooted($value)) {
        return [IO.Path]::GetFullPath($value)
    }

    return [IO.Path]::GetFullPath((Join-Path $RepositoryRoot $value))
}

function Get-CGWTMetadataRoot {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)

    Join-Path (Get-CGWTCommonGitDir -RepositoryRoot $RepositoryRoot) 'cadgrounded-worktrees'
}

function Get-CGWTMetadataPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$WorktreePath
    )

    $leaf = Split-Path (Resolve-CGWTFullPath -Path $WorktreePath) -Leaf
    if ([string]::IsNullOrWhiteSpace($leaf)) {
        $leaf = 'root'
    }
    $safe = $leaf -replace '[^A-Za-z0-9._-]', '_'
    Join-Path (Get-CGWTMetadataRoot -RepositoryRoot $RepositoryRoot) ($safe + '.json')
}

function Test-CGWTProtected {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$WorktreePath,
        [string[]]$ProtectedWorktreeNames = $script:DefaultProtectedWorktreeNames
    )

    if (Test-CGWTPathEqual -A $RepositoryRoot -B $WorktreePath) {
        return $true
    }

    $leaf = Split-Path (Resolve-CGWTFullPath -Path $WorktreePath) -Leaf
    return ($ProtectedWorktreeNames -contains $leaf)
}

function Get-CGWTFreeGB {
    param([Parameter(Mandatory = $true)][string]$Path)

    $full = Resolve-CGWTFullPath -Path $Path
    $root = [IO.Path]::GetPathRoot($full)
    if ([string]::IsNullOrWhiteSpace($root)) {
        return $null
    }

    try {
        $drive = New-Object -TypeName System.IO.DriveInfo -ArgumentList $root
        return [math]::Round(($drive.AvailableFreeSpace / 1GB), 2)
    }
    catch {
        return $null
    }
}

function Get-CGWTDirectorySizeGB {
    param([Parameter(Mandatory = $true)][string]$Path)

    $items = Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue
    $sum = ($items | Measure-Object Length -Sum).Sum
    if ($null -eq $sum) { $sum = 0 }
    [math]::Round(($sum / 1GB), 2)
}

function Get-CGWTStatusLines {
    param([Parameter(Mandatory = $true)][string]$WorktreePath)

    (Invoke-CGWTGit -RepositoryRoot $WorktreePath -ArgumentList @('status', '--porcelain=v1', '-uall')).Output
}

function Get-CGWTUntrackedFiles {
    param([Parameter(Mandatory = $true)][string]$WorktreePath)

    @((Invoke-CGWTGit -RepositoryRoot $WorktreePath -ArgumentList @('ls-files', '--others', '--exclude-standard')).Output | Where-Object { $_ })
}

function Get-CGWTIgnoredFiles {
    param([Parameter(Mandatory = $true)][string]$WorktreePath)

    @((Invoke-CGWTGit -RepositoryRoot $WorktreePath -ArgumentList @('ls-files', '--others', '--ignored', '--exclude-standard')).Output | Where-Object { $_ })
}

function Get-CGWTContainingRefs {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$HEAD
    )

    $result = Invoke-CGWTGit -RepositoryRoot $RepositoryRoot -ArgumentList @('branch', '-a', '--contains', $HEAD) -AllowFailure
    if ($result.ExitCode -ne 0) {
        return @()
    }

    @($result.Output | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}
