# CADGrounded Reasoning Database v0

This is a semantic and inference layer for CADGrounded. SQLite is only the
storage substrate; the database contract is built around evidence, relations,
worlds, contradictions, derivations, and discovery.

## Primitive records

1. `World` — one bounded modeled world, such as a specific SOLIDWORKS assembly/revision.
2. `Entity` — component, body, process step, sensor, bottle, relation target, etc.
3. `Interval` — valid-time or other bounded interval.
4. `Observation` — append-only evidence received from SOLIDWORKS, a human, or another source.
5. `Assertion` — subject/predicate/object or subject/predicate/literal plus independent support channels.
6. `QualitativeRelation` — Allen or RCC8 relation with evidence and provenance.
7. `Constraint` — hard/soft/critical invariant or goal expression.
8. `Derivation` — proof edge from premises to a conclusion.
9. `Action` — proposed/read/authorized operation with explicit authority.
10. `DiscoverySignal` — evidence that the current model may be incomplete.

## Epistemic semantics

Assertions do not store one Boolean truth value. They store two independent
support channels:

```text
supports_true  supports_false  state
0              0               neither
1              0               true_only
0              1               false_only
1              1               both
```

`both` is preserved rather than overwritten. Evidence authority decides which
claims are usable for a particular proof without deleting contradictory history.

Evidence order in v0:

```text
unknown
< inferred
< approximate_getbox
< verified_solidworks_api
< human_mechanical_review
```

## Open-world rule

Absence of an assertion does not imply false.

- represented but unanswered -> known unknown
- evidence exists but has not been mapped -> operational unknown-known
- concept/question not represented -> unknown unknown, which cannot be enumerated directly

Unknown unknowns are approached through `DiscoverySignal` records such as
selector ambiguity, document mismatch, unexpected component, unexplained
interference, or exact-vs-approximate disagreement.

## Allen interval algebra

The v0 vocabulary contains the 13 basic relations:

```text
before, meets, overlaps, finished_by, contains, starts, equals,
started_by, during, finishes, overlapped_by, met_by, after
```

The CLI includes deterministic interval classification and converse generation.

The **full Allen composition table and path-consistency closure are deliberately
not implemented in v0**. They belong in the next inference layer and should be
added with tests against a verified composition table.

Allen relations may be stored with axis `time`, or applied independently to
`x`, `y`, and `z` intervals for qualitative spatial screening.

## RCC8

The v0 topology vocabulary is:

```text
dc, ec, po, tpp, ntpp, eq, tppi, ntppi
```

RCC8 relations are stored as evidence-bearing observations/derivations. The
database does not infer RCC8 directly from arbitrary SOLIDWORKS BREP in v0.

## Temporal model

`observed_at` and `recorded_at` capture knowledge time. `valid_interval_id`
captures modeled valid time. `world_id` + `revision` scopes evidence to a CAD
world so stale evidence from another assembly does not silently authorize a
decision.

## Safety boundary

This database does not execute CAD operations. `actions.authority` can record:

```text
none
read
write_proposed
write_authorized
```

but an entry marked `write_authorized` is not itself sufficient to cause an
operation. The registry/worker safety policy remains authoritative.

## Quick start

```powershell
cd C:\ChatGPT\Solidworks\agent-registry\reasoning-db

py -3 .\reasoning_db.py init
py -3 .\reasoning_db.py selftest
```

Create a world and entities:

```powershell
py -3 .\reasoning_db.py world `
  --id ixor-v21 `
  --title IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE `
  --source-system solidworks

py -3 .\reasoning_db.py entity `
  --id ar60-2 --world ixor-v21 --kind component `
  --name 6130460_03_AR60_NATIVE_PORTABLE_V18-2

py -3 .\reasoning_db.py entity `
  --id bottle3 --world ixor-v21 --kind product `
  --name BENCH_BOTTLE_D48_H180-3
```

Record conflicting evidence without overwriting either observation:

```powershell
py -3 .\reasoning_db.py assert `
  --world ixor-v21 --subject ar60-2 --predicate physically_interferes `
  --object bottle3 --true-support --evidence approximate_getbox

py -3 .\reasoning_db.py assert `
  --world ixor-v21 --subject ar60-2 --predicate physically_interferes `
  --object bottle3 --false-support --evidence verified_solidworks_api

py -3 .\reasoning_db.py proposition `
  --world ixor-v21 --subject ar60-2 --predicate physically_interferes `
  --object bottle3
```

The proposition state is `both`; provenance remains visible.

Classify Allen relations deterministically:

```powershell
py -3 .\reasoning_db.py allen-classify 0 2 1 3
```

returns `overlaps`, with inverse `overlapped_by`.

Record discovery pressure:

```powershell
py -3 .\reasoning_db.py discovery `
  --world ixor-v21 `
  --kind selector_ambiguity `
  --severity high `
  --detail '{"selector":"AR60","matches":2}'
```

## Next inference milestone

v0.1 should add:

1. full Allen composition table,
2. relation-set representation rather than only one basic relation,
3. path-consistency propagation,
4. contradiction creation when a relation set becomes empty,
5. proof/WHY query returning derivation graph + evidence,
6. model-completeness gate that blocks `solved` while critical discovery signals are open,
7. adapter that ingests `cad.ps1` read snapshots into append-only observations.
