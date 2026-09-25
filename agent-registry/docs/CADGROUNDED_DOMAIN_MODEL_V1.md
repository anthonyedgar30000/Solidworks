# CADGrounded Domain Model v1

Status: **candidate contract / non-runtime**  
Branch intent: formalize type, subtype, partition, provenance, and state semantics before any runner refactor.

## Purpose

CADGrounded already behaves as a typed system, but several type rules are spread across PowerShell, JSON, evidence normalization, reasoning code, and documentation. Domain Model v1 makes those distinctions explicit so requests and evidence can be validated consistently without granting any new authority.

This model does **not** change SOLIDWORKS geometry, queue write authority, scheduler authority, mechanical acceptance, or LLM authority.

## Core separation

Every governed object answers three different questions:

1. **What is the object?** — supertype.
2. **What specialized kind is it?** — subtype selected by a discriminator/partition attribute.
3. **What is currently known about it?** — state attributes.

Subtype and state are deliberately orthogonal.

Examples:

- `CADRequest` is a supertype; `sw.query_components` is a subtype selected by `command_id`.
- `EvidenceRecord` is a supertype; `solidworks_observation` is a subtype selected by `evidence_type`.
- `VERIFIED`, `UNRESOLVED`, `FIT_CHECK`, and `MECHANICAL_ACCEPTANCE_BLOCKED` are states, not subtypes.

A state change must not silently change object identity or source authority.

## 1. CADRequest supertype

Common attributes belong to every request:

- `schema_version`
- `job_id`
- `command_id`
- `write_authority`
- `created_utc`
- `expires_utc`
- `source`
- `preconditions`
- `payload`

`command_id` is the partition/discriminator attribute.

Current read-only subtypes:

| Subtype | Discriminator | Subtype-only payload |
|---|---|---|
| StatusRequest | `sw.status` | empty payload |
| ComponentQueryRequest | `sw.query_components` | `top_level_only` |
| ClosestDistanceRequest | `sw.closest_distance_pair` | `a_name_exact`, `b_name_exact` |

The subtypes are mutually exclusive. A request is exactly one command subtype.

### CADRequest invariants

- `job_id` is established as request identity before downstream validation such as TTL rejection.
- `write_authority` remains exactly `NONE` for Remote Queue v1.
- document-bound commands require exact document identity preconditions.
- subtype payload fields cannot leak into another subtype.
- unknown/unsupported properties are rejected rather than guessed.

The candidate schema is `agent-registry/schemas/cad-read-request.v1.schema.json`.

The currently deployed remote-queue schema remains the runtime contract until a separately reviewed migration is accepted.

## 2. EvidenceRecord supertype

Evidence from different sources needs the same provenance skeleton even though source-specific payloads differ.

Common attributes:

- `schema_version`
- `record_type`
- `evidence_id`
- `evidence_type`
- `evidence_state`
- `source_authority`
- `source_classification`
- `subject`
- `provenance`
- `dependencies`
- optional `geometry_state`
- optional `temporal_scope`
- optional `ambiguity_bucket`
- `mechanical_acceptance_granted`
- `payload`

`evidence_type` is the partition/discriminator attribute.

Initial subtypes:

| Subtype | Source authority | Typical state |
|---|---|---|
| SolidWorksObservation | `SOLIDWORKS_LIVE_STATE` | `VERIFIED` |
| OEMEvidence | OEM CAD/docs/photo | `VERIFIED` |
| DeterministicCalculation | `DETERMINISTIC_CALCULATION` | `MEASURED_CALCULATED` |
| HumanObservation | `HUMAN_OBSERVATION` | bounded by observation |
| AIVisualizationRecord | `GENERATIVE_AI` | `AI_GENERATED` |

### EvidenceRecord invariants

- evidence records do not themselves grant mechanical acceptance;
- exact SOLIDWORKS observations retain exact document/component identity and API provenance;
- deterministic calculations identify their method, inputs, and result;
- AI-generated records are explicitly AI-generated and cannot become engineering evidence by state promotion;
- dependencies point to the evidence used to support a derived record;
- unresolved information remains unresolved until authoritative evidence or accepted deterministic derivation exists.
- a `temporal_scope` makes the evidence coverage explicit: `POINT_ONLY`,
  `THROUGHOUT_SCOPE`, or `REACHABLE_STATE_SET`, plus `CURRENT`, `STALE`, or
  `UNKNOWN` validity. A point observation is valid evidence of that point; it
  is not silently promoted into proof that a contact, restraint, or clearance
  condition persists through an operating interval.

The candidate schema is `agent-registry/schemas/evidence-record.v1.schema.json`.

## 3. State attributes are not subtypes

The following are examples of state dimensions:

### Epistemic state

- `VERIFIED`
- `MEASURED_CALCULATED`
- `INFERRED`
- `HYPOTHETICAL`
- `UNRESOLVED`
- `AI_GENERATED`

### Geometry lifecycle state

- `SOURCE_GEOMETRY`
- `FIT_CHECK`
- `CANDIDATE_OPERATING`
- `MECHANICALLY_ACCEPTED`
- `NOT_APPLICABLE`

### Ambiguity bucket

- `IDENTITY_AMBIGUOUS`
- `GEOMETRY_UNRESOLVED`
- `KINEMATIC_STATE_UNRESOLVED`
- `MEASUREMENT_REQUIRED`
- `CAD_READ_REQUIRED`
- `OEM_SOURCE_REQUIRED`
- `SOURCE_CONFLICT`
- `MULTIPLE_PLAUSIBLE_HYPOTHESES`
- `INSUFFICIENT_EVIDENCE`
- `STALE_STATE`
- `POLICY_BLOCKED`
- `MECHANICAL_ACCEPTANCE_BLOCKED`

A `SolidWorksObservation` can become stale without ceasing to be a SolidWorks observation. A fit-check object can later become candidate operating geometry without changing its component identity. This is why type and state remain separate.

## 4. Relationship to the epistemic graph

The intended flow is:

```text
CADRequest
  -> produces EvidenceRecord
  -> supports or weakens Finding
  -> resolves / weakens / disproves Hypothesis
  -> updates GateState
```

Dependency edges preserve why a downstream finding exists. If an upstream observation becomes stale or is superseded, dependent findings can be invalidated or reopened deterministically.

## 5. Functional decomposition + temporal operating-state architecture

`functional-temporal-architecture.v1.schema.json` and
`reasoning/functional_temporal.py` add a generic candidate model that sits
beside the existing graph rather than replacing it.

It decomposes a machine goal into:

- bounded **subsystems** with local obligations;
- explicit cross-subsystem **interface contracts**;
- **events** and persistent **states/modes**;
- transition **guards** and duration/watchdog constraints;
- interval **invariants** and Allen temporal relations; and
- hypothesis-linked, deterministic **next tests**.

States may also carry an optional generic `operating_phase` classification such
as `FREE_APPROACH`, `CAPTURE_BEGINNING`, `CAPTURED`,
`LABEL_TRANSFER_INTERVAL`, `WRAP_ROTATION_INTERVAL`, `RELEASE`, or
`FREE_EXIT`. This makes the intended temporal role queryable without changing
the stable identity of a state. A phase label is a model declaration, not
evidence that the machine reached that phase.

This keeps “a subsystem passes locally” distinct from “the machine is
mechanically accepted.” The model always emits
`mechanical_acceptance_granted: false`; its graph fragment intentionally does
not attach itself to a project acceptance obligation. A separately governed
whole-machine gate must decide whether geometry, motion, force/reaction paths,
interfaces, product flow, safety, and acceptance evidence are sufficient.

### Temporal coverage rule

Each obligation/invariant names a scope (`state_ids` and/or `transition_ids`)
and its required coverage:

| Requirement type | Required evidence coverage |
|---|---|
| Snapshot fact | `POINT_ONLY` |
| Contact/restraint that must persist during a state | `THROUGHOUT_SCOPE` |
| Clearance/interference claim over possible mechanism motion | `REACHABLE_STATE_SET` |

The deterministic evaluator rejects a point snapshot as proof of either
interval-wide contact/restraint or reachable-state clearance. If the record is
not freshly bound to the relevant live state, the requirement remains
`UNRESOLVED` with `STALE_STATE`; it is not treated as false and it is not
treated as accepted.

### CADRequest, EvidenceRecord, and hypotheses

A declared next test may carry a `CADRequest` only when it matches the current
read-only v1 command partition and has `write_authority: NONE`. The model does
not invent a new CAD command for temporal reasoning.

Evidence references remain `EvidenceRecord` references. The evaluator checks
their authority, epistemic state, freshness, and temporal coverage without
changing any of those fields. Hypotheses preserve prior
(`COMMON`/`UNCOMMON`/`RARE`), evidence state, and investigation frontier
state; tests may discriminate among them but do not promote them into facts.
Each hypothesis also names its affected operating states and the exact
authoritative observation, document, or bounded calculation needed to resolve
it. That field specifies an investigation; it is never evidence by itself.

When the required observation is outside the deployed read-only CADRequest
partition, the next test remains a planning-only candidate with no
`cad_request`. The model must not invent a queue command or convert a broad
native API capability into an authorized Remote Queue operation.

For a separately reviewed local native observation, a next test may instead
declare `native_read_candidates`. This is a distinct planning object, not a
`CADRequest`: it must retain `write_authority: NONE`,
`remote_queue_authorized: false`, and
`requires_independent_no_mutation_verification: true`. The candidate has no
evidence authority until a host-side pre/post verification produces a reviewable
observation. The v42 `sw.query_mates` candidate follows this boundary; it
cannot be placed in the Remote Queue allowlist merely because the native worker
can compile or return JSON.

The first reference case is v42 `CAPTURE_AND_ROTATION`. It records the current
fit-check evidence while preserving capture kinematic ownership, preload,
reaction-force path, interval restraint/contact, and reachable motion
clearance as unresolved. It does not alter live CAD geometry.


### CAD interface contract

`../schemas/cad-interface-contract.v1.schema.json` and
`reasoning/cad_interface_contract.py` define a separate candidate contract for
machine-facing CAD interfaces. This contract is deliberately distinct from the
functional-temporal subsystem `interface` object.

A CAD interface contract pairs two evidence channels without collapsing their
authority:

- a SOLIDWORKS Published Reference / Asset Publisher connector for native
  snapping and human-visible interface declaration; and
- an API-readable named coordinate system for deterministic origin/orientation
  consumption, logging, comparison, and regression testing.

The pairing preserves separate evidence states. A connector identity and its
human-established semantic role may be verified while exact geometric
coincidence between the `MagneticConnectRef` and the named coordinate system
remains `UNRESOLVED` unless a suitable authoritative API or deterministic
binding proves it.

The v42 reference fixture is
`reasoning/reference_cases/v42_product_flow.cad-interface-contract.v1.json`.
It records:

- `Connector2` ↔ `PRODUCT_ENTRY_CS`;
- `Connector1` ↔ `PRODUCT_EXIT_CS`;
- local `+X` = product flow, `+Y` = lateral, `+Z` = up; and
- a deterministic entry-to-exit displacement of `[900, 0, 0] mm` in the
  entry interface frame.

The contract is a geometry/interface declaration only. It does not establish
product restraint, collision-free motion, label-transfer correctness,
mechanical suitability, or mechanical acceptance.

## 6. Authority boundary

This model does not change the authority hierarchy.

- SOLIDWORKS remains live geometry/state authority.
- GitHub remains source/policy/test/history authority.
- Google Drive remains mirror/reference/transport.
- OEM evidence retains its established source authority.
- deterministic calculations may derive bounded facts from accepted inputs.
- Ollama/LLMs may classify or propose investigations but cannot change UNKNOWN to VERIFIED.
- generative imagery remains visualization only.

API success is not mechanical acceptance.

## 7. Migration plan

### Phase 1 — this branch

- formalize request and evidence supertypes/subtypes;
- add candidate JSON Schemas;
- add contract regression tests;
- make no deployed runner changes.

### Phase 2 — separate reviewed change

- compare the deployed `cad-job.schema.json` against the candidate request schema;
- migrate only if behavior is equivalent or deliberately improved;
- validate existing scheduler/Drive fixtures;
- run local PowerShell parser and queue regression tests;
- reread CURRENT main before deployment.

### Phase 3

- have evidence normalization emit canonical `EvidenceRecord` objects;
- preserve backward-compatible transaction envelopes during migration;
- connect evidence dependencies to the epistemic graph.

### Phase 4 — separate reviewed change

- admit functional-temporal architecture documents through a reviewed
  registry path;
- bind their EvidenceRecord references to a current CAD world/revision;
- use the resulting graph fragment for read-only next-test planning;
- keep whole-machine acceptance outside the evaluator.

## Acceptance criteria for Domain Model v1

The model is useful only if it makes invalid states harder to represent:

- exactly one request subtype per request;
- exactly one evidence subtype per evidence record;
- subtype-only fields are required only where applicable;
- state attributes remain independent of subtype identity;
- AI evidence cannot masquerade as deterministic or SOLIDWORKS evidence;
- evidence cannot directly grant mechanical acceptance;
- UNKNOWN/UNRESOLVED is preserved;
- exact identities and provenance remain mandatory where authority depends on them.
- a point observation cannot masquerade as interval-wide or reachable-motion
  proof;
- a stale evidence record reopens the dependent claim instead of silently
  authorizing it;
- a local subsystem result cannot create whole-machine mechanical acceptance.
