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

### Captured response bundle

`source_freshness_bundle.py` accepts the original JSON responses from three
read-only connector calls. A response bundle has `schema_version: 1` and:

- `solidworks`: `observed_at`, `tool: cadgrounded_solidworks_sw_status`,
  `response` from the status connector;
- `github`: `observed_at`, `repository_full_name`, exact 40-character
  `commit_sha`, runtime EvidenceRecord `path`, its `response`, and
  `current_plan_response` from `agent-registry/planning/CURRENT_PLAN.json`;
  fetch both files at that same pinned commit;
- `google_drive`: `observed_at`, exact canonical `document_id`, and `response`
  from the Google Docs text read, including `revisionId` and paragraphs.

Run `python agent-registry/planning/source_freshness_bundle.py bundle.json`.
The normalizer verifies the Git blob SHA against its content, checks that the
EvidenceRecord is a bounded `VERIFIED` SolidWorks observation, checks exact
subject/payload document binding, requires its `evidence_id` to match
`CURRENT_PLAN.current_evidence_id`, binds the live title to its assembly path,
and reads the single checkpoint in the canonical document's `Freshness rule`
paragraph. A missing or ambiguous statement fails explicitly. It then invokes
the existing point-in-time comparator. It never fetches, changes, or admits
anything itself. Capture timestamps, commit ref, and connector responses are
caller supplied; a content hash or revision ID does not authenticate their
origin. Keep response bundles outside version control when they contain local
paths or sensitive source details.

Focused regression: `python -m unittest -v test_source_freshness_bundle.py`
from `agent-registry/planning`.

### OpenTelemetry event projection

`source_freshness_otlp.py` serializes the point-in-time observation as one
OTLP/JSON `ExportLogsServiceRequest`. It accepts either an existing report or
`--bundle` followed by a captured response bundle:

```text
python agent-registry/planning/source_freshness_otlp.py report.json
python agent-registry/planning/source_freshness_otlp.py --bundle bundle.json
```

The fixed `LogRecord.eventName` is `cadgrounded.source_freshness.checked`.
The resource identifies `cadgrounded-freshness-monitor`. Attributes include
only the status for each source, checkpoint generation numbers, point-in-time
scope, caller-supplied verification state, and the false acceptance flag.
Source paths, titles, refs, document IDs, record content, prompts, and model
data are excluded. A stale, conflicting, or unknown state has WARN severity;
checkpoint-name alignment has INFO severity. No trace ID is invented.

This is a serialization step only: it makes no OTLP network request, does not
run a collector, and does not reclassify the input as trusted. It uses a custom
`cadgrounded.*` event definition because a source checkpoint comparison is not
a GenAI model operation. The event shape follows the OpenTelemetry
[LogRecord/EventName model](https://opentelemetry.io/docs/specs/otel/logs/data-model/),
[OTLP JSON encoding](https://opentelemetry.io/docs/specs/otlp/), and
[event naming guidance](https://opentelemetry.io/docs/specs/semconv/general/events/).
The separate source-freshness report retains detailed provenance for local
review. Keep captured bundles out of version control.

Focused regression: `python -m unittest -v test_source_freshness_otlp.py`
from `agent-registry/planning`.

### Local OTLP receiver

`telemetry/compose.yaml` starts a pinned OpenTelemetry Collector with only an
OTLP/HTTP logs receiver. A one-shot container makes the named volume writable
by the Collector's UID 10001 before it starts. The host port is bound to
`127.0.0.1:4318`. The logs pipeline writes OTLP JSON to that volume with
1 MB rotation, three days of retention, and three backup files. It does not
configure traces, metrics, remote exporters, or a schedule.

From the repository root, with Docker Compose available:

```sh
docker compose -f agent-registry/planning/telemetry/compose.yaml up -d
python agent-registry/planning/source_freshness_send.py --bundle /path/to/captured-bundle.json
docker compose -f agent-registry/planning/telemetry/compose.yaml cp collector:/data/freshness.json /tmp/cadgrounded-freshness.json
docker compose -f agent-registry/planning/telemetry/compose.yaml down
```

Use a captured, read-only response bundle at the pinned current-plan commit.
The sender performs the same normalization and comparison as the existing
bundle CLI, serializes only the bounded event, and sends it by HTTP POST to
`127.0.0.1:4318/v1/logs` with a three-second timeout. An existing freshness
report can be sent without `--bundle`. `--port` changes the local port only,
for a receiver bound on another loopback port. A collector error, partial
success, or unavailable receiver exits with an error. HTTP 200 means the
receiver accepted the request; inspect the exported file to confirm storage.
The separate report retains source provenance. Keep bundles and exported logs
outside version control; the Docker volume survives `down` unless removed
explicitly. The collector accepts any local client on that port, so run this
lane only in a trusted local environment. No collector is run by the sender.

Focused regression: `python -m unittest -v test_source_freshness_send.py`
from `agent-registry/planning`. It exercises an in-process loopback receiver;
the `collector-smoke` CI job also starts the pinned Docker Collector, posts a
synthetic unverified observation, and checks the rotating file export for the
bounded event and false acceptance flag. The CI job deletes its test volume
afterward. A passing CI job verifies this Collector image and configuration on
the Ubuntu runner; it does not prove that any particular Windows host has
started a collector or observed live source freshness.
