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
