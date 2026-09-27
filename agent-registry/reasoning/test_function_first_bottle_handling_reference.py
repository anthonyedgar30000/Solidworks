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

    def test_contact_maintenance_source_probe_activates_candidate_eligibility(self):
        case = load_case()

        source_probe = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.CONTACT_MAINTENANCE_SOURCE_PROBE.20260927T150842223Z",
            field="evidence_id",
        )
        self.assertEqual(source_probe["evidence_type"], "solidworks_observation")
        self.assertEqual(source_probe["evidence_state"], "VERIFIED")
        self.assertEqual(source_probe["source_authority"], "SOLIDWORKS_LIVE_STATE")
        self.assertEqual(source_probe["payload"]["component_inventory_count"], 64)
        self.assertEqual(source_probe["payload"]["explicit_name_classification"]["spring_or_spring_synonym_matches"], [])
        self.assertEqual(source_probe["payload"]["explicit_name_classification"]["pneumatic_or_cylinder_matches"], [])
        self.assertEqual(
            source_probe["payload"]["explicit_name_classification"]["actuator_matches"],
            ["FITCHECK_PRISM_ACTUATOR_ENVELOPE_45x35x35_V43-1"],
        )
        self.assertTrue(
            all(
                row["incident_active_assembly_mate_count"] == 0
                for row in source_probe["payload"]["targets"]
            )
        )
        self.assertFalse(source_probe["mechanical_acceptance_granted"])

        dof_hypothesis = by_id(case["hypotheses"], "H_FUNCTION_FIRST_REQUIRED_DOF")
        self.assertEqual(dof_hypothesis["evidence_state"], "SUPPORTED")
        self.assertEqual(dof_hypothesis["investigation_state"], "EXHAUSTED")

        contact_hypothesis = by_id(case["hypotheses"], "H_FUNCTION_FIRST_CONTACT_SET")
        self.assertEqual(contact_hypothesis["evidence_state"], "SUPPORTED")
        self.assertEqual(contact_hypothesis["investigation_state"], "ACTIVE")

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
            "H_MOVING_SIDE_WALL_OR_BELT_DRIVE",
            "H_PINCH_BELT_OR_MULTIROLLER_CAPTURE",
            "H_CANDIDATE_A_V43_PRISM",
            "H_PNEUMATIC_CAPTURE_ACTUATOR",
            "H_OTHER_EXPLICIT_CLOSURE_MECHANISM",
        ):
            self.assertEqual(by_id(case["hypotheses"], item_id)["investigation_state"], "DORMANT")

        candidate_a = by_id(case["hypotheses"], "H_CANDIDATE_A_V43_PRISM")
        self.assertEqual(candidate_a["evidence_state"], "WEAKENED")
        pneumatic = by_id(case["hypotheses"], "H_PNEUMATIC_CAPTURE_ACTUATOR")
        self.assertEqual(pneumatic["evidence_state"], "WEAKENED")

    def test_finite_line_rank_and_source_probe_route_to_candidate_registry(self):
        case = load_case()

        wrap_axis = by_id(case["obligations"], "BOTTLE_WRAP_AXIS_BOUND")
        self.assertEqual(wrap_axis["verification_state"], "VERIFIED")

        manifold = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.BOTTLE_LATERAL_CONTACT_MANIFOLD.20260927T100903861Z",
            field="evidence_id",
        )
        self.assertEqual(
            [item["trimmed_axis_overlap"]["length_mm"] for item in manifold["payload"]["lateral_contact_manifolds"]],
            [93, 93, 93],
        )

        finite_rank = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.BOTTLE_FINITE_LINE_RESTRAINT_RANK.20260927T100903861Z",
            field="evidence_id",
        )
        self.assertEqual(finite_rank["payload"]["result"]["matrix_rank"], 5)
        self.assertEqual(finite_rank["payload"]["result"]["nullity"], 1)
        self.assertTrue(finite_rank["payload"]["result"]["wrap_axis_rotation_is_null_mode"])

        source_probe = by_id(
            case["evidence_catalog"],
            "E.FUNCTION_FIRST.CONTACT_MAINTENANCE_SOURCE_PROBE.20260927T150842223Z",
            field="evidence_id",
        )

        for obligation_id in (
            "CAPTURE_KINEMATIC_OWNER",
            "BOTTLE_SUPPORT_CONTACT_SET_BOUND",
            "BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE",
            "WRAP_CONTACT_THROUGHOUT_CAPTURE",
            "CAPTURE_REACTION_FORCE_PATH",
        ):
            obligation = by_id(case["obligations"], obligation_id)
            self.assertIn(source_probe["evidence_id"], obligation["evidence_refs"])
            self.assertEqual(obligation["verification_state"], "UNRESOLVED")

        self.assertEqual(
            by_id(case["obligations"], "CAPTURE_KINEMATIC_OWNER")["ambiguity_bucket"],
            "OEM_SOURCE_REQUIRED",
        )

        ids = [item["id"] for item in case["next_tests"]]
        self.assertEqual(ids, ["TEST_FUNCTION_FIRST_MAINTENANCE_CANDIDATE_ELIGIBILITY"])
        test = by_id(case["next_tests"], "TEST_FUNCTION_FIRST_MAINTENANCE_CANDIDATE_ELIGIBILITY")
        for token in (
            "Get-CGContactMaintenanceRequirements",
            "cg.mechanism.candidates",
            "translating roller carrier/slide",
            "pivoting roller arm/carrier",
            "moving wrap-belt assembly",
            "spring/compliant preload architecture",
            "V43 Prism remains WEAKENED/DORMANT",
            "pneumatic capture remains WEAKENED/DORMANT",
            "Do not rank/select a winner",
            "do not create or move CAD geometry",
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
