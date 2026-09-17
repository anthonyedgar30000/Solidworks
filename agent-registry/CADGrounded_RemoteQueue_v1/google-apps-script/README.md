# Google Apps Script scheduler for CADGrounded Remote Queue v1

This folder adds a Google-side clock to the existing read-only CADGrounded remote queue.

It does **not** connect Google directly to SOLIDWORKS and it does **not** grant CAD write authority.

## Authority boundary

- SOLIDWORKS remains authoritative for live CAD geometry and document state.
- The local CADGrounded remote queue remains authoritative for request validation, stale-state checks, replay rejection, and execution against the native worker.
- Google Drive is transport only.
- Apps Script supplies time-based scheduling only.
- GitHub remains authoritative for the versioned scheduler source and policy.

The script can enqueue only two commands:

1. `sw.status`
2. `sw.query_components`

Every generated job sets:

```json
"write_authority": "NONE"
```

The script deliberately does **not** enqueue transforms, inserts, mates, saves, arbitrary code, or mechanical-acceptance decisions.

## Existing queue assumed by this scheduler

The local queue runner already owns the safety boundary and must remain enabled. Its current flow is:

```text
Google Drive remote-queue/incoming
        |
        v
local synced incoming directory
        |
        v
Invoke-CADRemoteQueue.ps1
        |
        +-- local schema/policy validation
        +-- replay protection
        +-- live sw.status preflight
        +-- exact document preconditions
        v
CadGrounded.SolidWorksWorker.exe
        |
        v
results / logs -> Google Drive mirror
```

Do not replace that runner with Apps Script.

## Why status comes first

`sw.query_components` requires an exact document precondition. Apps Script therefore never guesses the active assembly name.

The scheduler first enqueues `sw.status`. It then reads the newest completed status result returned through Drive. Only when that result is fresh does it emit `sw.query_components`, carrying both:

- `preconditions.document_title_exact`
- `preconditions.document_path_exact`

The local queue performs another live `sw.status` immediately before execution. If the operator changed assemblies in the meantime, the component job is rejected rather than executed against the wrong document.

## Google setup

Create a standalone Google Apps Script project under the same Google account that can access the CADGrounded Drive mirror.

Copy `Code.gs` into the project. Enable the manifest in **Project Settings -> Show "appsscript.json" manifest file in editor** and replace it with the `appsscript.json` in this folder.

Set these Script Properties in **Project Settings -> Script Properties**:

```text
CAD_QUEUE_INCOMING_FOLDER_ID=<Drive folder id for remote-queue/incoming>
CAD_QUEUE_RESULTS_FOLDER_ID=<Drive folder id for remote-queue/results>
CAD_QUEUE_BRIDGE_READY_FILE_ID=<Drive file id for REMOTE_QUEUE_BRIDGE_READY.json>
```

The actual Drive IDs are intentionally not stored in this public repository.

## Safe installation sequence

1. Run `cadGroundedSchedulerDryRun()` manually.
2. Inspect the returned object. It must report `write_authority: NONE` and a valid bridge-ready marker.
3. Run `installCadGroundedScheduler()` manually.
4. Approve the Google Drive permission prompt.
5. Confirm one trigger exists for `cadGroundedSchedulerTick`.
6. Wait for a `gdrive-status-*.job.json` request to appear in `remote-queue/incoming`.
7. Confirm the local runner consumes it and returns a matching `*.result.json` under `remote-queue/results`.
8. Confirm a later tick emits `gdrive-components-*.job.json` with the exact document title/path from the status result.

## Schedule

The installed Apps Script trigger runs every five minutes. Status job IDs are bucketed into ten-minute windows, so repeated trigger invocations do not intentionally create a new status job on every tick.

Apps Script trigger timing is approximate; it should not be treated as a real-time motion/control scheduler.

## Fail-closed behavior

The Google producer refuses to proceed when:

- any required Script Property is missing;
- `REMOTE_QUEUE_BRIDGE_READY.json` has the wrong schema/type;
- the bridge marker does not state `write_authority: NONE`;
- no completed fresh status result exists for the component query;
- the status result lacks an exact document title or path.

The local queue provides the second safety layer and independently rejects unsupported commands, stale/expired jobs, duplicates/replays, and document-precondition mismatches.

## Removing the Google schedule

Run:

```javascript
uninstallCadGroundedScheduler();
```

This removes only triggers whose handler is `cadGroundedSchedulerTick`.

## Mechanical interpretation

A successful scheduled read is evidence that a bounded observation completed. It is **not** evidence of:

- contact;
- seating;
- clearance;
- absence of interference;
- bottle restraint;
- correct product flow;
- labeling functionality;
- mechanical acceptance.

Those remain separate deterministic engineering-verification steps.
