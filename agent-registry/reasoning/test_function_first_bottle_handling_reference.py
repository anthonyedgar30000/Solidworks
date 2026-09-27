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

    def test_function_first_hypotheses_active_and_mechanism_families_dormant(self):
        case = load_case()
        dof_hypothesis = by_id(case["hypotheses"], "H_FUNCTION_FIRST_REQUIRED_DOF")
        self.assertEqual(dof_hypothesis["evidence_state"], "SUPPORTED")
        self.assertEqual(dof_hypothesis["investigation_state"], "EXHAUSTED")
        contact_hypothesis = by_id(case["hypotheses"], "H_FUNCTION_FIRST_CONTACT_SET")
        self.assertEqual(contact_hypothesis["evidence_state"], "SUPPORTED")
        self.assertEqual(contact_hypothesis["investigation_state"], "ACTIVE")
        for item_id in (
            "H_CAPTURE_CLOSURE_OWNER",
            "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
            "H_PIVOTING_ROLLER_ARM_OR_CARRIER",
            "H_MOVING_WRAP_BELT_ASSEMBLY",
            "H_MOVING_SIDE_WALL_OR_BELT_DRIVE",
            "H_PINCH_BELT_OR_MULTIROLLER_CAPTURE",
            "H_CANDIDATE_A_V43_PRISM",
            "H_PNEUMATIC_CAPTURE_ACTUATOR",
            "H_SPRING_OR_COMPLIANT_PRELOAD_MECHANISM",
            "H_OTHER_EXPLICIT_CLOSURE_MECHANISM",
        ):
            self.assertEqual(by_id(case["hypotheses"], item_id)["investigation_state"], "DORMANT")

        candidate_a = by_id(case["hypotheses"], "H_CANDIDATE_A_V43_PRISM")
        self.assertEqual(candidate_a["evidence_state"], "WEAKENED")
        self.assertIn("zero-mate", candidate_a["description"])

    def test_finite_line_rank_is_admitted_and_frontier_routes_to_contact_maintenance(self):
        case = load_case()

        wrap_axis = by_id(case["obligations"], "BOTTLE_WRAP_AXIS_BOUND")
        self.assertEqual(wrap_axis["verification_state"], "VERIFIED")

        manifold = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.BOTTLE_LATERAL_CONTACT_MANIFOLD.20260927T100903861Z",
            field="evidence_id",
        )
        self.assertEqual(manifold["evidence_type"], "solidworks_observation")
        self.assertEqual(manifold["evidence_state"], "VERIFIED")
        self.assertEqual(manifold["source_authority"], "SOLIDWORKS_LIVE_STATE")
        self.assertEqual(
            [item["trimmed_axis_overlap"]["length_mm"] for item in manifold["payload"]["lateral_contact_manifolds"]],
            [93, 93, 93],
        )
        self.assertFalse(manifold["mechanical_acceptance_granted"])

        finite_rank = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.BOTTLE_FINITE_LINE_RESTRAINT_RANK.20260927T100903861Z",
            field="evidence_id",
        )
        self.assertEqual(finite_rank["evidence_type"], "deterministic_calculation")
        self.assertEqual(finite_rank["evidence_state"], "MEASURED_CALCULATED")
        self.assertEqual(finite_rank["payload"]["result"]["matrix_rank"], 5)
        self.assertEqual(finite_rank["payload"]["result"]["nullity"], 1)
        self.assertTrue(finite_rank["payload"]["result"]["wrap_axis_rotation_is_null_mode"])
        self.assertEqual(
            finite_rank["payload"]["result"]["five_dof_restraint_excluding_wrap_rotation"],
            "SUPPORTED_BY_IDEAL_FINITE_LINE_NORMAL_MODEL",
        )
        self.assertFalse(finite_rank["mechanical_acceptance_granted"])

        support = by_id(case["obligations"], "BOTTLE_SUPPORT_CONTACT_SET_BOUND")
        self.assertIn(manifold["evidence_id"], support["evidence_refs"])
        self.assertIn(finite_rank["evidence_id"], support["evidence_refs"])
        self.assertEqual(support["verification_state"], "UNRESOLVED")

        restraint = by_id(case["obligations"], "BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE")
        self.assertIn(finite_rank["evidence_id"], restraint["evidence_refs"])
        self.assertEqual(restraint["verification_state"], "UNRESOLVED")

        ids = [item["id"] for item in case["next_tests"]]
        self.assertEqual(ids, ["TEST_FUNCTION_FIRST_CONTACT_MAINTENANCE_PRELOAD_SOURCE"])
        test = by_id(case["next_tests"], "TEST_FUNCTION_FIRST_CONTACT_MAINTENANCE_PRELOAD_SOURCE")
        for token in (
            "93 mm lateral generator-line contacts",
            "rank 5/nullity 1",
            "maintains those unilateral lateral contacts",
            "CAPTURE_AND_ROTATION",
            "LABEL_TRANSFER_INTERVAL",
            "WRAP_ACTIVE",
            "usable travel/range",
            "reaction path",
            "Do not infer preload",
            "Do not select a mechanism",
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
