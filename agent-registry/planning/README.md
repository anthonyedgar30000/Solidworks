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

## Cross-source checkpoint freshness

`source_freshness.py` compares one explicitly collected, timestamped snapshot
of live SOLIDWORKS identity, an admitted GitHub evidence record's document
binding, and the Drive canonical identity document's checkpoint. It emits a
JSON observability event on stdout. It does not call any connector, poll a
service, change an EvidenceRecord, or update the ledger. Feed the result to a
telemetry collector only after provenance has been captured for all three
inputs; a GitHub branch head or Drive mirror activity is not a checkpoint
identity.

Example input structure (source refs and times are illustrative, not current
observations):

```json
{
  "schema_version": 1,
  "solidworks": {
    "retrieval_state": "OK", "source_ref": "OBS:exact-status-read",
    "observed_at": "2026-09-27T01:00:00Z",
    "document_title_exact": "IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE",
    "document_path_exact": "C:\\path\\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM"
  },
  "github": {
    "retrieval_state": "OK", "reference_kind": "admitted_evidence",
    "source_ref": "E:exact-evidence-id@commit-sha", "observed_at": "2026-09-27T01:01:00Z",
    "document_title_exact": "IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE"
  },
  "google_drive": {
    "retrieval_state": "OK", "reference_kind": "canonical_identity",
    "source_ref": "drive:exact-file-id-or-revision", "observed_at": "2026-09-27T01:02:00Z",
    "document_title_exact": "IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE"
  }
}
```

Run `python agent-registry/planning/source_freshness.py snapshot.json` from the
repository root. An unavailable source is represented by
`{"retrieval_state":"UNAVAILABLE"}`; a missing live SOLIDWORKS anchor is an
error. `STALE_REFERENCE` means that a reference names an older checkpoint
generation than the live anchor. `SOURCE_CONFLICT` means that a reference
names a different identity at the same or newer generation or contradicts a
bound path/configuration. `UNKNOWN` keeps unavailable references unresolved.
`ALIGNED_AT_CHECKPOINT_LEVEL` means only that the names match at those recorded
instants. None of these states verifies geometry, proves continuing freshness,
or grants mechanical acceptance. The comparator does not authenticate the
caller-supplied references; its output marks them `CALLER_SUPPLIED_UNVERIFIED`.
This event is suitable for later OpenTelemetry
export, but introduces no telemetry service dependency.

Focused regression: `python -m unittest -v test_source_freshness.py` from
`agent-registry/planning`.
