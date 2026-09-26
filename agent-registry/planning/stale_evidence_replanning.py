#!/usr/bin/env python3
"""Deterministic stale-evidence replanning proposal for CADGrounded.

This planning layer consumes an invalidation event from the existing reasoning
DB plus a functional-temporal architecture. It overlays the DB's current
validity projection onto a deep copy of the architecture, reuses the existing
functional-temporal evaluator and next-test ranking, and emits a bounded
read-only reacquisition proposal.

It does not:
- mutate the reasoning DB;
- mutate the source architecture;
- append or rewrite the temporal planning ledger;
- execute a CAD request or local native read;
- invent a new investigation;
- grant CAD write authority or mechanical acceptance.
"""
from __future__ import annotations

import argparse
import copy
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
REASONING_DIR = HERE.parent / "reasoning"
if str(REASONING_DIR) not in sys.path:
    sys.path.insert(0, str(REASONING_DIR))

from functional_temporal import (  # noqa: E402
    FunctionalTemporalError,
    evaluate_architecture,
    rank_next_tests,
    validate_architecture,
)


class StaleReplanningError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StaleReplanningError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StaleReplanningError(f"{path}: expected a JSON object")
    return value


def _parse_json_array(value: str, label: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise StaleReplanningError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise StaleReplanningError(f"{label} must contain a JSON array")
    return parsed


def _read_only_connection(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise StaleReplanningError(f"reasoning DB does not exist: {db}")
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA query_only = ON")
    return connection


def load_invalidation_context(
    db: Path, world_id: str, event_id: str
) -> dict[str, Any]:
    """Load one exact invalidation event and its current validity projection."""

    with _read_only_connection(db) as connection:
        event = connection.execute(
            "SELECT id,world_id,previous_run_id,current_run_id,"
            "changed_dependency_keys_json,affected_evidence_ids_json,created_at "
            "FROM invalidation_events WHERE world_id=? AND id=?",
            (world_id, event_id),
        ).fetchone()
        if event is None:
            raise StaleReplanningError(
                f"unknown invalidation event {event_id!r} for world {world_id!r}"
            )

        current_run = connection.execute(
            "SELECT id,document_title,document_path,active_configuration,"
            "observation_sha256,state_fingerprint "
            "FROM inspection_runs WHERE world_id=? AND id=?",
            (world_id, event["current_run_id"]),
        ).fetchone()
        if current_run is None:
            raise StaleReplanningError(
                f"invalidation event references missing current run {event['current_run_id']}"
            )

        affected_ids = _parse_json_array(
            event["affected_evidence_ids_json"],
            "affected_evidence_ids_json",
        )
        changed_keys = _parse_json_array(
            event["changed_dependency_keys_json"],
            "changed_dependency_keys_json",
        )

        projection: dict[str, dict[str, Any]] = {}
        for evidence_id in affected_ids:
            if not isinstance(evidence_id, str) or not evidence_id:
                raise StaleReplanningError(
                    "affected_evidence_ids_json contains a non-string evidence id"
                )
            row = connection.execute(
                "SELECT evidence_id,record_sha256,validity_state,"
                "last_invalidation_event_id,updated_at "
                "FROM evidence_validity_projection "
                "WHERE world_id=? AND evidence_id=?",
                (world_id, evidence_id),
            ).fetchone()
            if row is None:
                raise StaleReplanningError(
                    f"affected evidence {evidence_id} has no validity projection"
                )
            projection[evidence_id] = dict(row)

    return {
        "event_id": event["id"],
        "world_id": event["world_id"],
        "previous_run_id": event["previous_run_id"],
        "current_run_id": event["current_run_id"],
        "changed_dependency_keys": changed_keys,
        "affected_evidence_ids": affected_ids,
        "created_at": event["created_at"],
        "current_run": dict(current_run),
        "validity_projection": projection,
    }


def _requirements(
    indexes: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> dict[str, Mapping[str, Any]]:
    return {
        **indexes["obligations"],
        **indexes["guards"],
        **indexes["invariants"],
    }


def overlay_validity_projection(
    architecture: Mapping[str, Any],
    projection: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Overlay validity only on a copy; never rewrite source EvidenceRecords."""

    validate_architecture(architecture)
    projected = copy.deepcopy(architecture)
    evidence_by_id = {
        record["evidence_id"]: record for record in projected["evidence_catalog"]
    }

    for evidence_id, row in projection.items():
        record = evidence_by_id.get(evidence_id)
        if record is None:
            continue
        state = row.get("validity_state")
        if state not in {"CURRENT", "STALE", "UNKNOWN"}:
            raise StaleReplanningError(
                f"invalid projected validity state for {evidence_id}: {state!r}"
            )
        scope = record.get("temporal_scope")
        if not isinstance(scope, dict):
            raise StaleReplanningError(
                f"architecture evidence {evidence_id} has no temporal_scope"
            )
        scope["validity_state"] = state

    validate_architecture(projected)
    return projected


def _assert_candidate_read_only(candidate: Mapping[str, Any]) -> None:
    request = candidate.get("cad_request")
    if request is not None and request.get("write_authority") != "NONE":
        raise StaleReplanningError(
            f"declared next test {candidate['test_id']} exposes non-read-only CAD authority"
        )
    for native in candidate.get("native_read_candidates") or []:
        if native.get("write_authority") != "NONE":
            raise StaleReplanningError(
                f"declared next test {candidate['test_id']} exposes native write authority"
            )
        if native.get("remote_queue_authorized") is not False:
            raise StaleReplanningError(
                f"declared next test {candidate['test_id']} improperly promotes a native read to Remote Queue"
            )


def build_reacquisition_proposal(
    architecture: Mapping[str, Any],
    invalidation: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a bounded proposal from declared tests only."""

    indexes = validate_architecture(architecture)
    projection = invalidation["validity_projection"]
    stale_evidence_ids = sorted(
        evidence_id
        for evidence_id, row in projection.items()
        if row["validity_state"] == "STALE"
    )

    projected = overlay_validity_projection(architecture, projection)
    projected_indexes = validate_architecture(projected)
    requirements = _requirements(projected_indexes)

    stale_requirement_ids = sorted(
        requirement_id
        for requirement_id, requirement in requirements.items()
        if set(requirement["evidence_refs"]) & set(stale_evidence_ids)
    )

    report = evaluate_architecture(projected)
    ranked = rank_next_tests(projected, evaluation=report)

    candidates = [
        candidate
        for candidate in ranked
        if set(candidate["resolves_requirement_ids"]) & set(stale_requirement_ids)
    ]
    for candidate in candidates:
        _assert_candidate_read_only(candidate)

    covered = {
        requirement_id
        for candidate in candidates
        for requirement_id in candidate["resolves_requirement_ids"]
        if requirement_id in stale_requirement_ids
    }
    uncovered = sorted(set(stale_requirement_ids) - covered)

    architecture_evidence_ids = set(indexes["evidence"])
    stale_not_bound_to_architecture = sorted(
        set(stale_evidence_ids) - architecture_evidence_ids
    )

    if not stale_evidence_ids:
        status = "NO_STALE_EVIDENCE"
    elif not stale_requirement_ids:
        status = "NO_BOUND_STALE_REQUIREMENTS"
    elif not candidates:
        status = "REACQUISITION_GAP"
    else:
        status = "READY_FOR_REVIEW"

    selected = copy.deepcopy(candidates[0]) if candidates else None
    proposed_step = None
    if selected is not None:
        proposed_step = {
            "step_id": "STALE_REACQUIRE.1",
            "title": f"Reacquire stale evidence via declared test {selected['test_id']}",
            "depends_on": [],
            "write_authority": "NONE",
            "status": "PROPOSED_NOT_EXECUTED",
            "declared_test_id": selected["test_id"],
            "question": selected["question"],
            "resolves_requirement_ids": selected["resolves_requirement_ids"],
            "cad_request": selected.get("cad_request"),
            "native_read_candidates": selected.get("native_read_candidates"),
        }

    current_run = invalidation["current_run"]
    return {
        "record_type": "stale_evidence_replanning_proposal",
        "schema_version": 1,
        "status": status,
        "architecture_id": architecture["architecture_id"],
        "source_invalidation_event_id": invalidation["event_id"],
        "world_id": invalidation["world_id"],
        "live_state_binding": {
            "inspection_run_id": current_run["id"],
            "document_title": current_run["document_title"],
            "document_path": current_run["document_path"],
            "active_configuration": current_run["active_configuration"],
            "observation_sha256": current_run["observation_sha256"],
            "state_fingerprint": current_run["state_fingerprint"],
        },
        "changed_dependency_keys": list(invalidation["changed_dependency_keys"]),
        "affected_evidence_ids": list(invalidation["affected_evidence_ids"]),
        "stale_evidence_ids": stale_evidence_ids,
        "stale_not_bound_to_architecture": stale_not_bound_to_architecture,
        "stale_requirement_ids": stale_requirement_ids,
        "uncovered_stale_requirement_ids": uncovered,
        "candidate_tests": copy.deepcopy(candidates),
        "selected_next_test": selected,
        "projected_steps": [] if proposed_step is None else [proposed_step],
        "ambiguity_bucket": "STALE_STATE" if stale_evidence_ids else None,
        "write_authority": "NONE",
        "cad_write_authorized": False,
        "mechanical_acceptance_granted": False,
        "ledger_mutation_performed": False,
        "execution_performed": False,
        "governance_note": (
            "This proposal reuses only tests already declared in the functional-temporal "
            "architecture. It must be reviewed before any planning-ledger append or read execution."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a read-only reacquisition proposal from stale evidence."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--world", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--architecture", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    try:
        architecture = _load_json(args.architecture)
        invalidation = load_invalidation_context(args.db, args.world, args.event)
        proposal = build_reacquisition_proposal(architecture, invalidation)
        text = json.dumps(proposal, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    except (
        StaleReplanningError,
        FunctionalTemporalError,
        sqlite3.Error,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
