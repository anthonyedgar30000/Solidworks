#!/usr/bin/env python3
"""CADGrounded epistemic audit v0.

This is a non-executing sidecar for the constraint-puzzle solver. It classifies
what the model knows, knows it does not know, may already possess without having
modeled, and where observations suggest the puzzle model itself is incomplete.

It performs no CAD calls and grants no execution authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


class AuditError(RuntimeError):
    pass


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except OSError as exc:
        raise AuditError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AuditError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"Top-level JSON must be an object: {path}")
    return value


def fact_value(record: Any) -> Any:
    if isinstance(record, dict) and "value" in record:
        return record.get("value")
    return record


def collect_referenced_facts(problem: Dict[str, Any]) -> Set[str]:
    result: Set[str] = set()
    for group in ("goals", "hard_constraints"):
        for item in problem.get(group, []):
            if isinstance(item, dict) and isinstance(item.get("fact"), str):
                result.add(item["fact"])
    for move in problem.get("candidate_moves", []):
        when = move.get("when") if isinstance(move, dict) else None
        if isinstance(when, dict) and isinstance(when.get("fact"), str):
            result.add(when["fact"])
    for action in problem.get("knowledge_actions", []):
        if not isinstance(action, dict):
            continue
        for fact in action.get("produces", []):
            if isinstance(fact, str):
                result.add(fact)
    return result


def merge_facts(problem: Dict[str, Any], state: Dict[str, Any] | None) -> Dict[str, Any]:
    facts = dict(problem.get("facts", {}))
    if state:
        state_facts = state.get("facts", {})
        if isinstance(state_facts, dict):
            facts.update(state_facts)
    return facts


def conflicting_history(record: Any) -> List[Any]:
    if not isinstance(record, dict):
        return []
    history = record.get("history")
    if not isinstance(history, list):
        return []
    values: List[Any] = []
    for item in history:
        value = item.get("value") if isinstance(item, dict) else item
        if value is not None and value not in values:
            values.append(value)
    return values if len(values) > 1 else []


def add_trigger(triggers: List[Dict[str, Any]], kind: str, severity: str,
                summary: str, evidence: Any, questions: Iterable[str]) -> None:
    triggers.append({
        "kind": kind,
        "severity": severity,
        "summary": summary,
        "evidence": evidence,
        "discovery_questions": list(questions),
    })


def audit(problem: Dict[str, Any], state: Dict[str, Any] | None) -> Dict[str, Any]:
    declared = problem.get("facts", {})
    if not isinstance(declared, dict):
        raise AuditError("problem.facts must be an object")

    state_facts: Dict[str, Any] = {}
    if state:
        raw = state.get("facts", {})
        if isinstance(raw, dict):
            state_facts = raw

    effective = merge_facts(problem, state)
    referenced = collect_referenced_facts(problem)

    known_known: List[Dict[str, Any]] = []
    known_unknown: List[Dict[str, Any]] = []
    latent_known: List[Dict[str, Any]] = []
    unknown_known: List[Dict[str, Any]] = []

    for name, record in effective.items():
        value = fact_value(record)
        if name in declared:
            if value is None:
                known_unknown.append({"fact": name})
            else:
                known_known.append({"fact": name, "value": value})
                if name not in referenced:
                    latent_known.append({"fact": name, "value": value})
        elif value is not None:
            # Evidence exists in state but the puzzle did not declare the fact.
            unknown_known.append({"fact": name, "value": value})

    triggers: List[Dict[str, Any]] = []

    # 1) Document identity drift: a puzzle about one assembly is being observed on another.
    expected_doc = problem.get("expected_document")
    context = state.get("context", {}) if state else {}
    observed_doc = context.get("document_title") if isinstance(context, dict) else None
    if isinstance(expected_doc, str) and observed_doc and observed_doc != expected_doc:
        add_trigger(
            triggers,
            "document_identity_mismatch",
            "high",
            "Observed CAD document does not match the puzzle's expected document.",
            {"expected": expected_doc, "observed": observed_doc},
            [
                "Was the wrong assembly active, or has the puzzle advanced to a new baseline?",
                "Which assumptions from the old puzzle are invalid in the observed document?",
                "Should this become a new puzzle instance rather than reusing old facts?",
            ],
        )

    # 2) Ambiguous selectors: the system knows that identity resolution is under-modeled.
    diagnostics = state.get("selector_diagnostics", []) if state else []
    if isinstance(diagnostics, list):
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            matches = item.get("matches", [])
            if isinstance(matches, list) and len(matches) > 1:
                selector = item.get("selector")
                add_trigger(
                    triggers,
                    "selector_ambiguity",
                    "high",
                    f"Selector {selector!r} resolves to multiple components.",
                    {"selector": selector, "matches": matches},
                    [
                        "Which exact component identity is intended?",
                        "Should component identity use exact Name2, path, parent, configuration, or a persistent ID?",
                        "Does the assembly title or virtual-component naming leak into selector matching?",
                    ],
                )

    # 3) Unexplained observations are direct unknown-unknown candidates.
    observations = state.get("observations", []) if state else []
    if isinstance(observations, list):
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            explained = obs.get("explained_by")
            modeled_fact = obs.get("modeled_fact")
            if not explained and not modeled_fact:
                add_trigger(
                    triggers,
                    "unexplained_observation",
                    "medium",
                    str(obs.get("summary", "Observation is not explained by the current puzzle model.")),
                    obs,
                    [
                        "What unmodeled component, mate, geometry, state transition, or assumption could explain this?",
                        "Which new fact should be created so this observation becomes a known unknown?",
                    ],
                )

    # 4) Conflicting evidence means truth cannot safely collapse to one value.
    for name, record in state_facts.items():
        values = conflicting_history(record)
        if values:
            add_trigger(
                triggers,
                "conflicting_evidence",
                "high",
                f"Fact {name!r} has conflicting observed values.",
                {"fact": name, "values": values},
                [
                    "Did the CAD state change between observations?",
                    "Are the observations tied to different document revisions or component identities?",
                    "Which evidence source should dominate, or should the fact be split into revision-scoped facts?",
                ],
            )

    # 5) Explicit anomaly events from workers/verifiers can become discovery triggers.
    events = state.get("events", []) if state else []
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind in {"unexpected_interference", "model_incomplete", "unmodeled_component", "verification_contradiction"}:
                add_trigger(
                    triggers,
                    str(kind),
                    str(event.get("severity", "high")),
                    str(event.get("summary", kind)),
                    event,
                    [
                        "What assumption predicted the opposite outcome?",
                        "What fact or constraint is missing from the puzzle model?",
                        "What bounded read would most reduce uncertainty?",
                    ],
                )

    status = "model_stable"
    if triggers:
        status = "discovery_required"
    elif known_unknown:
        status = "known_unknowns_remaining"

    return {
        "puzzle_id": problem.get("id"),
        "status": status,
        "epistemic_counts": {
            "known_known": len(known_known),
            "known_unknown": len(known_unknown),
            "unknown_known_candidates": len(unknown_known),
            "latent_known": len(latent_known),
            "unknown_unknown_triggers": len(triggers),
        },
        "known_known": known_known,
        "known_unknown": known_unknown,
        "unknown_known_candidates": unknown_known,
        "latent_known": latent_known,
        "unknown_unknown_triggers": triggers,
        "rule": "Unknown unknowns are not represented as facts until an anomaly/discovery trigger causes the model to create a new known-unknown fact.",
        "execution_authority": "NONE",
    }


def print_human(report: Dict[str, Any]) -> None:
    counts = report["epistemic_counts"]
    print(f"Puzzle: {report.get('puzzle_id')}")
    print(f"Epistemic status: {report['status']}")
    print()
    print("Epistemic inventory:")
    print(f"  known-knowns              {counts['known_known']}")
    print(f"  known-unknowns            {counts['known_unknown']}")
    print(f"  unknown-known candidates  {counts['unknown_known_candidates']}")
    print(f"  latent knowns             {counts['latent_known']}")
    print(f"  unknown-unknown triggers  {counts['unknown_unknown_triggers']}")

    if report["known_unknown"]:
        print("\nKnown unknowns:")
        for item in report["known_unknown"]:
            print(f"  ? {item['fact']}")

    if report["unknown_known_candidates"]:
        print("\nUnknown-known candidates (evidence exists outside declared model):")
        for item in report["unknown_known_candidates"]:
            print(f"  ! {item['fact']} = {item['value']!r}")

    if report["unknown_unknown_triggers"]:
        print("\nUnknown-unknown discovery triggers:")
        for trigger in report["unknown_unknown_triggers"]:
            print(f"  [{trigger['severity']}] {trigger['kind']}: {trigger['summary']}")
            for question in trigger["discovery_questions"]:
                print(f"      - {question}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Epistemic audit for CADGrounded puzzle models")
    parser.add_argument("problem", type=Path, help="Puzzle problem JSON")
    parser.add_argument("--state", type=Path, help="Optional runtime/evidence state JSON")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    problem = load_json(args.problem.resolve())
    state = load_json(args.state.resolve()) if args.state else None
    report = audit(problem, state)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
