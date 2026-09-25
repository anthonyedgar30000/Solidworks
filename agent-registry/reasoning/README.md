# HELIX Epistemic Project-Health PoC

This is a deliberately small proof-of-concept for the reasoning architecture we discussed.

It models a project as a graph of:

- facts,
- unresolved (`NULL`) values,
- derived claims,
- constraints/invariants,
- acceptance obligations,
- provenance/authority,
- dependency relationships,
- optional Allen temporal relations.

The important idea is that **a NULL is not treated as an empty hole**. The graph around it lets the system determine what project obligations are exposed by not knowing that value.

## Files

- `graph.json` — original illustrative IXOR/AR60 example knowledge graph; its numeric geometry values are PoC placeholders, not live engineering evidence.
- `reasoner.py` — deterministic project-health and exposure propagation.
- `ollama_worker.py` — optional local LLM planner; it can choose the next investigation but cannot verify facts.
- `evidence_ingest.py` — validates and normalizes completed read-only `sw.query_components` observations into evidence transactions.
- `v21_identity_bindings.json` — exact v21 semantic-role to `Component2.Name2` bindings.
- `identity_bindings.py` — validates those exact bindings against admitted live SOLIDWORKS evidence.
- `geometry_projection.py` — calculates conservative AABB relations from admitted exact-identity evidence.
- `graph_projection.py` — creates a fresh runtime epistemic graph from admitted/calculated live evidence without copying toy geometry values.
- `functional_temporal.py` — validates and evaluates generic functional decomposition, interface contracts, temporal states/events/invariants, and deterministic next-test ranking without commanding CAD.
- `cad_interface_contract.py` — validates API-readable CAD interface frames and deterministically derives interface-to-interface displacement without commanding CAD.
- `cad_interface_live_verifier.py` — compares one bounded local native interface observation to a declared contract, preserving `STALE_STATE`, drift, and authority-rejection outcomes rather than rebaselining.
- `cad_interface_consumption.py` — calculates a non-materialized complementary-asset connection transform from accepted interface-frame inputs; it has no CAD-write capability.
- `reference_cases/v42_capture_and_rotation.functional-temporal.v1.json` — v42 fit-check reference case; it preserves capture-owner binding, interval restraint/contact, and reachable-motion clearance as unresolved while recording the fresh 2026-09-25 full inventory.
- `reference_cases/v42_product_flow.cad-interface-contract.v1.json` — v42 candidate product-flow interface contract pairing Published Asset connector identities with API-readable entry/exit coordinate-system frames while leaving connector/frame geometric coincidence unresolved.
- `reference_cases/v42_disposable_complementary_asset_interface_test.v1.json` — v42 design-only complementary receiver frame test; it is not a CAD asset and carries `cad_write_authorized: false`.
- `reference_cases/v42_interface_live_reconciliation_2026-09-25.md` — fresh bridge/document reconciliation preserving the coordinate-system and Published Asset geometry boundary as stale/unresolved until the local native verifier runs.
- `reference_cases/v42_capture_owner_investigation_2026-09-25.md` — evidence-bound v42 capture-owner investigation note, including stale-state limits and the exact next read-only boundary.
- `../docs/V42_CAPTURE_OWNER_BINDING_EVIDENCE_CONTRACT.md` — local-only v42 `sw.query_mates` candidate contract. It defines the exact parentage/constraint evidence required, pre/post no-mutation comparison, and the facts the probe cannot establish.
- `test_reasoner.py` — reasoner regression tests.
- `test_evidence_ingest.py` — evidence-boundary regression tests.
- `test_identity_bindings.py` — exact identity binding regression tests.
- `test_geometry_projection.py` — deterministic AABB projection regression tests.
- `test_graph_projection.py` — live-evidence runtime graph regression tests.
- `test_domain_model_contract.py` — static regression tests for the CADRequest/EvidenceRecord subtype partitions and authority boundaries.
- `test_functional_temporal.py` — functional/temporal architecture regression tests, including stale interval evidence and no-acceptance boundaries.
- `test_cad_interface_contract.py` — CAD-interface regression tests, including the 900 mm +X entry-to-exit product-flow derivation and the connector/frame evidence boundary.
- `test_cad_interface_live_verifier.py` — regression tests for fresh-observation authority, drift detection, stale-state preservation, and no implicit connector/frame geometry proof.
- `test_cad_interface_consumption.py` — regression tests for row-vector connection-transform algebra and the non-materialization boundary.

## Domain Model v1

The candidate domain contract is documented in `../docs/CADGROUNDED_DOMAIN_MODEL_V1.md` with schemas in `../schemas/cad-read-request.v1.schema.json` and `../schemas/evidence-record.v1.schema.json`.

The model separates object type/subtype from epistemic and lifecycle state. `command_id` partitions read-only CAD request subtypes; `evidence_type` partitions evidence subtypes. States such as `UNRESOLVED`, `FIT_CHECK`, and ambiguity buckets remain attributes rather than becoming new object types.

These files are candidate contracts only. They do not change the deployed remote-queue runner or grant additional CAD authority.


## CAD interface contracts

`../schemas/cad-interface-contract.v1.schema.json` defines a candidate,
non-runtime contract for machine-facing CAD interfaces. It is intentionally
separate from the functional-temporal subsystem-interface model.

The v42 reference case pairs:

```text
Connector2 <-> PRODUCT_ENTRY_CS
Connector1 <-> PRODUCT_EXIT_CS
```

The Published References remain the native SOLIDWORKS snapping declarations.
The named coordinate systems provide deterministic API-readable origin and
orientation. Their shared convention is local `+X` product flow, local `+Y`
lateral, and local `+Z` up.

The deterministic consumer derives the saved entry-to-exit relation from the
coordinate-system transforms alone. For the current v42 test assembly that
relation is `[900, 0, 0] mm` in the entry interface frame.

The contract does **not** claim that the public API has verified geometric
coincidence between each `MagneticConnectRef` and its paired coordinate
system. That binding remains explicitly `UNRESOLVED` until authoritative
geometry evidence is available. The contract cannot grant mechanical
acceptance.

### Interface consumption and live verification v1

`../docs/CAD_INTERFACE_CONSUMPTION_LIVE_VERIFICATION_V1.md` documents the
local-only `sw.query_interface_contract` evidence contract. The command returns
only exact requested `CoordSys` and `MagneticConnectRef` feature records and is
not in the Remote Queue. `cad_interface_live_verifier.py` compares that fresh
envelope to the source contract. Missing evidence remains `STALE_STATE`; a
changed document, name/type, or transform becomes `DRIFT_DETECTED`; invalid
authority or mutation declarations are rejected. The verifier never updates
the contract and never promotes Published Asset ↔ coordinate-system geometric
coincidence beyond `UNRESOLVED`.

The disposable complementary-asset test uses a local identity connection frame
and calculates its proposed asset-to-world transform from `PRODUCT_EXIT_CS`.
It is a design-only deterministic calculation, not a CAD insertion or a
mechanical-acceptance claim. Before any future materialization it requires a
fresh live frame verification and separate explicit CAD-write authorization.

Run the focused regression tests from this directory:

```powershell
python -m unittest -v test_cad_interface_contract.py
```

## Functional decomposition + temporal operating states

`../schemas/functional-temporal-architecture.v1.schema.json` defines a
candidate generic model for splitting a machine goal into bounded subsystems,
local obligations, and cross-subsystem interface contracts. It separately
models events, persistent states/modes, transition guards, duration
constraints, Allen relations, and invariants that must survive an interval or
reachable state set. States may carry an optional generic `operating_phase`
classification so a reference case can explicitly distinguish free approach,
capture beginning, captured, label transfer, wrap rotation, release, and free
exit without renaming the state identities. Hypotheses additionally record
affected states and the exact evidence required to resolve them; these fields
define investigations and never promote a hypothesis to fact.

Run the v42 reference case from this directory:

```powershell
python .\functional_temporal.py `
  .\reference_cases\v42_capture_and_rotation.functional-temporal.v1.json `
  --summary
```

The output is an evidence/planning report. It cannot grant mechanical
acceptance, create a CAD write, or promote `UNRESOLVED` evidence. In
particular, a `POINT_ONLY` SOLIDWORKS observation or distance calculation is
not accepted as proof that bottle restraint/contact persists throughout
`CAPTURE_AND_ROTATION`, nor that clearance holds across reachable motion.
The current v42 capture-owner test intentionally has no `cad_request`: parent,
feature/mate, and DOF binding is not in the deployed Remote Queue read-only
command partition. It does declare three `native_read_candidates` for the
existing local `sw.query_mates` worker command. These are not queue jobs: each
is explicitly `remote_queue_authorized: false`, requires independent
no-mutation verification, and remains `CANDIDATE_UNVERIFIED` until the Windows
host runs the bounded verification script. A mate/parentage result is evidence
of CAD connectivity only; it cannot by itself establish preload, force,
physical closure, operating motion, or mechanical acceptance.

### Reference precedence

For the bottle-labeler capture investigation, the v42 reference case and its
fresh evidence records take precedence over the legacy v21 examples below.
The v21 commands and role registry remain useful pipeline examples, but are
not current live-state evidence for the v42 FITCHECK station.

## Run

From this directory:

```powershell
python .\reasoner.py .\graph.json
```

For machine-readable output:

```powershell
python .\reasoner.py .\graph.json --json
```

Run tests:

```powershell
python -m unittest -v
```

If Ollama is running locally:

```powershell
ollama pull qwen2.5:3b
python .\ollama_worker.py .\graph.json --model qwen2.5:3b
```

The Ollama worker defaults to:

```text
http://127.0.0.1:11434/api/chat
```

## Ingest a live read-only SOLIDWORKS observation

Given a completed CADGrounded `sw.query_components` envelope such as:

```text
C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\LIVE_CAD_ALL_COMPONENTS.json
```

run:

```powershell
python .\evidence_ingest.py `
  "C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\LIVE_CAD_ALL_COMPONENTS.json" `
  --expected-document "IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE" `
  --out .\runtime\v21-components-evidence.json `
  --summary
```

The importer admits only a completed `sw.query_components` observation with no reported error, validates component count and exact `Component2.Name2` identity, preserves transform/GetBox/provenance fields, and records a SHA-256 of the raw observation.

A successful import grants **observation authority only**. It explicitly does not establish valid contact, clearance, mechanical suitability, operating sequence, or project acceptance.

## Bind legacy v21 semantic roles to exact live SOLIDWORKS identities

After the evidence transaction exists, run:

```powershell
python .\identity_bindings.py `
  .\runtime\v21-components-evidence.json `
  .\v21_identity_bindings.json `
  --out .\runtime\v21-identity-evidence.json `
  --summary
```

The binding stage requires each configured `Component2.Name2` to match **exactly one** admitted component. Missing or duplicate exact identities are rejected. It copies observed transform/GetBox/provenance fields into the role record but still grants **no mechanical acceptance**.

The legacy v21 role registry includes the exact identities for the IXOR head,
SP100, AR60 roller, AR carriage, GHF120, tie rod, two mounting rods, conveyor,
and five deterministic bottles. It is not a current binding for the v42
FITCHECK capture station.

## Project deterministic geometry facts

After exact identity binding succeeds, run:

```powershell
python .\geometry_projection.py `
  .\runtime\v21-identity-evidence.json `
  --out .\runtime\v21-geometry-projection.json `
  --summary
```

This stage performs deterministic arithmetic on the admitted GetBox-derived approximate axis-aligned bounding boxes. It reports observed transforms/envelopes, per-axis AABB gaps, minimum AABB separation, and AABB overlap relations.

Its authority is intentionally bounded:

- AABB overlap is **not** body interference.
- AABB separation is **not** exact surface clearance.
- It does not establish contact, seating, restraint, product flow, operating sequence, or functional suitability.
- It never grants mechanical acceptance.

The point is to replace toy geometry facts with reproducible calculations while preserving stronger mechanical claims as unresolved until a suitable deterministic SOLIDWORKS check exists.

## Build the legacy v21 epistemic graph

After `v21-geometry-projection.json` exists, build a fresh runtime graph:

```powershell
python .\graph_projection.py `
  .\runtime\v21-geometry-projection.json `
  --out .\runtime\v21-live-graph.json `
  --summary
```

Then run the deterministic reasoner against the live graph:

```powershell
python .\reasoner.py .\runtime\v21-live-graph.json
```

The runtime graph does **not** copy the illustrative `BOTTLE_CENTERLINE`, `AR60_RADIUS`, or `AR60_MAX_TRAVEL = 70` values from the original PoC graph. Live observation-backed transforms/envelopes and deterministic AABB calculations become `KNOWN`; unverified travel, intended application-station geometry, contact, peel-edge relation, bottle restraint, product flow, and acceptance remain unresolved/exposed.

Within the legacy v21 example, the expected highest-value next investigation is
`INTENDED_APPLICATION_STATION_TRANSFORM`. It does not supersede the v42
capture-owner investigation declared above.

## Expected project-health semantics

The deterministic reasoner should distinguish:

```text
OVERALL STATE: EXPOSED
KNOWN VIOLATIONS: none
```

from either `FAILED` or `VERIFIED`.

The key distinction is:

- the project is **not proven failed**;
- the project is **not ready to advance**;
- unresolved engineering facts have explicit downstream risk footprints;
- resolving an unknown may reveal either a valid configuration or a real violation;
- reducing ambiguity is success even if project health becomes worse after stronger evidence is obtained.

That demonstrates the architecture's central idea:

> Unknownness is evaluated by the project obligations it places at risk, not merely by counting missing fields.

## Evidence insertion rule

Do not let the LLM edit a NULL into a known value merely because it guessed one.

A field should transition from:

```json
{
  "value": null,
  "state": "NULL"
}
```

to something such as:

```json
{
  "value": 270.0,
  "state": "KNOWN",
  "authority": "SOLIDWORKS_MEASUREMENT"
}
```

only after authoritative evidence or an accepted deterministic derivation is available.

## Current deterministic pipeline

1. admit live SOLIDWORKS observations;
2. resolve exact semantic identities;
3. calculate bounded deterministic geometry relations;
4. generate a fresh live runtime graph from supported evidence only;
5. preserve contact/clearance/operating claims as `NULL` unless separately proven;
6. run dependency/exposure propagation;
7. choose the next read-only investigation based on remaining risk exposure.

This preserves the boundary that SOLIDWORKS observations establish live state, deterministic checks establish mechanical relationships, and LLMs only help select or formulate investigations.
