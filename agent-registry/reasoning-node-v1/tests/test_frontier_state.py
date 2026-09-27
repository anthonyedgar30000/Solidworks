import copy
import unittest
from pathlib import Path

from frontier_binding import load_current_frontier
from frontier_state import (
    COMMON_MECHANISM_SEQUENCE_IDS,
    UNCOMMON_MECHANISM_IDS,
    evaluate_frontier_state,
    render_frontier_state,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


class FrontierStateTests(unittest.TestCase):

    def setUp(self):
        self.snapshot = load_current_frontier(REPO_ROOT)

    def synthetic_snapshot(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["current_diagnostic"] = None
        return snapshot

    def test_current_function_first_frontier_is_common_open(self):
        state = evaluate_frontier_state(self.snapshot)

        self.assertEqual(
            state["common_frontier_state"],
            "COMMON_FRONTIER_OPEN",
        )
        self.assertEqual(
            state["widening_state"],
            "BLOCKED_BY_COMMON_OPEN",
        )
        self.assertEqual(
            state["search_exhaustion_state"],
            "COMMON_SEARCH_NOT_EXHAUSTED",
        )
        self.assertEqual(
            state["next_action_mode"],
            "REVIEW_DIAGNOSTIC_RESULT",
        )
        self.assertEqual(
            state["current_diagnostic_test_id"],
            "TEST_POP_V43_PRISM_DUAL_PIVOT_EXACT_HYPOTHETICAL_SWEEP",
        )
        self.assertEqual(
            state["current_diagnostic_state"],
            "EXECUTED_RESULT_REVIEW_REQUIRED",
        )
        self.assertEqual(
            state["current_diagnostic_mechanical_effect"],
            "NO_AUTOMATIC_HYPOTHESIS_STATE_CHANGE",
        )
        self.assertEqual(
            state["current_diagnostic_ambiguity_buckets"],
            [],
        )
        self.assertFalse(state["uncommon_review_eligible"])
        self.assertFalse(state["novel_review_eligible"])
        self.assertFalse(state["rare_review_eligible"])
        self.assertEqual(
            state["common_open_ids"],
            [
                "H_CAPTURE_CLOSURE_OWNER",
                "H_CAPTURE_COMPLIANCE_OR_PRELOAD",
                "H_MOVING_WRAP_BELT_ASSEMBLY",
                "H_PIVOTING_ROLLER_ARM_OR_CARRIER",
                "H_SPRING_OR_COMPLIANT_PRELOAD_MECHANISM",
                "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
            ],
        )
        self.assertEqual(
            state["common_dormant_ids"],
            ["H_MOVING_SIDE_WALL_OR_BELT_DRIVE"],
        )
        self.assertEqual(
            state["declared_next_test_ids"],
            [
                "TEST_FUNCTION_FIRST_POP_ACCEPTANCE_ENVELOPE",
                "TEST_POP_CANDIDATE_CONTRACT_SCREEN",
            ],
        )
        self.assertNotIn(
            "H_FUNCTION_FIRST_CONTACT_SET",
            state["escalation_blockers"],
        )

    def test_dormant_common_blocks_widening_after_open_common_exhausts(self):
        snapshot = self.synthetic_snapshot()

        for hypothesis_id in COMMON_MECHANISM_SEQUENCE_IDS:
            item = snapshot["hypotheses"][hypothesis_id]
            if hypothesis_id == "H_MOVING_SIDE_WALL_OR_BELT_DRIVE":
                continue
            item["investigation_state"] = "EXHAUSTED"

        state = evaluate_frontier_state(snapshot)

        self.assertEqual(
            state["common_frontier_state"],
            "COMMON_FRONTIER_DORMANT_REMAINS",
        )
        self.assertEqual(
            state["widening_state"],
            "BLOCKED_BY_COMMON_DORMANT",
        )
        self.assertEqual(
            state["search_exhaustion_state"],
            "COMMON_SEARCH_NOT_EXHAUSTED_DORMANT_REMAINS",
        )
        self.assertEqual(
            state["next_action_mode"],
            "REVIEW_DORMANT_COMMON_ACTIVATION",
        )
        self.assertEqual(
            state["escalation_blockers"],
            ["H_MOVING_SIDE_WALL_OR_BELT_DRIVE"],
        )
        self.assertFalse(state["uncommon_review_eligible"])
        self.assertFalse(state["novel_review_eligible"])

    def test_supported_common_blocks_widening_even_when_investigation_is_exhausted(self):
        snapshot = self.synthetic_snapshot()

        for hypothesis_id in COMMON_MECHANISM_SEQUENCE_IDS:
            snapshot["hypotheses"][hypothesis_id][
                "investigation_state"
            ] = "EXHAUSTED"

        supported_id = "H_MOVING_WRAP_BELT_ASSEMBLY"
        snapshot["hypotheses"][supported_id][
            "evidence_state"
        ] = "SUPPORTED"

        state = evaluate_frontier_state(snapshot)

        self.assertEqual(
            state["common_frontier_state"],
            "COMMON_FRONTIER_SUPPORTED_PRESENT",
        )
        self.assertEqual(
            state["search_exhaustion_state"],
            "COMMON_SEARCH_NOT_EXHAUSTED_SUPPORTED_PRESENT",
        )
        self.assertEqual(
            state["widening_state"],
            "BLOCKED_BY_COMMON_SUPPORTED",
        )
        self.assertEqual(
            state["next_action_mode"],
            "REVIEW_SUPPORTED_COMMON_RESOLUTION",
        )
        self.assertEqual(state["escalation_blockers"], [supported_id])
        self.assertFalse(state["uncommon_review_eligible"])
        self.assertFalse(state["novel_review_eligible"])

    def test_uncommon_review_becomes_eligible_only_after_common_exhaustion(self):
        snapshot = self.synthetic_snapshot()

        for hypothesis_id in COMMON_MECHANISM_SEQUENCE_IDS:
            snapshot["hypotheses"][hypothesis_id][
                "investigation_state"
            ] = "EXHAUSTED"

        state = evaluate_frontier_state(snapshot)

        self.assertEqual(
            state["common_frontier_state"],
            "COMMON_FRONTIER_EXHAUSTED",
        )
        self.assertEqual(
            state["widening_state"],
            "UNCOMMON_REVIEW_ELIGIBLE",
        )
        self.assertEqual(
            state["search_exhaustion_state"],
            "COMMON_SEARCH_EXHAUSTED",
        )
        self.assertEqual(
            state["uncommon_frontier_state"],
            "UNCOMMON_FRONTIER_DORMANT_REMAINS",
        )
        self.assertEqual(
            state["uncommon_search_exhaustion_state"],
            "UNCOMMON_SEARCH_NOT_EXHAUSTED_DORMANT_REMAINS",
        )
        self.assertEqual(
            state["next_action_mode"],
            "REVIEW_UNCOMMON_DORMANT_ACTIVATION",
        )
        self.assertEqual(state["escalation_blockers"], [])
        self.assertTrue(state["uncommon_review_eligible"])
        self.assertTrue(state["novel_review_eligible"])
        self.assertFalse(state["rare_review_eligible"])
        self.assertEqual(
            state["rare_review_requirement"],
            "UNCOMMON_EXHAUSTION_OR_DISTINCTIVE_EVIDENCE_REQUIRED",
        )
        self.assertFalse(state["distinctive_evidence_override_present"])
        self.assertEqual(
            state["rare_escalation_blockers"],
            sorted(UNCOMMON_MECHANISM_IDS),
        )

    def test_supported_uncommon_blocks_rare_widening(self):
        snapshot = self.synthetic_snapshot()

        for hypothesis_id in (
            *COMMON_MECHANISM_SEQUENCE_IDS,
            *UNCOMMON_MECHANISM_IDS,
        ):
            snapshot["hypotheses"][hypothesis_id][
                "investigation_state"
            ] = "EXHAUSTED"

        supported_id = "H_PINCH_BELT_OR_MULTIROLLER_CAPTURE"
        snapshot["hypotheses"][supported_id][
            "evidence_state"
        ] = "SUPPORTED"

        state = evaluate_frontier_state(snapshot)

        self.assertEqual(
            state["common_frontier_state"],
            "COMMON_FRONTIER_EXHAUSTED",
        )
        self.assertEqual(
            state["uncommon_frontier_state"],
            "UNCOMMON_FRONTIER_SUPPORTED_PRESENT",
        )
        self.assertEqual(
            state["next_action_mode"],
            "REVIEW_SUPPORTED_UNCOMMON_RESOLUTION",
        )
        self.assertFalse(state["rare_review_eligible"])
        self.assertEqual(
            state["rare_escalation_blockers"],
            [supported_id],
        )

    def test_rare_review_becomes_eligible_after_common_and_uncommon_exhaustion(self):
        snapshot = self.synthetic_snapshot()

        for hypothesis_id in (
            *COMMON_MECHANISM_SEQUENCE_IDS,
            *UNCOMMON_MECHANISM_IDS,
        ):
            snapshot["hypotheses"][hypothesis_id][
                "investigation_state"
            ] = "EXHAUSTED"
            if snapshot["hypotheses"][hypothesis_id][
                "evidence_state"
            ] == "SUPPORTED":
                snapshot["hypotheses"][hypothesis_id][
                    "evidence_state"
                ] = "UNRESOLVED"

        state = evaluate_frontier_state(snapshot)

        self.assertEqual(
            state["common_frontier_state"],
            "COMMON_FRONTIER_EXHAUSTED",
        )
        self.assertEqual(
            state["uncommon_frontier_state"],
            "UNCOMMON_FRONTIER_EXHAUSTED",
        )
        self.assertEqual(
            state["widening_state"],
            "RARE_REVIEW_ELIGIBLE",
        )
        self.assertEqual(
            state["next_action_mode"],
            "REVIEW_RARE_FRONTIER",
        )
        self.assertTrue(state["rare_review_eligible"])
        self.assertEqual(state["rare_escalation_blockers"], [])
        self.assertFalse(state["distinctive_evidence_override_present"])

    def test_render_is_advisory_and_read_only(self):
        state = evaluate_frontier_state(self.snapshot)
        rendered = render_frontier_state(state)

        self.assertIn("COMMON_FRONTIER_OPEN", rendered)
        self.assertIn("REVIEW_DIAGNOSTIC_RESULT", rendered)
        self.assertIn("EXECUTED_RESULT_REVIEW_REQUIRED", rendered)
        self.assertIn("NO_AUTOMATIC_HYPOTHESIS_STATE_CHANGE", rendered)
        self.assertIn(
            "TEST_FUNCTION_FIRST_POP_ACCEPTANCE_ENVELOPE",
            rendered,
        )
        self.assertIn(
            "TEST_POP_CANDIDATE_CONTRACT_SCREEN",
            rendered,
        )
        self.assertIn(
            "does not change any hypothesis evidence or investigation state",
            rendered,
        )
        self.assertIn(
            "RARE review becomes eligible after the modeled UNCOMMON sequence is exhausted",
            rendered,
        )
        self.assertIn(
            "Early RARE escalation from distinctive evidence is not modeled here",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
