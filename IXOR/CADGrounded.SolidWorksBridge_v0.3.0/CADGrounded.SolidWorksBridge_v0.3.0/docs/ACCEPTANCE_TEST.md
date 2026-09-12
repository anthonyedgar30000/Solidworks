# Acceptance Test — IXOR Benchmark v1.1 Bridge

This is the first bridge acceptance sequence for the current deterministic benchmark.

## Gate A — SOLIDWORKS add-in is alive

With `IXOR_Benchmark_v11.SLDASM` active:

```powershell
cd src\mcp-server
node scripts\pipe-smoke.mjs sw_status
```

Pass criteria:

- response `ok=true`;
- bridge version `0.1.0`;
- active document title contains `IXOR_Benchmark_v11`;
- document type is `assembly`.

## Gate B — canonical component state is read back

Run:

```powershell
node scripts\pipe-smoke.mjs sw_query_components
npm run verify:benchmark
```

`verify:benchmark` compares the live API readback against `docs/CURRENT_BENCHMARK_EXPECTED.json` and fails closed on transform/fixed-state or sanity-envelope drift.

The current benchmark was last verified in SOLIDWORKS with these top-level states.

### IXOR_6130800_NATIVE-1

Classification: deterministic benchmark transform, re-read from SOLIDWORKS API.

```text
Fixed: true
Rotation9:
[1, 0, 0,
 0, 0, 1,
 0,-1, 0]
Translation mm:
[154.240, -200.000, 1000.000]
```

Approximate SOLIDWORKS `GetBox` envelope:

```text
Min [-78.760, -360.325, 948.000]
Max [416.240, -143.000, 1541.000]
```

### 5983425_01_Floor_stand_Bodenstativ_1632.stp-1

Classification: deterministic benchmark transform, re-read from SOLIDWORKS API.

```text
Fixed: true
Rotation9:
[1, 0, 0,
 0, 0, 1,
 0,-1, 0]
Translation mm:
[0.000, 0.000, 0.000]
```

Approximate SOLIDWORKS `GetBox` envelope:

```text
Min [-324.000, -692.500, 0.000]
Max [324.000, 217.500, 1682.000]
```

`GetBox` is a sanity/orientation check and is explicitly not promoted to precision geometry authority.

## Gate C — MCP server sees the same state

Start read-only server:

```powershell
npm install
npm start
```

Connect through the supported private/remote MCP path and call:

```text
sw_status
sw_query_components
```

Pass criteria: the values returned through MCP match Gates A/B.

## Gate D — dry-run write contract

Call `sw_set_transform` for the IXOR with its *existing* canonical transform and `apply=false`.

Pass criteria:

- no geometry moves;
- response says `applied=false` and `dry_run=true`;
- before state comes from the live SOLIDWORKS API;
- proposed state exactly contains the requested transform.

## Gate E — actual write deferred to next floating component

Do not move the already-frozen IXOR or stand just to exercise a write.

The first live write should be an intentionally inserted **floating** OEM application component, after its identity/source state is inspected. Recommended next candidate: SP100.

For that test:

1. keep the component floating;
2. query exact `Name2` and before transform;
3. capture `expected_document_title` from `sw_status`;
4. construct complete `expected_before` from the API result;
5. enable `SWBRIDGE_ALLOW_WRITES=1`;
6. call `sw_set_transform` with `apply=true`;
7. require `applied_and_reverified` result;
8. inspect the audit record;
9. run the project's mechanical/source checks before fixing or freezing the component.
