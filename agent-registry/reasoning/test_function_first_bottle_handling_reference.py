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

    def test_wrench_rank_is_admitted_and_frontier_routes_to_contact_manifold(self):
        case = load_case()

        wrap_axis = by_id(case["obligations"], "BOTTLE_WRAP_AXIS_BOUND")
        self.assertEqual(wrap_axis["verification_state"], "VERIFIED")
        self.assertIn("E.FUNCTION_FIRST.BOTTLE_CYLINDER_AXIS.20260927T090058895Z", wrap_axis["evidence_refs"])
        self.assertIn("E.FUNCTION_FIRST.BOTTLE_WRAP_AXIS_BINDING.20260927T090058895Z", wrap_axis["evidence_refs"])

        wrench = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.BOTTLE_CONTACT_WRENCH_RANK.20260927T091125291Z",
            field="evidence_id",
        )
        self.assertEqual(wrench["evidence_type"], "deterministic_calculation")
        self.assertEqual(wrench["evidence_state"], "MEASURED_CALCULATED")
        self.assertEqual(wrench["source_authority"], "DETERMINISTIC_CALCULATION")
        self.assertEqual(wrench["payload"]["result"]["matrix_rank"], 4)
        self.assertEqual(wrench["payload"]["result"]["nullity"], 2)
        self.assertTrue(wrench["payload"]["result"]["wrap_axis_rotation_test"]["is_null_mode"])
        self.assertEqual(
            wrench["payload"]["result"]["restraint_projection"]["additional_independent_null_modes_beyond_wrap_axis_rotation"],
            1,
        )
        self.assertEqual(
            wrench["payload"]["result"]["restraint_projection"]["five_dof_restraint_excluding_wrap_axis_rotation"],
            "NOT_SUPPORTED_BY_CURRENT_FOUR_POINT_NORMAL_MODEL",
        )
        self.assertFalse(wrench["mechanical_acceptance_granted"])

        support = by_id(case["obligations"], "BOTTLE_SUPPORT_CONTACT_SET_BOUND")
        self.assertIn("E.FUNCTION_FIRST.BOTTLE_CONTACT_WRENCH_RANK.20260927T091125291Z", support["evidence_refs"])
        self.assertEqual(support["verification_state"], "UNRESOLVED")

        rotation = by_id(case["obligations"], "BOTTLE_ROTATION_SOURCE_BOUND")
        self.assertEqual(rotation["verification_state"], "UNRESOLVED")
        self.assertIn("BOTTLE_WRAP_AXIS_BOUND", rotation["depends_on_requirement_ids"])

        ids = [item["id"] for item in case["next_tests"]]
        self.assertEqual(ids, ["TEST_FUNCTION_FIRST_LATERAL_CONTACT_MANIFOLD"])
        test = by_id(case["next_tests"], "TEST_FUNCTION_FIRST_LATERAL_CONTACT_MANIFOLD")
        for token in (
            "point, line/generator, or finite patch contact",
            "measure its extent along the bound bottle rotation_wrap_axis",
            "ClosestDistance point",
            "adds an independent tilt-restraint constraint",
            "preserving rotation about the bound wrap axis",
            "preload/compliance",
            "interval-wide behavior",
        ):
            self.assertIn(token, test["question"])
        self.assertEqual(test["resolves_requirement_ids"], ["BOTTLE_SUPPORT_CONTACT_SET_BOUND"])

    def test_static_fit_remains_disproven_as_operating_proof(self):
        case = load_case()
        hypothesis = by_id(case["hypotheses"], "H_STATIC_FIT_IS_SUFFICIENT_FOR_CAPTURE")
        self.assertEqual(hypothesis["evidence_state"], "DISPROVEN")
        self.assertEqual(hypothesis["investigation_state"], "EXHAUSTED")


if __name__ == "__main__":
    unittest.main()
