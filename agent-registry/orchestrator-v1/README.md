# CADGrounded frontier runner v1

This is a small unattended, **read-only** projector for PLAN-0010's source-acquisition frontier. It consumes five exact versioned repository inputs, checks their IDs, dependency and authority bindings, candidate-selection state, point-only coverage, and v43 document/configuration binding. It creates one immutable task proposal per distinct input snapshot. A stale record, moved plan, changed candidate evidence, or missing file blocks projection.

It does not fetch sources, call Ollama, contact SOLIDWORKS, dispatch queue jobs, change CAD, verify live freshness, admit evidence, select a mechanism, or declare mechanical acceptance. The proposal is a prompt for a separately governed source-acquisition step. A future executor can consume receipts only after implementing its own source and authority checks.

From the repository root:

```bash
python agent-registry/orchestrator-v1/frontier_runner.py --repo . --state-dir /path/to/durable/local/state
python agent-registry/orchestrator-v1/frontier_runner.py --repo . --state-dir /path/to/durable/local/state --watch --interval-seconds 60
python -m unittest discover -s agent-registry/orchestrator-v1 -p 'test_*.py' -v
```

The state directory must be outside Git. Repeated scans of the same bytes return `new: false` and do not create another task. When GitHub's plan advances beyond PLAN-0010, this runner returns `BLOCKED: FRONTIER_MOVED`; it needs a separately reviewed frontier contract before following the new plan. The watcher reads the **local** checkout, so a separate governed sync must update that checkout before a new remote commit is visible.

## Isolated GitHub input sync

`source_sync.py` is the unattended entry point when the local checkout is used for other work. It resolves the public repository's exact `main` commit, downloads only the five allowlisted JSON paths at that commit, and stores them under `state/snapshots/<commit>`. It never fetches into, resets, or checks out the active project repository. A repeated commit must reproduce the identical immutable snapshot. The existing runner then evaluates that snapshot and deduplicates the proposal by input bytes.

```bash
python agent-registry/orchestrator-v1/source_sync.py --state-dir /path/to/durable/local/state
```

`state/last_sync_status.json` reports the pinned commit, input hashes, receipt or blocking reason. Network failure does not fall back to a stale snapshot. A new plan, changed evidence, or unsupported input remains blocked. The sync downloads source data only; it does not execute repository code, search OEM sources, dispatch CAD reads, or admit evidence. Run the test suite with the `unittest discover` command above.

## Official source capture candidates

`source_registry.v1.json` registers three exact official URLs for bounded source review: cab's IXOR+ assembly instructions, plus HERMA's 152C and wrap-labeling technology pages. HERMA describes a **different manufacturer's mechanism**, so it is comparative source material only. None of these URLs proves the mechanism in the live v43 assembly.

```bash
python agent-registry/orchestrator-v1/source_capture.py --state-dir /path/to/durable/local/state
```

Before fetching, capture invokes the pinned GitHub input sync and requires its exact active PLAN-0010 projection. A moved or unreachable frontier blocks every source fetch. The capture accepts only the hardcoded URL, media type, role, and size bounds. It stores the first raw response by SHA-256 and immutable `UNADMITTED` candidate records. HTML versions are keyed by normalized visible text, so changes to session tokens or markup outside visible text do not create repeated records; the latest raw response hash is still reported in scan status. For HTML, marker windows reproduce source text for review; the PDF is stored without text extraction. `last_capture_status.json` records successes and failures. A failed source yields `PARTIAL_BLOCKED` and no implied claim verification. No captured material is admitted to the epistemic graph, used to select a mechanism, or treated as mechanical acceptance.
