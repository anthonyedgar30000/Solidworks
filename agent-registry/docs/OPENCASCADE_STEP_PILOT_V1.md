# Open CASCADE STEP Pilot v1 — CAB AL Carriage 6130648

Status: **prepared / not executed**  
Sidecar: `opencascade-step-inspector`  
Mechanical acceptance: **not granted**

## Purpose

Run the first CADGrounded engineering-sidecar pilot against one immutable OEM STEP artifact and determine whether an independent Open CASCADE-based reader can produce repeatable, provenance-preserving geometry measurements without changing CAD state or bypassing SOLIDWORKS authority.

This pilot is deliberately narrow. It does not attempt to model the whole labeler and it does not touch V43.

## Input artifact

Exact source artifact:

`C:\ChatGPT\Solidworks\IXOR\6130648_01_Carriage_Schlitten_AL (2)\6130648_01_Carriage_Schlitten_AL.stp`

Expected SHA256:

`bfcd381045f4e115be81ea22a349dfeccc6453ae49a00acab25c547205b50c5b`

The historical project evidence identifies this as the correct CAB AL carriage source for the left-hand IXOR/SP100 arrangement.

The file hash is an execution precondition. If it differs, stop. Do not inspect a same-named artifact and assume identity.

## Why this artifact

The AL carriage is a useful pilot because prior deterministic work already established several geometry facts that can be compared without making those facts pass/fail assumptions for the sidecar itself:

- the STEP imported as one solid body;
- nominal roller-mount bore diameter: approximately `7 mm`;
- roller-mount bore depth: approximately `8 mm`;
- pivot-to-roller-mount radius: `77.000 mm`.

These are **historical comparison targets**. The Open CASCADE result must be recorded independently even if it disagrees.

A disagreement is evidence worth investigating, not permission to force either source to match.

## Tool under test

Pinned initial package:

`cad-mcp-server@0.6.1`

Reference launch command:

`npx -y cad-mcp-server@0.6.1`

The upstream server describes itself as local-first and read-only, using an Open CASCADE kernel and exposing a small STEP-inspection surface including `inspect_step`, `find_faces`, `find_edges`, `measure_geometry`, and `diff_step`.

CADGrounded uses only the bounded inspection subset needed for this pilot.

## Execution phases

### 0. Host preflight

Before starting the MCP server:

1. confirm the exact STEP path exists;
2. calculate SHA256 and compare it to the expected hash;
3. verify Node.js major version is at least 24;
4. record the exact `cad-mcp-server` package version selected;
5. create a dedicated result directory;
6. do not open or save the STEP in a mutating CAD editor as part of the pilot.

The preparation script is:

`agent-registry/sidecars/opencascade/Prepare-OpenCascade-Step-Pilot-V1.ps1`

It performs only the host preflight. It does **not** install or launch the MCP server.

### 1. Independent STEP observation

Use the pinned MCP server through an MCP-capable client and capture the raw responses for:

1. `inspect_step` — overall model/body/topology summary;
2. `find_faces` — cylindrical faces relevant to the roller-mount bore;
3. `measure_geometry` — measurements needed to characterize the selected bore and pivot-to-mount relationship when the tool surface supports them.

No query should contain the historical expected values as instructions to the measurement tool. The tool should be asked to measure the geometry, not confirm a number.

### 2. Raw-result preservation

Preserve the exact tool name, request arguments, complete response, package version, execution UTC, and input STEP SHA256.

No normalized EvidenceRecord is admitted until the raw responses are durably preserved.

### 3. Deterministic comparison

Compare the independent result against historical project measurements.

Classification per target:

- `AGREE_WITHIN_DECLARED_TOLERANCE`
- `DISAGREE`
- `NOT_MEASURABLE_WITH_CURRENT_TOOL_SURFACE`
- `AMBIGUOUS_FEATURE_IDENTITY`

Do not silently select the cylinder whose diameter happens to be closest to 7 mm. The bore must be identified from topology/location evidence, or the claim remains ambiguous.

### 4. Evidence admission

Only after review should the normalized sidecar result enter the CADGrounded evidence system as:

- `evidence_type = deterministic_calculation`
- `evidence_state = MEASURED_CALCULATED`
- `source_authority = DETERMINISTIC_CALCULATION`
- `source_classification = opencascade_step_inspection`
- `geometry_state = SOURCE_GEOMETRY`
- `mechanical_acceptance_granted = false`

The OEM STEP itself retains higher source authority than the sidecar's interpretation of it.

The result is **not** a `SolidWorksObservation`.

## Success criteria

The pilot succeeds as infrastructure when the input artifact is exact-hash bound, the external tool remains read-only, identical requests are repeatable, raw output is preserved, normalized evidence names exact provenance, disagreement is preserved rather than corrected by assumption, and no result grants mechanical acceptance.

Agreement with previous measurements is useful diagnostic evidence but is not required for the infrastructure pilot to be considered well-controlled.

## Stop / escalation rules

Stop the pilot and classify it rather than improvising when the input hash is wrong, feature identity is ambiguous, the server cannot expose the needed measurement, units or coordinate conventions are unclear, the result changes between repeated runs with identical input, or any tool call attempts mutation.

Recommended ambiguity buckets are `IDENTITY_AMBIGUOUS`, `MEASUREMENT_REQUIRED`, `SOURCE_CONFLICT`, or `INSUFFICIENT_EVIDENCE` as applicable.

## Relationship to V43

A fresh live read immediately before preparation confirmed the active SOLIDWORKS document is `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`.

This pilot makes **no claim** about V43 kinematics, capture closure, reaction-force path, bottle restraint, operating-state reachability, or mechanical acceptance.

It is a sidecar infrastructure proof using one OEM source artifact.

## Post-pilot topology clarification

The original comparison IDs `AL.ROLLER_MOUNT_BORE_DIAMETER` and `AL.ROLLER_MOUNT_BORE_DEPTH` retain the wording used when the pilot was prepared. They are **historical comparison labels, not current geometry semantics**.

Subsequent bounded Open CASCADE topology refinement against the same exact-hash OEM STEP established that the candidate nominal Ø7 feature is represented by two coaxial trimmed cylindrical patches (`face:160` and `face:161`) with an 8 mm axial extent, not a complete or blind cylindrical bore. The frozen deterministic bundle records 258.492266° of sectional cylindrical coverage, two opposed sampled void regions at a 4 mm probe radius, and a 77.000000000 mm separation from the `face:3` Ø10 reference axis.

Frozen bundle root SHA256:

`dc9cb4cc01a30dfd90ea88997f877d671fdfede0eecb30910b0bf894a6062ac4`

This clarification does **not** independently verify that the partial cylindrical feature is functionally the roller mount, does **not** independently verify that `face:3` is the functional pivot, does **not** create a SolidWorksObservation, and does **not** grant mechanical acceptance. Those semantic identities remain supported but unresolved until bound by authoritative evidence.

