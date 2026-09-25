Set-StrictMode -Version Latest

function Get-FileEvidence {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$Path)

    $beforeItem = $null
    try {
        $beforeItem = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if ($beforeItem.PSIsContainer) {
            throw "Path is not a file."
        }
    }
    catch {
        throw "Unable to obtain a stable shared read for '$Path'; file observation rejected before hashing: $($_.Exception.Message)"
    }

    $beforeLength = [int64]$beforeItem.Length
    $beforeLastWriteTicks = $beforeItem.LastWriteTimeUtc.Ticks
    $beforeLastWriteTimeUtc = $beforeItem.LastWriteTimeUtc.ToString('o')
    $stream = $null
    $sha256 = $null
    $digest = $null

    try {
        # Read-only access; ReadWrite sharing permits an already-open SOLIDWORKS
        # document when its handle allows a compatible reader. Delete and write
        # access are deliberately not requested.
        $stream = [System.IO.FileStream]::new(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        $digest = $sha256.ComputeHash($stream)
    }
    catch {
        throw "Unable to obtain a stable shared read for '$Path'; file observation rejected during SHA-256: $($_.Exception.Message)"
    }
    finally {
        if ($null -ne $sha256) {
            $sha256.Dispose()
        }
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }

    $afterItem = $null
    try {
        $afterItem = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if ($afterItem.PSIsContainer) {
            throw "Path is not a file."
        }
    }
    catch {
        throw "Unable to obtain a stable shared read for '$Path'; file observation rejected after SHA-256: $($_.Exception.Message)"
    }

    if (
        $beforeLength -ne [int64]$afterItem.Length -or
        $beforeLastWriteTicks -ne $afterItem.LastWriteTimeUtc.Ticks
    ) {
        throw "Assembly file changed while SHA-256 was being computed; file observation rejected."
    }

    return [ordered]@{
        length = $beforeLength
        last_write_time_utc = $beforeLastWriteTimeUtc
        sha256 = ([System.BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
    }
}
