# Read-only synced CAD snapshot relay

## Purpose

This relay provides ordinary Chat sessions with a safe, timestamped SOLIDWORKS read snapshot when the ChatGPT runtime does not permit the developer MCP connection.

It is transport only. SOLIDWORKS remains the live geometry authority. A successful read is not evidence of contact, seating, clearance, interference, restraint, functionality, or mechanical acceptance.

## Safety boundary

The publisher intentionally reuses the existing validated read path:

```text
publish-live-cad-snapshot.ps1
  -> C:\ChatGPT\Solidworks\agent-registry\cad-ask.ps1
  -> local validated intent router
  -> Agent Registry
  -> SOLIDWORKS worker
  -> SOLIDWORKS
```

The publisher does **not** call SOLIDWORKS COM, the registry API, or the worker directly.

Only two hard-coded reads are issued:

1. `What assembly is active?` -> expected `sw.status`
2. `List the top-level components.` -> expected `sw.query_components`

The result is rejected unless each response is one completed JSON object, has data, and matches the expected allowlisted command. There is no automatic retry and no fallback to the full MCP profile.

The publisher does not expose transforms, moves, mates, suppression, save/rebuild/export, arbitrary code, closest-distance/interference measurements, or mechanical approval.

## Output

Default output:

```text
C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\LIVE_CAD_SNAPSHOT.json
```

That path is intended to live inside the existing project mirror so the local sync mechanism can carry the snapshot to Google Drive. If the local mirror uses a different path, pass `-OutputPath` explicitly.

Every output contains:

- schema version
- unique snapshot ID
- UTC publication timestamp
- `source_authority: SOLIDWORKS_LIVE_SNAPSHOT`
- `mechanical_acceptance: NOT_EVALUATED`
- explicit safety flags
- the raw validated `sw.status` snapshot
- the raw validated `sw.query_components` snapshot

The file is written through a temporary file and then renamed into place to reduce the chance of a reader seeing a partial JSON document.

## One-shot use

From the bridge repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish-live-cad-snapshot.ps1
```

Or with an explicit sync destination:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish-live-cad-snapshot.ps1 `
  -OutputPath "C:\path\to\synced\IXOR\LIVE_CAD_SNAPSHOT.json"
```

The script is deliberately one-shot. It does not install a service, start a daemon, or schedule itself.

## Ordinary Chat use

After the file has synchronized, ordinary Chat can read `LIVE_CAD_SNAPSHOT.json` from Google Drive and compare it with `PROJECT_STATE.md`.

Treat the snapshot as fresh live-state evidence only when:

- the timestamp is current for the engineering step,
- both embedded commands completed successfully,
- the active assembly is the expected checkpoint,
- exact `Component2.Name2` identities match the intended components.

Do not infer mechanical correctness from the snapshot.

## Failure behavior

If `cad-ask.ps1` is missing, returns malformed JSON, returns an unallowlisted command, returns a non-completed state, or exits nonzero, the publisher fails without creating a new authoritative snapshot.

No automatic retry is attempted. Repair the read path first; do not broaden permissions as a workaround.
