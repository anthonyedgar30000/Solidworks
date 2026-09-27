#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

from functional_temporal import evaluate_architecture, validate_architecture

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference_cases" / "v43_prism_capture_and_rotation.functional-temporal.v1.json"
GUIDE_VERIFIER = HERE.parent / "workers" / "CadGrounded.SolidWorksWorker" / "Verify-ClassifyContact-V43-Prism-GuideRails.ps1"
SLIDER_LINK_VERIFIER = HERE.parent / "workers" / "CadGrounded.SolidWorksWorker" / "Verify-ClassifyContact-V43-Prism-SliderLinks.ps1"
LINK_ARM_VERIFIER = HERE.parent / "workers" / "CadGrounded.SolidWorksWorker" / "Verify-ClassifyContact-V43-Prism-LinkArms.ps1"
ARM_ROLLER_VERIFIER = HERE.parent / "workers" / "CadGrounded.SolidWorksWorker" / "Verify-ClassifyContact-V43-Prism-ArmRollers.ps1"
FULL_CHAIN_MATES_VERIFIER = HERE.parent / "workers" / "CadGrounded.SolidWorksWorker" / "Verify-QueryMates-V43-Prism-FullChain.ps1"

def load_case():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))

def by_id(items, item_id, field="id"):
    return next(item for item in items if item[field] == item_id)

class V43PrismRegistrationTests(unittest.TestCase):
    def test_reference_registers_admitted_topology_evidence_without_acceptance(self):
        case = load_case()
        indexes = validate_architecture(case)
        evidence_ids = set(indexes["evidence"])
        self.assertIn("E.V43.PRISM.MATE_BINDING.ARCH_PROJECTION.20260926", evidence_ids)
        self.assertIn("E.V43.PRISM.LINK1_REACTION_BASE.ARCH_PROJECTION.20260926", evidence_ids)
        self.assertIn("E.V43.PRISM.GUIDE_CONTACT.ARCH_PROJECTION.20260927", evidence_ids)
        self.assertIn("E.V43.PRISM.SLIDER_LINK_CONTACT.ARCH_PROJECTION.20260927", evidence_ids)
        self.assertIn("E.V43.PRISM.LINK_ARM_CONTACT.ARCH_PROJECTION.20260927", evidence_ids)
        self.assertIn("E.V43.PRISM.ARM_ROLLER_CONTACT.ARCH_PROJECTION.20260927", evidence_ids)
        self.assertIn("E.V43.PRISM.FULL_CHAIN_MATE_BINDING.ARCH_PROJECTION.20260927", evidence_ids)
        report = evaluate_architecture(case)
        self.assertEqual(report["machine_acceptance_state"], "MECHANICAL_ACCEPTANCE_BLOCKED")
        self.assertFalse(report["mechanical_acceptance_granted"])

    def test_v43_hypothesis_states_reflect_bounded_guide_contact_support(self):
        case = load_case()
        expected = {
            "H_V43_PRISM_GUIDED_SLIDER": "SUPPORTED",
            "H_V43_PRISM_LINKS_AND_ARMS_TRANSFER_CLOSURE": "WEAKENED",
            "H_V43_PRISM_REACTION_BASE_CARRIES_LOAD": "WEAKENED",
            "H_V43_PRISM_ACTUATOR_DRIVES_CLOSURE": "UNRESOLVED",
        }
        for hypothesis_id, state in expected.items():
            self.assertEqual(by_id(case["hypotheses"], hypothesis_id)["evidence_state"], state)

    def test_completed_full_chain_mate_test_is_replaced_by_kinematic_source_provenance_test(self):
        case = load_case()
        ids = {item["id"] for item in case["next_tests"]}
        self.assertNotIn("TEST_V43_PRISM_FULL_CHAIN_MATE_BINDING", ids)
        test = by_id(case["next_tests"], "TEST_V43_PRISM_KINEMATIC_SOURCE_PROVENANCE")
        for token in (
            "FITCHECK_PRISM",
            "zero-mate full-chain result",
            "slider axis",
            "pivot relationships",
            "actuator attachment",
            "stroke",
            "KINEMATIC_STATE_UNRESOLVED",
            "OEM_SOURCE_REQUIRED",
        ):
            self.assertIn(token, test["question"])
        self.assertEqual(
            test["hypothesis_ids"],
            [
                "H_V43_PRISM_LINKS_AND_ARMS_TRANSFER_CLOSURE",
                "H_V43_PRISM_ACTUATOR_DRIVES_CLOSURE",
                "H_V43_PRISM_GUIDED_SLIDER",
            ],
        )

    def test_guide_verifier_preserves_bounded_read_only_contract(self):
        source = GUIDE_VERIFIER.read_text(encoding="utf-8")
        for token in (
            "sw.classify_contact_pair",
            "FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1",
            "FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-1",
            "FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-2",
            "write_authority -cne 'NONE'",
            "model_mutation -ne $false",
            "Get-TargetState",
            "Get-FileEvidence",
            "V43_WRAP",
        ):
            self.assertIn(token, source)
        for forbidden in ("sw.set_transform", "sw.insert_component", "AddMate", "CreateMate", "EditRebuild", "ForceRebuild", "SaveAs"):
            self.assertNotIn(forbidden, source)

    def test_slider_link_verifier_preserves_bounded_read_only_contract(self):
        source = SLIDER_LINK_VERIFIER.read_text(encoding="utf-8")
        for token in (
            "sw.classify_contact_pair",
            "FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1",
            "FITCHECK_PRISM_LINK_15x10x25_V43-1",
            "FITCHECK_PRISM_LINK_15x10x25_V43-2",
            "write_authority -cne 'NONE'",
            "model_mutation -ne $false",
            "Get-TargetState",
            "Get-FileEvidence",
            "V43_WRAP",
        ):
            self.assertIn(token, source)
        for forbidden in ("sw.set_transform", "sw.insert_component", "AddMate", "CreateMate", "EditRebuild", "ForceRebuild", "SaveAs"):
            self.assertNotIn(forbidden, source)

    def test_link_arm_verifier_preserves_bounded_read_only_contract(self):
        source = LINK_ARM_VERIFIER.read_text(encoding="utf-8")
        for token in (
            "sw.classify_contact_pair",
            "FITCHECK_PRISM_LINK_15x10x25_V43-1",
            "FITCHECK_PRISM_LINK_15x10x25_V43-2",
            "FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1",
            "FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1",
            "write_authority -cne 'NONE'",
            "model_mutation -ne $false",
            "Get-TargetState",
            "Get-FileEvidence",
            "V43_WRAP",
        ):
            self.assertIn(token, source)
        for forbidden in ("sw.set_transform", "sw.insert_component", "AddMate", "CreateMate", "EditRebuild", "ForceRebuild", "SaveAs"):
            self.assertNotIn(forbidden, source)

    def test_arm_roller_verifier_preserves_bounded_read_only_contract(self):
        source = ARM_ROLLER_VERIFIER.read_text(encoding="utf-8")
        for token in (
            "sw.classify_contact_pair",
            "FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1",
            "FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1",
            "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1",
            "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2",
            "write_authority -cne 'NONE'",
            "model_mutation -ne $false",
            "Get-TargetState",
            "Get-FileEvidence",
            "V43_WRAP",
        ):
            self.assertIn(token, source)
        for forbidden in ("sw.set_transform", "sw.insert_component", "AddMate", "CreateMate", "EditRebuild", "ForceRebuild", "SaveAs"):
            self.assertNotIn(forbidden, source)

    def test_full_chain_mates_verifier_preserves_bounded_read_only_contract(self):
        source = FULL_CHAIN_MATES_VERIFIER.read_text(encoding="utf-8")
        for token in (
            "sw.query_mates",
            "FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1",
            "FITCHECK_PRISM_LINK_15x10x25_V43-1",
            "FITCHECK_PRISM_LINK_15x10x25_V43-2",
            "FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1",
            "FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1",
            "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1",
            "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2",
            "write_authority -cne 'NONE'",
            "model_mutation -ne $false",
            "Get-TargetState",
            "Get-FileEvidence",
            "V43_WRAP",
        ):
            self.assertIn(token, source)
        for forbidden in ("sw.set_transform", "sw.insert_component", "AddMate", "CreateMate", "EditRebuild", "ForceRebuild", "SaveAs"):
            self.assertNotIn(forbidden, source)

if __name__ == "__main__":
    unittest.main()
