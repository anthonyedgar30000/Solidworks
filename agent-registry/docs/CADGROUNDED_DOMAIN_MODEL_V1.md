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

## 5. Authority boundary

This model does not change the authority hierarchy.

- SOLIDWORKS remains live geometry/state authority.
- GitHub remains source/policy/test/history authority.
- Google Drive remains mirror/reference/transport.
- OEM evidence retains its established source authority.
- deterministic calculations may derive bounded facts from accepted inputs.
- Ollama/LLMs may classify or propose investigations but cannot change UNKNOWN to VERIFIED.
- generative imagery remains visualization only.

API success is not mechanical acceptance.

## 6. Migration plan

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
