# CADGrounded Engineering Sidecars v1

Status: **candidate contract / non-runtime**  
Write authority: **NONE**  
Mechanical acceptance granted: **false**

## Purpose

CADGrounded can use external MCP-enabled engineering tools as bounded deterministic sidecars without turning those tools into engineering authority.

The sidecar pattern is:

```text
authoritative source artifact / accepted inputs
                 |
                 v
      bounded engineering sidecar
                 |
                 v
     deterministic result + provenance
                 |
                 v
         EvidenceRecord admission
                 |
                 v
      CADGrounded dependency graph
                 |
                 v
  SOLIDWORKS verification when geometry matters
```

MCP is transport. It is not authority.

The authority ceiling for every sidecar in v1 is `DETERMINISTIC_CALCULATION`. A sidecar result may support, weaken, or discriminate a hypothesis; it may not silently become `SOLIDWORKS_LIVE_STATE`, may not rewrite OEM evidence, and may not grant mechanical acceptance.

## Why this fits the current project

The live CAD checkpoint at the time this contract was created is:

- `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`
- live path: `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`

This was freshly observed from the SOLIDWORKS API before this branch was created.

V43 is already beyond the original v42 fit-check in project history, but it remains a candidate operating geometry. The sidecar work must therefore help answer unresolved geometry, kinematic, temporal, and product-flow questions without bypassing the existing live-CAD and acceptance gates.

## Selected v1 candidates

### 1. Open CASCADE STEP inspector — first pilot

Repository: `mattmohandiss/cad-mcp-server`

Intended role:

- independently inspect hashed OEM or exported STEP artifacts;
- measure geometry and identify deterministic features;
- compare STEP revisions;
- provide a second-kernel check when useful.

Boundary:

- read-only source access;
- no live SOLIDWORKS observation;
- no CAD mutation;
- no automatic promotion of a result to `VERIFIED`.

Admission mapping:

- `evidence_type = deterministic_calculation`
- `evidence_state = MEASURED_CALCULATED`
- `source_authority = DETERMINISTIC_CALCULATION`
- input hashes must identify the exact STEP artifacts.

This is the safest first integration because it adds deterministic inspection without creating another mutable CAD state.

### 2. FreeCAD MCP — isolated candidate-geometry sandbox

Repository: `blwfish/freecad-mcp`

The current tool surface includes parametric part creation, assemblies and joints, measurement, interference/clearance queries, geometric verification, and snapshot-style fixture regression. It also exposes arbitrary Python execution.

CADGrounded therefore treats it as a **sandbox only**.

Allowed candidate use:

- deterministic bottle/roller/belt/guide/stop geometry;
- assembly-joint experiments;
- candidate motion-limit declarations;
- collision/clearance screening inside the sandbox;
- fixture snapshots and regression comparison;
- neutral STEP/BREP exports for later inspection.

Forbidden governed use:

- opening or writing the authoritative V43 `.SLDASM` / `.SLDPRT` files;
- using `execute_python`, `execute_python_async`, or unrestricted macro execution through the governed adapter;
- treating a FreeCAD assembly solution as proof of SOLIDWORKS assembly state;
- granting mechanical acceptance.

Useful results are still `DeterministicCalculation` evidence with `geometry_state = CANDIDATE_OPERATING` when they concern candidate geometry.

Any candidate worth keeping must return to SOLIDWORKS or another accepted exact B-rep verification path before it can support a geometry-critical acceptance gate.

### 3. OpenModelica / OMEdit MCP — operating-state simulator

OpenModelica 1.27 includes an experimental OMEdit MCP server over local Streamable HTTP. It can modify Modelica model parameters, simulate/re-simulate, and inspect results.

For CADGrounded its role is not geometry creation. Its role is temporal and physical-system investigation.

Candidate V43 questions include:

- bottle entry and capture sequence;
- wrap-belt surface speed versus bottle angular velocity;
- support-roller reaction timing;
- hard-stop/index timing;
- label-transfer interval;
- wrap completion;
- product release;
- failure modes such as slip, incomplete wrap, or an impossible state transition.

The simulator consumes explicit parameters and state assumptions. It does not invent missing geometry or force data. Missing quantities remain unresolved.

A simulation trajectory is `MEASURED_CALCULATED` evidence about the declared model, not proof that the real CAD mechanism reaches that trajectory.

## Evidence admission rules

Every admitted sidecar result must include at least:

1. exact sidecar/tool identity;
2. exact tool version or immutable source revision where available;
3. hashes for all geometry/model/input artifacts;
4. the deterministic method or tool operation;
5. execution timestamp;
6. a durable raw-result reference when available;
7. dependencies linking back to the accepted input evidence records.

A sidecar result is rejected from current decision use when its inputs become stale, even though the historical calculation remains intact.

The existing EvidenceRecord split remains authoritative:

- admission classification stays immutable;
- `temporal_scope.validity_state` controls current applicability;
- downstream findings reopen when a dependency becomes stale.

## Hard authority boundaries

Sidecars may not:

- read SOLIDWORKS live state unless a separately governed adapter is explicitly created for that purpose;
- write SOLIDWORKS;
- mutate OEM source artifacts;
- convert `UNKNOWN` / `UNRESOLVED` to `VERIFIED` merely because a simulation or alternate CAD system produced a plausible result;
- infer mechanical acceptance from solver success;
- become an alternate machine truth database.

SOLIDWORKS remains the live geometry/state authority. GitHub remains source/policy/test/history authority. OEM sources retain their existing authority. Sidecars produce bounded derived evidence.

## Initial integration sequence

### Phase A — contract and catalog

This branch adds:

- `schemas/engineering-sidecar-manifest.v1.schema.json`;
- `sidecars/catalog.v1.json`;
- this architecture document;
- a source-contract regression test.

No external software is installed by this branch.

### Phase B — Open CASCADE pilot

After local installation is explicitly authorized and verified:

1. select one immutable OEM STEP already used in the IXOR investigation;
2. hash it;
3. run a bounded inspection;
4. preserve raw output;
5. normalize one result into a `DeterministicCalculation` EvidenceRecord;
6. compare the result against existing SOLIDWORKS/OEM evidence without overriding it.

Success criterion: deterministic repeatability and clean provenance, not agreement by assumption.

### Phase C — FreeCAD sandbox pilot

Use copied neutral geometry only. Rebuild a small isolated handling fixture:

- D48 x H180 bottle;
- driven wrap-belt plane/solid;
- two support rollers;
- one stop/index element.

Exercise:

- assembly/joint representation;
- interference/clearance checks;
- fixture snapshot;
- repeatability after parameter change and rollback.

Do not import the authoritative V43 SOLIDWORKS assembly as a writable project.

### Phase D — OpenModelica temporal pilot

Create a minimal model from already accepted or explicitly hypothetical inputs:

- conveyor velocity;
- wrap-belt velocity;
- bottle radius;
- capture/release state;
- stop/index state.

Demonstrate that the model preserves unresolved inputs rather than fabricating them and produces a reviewable state/time result.

## Non-goals

Engineering Sidecars v1 does not:

- install MCP servers;
- alter the Remote Queue allowlist;
- add SOLIDWORKS write authority;
- change the V43 assembly;
- create a new mechanical-acceptance gate;
- authorize AI visualization.

## Reference implementation lesson from Fusion 360 MCP

`faust-machines/fusion360-mcp-server` is retained as a design reference, not a selected CAD runtime. Its documented use of MCP tool annotations, structured timeout errors, mutation non-retry behavior, and mandatory state reread after timeout matches CADGrounded's control philosophy.

Those control-plane ideas may be adopted independently of Fusion 360 itself.
