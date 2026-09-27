# CADGrounded.Worktrees

`CADGrounded.Worktrees` governs temporary Git worktrees for the CAD-heavy Solidworks repository.

It exists because a normal Git worktree materializes the checked-out repository. In this project that can mean many gigabytes of OEM/CAD files for a branch whose actual code or verification delta is only kilobytes or megabytes.

The module does **not** grant SOLIDWORKS write authority and does not establish mechanical acceptance.

## Policy

The workstation operating model is:

- keep `C:\ChatGPT\Solidworks` as the live/project tree;
- keep `C:\ChatGPT\Solidworks-main-current` as the full `main` checkout;
- create temporary engineering/PR worktrees through `New-CADGroundedWorktree`;
- temporary worktrees are sparse by default (`agent-registry` and `.github`);
- permit at most three temporary worktrees by default;
- block new temporary worktrees below 100 GB free by default;
- never automatically remove a worktree;
- never retire a protected worktree;
- block retirement when tracked changes exist;
- archive and SHA-256 verify untracked files before retirement;
- block ignored files unless the operator explicitly chooses `-DiscardIgnored`;
- require a named preservation branch when a detached HEAD is not reachable from another branch ref.

The machine-specific defaults are also recorded in `worktree-policy.v1.json`.

## Import

```powershell
Import-Module .\agent-registry\powershell\CADGrounded.Worktrees\CADGrounded.Worktrees.psd1 -Force
```

## Create a sparse temporary worktree

```powershell
New-CADGroundedWorktree `
    -Name pr89-worktree-governance `
    -BaseRef origin/main
```

The default destination is a sibling of the repository, for example:

```text
C:\ChatGPT\Solidworks-pr89-worktree-governance
```

The default sparse checkout includes only:

```text
agent-registry
.github
```

A job that genuinely needs additional tracked content must name those sparse paths explicitly:

```powershell
New-CADGroundedWorktree `
    -Name topology-investigation `
    -BaseRef origin/main `
    -SparsePaths @('agent-registry', '.github', 'some-required-reference-path')
```

This command intentionally provides no `-FullCheckout` convenience switch. A full temporary CAD worktree requires a separate, deliberate manual decision rather than a casual default.

## Inspect worktrees

```powershell
Get-CADGroundedWorktreeStatus
Get-CADGroundedWorktreeStatus -MeasureSize
```

The status includes tracked, untracked, and ignored counts; age; branch/HEAD; protected/temporary classification; free disk space; and warnings such as `STALE_TEMPORARY_WORKTREE` and `LOW_DISK_SPACE`.

## Retirement preflight

```powershell
Test-CADGroundedWorktreeRetirement `
    -WorktreePath C:\ChatGPT\Solidworks-pr89-worktree-governance
```

The preflight is read-only. It reports blockers including:

- `PROTECTED_WORKTREE`
- `TRACKED_CHANGES_REQUIRE_MANUAL_REVIEW`
- `UNTRACKED_FILES_REQUIRE_ARCHIVE`
- `IGNORED_FILES_REQUIRE_EXPLICIT_DISPOSITION`
- `HEAD_NOT_REACHABLE_FROM_BRANCH_REF`

Unknown or unresolved state stays blocked rather than being guessed away.

## Retire a worktree

A clean, reachable temporary worktree can be removed with explicit approval:

```powershell
Remove-CADGroundedWorktree `
    -WorktreePath C:\ChatGPT\Solidworks-pr89-worktree-governance `
    -ApproveRemoval
```

If untracked files exist, an evidence archive root is mandatory:

```powershell
Remove-CADGroundedWorktree `
    -WorktreePath C:\ChatGPT\Solidworks-pr89-worktree-governance `
    -ApproveRemoval `
    -EvidenceArchiveRoot D:\CADGrounded_Evidence\worktree-retirement
```

The command copies every untracked file while preserving its relative path, computes SHA-256 at source and destination, verifies equality, and writes `EVIDENCE_MANIFEST_SHA256.json` with the worktree HEAD before invoking `git worktree remove`.

If HEAD is not reachable from any branch ref, removal remains blocked unless the operator supplies a preservation ref:

```powershell
Remove-CADGroundedWorktree `
    -WorktreePath C:\ChatGPT\Solidworks-investigation `
    -ApproveRemoval `
    -PreserveRefName archive/investigation-2026-09-27 `
    -EvidenceArchiveRoot D:\CADGrounded_Evidence\worktree-retirement
```

Ignored files are *not* silently discarded. `-DiscardIgnored` is an explicit disposition decision and should be used only for known reproducible cache/build material.

## Metadata

Temporary worktree creation writes local metadata under the repository's common Git directory:

```text
.git\cadgrounded-worktrees\<worktree>.json
```

This records purpose, base ref, branch, sparse paths, HEAD, and creation timestamp without dirtying the tracked repository.

## Automation rule

CADGrounded automation should call this module rather than raw `git worktree add` / `git worktree remove` for temporary engineering investigations. Reads may be automated. Retirement remains an explicit governed write with evidence and reachability gates.
