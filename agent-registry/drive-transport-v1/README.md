# CADGrounded Drive Transport v1

This package fills the transport hop between Google Drive and the canonical local CADGrounded queue.

It is deliberately **not** a CAD controller. It cannot call SOLIDWORKS, execute arbitrary downloaded code, move components, insert parts, create mates, save documents, or make mechanical-acceptance decisions.

## Authority boundary

- SOLIDWORKS remains live geometry authority.
- `Invoke-CADRemoteQueue.ps1` remains local request-validation/execution authority.
- GitHub remains version/history authority.
- Google Drive remains transport only.
- These transport agents only move validated JSON request/result artifacts.

Canonical local queue root:

```text
C:\ChatGPT\Solidworks\agent-registry\remote-queue
```

## Preferred deployment: Google Drive `My Drive`

The transport endpoint must live in a Google Drive for desktop location that is actually available to Windows in both directions. Use a dedicated folder under **My Drive**, not the `Computers` / `My Laptop` backup tree.

The canonical cloud-side transport folder is:

```text
My Drive / CADGroundedRemoteQueue
    REMOTE_QUEUE_BRIDGE_READY.json
    incoming/
    results/
```

The exact local Windows path for `My Drive / CADGroundedRemoteQueue` is deployment-specific because Drive for desktop may stream My Drive through a virtual drive letter or mirror it into a normal local folder. Verify the local path before enabling the task.

Use `Invoke-CADDriveMirrorTransport.ps1` with `mirror_queue_root` set to that verified local My Drive queue path and `local_queue_root` set to:

```text
C:\ChatGPT\Solidworks\agent-registry\remote-queue
```

Copy `mirror-transport-config.example.json` to the local-only `mirror-transport-config.json`, replace the fail-closed placeholder with the verified local My Drive queue path, then run:

```powershell
.\Invoke-CADDriveMirrorTransport.ps1 -DryRun
.\Invoke-CADDriveMirrorTransport.ps1
.\Install-CADDriveMirrorTransportTask.ps1
```

The task runs under the same logged-on interactive Windows identity as Drive for desktop and the local queue.

## Why the `My Laptop` backup tree is not accepted for inbound queue transport

The workstation previously copied `C:\ChatGPT\Solidworks` into `C:\ChatGPT\GoogleDriveMirror\Solidworks`, which Google Drive exposed under `My Laptop / Solidworks / ...`.

A fresh cloud-created `sw.status` probe was visible in that Drive backup tree but never materialized in `C:\ChatGPT\GoogleDriveMirror\Solidworks\agent-registry\remote-queue\incoming`. That proved the backup tree could not be treated as the required inbound queue transport path. Preserve it for backup/reference use only; do not use it as the accepted queue ingress.

## Optional fallback: direct rclone transport

`Invoke-CADDriveTransport.ps1` remains available for deployments that intentionally use a separately authenticated `rclone` Google Drive remote instead of Drive for desktop.

For that fallback, copy `transport-config.example.json` to `transport-config.json` and configure `rclone_exe`, `rclone_remote`, and the Drive folder IDs locally. Do not commit the populated local config.

## Safety semantics

Incoming requests are accepted only when all of the following are true:

- file name is exactly `<job_id>.job.json`;
- `schema_version` is `1`;
- `write_authority` is exactly `NONE`;
- `command_id` is in the configured read-only allowlist;
- file size is below the configured cap;
- no local incoming/processing/terminal/result artifact already exists for the same job.

The mirror transport first copies the Drive-backed request into staging under the canonical local queue, validates it, then atomically renames it into local `incoming`.

Terminal results are exported only when:

- local file name is exactly `<job_id>.result.json`;
- `runner_write_authority` is exactly `NONE`;
- `state` is `completed`, `failed`, or `rejected`.

For the mirror transport, the result copy is SHA-256 verified before the corresponding Drive-backed request can be retired. For the rclone fallback, the uploaded Drive result is re-read by name before request retirement.

A Drive request is retired only **after** a matching terminal result has been copied and verified. Therefore disappearance from Drive `incoming` without a result is never runner success.

## Acceptance test

The transport is not operationally accepted until a fresh post-deployment `sw.status` request travels:

```text
My Drive / CADGroundedRemoteQueue / incoming
  -> Drive for desktop local My Drive path
  -> canonical local remote-queue\incoming
  -> local read-only queue runner
  -> native SOLIDWORKS worker
  -> canonical local remote-queue\results
  -> Drive for desktop local My Drive path / results
  -> My Drive / CADGroundedRemoteQueue / results
```

and the terminal record verifies:

- `runner_write_authority: NONE`;
- native/SOLIDWORKS API provenance;
- exact active document title and path.

API/transport success is not mechanical acceptance.
