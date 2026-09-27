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
        indexes = validate_architecture(case)
        report = evaluate_architecture(case)
        self.assertEqual(case["architecture_id"], "IXOR_FUNCTION_FIRST_BOTTLE_HANDLING_REFERENCE")
        self.assertIn("BOTTLE_REQUIRED_DOF_BOUND", indexes["obligations"])
        self.assertIn("BOTTLE_SUPPORT_CONTACT_SET_BOUND", indexes["obligations"])
        self.assertIn("BOTTLE_ROTATION_SOURCE_BOUND", indexes["obligations"])
        dof = by_id(case["obligations"], "BOTTLE_REQUIRED_DOF_BOUND")
        self.assertEqual(dof["verification_state"], "VERIFIED")
        self.assertIn("E.FUNCTION_FIRST.BOTTLE_DOF.20260927T075043247Z", dof["evidence_refs"])
        self.assertEqual(by_id(case["obligations"], "BOTTLE_SUPPORT_CONTACT_SET_BOUND")["verification_state"], "UNRESOLVED")
        self.assertEqual(by_id(case["obligations"], "BOTTLE_ROTATION_SOURCE_BOUND")["verification_state"], "UNRESOLVED")
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
            "TEST_FRESH_V42_COMPONENT_BINDING",
        ):
            self.assertNotIn(test_id, next_test_ids)

    def test_dof_is_verified_but_support_and_rotation_source_remain_unresolved(self):
        case = load_case()
        dof = by_id(case["obligations"], "BOTTLE_REQUIRED_DOF_BOUND")
        support = by_id(case["obligations"], "BOTTLE_SUPPORT_CONTACT_SET_BOUND")
        rotation = by_id(case["obligations"], "BOTTLE_ROTATION_SOURCE_BOUND")

        self.assertEqual(dof["verification_state"], "VERIFIED")
        self.assertEqual(dof["depends_on_requirement_ids"], [])
        self.assertIn("E.FUNCTION_FIRST.BOTTLE_DOF.20260927T075043247Z", dof["evidence_refs"])
        self.assertEqual(support["verification_state"], "UNRESOLVED")
        self.assertEqual(rotation["verification_state"], "UNRESOLVED")

        evidence = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.BOTTLE_DOF.20260927T075043247Z",
            field="evidence_id",
        )
        self.assertEqual(evidence["evidence_type"], "deterministic_calculation")
        self.assertEqual(evidence["evidence_state"], "MEASURED_CALCULATED")
        self.assertFalse(evidence["mechanical_acceptance_granted"])

    def test_contact_maintenance_candidate_registry_is_admitted_without_selection(self):
        case = load_case()

        source_probe = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.CONTACT_MAINTENANCE_SOURCE_PROBE.20260927T150842223Z",
            field="evidence_id",
        )
        self.assertEqual(source_probe["evidence_state"], "VERIFIED")
        self.assertFalse(source_probe["mechanical_acceptance_granted"])

        registry = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.MAINTENANCE_CANDIDATE_REGISTRY.20260927T151927324Z",
            field="evidence_id",
        )
        self.assertEqual(registry["evidence_type"], "deterministic_calculation")
        self.assertEqual(registry["evidence_state"], "MEASURED_CALCULATED")
        self.assertEqual(registry["payload"]["result"]["selection_status"], "NOT_SELECTED")
        self.assertEqual(
            registry["payload"]["result"]["eligible_candidates"],
            [
                "CANDIDATE_TRANSLATING_ROLLER_CARRIER",
                "CANDIDATE_PIVOTING_ROLLER_CARRIER",
                "CANDIDATE_MOVING_WRAP_BELT_ASSEMBLY",
                "CANDIDATE_SPRING_OR_COMPLIANT_PRELOAD",
            ],
        )
        self.assertFalse(registry["mechanical_acceptance_granted"])

        owner = by_id(case["obligations"], "CAPTURE_KINEMATIC_OWNER")
        self.assertIn(registry["evidence_id"], owner["evidence_refs"])
        self.assertEqual(owner["verification_state"], "UNRESOLVED")
        self.assertEqual(owner["ambiguity_bucket"], "MULTIPLE_PLAUSIBLE_HYPOTHESES")

        closure_owner = by_id(case["hypotheses"], "H_CAPTURE_CLOSURE_OWNER")
        self.assertEqual(closure_owner["investigation_state"], "ACTIVE")

        for item_id in (
            "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
            "H_PIVOTING_ROLLER_ARM_OR_CARRIER",
            "H_MOVING_WRAP_BELT_ASSEMBLY",
            "H_SPRING_OR_COMPLIANT_PRELOAD_MECHANISM",
        ):
            self.assertEqual(by_id(case["hypotheses"], item_id)["investigation_state"], "ELIGIBLE")

        for item_id in (
            "H_CANDIDATE_A_V43_PRISM",
            "H_PNEUMATIC_CAPTURE_ACTUATOR",
        ):
            self.assertEqual(by_id(case["hypotheses"], item_id)["investigation_state"], "DORMANT")
            self.assertEqual(by_id(case["hypotheses"], item_id)["evidence_state"], "WEAKENED")

    def test_candidate_registry_routes_to_nonranking_screen_contract(self):
        case = load_case()

        ids = [item["id"] for item in case["next_tests"]]
        self.assertEqual(ids, ["TEST_FUNCTION_FIRST_MECHANISM_SCREEN_CONTRACT"])
        test = by_id(case["next_tests"], "TEST_FUNCTION_FIRST_MECHANISM_SCREEN_CONTRACT")

        for token in (
            "cg.mechanism.screen",
            "Test-CGMechanismCandidate",
            "Get-CGMechanismCandidates",
            "closure owner",
            "open/capture/release motion definition",
            "contact-maintenance law",
            "bottle-contact interval",
            "wrap-axis preservation",
            "reaction path",
            "release behavior",
            "PASS only when explicitly established",
            "FAIL only when contradicted",
            "otherwise UNRESOLVED",
            "MAINTENANCE_LAW_AUGMENTATION",
            "Do not rank, score, prefer, select",
            "do not create/move CAD geometry",
        ):
            self.assertIn(token, test["question"])

        preload = by_id(case["hypotheses"], "H_CAPTURE_COMPLIANCE_OR_PRELOAD")
        self.assertEqual(preload["evidence_state"], "UNRESOLVED")
        self.assertEqual(preload["investigation_state"], "ACTIVE")

    def test_static_fit_remains_disproven_as_operating_proof(self):
        case = load_case()
        hypothesis = by_id(case["hypotheses"], "H_STATIC_FIT_IS_SUFFICIENT_FOR_CAPTURE")
        self.assertEqual(hypothesis["evidence_state"], "DISPROVEN")
        self.assertEqual(hypothesis["investigation_state"], "EXHAUSTED")


if __name__ == "__main__":
    unittest.main()
