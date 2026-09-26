# Temporal planning ledger

This append-only ledger keeps intent, observed execution, and replanning separate. It is a GitHub project-state record; it is **not** mechanical evidence and does not grant CAD write authority.

## Record types

- `plan` — a bounded plan with a frozen live-state binding and a dependency graph.
- `divergence_record` — why an earlier plan could not be followed as written.
- `plan_reconciliation` — plan-versus-actual outcomes for a completed observation batch.

Records are never edited to hide history. A change in live CAD state requires a divergence record and a successor plan.

## Authority

- SOLIDWORKS is the authority for live geometry and active-document state.
- GitHub is the authority for versioned source, policy, and this ledger.
- Drive is a mirror/reference surface, never evidence promotion.
- A `Proceed` instruction authorizes continued planning/project-state work only. It does not authorize a SOLIDWORKS write.

Observation identifiers prefixed `OBS_` identify raw read-only connector observations. They are deliberately not treated as admitted EvidenceRecords; successor plans must admit or refresh them before making mechanical claims.

## Current entrypoint

Read `CURRENT_PLAN.json`, then the referenced plan, divergence, and reconciliation records in `ledger/`.


## Stale-evidence replanning proposals

`stale_evidence_replanning.py` is a read-only planning bridge from the
incremental evidence runtime to the functional-temporal next-test model.

It consumes:

- one exact `invalidation_events` row from the existing reasoning DB;
- the corresponding `evidence_validity_projection` rows;
- one validated functional-temporal architecture whose `next_tests` are already declared.

It overlays validity onto a deep copy of the architecture, evaluates the affected
requirements, and filters the existing deterministic next-test ranking to tests
that actually cover requirements directly bound to stale evidence.

It never invents a test. If stale evidence is not bound to the architecture, or
no declared test covers the affected requirement, the result is an explicit gap
rather than an inferred investigation.

The output is a **proposal only**:

- `write_authority: NONE`
- `cad_write_authorized: false`
- `mechanical_acceptance_granted: false`
- `ledger_mutation_performed: false`
- `execution_performed: false`

A proposal must be reviewed before any append-only planning-ledger record or
read execution is created.

Focused regression:

```powershell
cd agent-registry/planning
python -m unittest -v test_stale_evidence_replanning.py
```
