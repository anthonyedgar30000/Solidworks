from __future__ import annotations

from typing import Any, Mapping


COMMON_MECHANISM_SEQUENCE_IDS = (
    "H_CAPTURE_CLOSURE_OWNER",
    "H_CAPTURE_COMPLIANCE_OR_PRELOAD",
    "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
    "H_PIVOTING_ROLLER_ARM_OR_CARRIER",
    "H_MOVING_WRAP_BELT_ASSEMBLY",
    "H_SPRING_OR_COMPLIANT_PRELOAD_MECHANISM",
    "H_MOVING_SIDE_WALL_OR_BELT_DRIVE",
)

UNCOMMON_MECHANISM_IDS = (
    "H_UNBOUND_NESTED_OR_EXTERNAL_CAPTURE_MECHANISM",
    "H_PNEUMATIC_CAPTURE_ACTUATOR",
    "H_OTHER_EXPLICIT_CLOSURE_MECHANISM",
    "H_PINCH_BELT_OR_MULTIROLLER_CAPTURE",
)


class FrontierStateError(ValueError):
    def __init__(self, violations: list[str]):
        self.violations = tuple(violations)
        super().__init__("; ".join(self.violations))


def _state_of(item: Mapping[str, Any]) -> str:
    evidence_state = item["evidence_state"]
    investigation_state = item["investigation_state"]

    if evidence_state == "DISPROVEN":
        return "RESOLVED_OUT_DISPROVEN"
    if evidence_state == "SUPPORTED":
        return "SUPPORTED"
    if investigation_state == "EXHAUSTED":
        return "RESOLVED_OUT_EXHAUSTED"
    if investigation_state in {"ACTIVE", "ELIGIBLE"}:
        return "OPEN"
    if investigation_state == "DORMANT":
        return "DORMANT_PENDING"
    return "UNCLASSIFIED"


def _require_hypothesis(
    snapshot: Mapping[str, Any],
    hypothesis_id: str,
    expected_prior: str,
) -> Mapping[str, Any]:
    hypotheses = snapshot.get("hypotheses") or {}
    if hypothesis_id not in hypotheses:
        raise FrontierStateError([
            f"FRONTIER_STATE_HYPOTHESIS_MISSING:{hypothesis_id}"
        ])

    item = hypotheses[hypothesis_id]
    if item.get("prior") != expected_prior:
        raise FrontierStateError([
            f"FRONTIER_STATE_PRIOR_MISMATCH:{hypothesis_id}:"
            f"{item.get('prior')}:{expected_prior}"
        ])

    return item


def _declared_test_ids(
    snapshot: Mapping[str, Any],
    hypothesis_ids: set[str],
) -> list[str]:
    tests = snapshot.get("next_tests") or {}
    declared: list[str] = []

    for test_id, test in tests.items():
        test_hypotheses = set(test.get("hypothesis_ids") or [])
        if test_hypotheses & hypothesis_ids:
            declared.append(test_id)

    return sorted(declared)


def evaluate_frontier_state(
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    common_open: list[str] = []
    common_supported: list[str] = []
    common_dormant: list[str] = []
    common_resolved_out: list[str] = []
    common_weakened: list[str] = []

    for hypothesis_id in COMMON_MECHANISM_SEQUENCE_IDS:
        item = _require_hypothesis(snapshot, hypothesis_id, "COMMON")
        state = _state_of(item)

        if item["evidence_state"] == "WEAKENED":
            common_weakened.append(hypothesis_id)

        if state == "OPEN":
            common_open.append(hypothesis_id)
        elif state == "SUPPORTED":
            common_supported.append(hypothesis_id)
        elif state == "DORMANT_PENDING":
            common_dormant.append(hypothesis_id)
        elif state.startswith("RESOLVED_OUT_"):
            common_resolved_out.append(hypothesis_id)
        else:
            raise FrontierStateError([
                f"FRONTIER_STATE_UNCLASSIFIED:{hypothesis_id}"
            ])

    uncommon_open: list[str] = []
    uncommon_supported: list[str] = []
    uncommon_dormant: list[str] = []
    uncommon_resolved_out: list[str] = []
    uncommon_weakened: list[str] = []

    for hypothesis_id in UNCOMMON_MECHANISM_IDS:
        item = _require_hypothesis(snapshot, hypothesis_id, "UNCOMMON")
        state = _state_of(item)

        if item["evidence_state"] == "WEAKENED":
            uncommon_weakened.append(hypothesis_id)

        if state == "OPEN":
            uncommon_open.append(hypothesis_id)
        elif state == "SUPPORTED":
            uncommon_supported.append(hypothesis_id)
        elif state == "DORMANT_PENDING":
            uncommon_dormant.append(hypothesis_id)
        elif state.startswith("RESOLVED_OUT_"):
            uncommon_resolved_out.append(hypothesis_id)
        else:
            raise FrontierStateError([
                f"FRONTIER_STATE_UNCLASSIFIED:{hypothesis_id}"
            ])

    if uncommon_open:
        uncommon_frontier_state = "UNCOMMON_FRONTIER_OPEN"
        uncommon_search_exhaustion_state = (
            "UNCOMMON_SEARCH_NOT_EXHAUSTED"
        )
    elif uncommon_supported:
        uncommon_frontier_state = "UNCOMMON_FRONTIER_SUPPORTED_PRESENT"
        uncommon_search_exhaustion_state = (
            "UNCOMMON_SEARCH_NOT_EXHAUSTED_SUPPORTED_PRESENT"
        )
    elif uncommon_dormant:
        uncommon_frontier_state = "UNCOMMON_FRONTIER_DORMANT_REMAINS"
        uncommon_search_exhaustion_state = (
            "UNCOMMON_SEARCH_NOT_EXHAUSTED_DORMANT_REMAINS"
        )
    else:
        uncommon_frontier_state = "UNCOMMON_FRONTIER_EXHAUSTED"
        uncommon_search_exhaustion_state = "UNCOMMON_SEARCH_EXHAUSTED"

    if common_open:
        common_frontier_state = "COMMON_FRONTIER_OPEN"
        search_exhaustion_state = "COMMON_SEARCH_NOT_EXHAUSTED"
        widening_state = "BLOCKED_BY_COMMON_OPEN"
        escalation_blockers = sorted(common_open)
    elif common_supported:
        common_frontier_state = "COMMON_FRONTIER_SUPPORTED_PRESENT"
        search_exhaustion_state = (
            "COMMON_SEARCH_NOT_EXHAUSTED_SUPPORTED_PRESENT"
        )
        widening_state = "BLOCKED_BY_COMMON_SUPPORTED"
        escalation_blockers = sorted(common_supported)
    elif common_dormant:
        common_frontier_state = "COMMON_FRONTIER_DORMANT_REMAINS"
        search_exhaustion_state = (
            "COMMON_SEARCH_NOT_EXHAUSTED_DORMANT_REMAINS"
        )
        widening_state = "BLOCKED_BY_COMMON_DORMANT"
        escalation_blockers = sorted(common_dormant)
    else:
        common_frontier_state = "COMMON_FRONTIER_EXHAUSTED"
        search_exhaustion_state = "COMMON_SEARCH_EXHAUSTED"
        widening_state = (
            "RARE_REVIEW_ELIGIBLE"
            if uncommon_frontier_state == "UNCOMMON_FRONTIER_EXHAUSTED"
            else "UNCOMMON_REVIEW_ELIGIBLE"
        )
        escalation_blockers = []

    open_common_set = set(common_open)
    declared_next_tests = _declared_test_ids(
        snapshot,
        open_common_set,
    )
    declared_uncommon_test_ids = _declared_test_ids(
        snapshot,
        set(uncommon_open),
    )

    current_diagnostic = snapshot.get("current_diagnostic")
    diagnostic_next_action = (
        current_diagnostic.get("next_action_mode")
        if isinstance(current_diagnostic, Mapping)
        else None
    )

    if diagnostic_next_action:
        next_action_mode = diagnostic_next_action
    elif common_open and declared_next_tests:
        next_action_mode = "RUN_DECLARED_COMMON_TESTS"
    elif common_open:
        next_action_mode = "COMMON_TEST_REQUIRED"
    elif common_supported:
        next_action_mode = "REVIEW_SUPPORTED_COMMON_RESOLUTION"
    elif common_dormant:
        next_action_mode = "REVIEW_DORMANT_COMMON_ACTIVATION"
    elif uncommon_open and declared_uncommon_test_ids:
        next_action_mode = "RUN_DECLARED_UNCOMMON_TESTS"
    elif uncommon_open:
        next_action_mode = "UNCOMMON_TEST_REQUIRED"
    elif uncommon_supported:
        next_action_mode = "REVIEW_SUPPORTED_UNCOMMON_RESOLUTION"
    elif uncommon_dormant:
        next_action_mode = "REVIEW_UNCOMMON_DORMANT_ACTIVATION"
    else:
        next_action_mode = "REVIEW_RARE_FRONTIER"

    common_exhausted = (
        common_frontier_state == "COMMON_FRONTIER_EXHAUSTED"
    )
    uncommon_exhausted = (
        uncommon_frontier_state == "UNCOMMON_FRONTIER_EXHAUSTED"
    )
    uncommon_review_eligible = common_exhausted
    novel_review_eligible = common_exhausted
    rare_review_eligible = common_exhausted and uncommon_exhausted

    if common_exhausted:
        rare_escalation_blockers = sorted(
            uncommon_open + uncommon_supported + uncommon_dormant
        )
    else:
        rare_escalation_blockers = list(escalation_blockers)

    return {
        "common_frontier_state": common_frontier_state,
        "search_exhaustion_state": search_exhaustion_state,
        "widening_state": widening_state,
        "next_action_mode": next_action_mode,
        "current_diagnostic_test_id": (
            current_diagnostic.get("test_id")
            if isinstance(current_diagnostic, Mapping)
            else None
        ),
        "current_diagnostic_state": (
            current_diagnostic.get("diagnostic_state")
            if isinstance(current_diagnostic, Mapping)
            else None
        ),
        "current_diagnostic_attempt_id": (
            current_diagnostic.get("attempt_id")
            if isinstance(current_diagnostic, Mapping)
            else None
        ),
        "current_diagnostic_mechanical_effect": (
            current_diagnostic.get("mechanical_effect")
            if isinstance(current_diagnostic, Mapping)
            else None
        ),
        "current_diagnostic_ambiguity_buckets": (
            list(current_diagnostic.get("ambiguity_buckets") or [])
            if isinstance(current_diagnostic, Mapping)
            else []
        ),
        "current_diagnostic_resume_condition": (
            current_diagnostic.get("resume_condition")
            if isinstance(current_diagnostic, Mapping)
            else None
        ),
        "common_open_ids": sorted(common_open),
        "common_supported_ids": sorted(common_supported),
        "common_dormant_ids": sorted(common_dormant),
        "common_resolved_out_ids": sorted(common_resolved_out),
        "common_weakened_ids": sorted(common_weakened),
        "uncommon_frontier_state": uncommon_frontier_state,
        "uncommon_search_exhaustion_state": (
            uncommon_search_exhaustion_state
        ),
        "uncommon_open_ids": sorted(uncommon_open),
        "uncommon_supported_ids": sorted(uncommon_supported),
        "uncommon_dormant_ids": sorted(uncommon_dormant),
        "uncommon_resolved_out_ids": sorted(uncommon_resolved_out),
        "uncommon_weakened_ids": sorted(uncommon_weakened),
        "escalation_blockers": escalation_blockers,
        "rare_escalation_blockers": rare_escalation_blockers,
        "declared_next_test_ids": declared_next_tests,
        "declared_uncommon_test_ids": declared_uncommon_test_ids,
        "uncommon_review_eligible": uncommon_review_eligible,
        "novel_review_eligible": novel_review_eligible,
        "rare_review_eligible": rare_review_eligible,
        "distinctive_evidence_override_present": False,
        "rare_review_requirement": (
            "UNCOMMON_EXHAUSTION_OR_DISTINCTIVE_EVIDENCE_REQUIRED"
        ),
        "state_mutation_authority": "NONE",
        "mechanical_acceptance_authority": "NONE",
    }


def render_frontier_state(
    state: Mapping[str, Any],
) -> str:
    lines = [
        "DETERMINISTIC FRONTIER STATE:",
        f"common_frontier_state: {state['common_frontier_state']}",
        f"search_exhaustion_state: {state['search_exhaustion_state']}",
        f"uncommon_frontier_state: {state['uncommon_frontier_state']}",
        f"uncommon_search_exhaustion_state: {state['uncommon_search_exhaustion_state']}",
        f"widening_state: {state['widening_state']}",
        f"next_action_mode: {state['next_action_mode']}",
        f"current_diagnostic_test_id: {state['current_diagnostic_test_id']}",
        f"current_diagnostic_state: {state['current_diagnostic_state']}",
        f"current_diagnostic_attempt_id: {state['current_diagnostic_attempt_id']}",
        f"current_diagnostic_mechanical_effect: {state['current_diagnostic_mechanical_effect']}",
        "current_diagnostic_ambiguity_buckets: "
        + ",".join(state["current_diagnostic_ambiguity_buckets"]),
        f"current_diagnostic_resume_condition: {state['current_diagnostic_resume_condition']}",
        "common_open_ids: "
        + ",".join(state["common_open_ids"]),
        "common_supported_ids: "
        + ",".join(state["common_supported_ids"]),
        "common_dormant_ids: "
        + ",".join(state["common_dormant_ids"]),
        "common_resolved_out_ids: "
        + ",".join(state["common_resolved_out_ids"]),
        "uncommon_dormant_ids: "
        + ",".join(state["uncommon_dormant_ids"]),
        "escalation_blockers: "
        + ",".join(state["escalation_blockers"]),
        "rare_escalation_blockers: "
        + ",".join(state["rare_escalation_blockers"]),
        "declared_next_test_ids: "
        + ",".join(state["declared_next_test_ids"]),
        "declared_uncommon_test_ids: "
        + ",".join(state["declared_uncommon_test_ids"]),
        f"uncommon_review_eligible: {state['uncommon_review_eligible']}",
        f"novel_review_eligible: {state['novel_review_eligible']}",
        f"rare_review_eligible: {state['rare_review_eligible']}",
        f"distinctive_evidence_override_present: {state['distinctive_evidence_override_present']}",
        "",
        "FRONTIER STATE CONTRACT:",
        "- This is a deterministic projection of versioned project state.",
        "- A bound current-plan diagnostic takes precedence over generic frontier test selection.",
        "- A blocked CAD read/rebind attempt is not negative mechanical evidence and does not weaken a hypothesis.",
        "- It does not change any hypothesis evidence or investigation state.",
        "- COMMON ACTIVE/ELIGIBLE mechanism explanations block widening.",
        "- A SUPPORTED COMMON mechanism also blocks widening; support is not failure or exhaustion.",
        "- If no COMMON item is open or supported, unresolved COMMON DORMANT items still block widening.",
        "- UNCOMMON review is eligible only after the modeled COMMON sequence is exhausted.",
        "- RARE review becomes eligible after the modeled UNCOMMON sequence is exhausted.",
        "- Early RARE escalation from distinctive evidence is not modeled here; the override remains false until an authoritative deterministic signal is designed.",
    ]
    return "\n".join(lines)
