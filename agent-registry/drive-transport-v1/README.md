# CADGrounded Drive Transport v1

This package fills the missing transport hop between the Google Drive queue folders and the canonical local CADGrounded queue.

It is deliberately **not** a CAD controller. It cannot call SOLIDWORKS, execute arbitrary downloaded code, move components, insert parts, create mates, save documents, or make mechanical-acceptance decisions.

## Authority boundary

- SOLIDWORKS remains live geometry authority.
- `Invoke-CADRemoteQueue.ps1` remains the local request-validation/execution authority.
- GitHub remains version/history authority.
- Google Drive remains transport only.
- This transport agent only copies validated JSON request/result artifacts.

Canonical local queue root:

```text
C:\ChatGPT\Solidworks\agent-registry\remote-queue
```

## Dependency

The transport uses an existing authenticated `rclone` Google Drive remote. This keeps Google OAuth credentials out of the repository and out of the transport script.

Create a local `transport-config.json` from `transport-config.example.json` and set:

- `rclone_exe`
- `rclone_remote`
- `drive_incoming_folder_id`
- `drive_results_folder_id`

Do **not** commit the populated local config. The real Drive folder IDs remain deployment state, not public source.

## Safety semantics

Incoming requests are accepted only when all of the following are true:

- file name is exactly `<job_id>.job.json`;
- `schema_version` is `1`;
- `write_authority` is exactly `NONE`;
- `command_id` is in the configured read-only allowlist;
- file size is below the configured cap;
- no local incoming/processing/terminal/result artifact already exists for the same job.

The transport downloads to a staging file, validates it, then performs an atomic local rename into `remote-queue\incoming`.

Terminal results are uploaded only when:

- the local file name is exactly `<job_id>.result.json`;
- `runner_write_authority` is exactly `NONE`;
- `state` is `completed`, `failed`, or `rejected`;
- `request_file_name`, when present, is a safe basename.

A Drive request is deleted only **after** the matching terminal result has been uploaded and verified in the Drive results folder. Therefore disappearance from Drive `incoming` without a result remains a transport failure, never success.

## Installation

1. Configure an authenticated rclone Google Drive remote under the same Windows user that will run the task.
2. Copy `transport-config.example.json` to `transport-config.json` and fill the local-only values.
3. Run a dry pass:

```powershell
.\Invoke-CADDriveTransport.ps1 -ConfigPath .\transport-config.json -DryRun
```

4. Run a live transport pass:

```powershell
.\Invoke-CADDriveTransport.ps1 -ConfigPath .\transport-config.json
```

5. Install the one-minute task:

```powershell
.\Install-CADDriveTransportTask.ps1 -ConfigPath .\transport-config.json
```

## Acceptance test

The transport is not accepted until a fresh post-deployment `sw.status` request travels:

```text
Drive incoming
  -> local remote-queue\incoming
  -> local read-only queue runner
  -> native SOLIDWORKS worker
  -> local remote-queue\results
  -> Drive results
```

and the terminal record verifies:

- `runner_write_authority: NONE`;
- native/SOLIDWORKS API provenance;
- exact active document title and path.

API/transport success is not mechanical acceptance.
