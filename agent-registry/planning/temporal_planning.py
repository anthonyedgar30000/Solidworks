#!/usr/bin/env python3
"""Fail-closed structural validator for CADGrounded temporal planning records."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class LedgerError(ValueError):
    pass


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError(f"{path}: expected a JSON object")
    return value


def require(record: dict, *keys: str) -> None:
    missing = [key for key in keys if key not in record]
    if missing:
        raise LedgerError(f"{record.get('record_id', '<unknown>')}: missing {missing}")


def validate(ledger_dir: Path, current_path: Path) -> None:
    current = load_json(current_path)
    require(current, "schema_version", "project_id", "current_plan_id",
            "latest_divergence_id", "latest_reconciliation_id")
    if current["schema_version"] != 1:
        raise LedgerError("CURRENT_PLAN: unsupported schema version")

    records = [load_json(path) for path in sorted(ledger_dir.glob("*.json"))]
    if not records:
        raise LedgerError("ledger contains no records")

    by_id: dict[str, dict] = {}
    for record in records:
        require(record, "record_type", "schema_version", "record_id", "project_id")
        if record["schema_version"] != 1:
            raise LedgerError(f"{record['record_id']}: unsupported schema version")
        if record["project_id"] != current["project_id"]:
            raise LedgerError(f"{record['record_id']}: project_id differs from CURRENT_PLAN")
        if record["record_id"] in by_id:
            raise LedgerError(f"duplicate record_id: {record['record_id']}")
        by_id[record["record_id"]] = record

    plans = {rid: record for rid, record in by_id.items()
             if record["record_type"] == "plan"}
    divergences = {rid: record for rid, record in by_id.items()
                   if record["record_type"] == "divergence_record"}
    reconciliations = {rid: record for rid, record in by_id.items()
                       if record["record_type"] == "plan_reconciliation"}

    if current["current_plan_id"] not in plans:
        raise LedgerError("CURRENT_PLAN current_plan_id does not identify a plan")
    if current["latest_divergence_id"] not in divergences:
        raise LedgerError("CURRENT_PLAN latest_divergence_id does not identify a divergence")
    if current["latest_reconciliation_id"] not in reconciliations:
        raise LedgerError("CURRENT_PLAN latest_reconciliation_id does not identify a reconciliation")

    for plan_id, plan in plans.items():
        require(plan, "created_at_utc", "state_binding", "projected_steps", "status")
        parent = plan.get("parent_plan_id")
        if parent is not None and parent not in plans:
            raise LedgerError(f"{plan_id}: parent_plan_id is not a plan")
        steps = plan["projected_steps"]
        if not isinstance(steps, list) or not steps:
            raise LedgerError(f"{plan_id}: projected_steps must be non-empty")
        step_ids = set()
        for step in steps:
            require(step, "step_id", "title", "depends_on", "write_authority", "status")
            if step["step_id"] in step_ids:
                raise LedgerError(f"{plan_id}: duplicate step_id {step['step_id']}")
            step_ids.add(step["step_id"])
            if step["write_authority"] != "NONE":
                raise LedgerError(f"{plan_id}/{step['step_id']}: ledger plan may not grant CAD write authority")
        for step in steps:
            unknown = set(step["depends_on"]) - step_ids
            if unknown:
                raise LedgerError(f"{plan_id}/{step['step_id']}: unknown dependency {sorted(unknown)}")
        for divergence_id in plan.get("caused_by_divergence_ids", []):
            if divergence_id not in divergences:
                raise LedgerError(f"{plan_id}: unknown divergence {divergence_id}")

    for divergence_id, record in divergences.items():
        require(record, "recorded_at_utc", "from_plan_id", "classification",
                "affected_step_outcomes", "successor_plan_id")
        if record["from_plan_id"] not in plans:
            raise LedgerError(f"{divergence_id}: from_plan_id is not a plan")
        successor = record["successor_plan_id"]
        if successor not in plans:
            raise LedgerError(f"{divergence_id}: successor_plan_id is not a plan")
        if divergence_id not in plans[successor].get("caused_by_divergence_ids", []):
            raise LedgerError(f"{divergence_id}: successor plan does not reference the divergence")

    for reconciliation_id, record in reconciliations.items():
        require(record, "reconciled_at_utc", "plan_id", "step_outcomes", "revised_plan_id")
        if record["plan_id"] not in plans or record["revised_plan_id"] not in plans:
            raise LedgerError(f"{reconciliation_id}: plan linkage is invalid")
        valid_steps = {step["step_id"] for step in plans[record["plan_id"]]["projected_steps"]}
        for outcome in record["step_outcomes"]:
            require(outcome, "step_id", "outcome")
            if outcome["step_id"] not in valid_steps:
                raise LedgerError(f"{reconciliation_id}: outcome refers to unknown plan step")

    print(
        "PASS: "
        f"{len(plans)} plans, {len(divergences)} divergences, "
        f"{len(reconciliations)} reconciliations; current={current['current_plan_id']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default="agent-registry/planning/ledger")
    parser.add_argument("--current", default="agent-registry/planning/CURRENT_PLAN.json")
    args = parser.parse_args()
    try:
        validate(Path(args.ledger), Path(args.current))
    except LedgerError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
