#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

from functional_temporal import evaluate_architecture, validate_architecture

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference_cases" / "function_first_bottle_handling.functional-temporal.v1.json"

def load_case():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))

def by_id(items, item_id, field="id"):
    return next(item for item in items if item[field] == item_id)

class FunctionFirstBottleHandlingTests(unittest.TestCase):
    def test_reference_validates_without_mechanical_acceptance(self):
        case = load_case()
        validate_architecture(case)
        report = evaluate_architecture(case)
        self.assertEqual(case["architecture_id"], "IXOR_FUNCTION_FIRST_BOTTLE_HANDLING_REFERENCE")
        self.assertEqual(report["machine_acceptance_state"], "MECHANICAL_ACCEPTANCE_BLOCKED")
        self.assertFalse(report["mechanical_acceptance_granted"])

    def test_prism_is_not_an_active_required_subsystem(self):
        case = load_case()
        subsystem_ids = {item["id"] for item in case["subsystems"]}
        obligation_ids = {item["id"] for item in case["obligations"]}
        next_test_ids = {item["id"] for item in case["next_tests"]}
        self.assertNotIn("PRISM_CLOSURE_AND_REACTION", subsystem_ids)
        for item_id in (
            "PRISM_KINEMATIC_CHAIN_BOUND",
            "PRISM_STROKE_AND_CLOSURE_LIMITS_BOUND",
            "PRISM_REACTION_FORCE_PATH_BOUND",
        ):
            self.assertNotIn(item_id, obligation_ids)
        for test_id in (
            "TEST_V43_PRISM_ACTUATION_LIMITS_AND_REACTION",
            "TEST_V43_PRISM_KINEMATIC_DESIGN_INTENT_SOURCE",
            "TEST_CAPTURE_KINEMATIC_OWNER",
        ):
            self.assertNotIn(test_id, next_test_ids)

    def test_bottle_requirements_are_bound_before_mechanism_selection(self):
        case = load_case()
        obligation_ids = {item["id"] for item in case["obligations"]}
        self.assertIn("BOTTLE_REQUIRED_DOF_BOUND", obligation_ids)
        self.assertIn("BOTTLE_SUPPORT_CONTACT_SET_BOUND", obligation_ids)

        test = by_id(case["next_tests"], "TEST_FUNCTION_FIRST_BOTTLE_SUPPORT_RESTRAINT_DOF")
        self.assertEqual(
            test["hypothesis_ids"],
            ["H_FUNCTION_FIRST_REQUIRED_DOF", "H_FUNCTION_FIRST_CONTACT_SET"],
        )
        for token in (
            "Before selecting any capture mechanism",
            "D48 upright bottle",
            "rotation must remain intentionally available",
            "distinguish current-pose contacts from required functional contacts",
            "must not assume the v43 Prism",
        ):
            self.assertIn(token, test["question"])

    def test_function_first_hypotheses_active_and_mechanism_families_dormant(self):
        case = load_case()
        self.assertEqual(
            by_id(case["hypotheses"], "H_FUNCTION_FIRST_REQUIRED_DOF")["investigation_state"],
            "ACTIVE",
        )
        self.assertEqual(
            by_id(case["hypotheses"], "H_FUNCTION_FIRST_CONTACT_SET")["investigation_state"],
            "ACTIVE",
        )
        for item_id in (
            "H_CAPTURE_CLOSURE_OWNER",
            "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
            "H_PIVOTING_ROLLER_ARM_OR_CARRIER",
            "H_MOVING_WRAP_BELT_ASSEMBLY",
            "H_PNEUMATIC_CAPTURE_ACTUATOR",
            "H_SPRING_OR_COMPLIANT_PRELOAD_MECHANISM",
            "H_OTHER_EXPLICIT_CLOSURE_MECHANISM",
        ):
            self.assertEqual(by_id(case["hypotheses"], item_id)["investigation_state"], "DORMANT")

if __name__ == "__main__":
    unittest.main()
