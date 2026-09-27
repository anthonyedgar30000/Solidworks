from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


CURRENT_PLAN_RELATIVE = Path("agent-registry/planning/CURRENT_PLAN.json")
ARCHITECTURE_PATHS = {
    "IXOR_FUNCTION_FIRST_BOTTLE_HANDLING_REFERENCE": Path(
        "agent-registry/reasoning/reference_cases/"
        "function_first_bottle_handling.functional-temporal.v1.json"
    ),
}

VALID_PRIORS = {"COMMON", "UNCOMMON", "RARE"}
VALID_EVIDENCE_STATES = {
    "UNTESTED", "SUPPORTED", "WEAKENED", "DISPROVEN", "UNRESOLVED",
}
VALID_INVESTIGATION_STATES = {
    "DORMANT", "ELIGIBLE", "ACTIVE", "EXHAUSTED",
}

MECHANISM_ESCALATION_BLOCKER_IDS = frozenset({
    "H_CAPTURE_CLOSURE_OWNER",
    "H_CAPTURE_COMPLIANCE_OR_PRELOAD",
    "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
    "H_PIVOTING_ROLLER_ARM_OR_CARRIER",
    "H_MOVING_WRAP_BELT_ASSEMBLY",
    "H_SPRING_OR_COMPLIANT_PRELOAD_MECHANISM",
})


class FrontierBindingError(ValueError):
    def __init__(self, violations: list[str]):
        self.violations = tuple(violations)
        super().__init__("; ".join(self.violations))


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _statement_sha256(statement: str) -> str:
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8-sig")), _sha256_bytes(raw)


def _require(condition: bool, violation: str) -> None:
    if not condition:
        raise FrontierBindingError([violation])


def load_current_frontier(repo_root: Path) -> dict[str, Any]:
    plan_path = repo_root / CURRENT_PLAN_RELATIVE
    plan, plan_sha256 = _read_json(plan_path)

    architecture_id = plan.get("current_architecture_id")
    _require(
        architecture_id in ARCHITECTURE_PATHS,
        f"FRONTIER_ARCHITECTURE_UNREGISTERED:{architecture_id}",
    )
    frontier_relative = ARCHITECTURE_PATHS[architecture_id]
    frontier_path = repo_root / frontier_relative
    frontier, frontier_sha256 = _read_json(frontier_path)

    _require(
        frontier.get("architecture_id") == architecture_id,
        "FRONTIER_ARCHITECTURE_ID_MISMATCH",
    )
    _require(
        str(plan.get("status") or "").startswith("ACTIVE_INVESTIGATION_"),
        "CURRENT_PLAN_NOT_ACTIVE_INVESTIGATION",
    )
    _require(
        bool(plan.get("current_plan_id")),
        "CURRENT_PLAN_ID_MISSING",
    )

    hypotheses = frontier.get("hypotheses")
    _require(isinstance(hypotheses, list), "FRONTIER_HYPOTHESES_NOT_LIST")

    index: dict[str, dict[str, Any]] = {}
    for position, hypothesis in enumerate(hypotheses):
        _require(
            isinstance(hypothesis, dict),
            f"FRONTIER_HYPOTHESIS_NOT_OBJECT:{position}",
        )
        hypothesis_id = hypothesis.get("id")
        _require(
            isinstance(hypothesis_id, str) and bool(hypothesis_id),
            f"FRONTIER_HYPOTHESIS_ID_MISSING:{position}",
        )
        _require(
            hypothesis_id not in index,
            f"FRONTIER_HYPOTHESIS_ID_DUPLICATE:{hypothesis_id}",
        )
        _require(
            hypothesis.get("prior") in VALID_PRIORS,
            f"FRONTIER_PRIOR_INVALID:{hypothesis_id}",
        )
        _require(
            hypothesis.get("evidence_state") in VALID_EVIDENCE_STATES,
            f"FRONTIER_EVIDENCE_STATE_INVALID:{hypothesis_id}",
        )
        _require(
            hypothesis.get("investigation_state")
            in VALID_INVESTIGATION_STATES,
            f"FRONTIER_INVESTIGATION_STATE_INVALID:{hypothesis_id}",
        )
        _require(
            isinstance(hypothesis.get("description"), str)
            and bool(hypothesis["description"].strip()),
            f"FRONTIER_DESCRIPTION_MISSING:{hypothesis_id}",
        )
        index[hypothesis_id] = hypothesis

    return {
        "current_plan_id": plan["current_plan_id"],
        "current_plan_status": plan["status"],
        "current_architecture_id": architecture_id,
        "current_plan_path": str(CURRENT_PLAN_RELATIVE).replace("\\", "/"),
        "current_plan_sha256": plan_sha256,
        "frontier_path": str(frontier_relative).replace("\\", "/"),
        "frontier_sha256": frontier_sha256,
        "hypotheses": index,
    }


def render_frontier_catalog(snapshot: Mapping[str, Any]) -> str:
    lines = [
        "CURRENT INVESTIGATION FRONTIER:",
        f"plan_id: {snapshot['current_plan_id']}",
        f"architecture_id: {snapshot['current_architecture_id']}",
        f"frontier_sha256: {snapshot['frontier_sha256']}",
        "",
    ]

    for hypothesis_id in sorted(snapshot["hypotheses"]):
        item = snapshot["hypotheses"][hypothesis_id]
        lines.append(
            f"- {hypothesis_id} | prior={item['prior']} | "
            f"evidence={item['evidence_state']} | "
            f"investigation={item['investigation_state']} | "
            f"{item['description']}"
        )
    lines.extend([
        "",
        "FRONTIER USE CONTRACT:",
        "- These records are read-only project state, not LLM authority.",
        "- Do not regenerate DISPROVEN or EXHAUSTED explanations.",
        "- Prefer unresolved COMMON ACTIVE/ELIGIBLE explanations before widening.",
        "- DORMANT hypotheses remain dormant unless separate evidence changes state.",
        "- A novel explanation is a proposal only and is not added to the frontier.",
    ])
    return "\n".join(lines)


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "STATIC_FIT_SUFFICIENCY",
        "H_STATIC_FIT_IS_SUFFICIENT_FOR_CAPTURE",
        _rx(
            r"\bstatic\b.*\b(?:fit|pose)\b.*"
            r"\b(?:sufficient|establish|prove|proves|establishes)\b.*"
            r"\b(?:capture|rotation|operational)\b"
        ),
    ),
    (
        "MOVING_WRAP_BELT",
        "H_MOVING_WRAP_BELT_ASSEMBLY",
        _rx(
            r"\b(?:wrap[- ]?belt|wrap belt)\b.*"
            r"\b(?:translate|pivot|move|moves|moving|close|closes|closure)\b"
        ),
    ),
    (
        "TRANSLATING_ROLLER_CARRIER",
        "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
        _rx(
            r"\b(?:translate|translates|translating|translation|slide|sliding)"
            r"\b.*\b(?:roller|rollers|carrier)\b|"
            r"\b(?:roller|rollers|carrier)\b.*"
            r"\b(?:translate|translates|translating|translation|slide|sliding)\b"
        ),
    ),
    (
        "PIVOTING_ROLLER_CARRIER",
        "H_PIVOTING_ROLLER_ARM_OR_CARRIER",
        _rx(
            r"\b(?:pivot|pivots|pivoting|lever|arm)\b.*"
            r"\b(?:roller|capture|carrier)\b"
        ),
    ),
    (
        "PNEUMATIC_CAPTURE",
        "H_PNEUMATIC_CAPTURE_ACTUATOR",
        _rx(r"\b(?:pneumatic|cylinder)\b"),
    ),
    (
        "SPRING_PRELOAD",
        "H_SPRING_OR_COMPLIANT_PRELOAD_MECHANISM",
        _rx(r"\b(?:spring|preload|preloaded)\b"),
    ),
    (
        "NESTED_EXTERNAL_BOUNDARY",
        "H_UNBOUND_NESTED_OR_EXTERNAL_CAPTURE_MECHANISM",
        _rx(
            r"\b(?:nested|external|unmodeled|unmodelled|configuration|"
            r"assembly boundary|feature boundary|hidden assembly|hidden feature)\b"
        ),
    ),
    (
        "MOVING_SIDE_WALL",
        "H_MOVING_SIDE_WALL_OR_BELT_DRIVE",
        _rx(r"\b(?:moving side wall|side wall|side belt)\b"),
    ),
    (
        "PINCH_BELT_MULTIROLLER",
        "H_PINCH_BELT_OR_MULTIROLLER_CAPTURE",
        _rx(r"\b(?:pinch[- ]?belt|multi[- ]?roller|multiroller)\b"),
    ),
    (
        "V43_PRISM",
        "H_CANDIDATE_A_V43_PRISM",
        _rx(r"\b(?:v43\s+prism|prism candidate|candidate a)\b"),
    ),
    (
        "OTHER_EXPLICIT_MECHANISM",
        "H_OTHER_EXPLICIT_CLOSURE_MECHANISM",
        _rx(r"\b(?:cam|follower|clamp|mechanical linkage)\b"),
    ),
)

_CLASS_FALLBACK = {
    "CLOSURE_KINEMATICS": "H_CAPTURE_CLOSURE_OWNER",
    "COMPLIANCE_PRELOAD": "H_CAPTURE_COMPLIANCE_OR_PRELOAD",
    "SOURCE_BOUNDARY": "H_UNBOUND_NESTED_OR_EXTERNAL_CAPTURE_MECHANISM",
    "OTHER_EXPLICIT_MECHANISM": "H_OTHER_EXPLICIT_CLOSURE_MECHANISM",
}


def _disposition(item: Mapping[str, Any]) -> str:
    if item["evidence_state"] == "DISPROVEN":
        return "KNOWN_DISPROVEN"
    if item["investigation_state"] == "EXHAUSTED":
        return "KNOWN_EXHAUSTED"
    if item["investigation_state"] == "DORMANT":
        return "KNOWN_DORMANT"
    if item["investigation_state"] == "ACTIVE":
        return "KNOWN_ACTIVE"
    return "KNOWN_ELIGIBLE"


def _open_common_ids(snapshot: Mapping[str, Any]) -> list[str]:
    return sorted(
        hypothesis_id
        for hypothesis_id, item in snapshot["hypotheses"].items()
        if hypothesis_id in MECHANISM_ESCALATION_BLOCKER_IDS
        and item["prior"] == "COMMON"
        and item["investigation_state"] in {"ACTIVE", "ELIGIBLE"}
        and item["evidence_state"] != "DISPROVEN"
    )


def _bind_one(
    hypothesis: Mapping[str, Any],
    index: int,
    snapshot: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    statement = str(hypothesis.get("statement") or "")
    hypothesis_class = str(hypothesis.get("hypothesis_class") or "")
    frontier = snapshot["hypotheses"]
    matched_id = None
    match_rule = None
    for rule_name, hypothesis_id, pattern in _RULES:
        if hypothesis_id not in frontier:
            continue
        if pattern.search(statement):
            matched_id = hypothesis_id
            match_rule = rule_name
            break

    if matched_id is None:
        fallback_id = _CLASS_FALLBACK.get(hypothesis_class)
        if fallback_id in frontier:
            matched_id = fallback_id
            match_rule = f"CLASS_FALLBACK:{hypothesis_class}"

    if matched_id is None:
        blockers = _open_common_ids(snapshot)
        disposition = (
            "NOVEL_HELD_COMMON_FRONTIER_OPEN"
            if blockers
            else "NOVEL_CANDIDATE_REVIEW_REQUIRED"
        )
        return ({
            "hypothesis_index": index,
            "statement_sha256": _statement_sha256(statement),
            "hypothesis_class": hypothesis_class,
            "novel": True,
            "frontier_hypothesis_id": None,
            "frontier_prior": None,
            "frontier_evidence_state": None,
            "frontier_investigation_state": None,
            "binding_disposition": disposition,
            "match_rule": "NO_DETERMINISTIC_MATCH",
            "escalation_blockers": blockers,
            "frontier_action": "HOLD_FOR_REVIEW",
        }, [])

    item = frontier[matched_id]
    disposition = _disposition(item)
    violations: list[str] = []

    if disposition == "KNOWN_DISPROVEN":
        violations.append(
            f"FRONTIER_HYPOTHESIS_DISPROVEN:{index}:{matched_id}"
        )
    elif disposition == "KNOWN_EXHAUSTED":
        violations.append(
            f"FRONTIER_HYPOTHESIS_EXHAUSTED:{index}:{matched_id}"
        )

    action = {
        "KNOWN_ACTIVE": "REUSE_EXISTING_ACTIVE",
        "KNOWN_ELIGIBLE": "REUSE_EXISTING_ELIGIBLE",
        "KNOWN_DORMANT": "PRESERVE_DORMANT_STATE",
        "KNOWN_DISPROVEN": "SUPPRESS_DISPROVEN",
        "KNOWN_EXHAUSTED": "SUPPRESS_EXHAUSTED",
    }[disposition]
    return ({
        "hypothesis_index": index,
        "statement_sha256": _statement_sha256(statement),
        "hypothesis_class": hypothesis_class,
        "novel": False,
        "frontier_hypothesis_id": matched_id,
        "frontier_prior": item["prior"],
        "frontier_evidence_state": item["evidence_state"],
        "frontier_investigation_state": item["investigation_state"],
        "binding_disposition": disposition,
        "match_rule": match_rule,
        "escalation_blockers": [],
        "frontier_action": action,
    }, violations)


def bind_hypotheses(
    payload: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    hypotheses = list(payload.get("hypotheses") or [])
    bindings: list[dict[str, Any]] = []
    violations: list[str] = []

    for index, hypothesis in enumerate(hypotheses):
        binding, item_violations = _bind_one(
            hypothesis,
            index,
            snapshot,
        )
        bindings.append(binding)
        violations.extend(item_violations)

    if violations:
        error = FrontierBindingError(violations)
        error.bindings = bindings
        raise error

    return bindings


def frontier_snapshot_metadata(
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "current_plan_id": snapshot["current_plan_id"],
        "current_plan_status": snapshot["current_plan_status"],
        "current_architecture_id": snapshot["current_architecture_id"],
        "current_plan_path": snapshot["current_plan_path"],
        "current_plan_sha256": snapshot["current_plan_sha256"],
        "frontier_path": snapshot["frontier_path"],
        "frontier_sha256": snapshot["frontier_sha256"],
        "hypothesis_count": len(snapshot["hypotheses"]),
    }
