#!/usr/bin/env python3
"""CADGrounded puzzle solver v0.

This kernel treats CAD reasoning as a constraint puzzle. By default it performs
no CAD calls: it evaluates known facts, selects the highest-value missing read,
and prints the exact approved read command to run.

With --execute-reads it may execute ONLY the hardcoded read command
sw.check_interference_pair through cad.ps1. It never submits a write command and
never executes candidate transform proposals.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


EVIDENCE_RANK = {
    "unknown": 0,
    "inferred": 1,
    "approximate_getbox": 2,
    "verified_solidworks_api": 3,
    "human_mechanical_review": 4,
}

ALLOWED_EXECUTABLE_READS = {"sw.check_interference_pair"}
SUPPORTED_OPS = {"eq", "ne", "lt", "le", "gt", "ge", "in", "not_in"}


class PuzzleError(RuntimeError):
    pass


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except OSError as exc:
        raise PuzzleError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PuzzleError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PuzzleError(f"Top-level JSON must be an object: {path}")
    return value


def save_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def merge_state(problem: Dict[str, Any], state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    facts = copy.deepcopy(problem.get("facts", {}))
    if not isinstance(facts, dict):
        raise PuzzleError("problem.facts must be an object")
    if state is None:
        return facts
    state_facts = state.get("facts", state)
    if not isinstance(state_facts, dict):
        raise PuzzleError("state facts must be an object")
    for name, record in state_facts.items():
        facts[name] = copy.deepcopy(record)
    return facts


def fact_record(facts: Dict[str, Any], name: str) -> Dict[str, Any]:
    raw = facts.get(name)
    if raw is None:
        return {"value": None, "evidence": "unknown"}
    if isinstance(raw, dict) and "value" in raw:
        evidence = raw.get("evidence", "unknown")
        return {"value": raw.get("value"), "evidence": evidence}
    return {"value": raw, "evidence": "inferred"}


def evidence_sufficient(actual: str, required: str) -> bool:
    if actual not in EVIDENCE_RANK:
        return False
    if required not in EVIDENCE_RANK:
        raise PuzzleError(f"Unknown minimum_evidence: {required}")
    return EVIDENCE_RANK[actual] >= EVIDENCE_RANK[required]


def compare(op: str, actual: Any, expected: Any) -> bool:
    if op not in SUPPORTED_OPS:
        raise PuzzleError(f"Unsupported predicate operator: {op}")
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "lt":
        return actual < expected
    if op == "le":
        return actual <= expected
    if op == "gt":
        return actual > expected
    if op == "ge":
        return actual >= expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    raise AssertionError(op)


def evaluate_predicate(predicate: Dict[str, Any], facts: Dict[str, Any]) -> Tuple[str, str]:
    fact = predicate.get("fact")
    op = predicate.get("op")
    if not isinstance(fact, str) or not fact:
        raise PuzzleError("Every predicate requires a non-empty fact")
    if not isinstance(op, str):
        raise PuzzleError(f"Predicate for {fact} requires an op")
    record = fact_record(facts, fact)
    actual = record["value"]
    evidence = str(record.get("evidence", "unknown"))
    required = str(predicate.get("minimum_evidence", "unknown"))
    if actual is None:
        return "unknown", f"{fact} has no value"
    if not evidence_sufficient(evidence, required):
        return "unknown", f"{fact} evidence {evidence} < required {required}"
    try:
        ok = compare(op, actual, predicate.get("value"))
    except (TypeError, ValueError) as exc:
        raise PuzzleError(f"Could not evaluate {fact}: {exc}") from exc
    return ("true" if ok else "false"), f"{fact}={actual!r} ({evidence})"


def evaluate_group(predicates: Iterable[Dict[str, Any]], facts: Dict[str, Any]) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for predicate in predicates:
        status, reason = evaluate_predicate(predicate, facts)
        results.append({
            "fact": str(predicate.get("fact")),
            "status": status,
            "reason": reason,
        })
    return results


def required_unknown_facts(problem: Dict[str, Any], facts: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for predicate in list(problem.get("goals", [])) + list(problem.get("hard_constraints", [])):
        status, _ = evaluate_predicate(predicate, facts)
        if status == "unknown":
            name = str(predicate["fact"])
            if name not in missing:
                missing.append(name)
    return missing


def choose_knowledge_action(problem: Dict[str, Any], missing: List[str]) -> Optional[Dict[str, Any]]:
    best: Optional[Tuple[float, Dict[str, Any]]] = None
    missing_set = set(missing)
    for action in problem.get("knowledge_actions", []):
        if not isinstance(action, dict):
            continue
        produces = set(action.get("produces", []))
        coverage = len(missing_set.intersection(produces))
        if coverage == 0:
            continue
        priority = float(action.get("priority", 0.0))
        cost = max(float(action.get("cost", 1.0)), 0.000001)
        # Coverage dominates, priority breaks ties, cost mildly penalizes expensive reads.
        score = coverage * 10000.0 + priority * 10.0 - cost
        if best is None or score > best[0]:
            best = (score, action)
    return None if best is None else best[1]


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_read_command(action: Dict[str, Any], cad_script: Path) -> str:
    command = action.get("command")
    payload = action.get("payload", {})
    if command != "sw.check_interference_pair":
        raise PuzzleError(f"No renderer for read command: {command}")
    a = str(payload.get("a_name_contains", ""))
    b = str(payload.get("b_name_contains", ""))
    if not a or not b:
        raise PuzzleError("Interference read requires both component selectors")
    return (
        f"& {powershell_quote(str(cad_script))} interference "
        f"-ANameContains {powershell_quote(a)} "
        f"-BNameContains {powershell_quote(b)} -Json"
    )


def find_powershell() -> str:
    for name in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        path = shutil.which(name)
        if path:
            return path
    raise PuzzleError("No PowerShell executable was found")


def execute_read(action: Dict[str, Any], cad_script: Path, wait_seconds: int) -> Dict[str, Any]:
    command = action.get("command")
    if command not in ALLOWED_EXECUTABLE_READS:
        raise PuzzleError(f"POLICY_BLOCK: solver cannot execute {command}")
    payload = action.get("payload", {})
    if command != "sw.check_interference_pair":
        raise PuzzleError(f"POLICY_BLOCK: no fixed executor for {command}")
    a = str(payload.get("a_name_contains", ""))
    b = str(payload.get("b_name_contains", ""))
    if not a or not b:
        raise PuzzleError("Interference read requires both component selectors")

    ps = find_powershell()
    args = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(cad_script),
        "interference",
        "-ANameContains", a,
        "-BNameContains", b,
        "-WaitSeconds", str(wait_seconds),
        "-Json",
    ]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=wait_seconds + 20)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise PuzzleError(f"Read action {action.get('id')} failed: {detail}")
    text = completed.stdout.strip()
    if not text:
        raise PuzzleError(f"Read action {action.get('id')} returned no JSON")
    try:
        snapshot = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PuzzleError(f"Read action returned invalid JSON: {text[:500]}") from exc
    if snapshot.get("state") != "completed":
        raise PuzzleError(f"Read snapshot state is {snapshot.get('state')!r}")
    if snapshot.get("command") != command:
        raise PuzzleError(f"Read snapshot command mismatch: {snapshot.get('command')!r}")
    data = snapshot.get("data")
    if not isinstance(data, dict):
        raise PuzzleError("Read snapshot contains no data object")
    return snapshot


def apply_read_result(action: Dict[str, Any], snapshot: Dict[str, Any], facts: Dict[str, Any]) -> None:
    data = snapshot["data"]
    result_map = action.get("result_map", {})
    evidence = str(action.get("evidence", "verified_solidworks_api"))
    if not isinstance(result_map, dict):
        raise PuzzleError("knowledge action result_map must be an object")
    for fact_name, field_name in result_map.items():
        if field_name not in data:
            raise PuzzleError(f"Read result missing expected field: {field_name}")
        facts[str(fact_name)] = {
            "value": data[field_name],
            "evidence": evidence,
            "source_job_id": snapshot.get("job_id"),
            "recorded_at": snapshot.get("recorded_at"),
            "source_command": snapshot.get("command"),
        }


def vector_norm(values: Iterable[Any]) -> float:
    numbers = [float(v) for v in values]
    return math.sqrt(sum(v * v for v in numbers))


def rank_candidate_moves(problem: Dict[str, Any], facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    scoring = problem.get("scoring", {})
    move_w = float(scoring.get("movement_weight", 1.0))
    rot_w = float(scoring.get("rotation_weight", 1.0))
    risk_w = float(scoring.get("risk_weight", 1.0))
    uncertainty_w = float(scoring.get("uncertainty_weight", 1.0))
    ranked: List[Dict[str, Any]] = []
    for move in problem.get("candidate_moves", []):
        if not isinstance(move, dict):
            continue
        when = move.get("when")
        if isinstance(when, dict):
            status, _ = evaluate_predicate(when, facts)
            if status != "true":
                continue
        translation = move.get("translation_delta_mm", [0.0, 0.0, 0.0])
        rotation = move.get("rotation_delta_deg", [0.0, 0.0, 0.0])
        cost = (
            vector_norm(translation) * move_w
            + vector_norm(rotation) * rot_w
            + float(move.get("risk_penalty", 0.0)) * risk_w
            + float(move.get("uncertainty_penalty", 0.0)) * uncertainty_w
        )
        item = copy.deepcopy(move)
        item["score"] = cost
        item["execution_authority"] = "NONE_PROPOSAL_ONLY"
        ranked.append(item)
    ranked.sort(key=lambda item: (float(item["score"]), str(item.get("id", ""))))
    return ranked


def assess(problem: Dict[str, Any], facts: Dict[str, Any]) -> Dict[str, Any]:
    goals = evaluate_group(problem.get("goals", []), facts)
    constraints = evaluate_group(problem.get("hard_constraints", []), facts)
    violated = [item for item in constraints if item["status"] == "false"]
    unknown = required_unknown_facts(problem, facts)

    if violated:
        status = "blocked_constraint_violation"
    elif unknown:
        status = "needs_evidence"
    elif all(item["status"] == "true" for item in goals) and all(
        item["status"] == "true" for item in constraints
    ):
        status = "solved"
    else:
        status = "needs_candidate_move"

    return {
        "status": status,
        "goals": goals,
        "hard_constraints": constraints,
        "unknown_required_facts": unknown,
    }


def print_human(report: Dict[str, Any]) -> None:
    print(f"Puzzle: {report['puzzle_id']}")
    print(f"Status: {report['assessment']['status']}")
    print()
    print("Goals:")
    for item in report["assessment"]["goals"]:
        print(f"  {item['status']:7} {item['fact']} - {item['reason']}")
    print("Hard constraints:")
    for item in report["assessment"]["hard_constraints"]:
        print(f"  {item['status']:7} {item['fact']} - {item['reason']}")
    next_read = report.get("next_read")
    if next_read:
        print()
        print("Next information action:")
        print(f"  {next_read['id']} -> {next_read['command']}")
        print("  " + next_read["powershell"])
    moves = report.get("ranked_candidate_moves", [])
    if moves:
        print()
        print("Ranked proposal-only moves:")
        for move in moves:
            print(f"  {move['score']:.3f}  {move['id']}  [NO EXECUTION AUTHORITY]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Constraint-puzzle planner for CADGrounded")
    parser.add_argument("problem", type=Path, help="Puzzle problem JSON")
    parser.add_argument("--state", type=Path, help="Optional fact-state JSON")
    parser.add_argument("--save-state", type=Path, help="Write merged/observed state JSON")
    parser.add_argument("--execute-reads", action="store_true", help="Execute only hardcoded approved read actions")
    parser.add_argument("--max-reads", type=int, default=3, help="Maximum safe reads in one run")
    parser.add_argument("--wait-seconds", type=int, default=30, help="Per CAD read wait timeout")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result")
    args = parser.parse_args()

    problem = load_json(args.problem.resolve())
    state = load_json(args.state.resolve()) if args.state else None
    facts = merge_state(problem, state)

    script_dir = Path(__file__).resolve().parent
    cad_script = script_dir / "cad.ps1"
    if args.execute_reads and not cad_script.is_file():
        raise PuzzleError(f"Missing CAD helper: {cad_script}")

    reads_executed: List[Dict[str, Any]] = []
    assessment = assess(problem, facts)

    if args.execute_reads:
        if args.max_reads < 0 or args.max_reads > 20:
            raise PuzzleError("--max-reads must be between 0 and 20")
        while assessment["status"] == "needs_evidence" and len(reads_executed) < args.max_reads:
            action = choose_knowledge_action(problem, assessment["unknown_required_facts"])
            if action is None:
                break
            snapshot = execute_read(action, cad_script, args.wait_seconds)
            apply_read_result(action, snapshot, facts)
            reads_executed.append({
                "action_id": action.get("id"),
                "command": action.get("command"),
                "job_id": snapshot.get("job_id"),
                "recorded_at": snapshot.get("recorded_at"),
            })
            assessment = assess(problem, facts)
            if assessment["status"] == "blocked_constraint_violation":
                break

    next_read: Optional[Dict[str, Any]] = None
    if assessment["status"] == "needs_evidence":
        action = choose_knowledge_action(problem, assessment["unknown_required_facts"])
        if action is not None:
            next_read = {
                "id": action.get("id"),
                "command": action.get("command"),
                "payload": action.get("payload"),
                "powershell": render_read_command(action, cad_script),
            }

    ranked_moves: List[Dict[str, Any]] = []
    if assessment["status"] == "needs_candidate_move":
        ranked_moves = rank_candidate_moves(problem, facts)

    if args.save_state:
        save_json(args.save_state.resolve(), {"facts": facts})

    report: Dict[str, Any] = {
        "puzzle_id": problem.get("id"),
        "mode": problem.get("mode", "proposal_only"),
        "assessment": assessment,
        "reads_executed": reads_executed,
        "next_read": next_read,
        "ranked_candidate_moves": ranked_moves,
        "write_authority": "NONE",
    }

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PuzzleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
