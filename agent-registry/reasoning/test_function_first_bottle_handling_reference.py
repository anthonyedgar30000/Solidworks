#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

from functional_temporal import evaluate_architecture, validate_architecture

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference_cases" / "ixor_bottle_handling_function_first_search.functional-temporal.v1.json"

def load_case():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))

def by_id(items, item_id, field="id"):
    return next(item for item in items if item[field] == item_id)

class FunctionFirstBottleHandlingTests(unittest.TestCase):
    def test_reference_is_structurally_valid_and_acceptance_blocked(self):
        case = load_case()
        validate_architecture(case)
        report = evaluate_architecture(case)
        self.assertEqual(case["architecture_id"], "IXOR_BOTTLE_HANDLING_FUNCTION_FIRST_SEARCH")
        self.assertEqual(report["machine_acceptance_state"], "MECHANICAL_ACCEPTANCE_BLOCKED")
        self.assertFalse(report["mechanical_acceptance_granted"])

    def test_v43_is_only_one_candidate_and_not_architecture_authority(self):
        case = load_case()
        hypotheses = {item["id"]: item for item in case["hypotheses"]}
        self.assertGreaterEqual(len(hypotheses), 4)
        self.assertEqual(hypotheses["H_ARCH_V43_PRISM_CHAIN"]["evidence_state"], "WEAKENED")
        self.assertEqual(hypotheses["H_ARCH_DRIVEN_WRAP_BELT_PASSIVE_SUPPORTS"]["evidence_state"], "UNTESTED")
        self.assertEqual(hypotheses["H_ARCH_TRANSLATING_PRESSURE_WALL"]["evidence_state"], "UNTESTED")
        self.assertEqual(hypotheses["H_ARCH_INDEXED_CRADLE_OR_CLAMP"]["evidence_state"], "UNTESTED")
        self.assertIn("not architecture authority", hypotheses["H_ARCH_V43_PRISM_CHAIN"]["description"])

    def test_zero_mate_projection_does_not_promote_alternative(self):
        case = load_case()
        evidence = by_id(case["evidence_catalog"], "E.V43.PRISM.FULL_CHAIN_MATES.ARCH_SEARCH_PROJECTION.20260927", "evidence_id")
        text = evidence["payload"]["result"]["planning_use"]
        self.assertIn("does not prove V43 mechanically invalid", text)
        self.assertIn("does not favor any alternative", text)
        self.assertFalse(evidence["mechanical_acceptance_granted"])

    def test_family_comparison_is_highest_value_next_test(self):
        case = load_case()
        report = evaluate_architecture(case)
        self.assertEqual(report["next_test_candidates"][0]["test_id"], "TEST_COMPARE_BOTTLE_HANDLING_FAMILIES")
        test = by_id(case["next_tests"], "TEST_COMPARE_BOTTLE_HANDLING_FAMILIES")
        self.assertNotIn("cad_request", test)
        self.assertNotIn("native_read_candidates", test)
        for token in (
            "V43 Prism chain",
            "driven wrap belt with passive supports",
            "translating pressure-wall/side-belt closure",
            "indexed cradle/clamp",
            "preserving unknowns",
        ):
            self.assertIn(token, test["question"])

if __name__ == "__main__":
    unittest.main()
