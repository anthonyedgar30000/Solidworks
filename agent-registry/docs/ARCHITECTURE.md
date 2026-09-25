# CADGrounded Shared Agent Registry v1 Architecture

## Layering

```text
GitHub
  versioned intent / code / policy / schemas / tests
        |
        v
Shared Agent Registry (FastAPI + SQLite)
  agents / documents / tasks / jobs / results / locks / events
        |
        v
CAD execution adapter
  MCP / local REST / CLI / bridge transport
        |
        v
SOLIDWORKS
  geometry authority
```

Google Drive is a project mirror and document backup surface. It is not used for locks, leases, job claiming, document revisions, or other transactional state.

## Domain contracts

`CADGROUNDED_DOMAIN_MODEL_V1.md` formalizes the registry's typed boundary using `CADRequest` and `EvidenceRecord` supertypes. Request and evidence subtypes are selected by explicit discriminator attributes, while epistemic state, geometry lifecycle state, and ambiguity remain orthogonal state attributes.

The v1 domain model is a candidate contract and does not itself expand runtime or CAD authority.

## Functional and temporal reasoning boundary

`functional-temporal-architecture.v1.schema.json` adds a candidate
reasoning-only layer for decomposing a machine goal into subsystems, local
obligations, interface contracts, events, persistent states/modes, transition
guards, duration constraints, and interval/reachable-motion invariants. Its
deterministic evaluator can project a dependency fragment into the epistemic
graph and rank declared read-only investigations.

It cannot modify SOLIDWORKS, invoke a queue worker, expand the CADRequest
allowlist, change EvidenceRecord states, or grant mechanical acceptance. A
subsystem's `LOCAL_VERIFIED` result is specifically not a whole-machine
acceptance result. Point evidence is not silently reused as proof of a
throughout-state or reachable-motion requirement, and stale evidence remains
explicitly `STALE_STATE` for current-decision purposes.

## Write transaction

A state-changing operation is accepted only when all of the following hold:

1. The requesting agent has the required capability.
2. The document write lease is valid.
3. The request carries the current monotonic fencing token.
4. `expected_revision` equals the registry document revision.
5. The idempotency key has not already produced a terminal result.
6. The live SOLIDWORKS document identity still matches the grounded document record.
7. Command-specific preconditions pass.
8. Any required CADGrounded preflight succeeds.

After execution, the bridge rereads live state before recording success. A successful API call alone does not establish mechanical correctness.

## Revision model

Read-only commands do not increment the document revision.

Accepted writes increment the logical document revision exactly once after post-write state verification. A timed-out command is treated as indeterminate until the bridge rereads live SOLIDWORKS state.

Manual or out-of-band edits in SOLIDWORKS must be detected through document events or a state fingerprint check. When detected, the registry advances/invalidate state and emits an audit event before another agent write can proceed.

## Lease fencing

Each newly acquired document write lease receives a monotonically increasing `fence_token`.

Example:

```text
lease A -> fence 81
lease A expires
lease B -> fence 82
late command from lease A carrying 81 -> reject
```

This prevents a paused or crashed executor from resuming with stale authority.

## Idempotency

Every write job has an immutable `idempotency_key`. A retry using a key that already reached a terminal state returns the existing result instead of executing the CAD operation again.

This is required for operations such as component insertion where a network timeout does not prove the first attempt failed.

## Baseline lineage

Versioned CAD baselines are immutable by default. `save_as` creates a child document record rather than mutating the source identity:

```text
ixor-v17 @ revision N
        |
        +-- derived_from --> ixor-v18-working @ revision 1
```

The lineage record stores the source document ID, source revision, resulting document ID, exact path, and timestamp.

## Command privilege classes

```text
READ
  sw.status
  sw.query_components
  future sw.measure

WRITE_SAFE
  sw.set_transform
  sw.insert_component
  future sw.rebuild
  future sw.create_mate

WRITE_DOCUMENT
  future sw.save_as

EXEC_PRIVILEGED
  sw.execute_code
```

Raw `sw.execute_code` is not granted to ordinary executor agents. Rebuild, save, mate, interference, and measurement operations should become registered fixed handlers so a local LLM normally selects bounded commands rather than synthesizing arbitrary C#.

## v1 implementation order

1. SQLite schema and FastAPI service.
2. Agent heartbeat and command discovery.
3. Document registration/readback.
4. Read-only adapter for `sw.status`.
5. Read-only adapter for `sw.query_components`.
6. Lease + fencing + revision + idempotency enforcement.
7. First protected write: `sw.set_transform`.
8. Protected component insertion.
9. Fixed handlers for rebuild, save-as, mates, measurements, and interference checks.
10. Result packages and durable audit exports.

## Four questions the registry must always answer

- WHO is acting?
- WHAT are they allowed to do?
- WHAT CAD state are they acting upon?
- WHAT actually happened?
