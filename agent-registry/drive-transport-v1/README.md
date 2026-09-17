# CADGrounded Drive Transport v1

This package fills the missing transport hop between Google Drive and the canonical local CADGrounded queue.

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

## Preferred deployment: existing Drive Desktop mirror

Runtime history shows the workstation already has a mirror task that copies:

```text
C:\ChatGPT\Solidworks
    -> C:\ChatGPT\GoogleDriveMirror\Solidworks
```

and Google Drive exposes that mirrored tree under the computer backup as:

```text
My Laptop / Solidworks / ...
```

The previous mirror job was local-to-mirror only. That was the missing inbound queue hop: a job could arrive through Google Drive into the mirrored tree without any mechanism copying it into the canonical live queue.

Use `Invoke-CADDriveMirrorTransport.ps1` to bridge only the queue artifacts between:

```text
C:\ChatGPT\GoogleDriveMirror\Solidworks\agent-registry\remote-queue
```

and:

```text
C:\ChatGPT\Solidworks\agent-registry\remote-queue
```

Copy `mirror-transport-config.example.json` to the local-only `mirror-transport-config.json`, verify the two roots, then run:

```powershell
.\Invoke-CADDriveMirrorTransport.ps1 -DryRun
.\Invoke-CADDriveMirrorTransport.ps1
.\Install-CADDriveMirrorTransportTask.ps1
```

The task runs under the same logged-on interactive Windows identity as Drive Desktop and the local queue.

## Optional fallback: direct rclone transport

`Invoke-CADDriveTransport.ps1` remains available for deployments that intentionally use a separately authenticated `rclone` Google Drive remote instead of the existing Drive Desktop mirror. It is not required for the current workstation architecture when the Drive Desktop mirror is healthy.

For that fallback, copy `transport-config.example.json` to `transport-config.json` and configure `rclone_exe`, `rclone_remote`, and the Drive folder IDs locally. Do not commit the populated local config.

## Safety semantics

Incoming requests are accepted only when all of the following are true:

- file name is exactly `<job_id>.job.json`;
- `schema_version` is `1`;
- `write_authority` is exactly `NONE`;
- `command_id` is in the configured read-only allowlist;
- file size is below the configured cap;
- no local incoming/processing/terminal/result artifact already exists for the same job.

The preferred mirror transport first copies the mirrored request into staging under the canonical local queue, validates it, then atomically renames it into local `incoming`.

Terminal results are exported only when:

- local file name is exactly `<job_id>.result.json`;
- `runner_write_authority` is exactly `NONE`;
- `state` is `completed`, `failed`, or `rejected`.

For the mirror transport, the result copy is SHA-256 verified before the corresponding mirrored request can be retired. For the rclone fallback, the uploaded Drive result is re-read by name before request retirement.

A Drive/mirror request is retired only **after** a matching terminal result has been copied and verified. Therefore disappearance from Drive `incoming` without a result is never runner success.

## Acceptance test

The transport is not operationally accepted until a fresh post-deployment `sw.status` request travels:

```text
Drive incoming
  -> Drive Desktop mirrored incoming
  -> canonical local remote-queue\incoming
  -> local read-only queue runner
  -> native SOLIDWORKS worker
  -> canonical local remote-queue\results
  -> Drive Desktop mirrored results
  -> Drive results
```

and the terminal record verifies:

- `runner_write_authority: NONE`;
- native/SOLIDWORKS API provenance;
- exact active document title and path.

API/transport success is not mechanical acceptance.
