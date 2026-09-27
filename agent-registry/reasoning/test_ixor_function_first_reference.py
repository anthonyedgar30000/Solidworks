#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

from functional_temporal import evaluate_architecture, validate_architecture

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference_cases" / "ixor_function_first_bottle_labeler.functional-temporal.v1.json"


def load_case():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def by_id(items, item_id, field="id"):
    return next(item for item in items if item[field] == item_id)


class IXORFunctionFirstReferenceTests(unittest.TestCase):
    def test_reference_validates_without_mechanical_acceptance(self):
        case = load_case()
        indexes = validate_architecture(case)
        self.assertEqual(case["architecture_id"], "IXOR_FUNCTION_FIRST_BOTTLE_LABELER_REFERENCE")
        self.assertIn("CAPTURE_KINEMATIC_OWNER", indexes["obligations"])
        self.assertIn("BOTTLE_ROTATION_SOURCE_BOUND", indexes["obligations"])
        report = evaluate_architecture(case)
        self.assertEqual(report["machine_acceptance_state"], "MECHANICAL_ACCEPTANCE_BLOCKED")
        self.assertFalse(report["mechanical_acceptance_granted"])

    def test_prism_is_not_a_required_subsystem(self):
        case = load_case()
        subsystem_ids = {item["id"] for item in case["subsystems"]}
        obligation_ids = {item["id"] for item in case["obligations"]}
        interface_ids = {item["id"] for item in case["interfaces"]}
        self.assertNotIn("PRISM_CLOSURE_AND_REACTION", subsystem_ids)
        self.assertFalse(any(item_id.startswith("PRISM_") for item_id in obligation_ids))
        self.assertNotIn("PRISM_TO_CAPTURE_RESTRAINT", interface_ids)

    def test_function_first_state_machine_is_preserved(self):
        case = load_case()
        state_ids = {item["id"] for item in case["states"]}
        for state_id in (
            "ENTRY",
            "INDEXED",
            "CAPTURE_AND_ROTATION",
            "LABEL_TRANSFER_INTERVAL",
            "WRAP_ACTIVE",
            "RELEASE",
            "EXIT_CLEAR",
        ):
            self.assertIn(state_id, state_ids)

        capture = by_id(case["subsystems"], "CAPTURE_AND_ROTATION")
        self.assertIn("No candidate mechanism family is privileged", capture["goal"])

    def test_v43_is_preserved_only_as_candidate_a(self):
        case = load_case()
        candidate = by_id(case["hypotheses"], "H_CANDIDATE_A_V43_PRISM")
        self.assertEqual(candidate["evidence_state"], "WEAKENED")
        self.assertEqual(candidate["investigation_state"], "ELIGIBLE")
        self.assertIn("fit-check", candidate["description"])

        evidence_ids = {item["evidence_id"] for item in case["evidence_catalog"]}
        self.assertIn("E.V43.PRISM.FULL_CHAIN_MATES.ARCH_PROJECTION.20260927", evidence_ids)

    def test_candidate_family_set_is_diverse_and_explicit(self):
        case = load_case()
        hypothesis_ids = {item["id"] for item in case["hypotheses"]}
        expected = {
            "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
            "H_PIVOTING_ROLLER_ARM_OR_CARRIER",
            "H_MOVING_WRAP_BELT_ASSEMBLY",
            "H_MOVING_SIDE_WALL_OR_BELT_DRIVE",
            "H_PINCH_BELT_OR_MULTIROLLER_CAPTURE",
            "H_CANDIDATE_A_V43_PRISM",
            "H_OTHER_EXPLICIT_CLOSURE_MECHANISM",
        }
        rotation = by_id(case["obligations"], "BOTTLE_ROTATION_SOURCE_BOUND")
        self.assertIn("drive source", rotation["description"])
        self.assertIn("DETERMINISTIC_CALCULATION", rotation["expected_authority"])
        self.assertTrue(expected.issubset(hypothesis_ids))

    def test_next_frontier_is_requirements_then_candidates_then_screen(self):
        case = load_case()
        ids = [item["id"] for item in case["next_tests"]]
        self.assertEqual(
            ids[:3],
            [
                "TEST_FUNCTIONAL_REQUIREMENTS_BASELINE",
                "TEST_MECHANISM_CANDIDATE_FAMILY_SET",
                "TEST_MECHANISM_CANDIDATE_SCREEN",
            ],
        )

        baseline = by_id(case["next_tests"], "TEST_FUNCTIONAL_REQUIREMENTS_BASELINE")
        for token in (
            "mechanism-independent",
            "product entry/index position",
            "CAB peel/presentation relationship",
            "release",
            "neighboring-product constraints",
            "UNKNOWN",
        ):
            self.assertIn(token, baseline["question"])

        screen = by_id(case["next_tests"], "TEST_MECHANISM_CANDIDATE_SCREEN")
        for token in (
            "same deterministic obligation matrix",
            "PASS, FAIL, or UNRESOLVED",
            "negative evidence",
            "do not grant mechanical acceptance",
        ):
            self.assertIn(token, screen["question"])

    def test_static_fit_remains_disproven_as_operating_proof(self):
        case = load_case()
        hypothesis = by_id(case["hypotheses"], "H_STATIC_FIT_IS_SUFFICIENT_FOR_CAPTURE")
        self.assertEqual(hypothesis["evidence_state"], "DISPROVEN")
        self.assertEqual(hypothesis["investigation_state"], "EXHAUSTED")


if __name__ == "__main__":
    unittest.main()
