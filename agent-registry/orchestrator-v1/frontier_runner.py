"""Fail-closed, read-only projection of the current source-acquisition frontier.

This process consumes versioned repository files. It never calls SOLIDWORKS,
the Remote Queue, Ollama, or an external source. Its output is an investigation
task, not an engineering observation or an authorization to execute a test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


PLAN = "agent-registry/planning/CURRENT_PLAN.json"
LEDGER = "agent-registry/planning/ledger/PLAN-0010.json"
SOURCE_PROBE = (
    "agent-registry/reasoning/runtime/"
    "function-first-contact-maintenance-source-probe-20260927T150842223Z.json"
)
SCREEN = (
    "agent-registry/reasoning/runtime/"
    "function-first-mechanism-screen-evidence-20260927T153026706Z.json"
)
REQUIREMENTS = (
    "agent-registry/reasoning/requirements/"
    "function-first-contact-maintenance.v1.json"
)
INPUTS = (PLAN, LEDGER, SOURCE_PROBE, SCREEN, REQUIREMENTS)


class FrontierBlocked(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise FrontierBlocked(reason)


def _read_inputs(repo: Path) -> tuple[dict[str, dict], dict[str, str]]:
    parsed, hashes = {}, {}
    for name in INPUTS:
        raw = (repo / name).read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        parsed[name] = json.loads(raw.decode("utf-8-sig"))
    return parsed, hashes


def _project(data: dict[str, dict], hashes: dict[str, str]) -> dict:
    pointer, plan = data[PLAN], data[LEDGER]
    probe, screen, requirements = data[SOURCE_PROBE], data[SCREEN], data[REQUIREMENTS]

    _require(pointer.get("project_id") == "CADGROUNDED.IXOR", "PROJECT_MISMATCH")
    _require(pointer.get("current_plan_id") == "PLAN-0010", "FRONTIER_MOVED")
    _require(pointer.get("current_evidence_id") == screen.get("evidence_id"), "CURRENT_EVIDENCE_MISMATCH")
    _require(pointer.get("status") == "ACTIVE_INVESTIGATION_FUNCTION_FIRST_MECHANISM_REFERENCE_SOURCE_ACQUISITION_PROJECTED", "FRONTIER_MOVED")
    _require(plan.get("record_id") == "PLAN-0010" and plan.get("status") == "ACTIVE", "PLAN_NOT_ACTIVE")
    _require(plan.get("no_write_boundary", "").startswith("No SOLIDWORKS"), "WRITE_BOUNDARY_MISSING")
    _require(probe.get("evidence_id") == "E.FUNCTION_FIRST.CONTACT_MAINTENANCE_SOURCE_PROBE.20260927T150842223Z", "PROBE_ID_MISMATCH")
    _require(probe.get("evidence_type") == "solidworks_observation" and probe.get("evidence_state") == "VERIFIED", "PROBE_AUTHORITY_MISMATCH")
    _require(probe.get("source_authority") == "SOLIDWORKS_LIVE_STATE", "PROBE_AUTHORITY_MISMATCH")
    _require(screen.get("evidence_id") == "E.FUNCTION_FIRST.MECHANISM_SCREEN.20260927T153026706Z", "SCREEN_ID_MISMATCH")
    _require(screen.get("evidence_type") == "deterministic_calculation" and screen.get("source_authority") == "DETERMINISTIC_CALCULATION", "SCREEN_AUTHORITY_MISMATCH")
    _require(screen.get("provenance", {}).get("source_ref"), "SCREEN_PROVENANCE_MISSING")
    _require(screen.get("evidence_id") in (pointer.get("current_evidence_id"),), "SCREEN_NOT_CURRENT")
    _require(probe.get("evidence_id") in screen.get("dependencies", []), "SCREEN_DEPENDENCY_MISSING")
    _require(requirements.get("requirement_model_id") == "CADGROUNDED.IXOR.CONTACT_MAINTENANCE.V1", "REQUIREMENTS_MISMATCH")
    _require(probe.get("evidence_id") in requirements.get("basis_evidence_ids", []), "REQUIREMENTS_DEPENDENCY_MISSING")
    for record, label in ((probe, "PROBE"), (screen, "SCREEN")):
        _require(record.get("mechanical_acceptance_granted") is False, f"{label}_ACCEPTANCE_BOUNDARY")
        _require(record.get("temporal_scope", {}).get("validity_state") == "CURRENT", f"{label}_STALE")
        _require(record.get("temporal_scope", {}).get("coverage") == "POINT_ONLY", f"{label}_SCOPE_CHANGED")

    binding = plan.get("state_binding", {})
    observed = probe.get("payload", {}).get("document", {})
    _require(binding.get("document_title") == observed.get("title"), "DOCUMENT_MISMATCH")
    _require(binding.get("document_path") == observed.get("path"), "DOCUMENT_MISMATCH")
    _require(binding.get("configuration_exact") == observed.get("active_configuration_exact"), "CONFIGURATION_MISMATCH")
    _require(probe.get("payload", {}).get("post_readback", {}).get("same_document_title_path") is True, "READBACK_MISSING")

    result = screen.get("payload", {}).get("result", {})
    _require(result.get("selection_status") == "NOT_SELECTED", "SELECTION_STATE_CHANGED")
    candidates = result.get("candidates", [])
    _require(len(candidates) == 4 and len({c.get("candidate_id") for c in candidates}) == 4, "CANDIDATE_SET_CHANGED")
    _require(all(c.get("engineering_evidence_layer") and
                 all(v == "UNRESOLVED" for v in c["engineering_evidence_layer"].values())
                 for c in candidates), "ENGINEERING_EVIDENCE_CHANGED")
    _require(requirements.get("candidate_selection_status") == "NOT_SELECTED", "REQUIREMENTS_SELECTION_CHANGED")

    return {
        "schema_version": 1,
        "record_type": "investigation_task_proposal",
        "status": "SOURCE_ACQUISITION_REQUIRED",
        "plan_id": "PLAN-0010",
        "basis_evidence_ids": [probe["evidence_id"], screen["evidence_id"]],
        "input_sha256": hashes,
        "task": "Locate OEM or other authoritative mechanism references that explicitly identify bottle contact closure, open/capture/release motion, usable travel, maintenance law, and reaction path. Record exact page/feature provenance for each claim before candidate-specific engineering screening.",
        "diagnostic_value": "Discriminates among the three eligible standalone mechanism classes and identifies whether compliant preload is an augmentation; does not select a mechanism.",
        "required_source_class": "OEM_SOURCE_REQUIRED",
        "evidence_to_resolve": [
            "CONTACT_MAINTENANCE_OWNER_BOUND",
            "OPEN_CAPTURE_RELEASE_MOTION_BOUND",
            "CONTACT_MAINTENANCE_LAW_BOUND",
            "REACTION_PATH_BOUND",
        ],
        "candidate_selection_status": "NOT_SELECTED",
        "mechanical_acceptance_granted": False,
        "cad_write_authority": "NONE",
        "remote_queue_write_authority": "NONE",
        "execution_authority": "NONE",
        "live_cad_freshness": "NOT_RECHECKED_BY_THIS_RUNNER",
    }


def run_once(repo: Path, state_dir: Path) -> dict:
    """Return a projection and persist one immutable receipt per input snapshot."""
    try:
        data, hashes = _read_inputs(repo)
        record = _project(data, hashes)
    except (OSError, UnicodeError, json.JSONDecodeError, FrontierBlocked,
            KeyError, TypeError) as exc:
        return {"status": "BLOCKED", "reason": str(exc), "execution_authority": "NONE"}

    snapshot = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    record["snapshot_sha256"] = snapshot
    receipts = state_dir / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    receipt = receipts / f"{snapshot}.json"
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=receipts,
                                         prefix=".pending-", delete=False) as stream:
            temp_name = stream.name
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, receipt)
    except FileExistsError:
        # A repeated scan never creates another task for the same inputs.
        return {**record, "receipt": str(receipt), "new": False}
    finally:
        if temp_name is not None:
            os.unlink(temp_name)
    return {**record, "receipt": str(receipt), "new": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.watch and args.interval_seconds < 10:
        parser.error("--interval-seconds must be at least 10")
    while True:
        result = run_once(args.repo, args.state_dir)
        print(json.dumps(result, sort_keys=True), flush=True)
        if not args.watch:
            return 0 if result["status"] != "BLOCKED" else 2
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
