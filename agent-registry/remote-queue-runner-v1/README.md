# CADGrounded Remote Queue v1

A deliberately narrow, read-only transport layer for CADGrounded.

The queue accepts declarative JSON jobs and invokes the existing native
`CadGrounded.SolidWorksWorker.exe` through its `execute-json` command. The remote
queue never executes downloaded `.ps1`, `.bat`, `.cmd`, or `.exe` files.

## v1 allowlist

- `sw.status`
- `sw.query_components`
- `sw.closest_distance_pair`

These are the commands currently implemented by the native C# worker. v1 does
not expose the experimental PowerShell B-rep/topology probes. Port those into
the native worker as separately reviewed read-only commands before adding them
to this queue.

## Trust boundary

Recommended flow:

    ChatGPT / operator
          |
          v
    Google Drive transport
          |
          v
    remote-queue\incoming\       JSON only
          |
          v
    Invoke-CADRemoteQueue.ps1
          |
          +--> schema/policy validation
          +--> replay check
          +--> live sw.status preflight
          +--> exact document preconditions
          |
          v
    native C# SOLIDWORKS worker
          |
          v
    results\ + logs\

Google Drive is transport only. SOLIDWORKS remains live geometry authority.

## Suggested local install directory

Extract this package to:

    C:\ChatGPT\Solidworks\agent-registry\remote-queue-runner-v1

The default queue itself is:

    C:\ChatGPT\Solidworks\remote-queue

Created subdirectories:

    incoming\
    processing\
    completed\
    failed\
    rejected\
    results\
    logs\

## Google Drive sync recommendation

Sync **job JSON files only** from your Drive mirror into:

    C:\ChatGPT\Solidworks\remote-queue\incoming

Sync local results/logs back toward Drive if desired:

    C:\ChatGPT\Solidworks\remote-queue\results
    C:\ChatGPT\Solidworks\remote-queue\logs

Avoid bidirectional "delete propagation" on the queue if your existing sync
script can be configured that way. The local runner moves consumed requests out
of `incoming`, and remote deletion semantics should not resurrect old jobs.

Do not sync executable files into `incoming`.

## Install

After reviewing the scripts:

    cd C:\ChatGPT\Solidworks\agent-registry\remote-queue-runner-v1

If Windows marks the downloaded scripts as Internet files and you trust the
package after review:

    Get-ChildItem .\*.ps1 | Unblock-File

Verify `queue-config.json`, especially `queue_root` and `worker_exe`.

Run a local read-only smoke test:

    .\Test-CADRemoteQueue.ps1

The test creates a single `sw.status` JSON job, runs one queue pass, and prints
the result.

Install a one-minute scheduled task:

    .\Install-CADRemoteQueueTask.ps1

Inspect it:

    Get-ScheduledTask -TaskName 'CADGrounded Remote Queue ReadOnly'

Remove it:

    .\Uninstall-CADRemoteQueueTask.ps1

## Job safety rules

The runner rejects a job when:

- schema version is not 1
- `job_id` contains unsafe/path characters
- command is not locally allowlisted
- `write_authority` is not exactly `NONE`
- payload contains unknown command-specific fields
- required exact document precondition is absent
- live SOLIDWORKS document fails the exact precondition
- job is expired
- a terminal result already exists for the same `job_id`
- incoming file is a reparse point/symlink
- file exceeds the configured size cap

`sw.closest_distance_pair` still has its original epistemic limitation:
zero distance means zero metric separation; it does not independently prove
contact versus physical overlap.

## Adding future geometry/topology reads

Do not point the queue at arbitrary PowerShell probes.

Preferred migration:

1. implement a narrow read-only command in the native C# worker
2. add it to the worker hard allowlist
3. define an exact JSON payload contract
4. test it manually against the correct live assembly
5. add the same command and validator to this queue
6. only then permit remote jobs for it

That keeps the control path deterministic and auditable.
