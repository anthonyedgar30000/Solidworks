#!/usr/bin/env python3
"""Regression tests for functional decomposition and temporal state reasoning."""

import copy
import json
import unittest
from pathlib import Path

from functional_temporal import (
    FunctionalTemporalError,
    build_epistemic_graph_fragment,
    evaluate_architecture,
    merge_into_epistemic_graph,
    rank_next_tests,
    validate_architecture,
)


REASONING = Path(__file__).resolve().parent
REFERENCE = REASONING / "reference_cases" / "v42_capture_and_rotation.functional-temporal.v1.json"
SCHEMA = REASONING.parent / "schemas" / "functional-temporal-architecture.v1.schema.json"


def load_reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def by_id(items, item_id):
    return next(item for item in items if item["id"] == item_id)


def evidence_by_id(case, evidence_id):
    return next(item for item in case["evidence_catalog"] if item["evidence_id"] == evidence_id)


class FunctionalTemporalTests(unittest.TestCase):
    def setUp(self):
        self.case = load_reference()

    def test_reference_validates_and_models_capture_and_rotation_as_a_persistent_state(self):
        indexes = validate_architecture(self.case)
        capture = indexes["states"]["CAPTURE_AND_ROTATION"]
        self.assertEqual(capture["state_type"], "PERSISTENT_STATE")
        self.assertEqual(capture["operating_phase"], "CAPTURED")
        self.assertIn("CAPTURE_AND_ROTATION", indexes["subsystems"])
        self.assertIn("INV_BOTTLE_RESTRAINT_REMAINS_VALID", indexes["invariants"])
        self.assertEqual(indexes["states"]["ENTRY"]["operating_phase"], "FREE_APPROACH")
        self.assertEqual(indexes["states"]["INDEXED"]["operating_phase"], "CAPTURE_BEGINNING")
        self.assertEqual(
            indexes["states"]["LABEL_TRANSFER_INTERVAL"]["operating_phase"],
            "LABEL_TRANSFER_INTERVAL",
        )
        self.assertEqual(indexes["states"]["WRAP_ACTIVE"]["operating_phase"], "WRAP_ROTATION_INTERVAL")
        self.assertEqual(indexes["states"]["RELEASE"]["operating_phase"], "RELEASE")
        self.assertEqual(indexes["states"]["EXIT_CLEAR"]["operating_phase"], "FREE_EXIT")

    def test_v42_reference_preserves_stale_interval_evidence_as_unresolved(self):
        report = evaluate_architecture(self.case)
        restraint = report["requirement_states"]["BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE"]
        contact = report["requirement_states"]["INV_CONTACT_REMAINS_VALID_DURING_WRAP"]

        self.assertEqual(restraint["state"], "UNRESOLVED")
        self.assertEqual(restraint["ambiguity_bucket"], "STALE_STATE")
        self.assertEqual(contact["state"], "UNRESOLVED")
        self.assertEqual(contact["ambiguity_bucket"], "STALE_STATE")
        self.assertEqual(report["machine_acceptance_state"], "MECHANICAL_ACCEPTANCE_BLOCKED")
        self.assertIs(report["mechanical_acceptance_granted"], False)
        current_inventory = evidence_by_id(
            self.case, "E_V42_COMPONENT_INVENTORY_20260925T025842Z"
        )
        current_status = evidence_by_id(self.case, "E_V42_STATUS_20260925T025241Z")
        stale_inventory = evidence_by_id(self.case, "E_V42_COMPONENT_SNAPSHOT_20260925")
        self.assertEqual(current_inventory["temporal_scope"]["validity_state"], "CURRENT")
        self.assertEqual(current_inventory["payload"]["component_count"], 55)
        self.assertEqual(current_status["payload"]["document_type"], "assembly")
        self.assertEqual(stale_inventory["temporal_scope"]["validity_state"], "STALE")

    def test_static_point_evidence_cannot_verify_throughout_capture(self):
        case = copy.deepcopy(self.case)
        requirement = by_id(case["obligations"], "BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE")
        requirement["verification_state"] = "VERIFIED"
        evidence_by_id(case, "E_V42_CAPTURE_DISTANCE_20260918")["temporal_scope"]["validity_state"] = "CURRENT"

        report = evaluate_architecture(case)
        result = report["requirement_states"]["BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE"]

        self.assertEqual(result["state"], "UNRESOLVED")
        self.assertTrue(any("POINT_ONLY" in reason for reason in result["reasons"]))

    def test_static_point_evidence_cannot_verify_reachable_motion_clearance(self):
        case = copy.deepcopy(self.case)
        requirement = by_id(case["obligations"], "REACHABLE_MOTION_CLEARANCE")
        requirement["verification_state"] = "VERIFIED"

        report = evaluate_architecture(case)
        result = report["requirement_states"]["REACHABLE_MOTION_CLEARANCE"]

        self.assertEqual(result["state"], "UNRESOLVED")
        self.assertTrue(any("POINT_ONLY" in reason for reason in result["reasons"]))

    def test_explicit_interval_evidence_can_verify_a_local_requirement_but_not_machine_acceptance(self):
        case = copy.deepcopy(self.case)
        requirement = by_id(case["obligations"], "BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE")
        requirement["verification_state"] = "VERIFIED"
        requirement["depends_on_requirement_ids"] = []
        for evidence_id in requirement["evidence_refs"]:
            record = evidence_by_id(case, evidence_id)
            record["temporal_scope"] = {
                "coverage": "THROUGHOUT_SCOPE",
                "validity_state": "CURRENT",
                "state_ids": [
                    "CAPTURE_AND_ROTATION",
                    "LABEL_TRANSFER_INTERVAL",
                    "WRAP_ACTIVE",
                ],
                "transition_ids": ["INDEXED_TO_CAPTURE", "CAPTURE_TO_RELEASE"],
            }

        report = evaluate_architecture(case)

        self.assertEqual(
            report["requirement_states"]["BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE"]["state"],
            "VERIFIED",
        )
        self.assertEqual(report["machine_acceptance_state"], "MECHANICAL_ACCEPTANCE_BLOCKED")
        self.assertIs(report["mechanical_acceptance_granted"], False)

    def test_requirement_dependency_propagates_unresolved_and_violated_states(self):
        case = copy.deepcopy(self.case)
        requirement = by_id(case["obligations"], "BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE")
        requirement["verification_state"] = "VERIFIED"
        requirement["depends_on_requirement_ids"] = ["CAPTURE_KINEMATIC_OWNER"]
        for evidence_id in requirement["evidence_refs"]:
            record = evidence_by_id(case, evidence_id)
            record["temporal_scope"] = {
                "coverage": "THROUGHOUT_SCOPE",
                "validity_state": "CURRENT",
                "state_ids": [
                    "CAPTURE_AND_ROTATION",
                    "LABEL_TRANSFER_INTERVAL",
                    "WRAP_ACTIVE",
                ],
                "transition_ids": ["INDEXED_TO_CAPTURE", "CAPTURE_TO_RELEASE"],
            }

        report = evaluate_architecture(case)
        result = report["requirement_states"]["BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE"]
        self.assertEqual(result["state"], "UNRESOLVED")
        self.assertTrue(any("CAPTURE_KINEMATIC_OWNER" in reason for reason in result["reasons"]))

        owner = by_id(case["obligations"], "CAPTURE_KINEMATIC_OWNER")
        owner["verification_state"] = "VIOLATED"
        report = evaluate_architecture(case)
        self.assertEqual(
            report["requirement_states"]["BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE"]["state"],
            "VIOLATED",
        )

    def test_interface_contract_does_not_pass_when_its_local_requirements_are_unresolved(self):
        report = evaluate_architecture(self.case)
        capture_to_label = next(
            item for item in report["interfaces"] if item["interface_id"] == "CAPTURE_TO_LABEL"
        )
        self.assertEqual(capture_to_label["state"], "EXPOSED")

    def test_next_test_rank_uses_declared_value_formula(self):
        report = evaluate_architecture(self.case)
        candidates = report["next_test_candidates"]
        self.assertEqual(candidates[0]["test_id"], "TEST_CAPTURE_KINEMATIC_OWNER")
        top = candidates[0]
        expected = (
            top["dependency_centrality"]
            * top["discrimination_power"]
            * top["evidence_confidence"]
            * top["unresolved_relevance"]
            / top["cost"]
        )
        self.assertAlmostEqual(top["value"], expected, places=6)
        self.assertTrue(top["does_not_promote_facts"])

    def test_next_test_cad_request_is_limited_to_existing_read_only_partition(self):
        case = copy.deepcopy(self.case)
        test = by_id(case["next_tests"], "TEST_FRESH_V42_COMPONENT_BINDING")
        test["cad_request"]["command_id"] = "sw.set_transform"
        test["cad_request"]["write_authority"] = "WRITE"

        with self.assertRaises(FunctionalTemporalError):
            validate_architecture(case)

    def test_capture_owner_hypotheses_preserve_exact_resolution_evidence(self):
        indexes = validate_architecture(self.case)
        expected = {
            "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE": ("COMMON", "UNRESOLVED", "ACTIVE"),
            "H_PIVOTING_ROLLER_ARM_OR_CARRIER": ("COMMON", "UNRESOLVED", "ACTIVE"),
            "H_MOVING_WRAP_BELT_ASSEMBLY": ("COMMON", "UNRESOLVED", "ACTIVE"),
            "H_PNEUMATIC_CAPTURE_ACTUATOR": ("UNCOMMON", "WEAKENED", "ELIGIBLE"),
            "H_SPRING_OR_COMPLIANT_PRELOAD_MECHANISM": ("COMMON", "UNRESOLVED", "ACTIVE"),
            "H_OTHER_EXPLICIT_CLOSURE_MECHANISM": ("UNCOMMON", "UNRESOLVED", "ACTIVE"),
        }
        for hypothesis_id, expected_state in expected.items():
            hypothesis = indexes["hypotheses"][hypothesis_id]
            self.assertEqual(
                (
                    hypothesis["prior"],
                    hypothesis["evidence_state"],
                    hypothesis["investigation_state"],
                ),
                expected_state,
            )
            self.assertTrue(hypothesis["required_evidence"])
            self.assertIn("CAPTURE_AND_ROTATION", hypothesis["affected_state_ids"])

        top_test = by_id(self.case["next_tests"], "TEST_CAPTURE_KINEMATIC_OWNER")
        self.assertNotIn("cad_request", top_test)
        self.assertIn("H_MOVING_WRAP_BELT_ASSEMBLY", top_test["hypothesis_ids"])

    def test_hypothesis_evidence_and_operating_phase_are_validated(self):
        case = copy.deepcopy(self.case)
        by_id(case["hypotheses"], "H_MOVING_WRAP_BELT_ASSEMBLY").pop("required_evidence")
        with self.assertRaises(FunctionalTemporalError):
            validate_architecture(case)

        case = copy.deepcopy(self.case)
        by_id(case["states"], "CAPTURE_AND_ROTATION")["operating_phase"] = "UNMODELED"
        with self.assertRaises(FunctionalTemporalError):
            validate_architecture(case)

    def test_duration_and_interface_contract_misconfigurations_are_rejected(self):
        case = copy.deepcopy(self.case)
        case["duration_constraints"][0]["minimum_duration"] = 20
        case["duration_constraints"][0]["maximum_duration"] = 10
        with self.assertRaises(FunctionalTemporalError):
            validate_architecture(case)

        case = copy.deepcopy(self.case)
        case["interfaces"][0]["consumer_subsystem_id"] = case["interfaces"][0]["provider_subsystem_id"]
        with self.assertRaises(FunctionalTemporalError):
            validate_architecture(case)

    def test_requirement_dependency_cycles_are_rejected(self):
        case = copy.deepcopy(self.case)
        product = by_id(case["obligations"], "PRODUCT_POSITION_STABLE")
        product["depends_on_requirement_ids"] = ["GUARD_ONE_BOTTLE_INDEXED"]
        with self.assertRaises(FunctionalTemporalError):
            validate_architecture(case)

    def test_ai_visualization_cannot_satisfy_engineering_requirement(self):
        case = copy.deepcopy(self.case)
        requirement = by_id(case["obligations"], "PRODUCT_POSITION_STABLE")
        requirement["verification_state"] = "VERIFIED"
        record = evidence_by_id(case, "E_V42_COMPONENT_INVENTORY_20260925T025842Z")
        record["evidence_type"] = "ai_visualization_record"
        record["evidence_state"] = "AI_GENERATED"
        record["source_authority"] = "GENERATIVE_AI"

        report = evaluate_architecture(case)
        result = report["requirement_states"]["PRODUCT_POSITION_STABLE"]
        self.assertEqual(result["state"], "UNRESOLVED")
        self.assertTrue(any("AI-generated" in reason for reason in result["reasons"]))

    def test_graph_fragment_integrates_without_changing_existing_acceptance_gate(self):
        fragment = build_epistemic_graph_fragment(self.case)
        self.assertIs(fragment["mechanical_acceptance_granted"], False)
        self.assertEqual(fragment["machine_acceptance_state"], "MECHANICAL_ACCEPTANCE_BLOCKED")
        self.assertTrue(
            any(node["id"].endswith("REQUIREMENT::BOTTLE_RESTRAINT_THROUGHOUT_CAPTURE") for node in fragment["nodes"])
        )

        base_graph = {
            "project": {"id": "base", "acceptance_obligation": "EXISTING_GATE"},
            "nodes": [
                {
                    "id": "EXISTING_GATE",
                    "kind": "obligation",
                    "description": "An independently governed existing gate.",
                    "value": True,
                    "state": "ASSERTED",
                    "authority": "PROJECT_ACCEPTANCE_RULE",
                    "acceptance_gate": True,
                }
            ],
            "relations": [],
        }
        merged = merge_into_epistemic_graph(base_graph, self.case)
        self.assertEqual(merged["project"]["acceptance_obligation"], "EXISTING_GATE")
        self.assertEqual(
            merged["project"]["functional_temporal_architectures"][0]["machine_acceptance_state"],
            "MECHANICAL_ACCEPTANCE_BLOCKED",
        )
        self.assertGreater(len(merged["nodes"]), len(base_graph["nodes"]))

    def test_schema_exposes_explicit_temporal_coverage_and_no_acceptance_constant(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["$defs"]["machineGoal"]["properties"]["mechanical_acceptance_granted"]["const"],
            False,
        )
        self.assertEqual(
            schema["$defs"]["readOnlyCadRequest"]["properties"]["write_authority"]["const"],
            "NONE",
        )
        self.assertIn(
            "REACHABLE_STATE_SET",
            schema["$defs"]["scope"]["properties"]["required_coverage"]["enum"],
        )
        self.assertIn(
            "CAPTURED",
            schema["$defs"]["state"]["properties"]["operating_phase"]["enum"],
        )
        self.assertIn(
            "required_evidence",
            schema["$defs"]["hypothesis"]["required"],
        )


if __name__ == "__main__":
    unittest.main()
