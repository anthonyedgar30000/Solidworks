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
