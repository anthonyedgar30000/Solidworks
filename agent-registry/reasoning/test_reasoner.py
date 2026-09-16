#!/usr/bin/env python3
import copy
import unittest

from reasoner import load_graph, explain


class ReasonerTests(unittest.TestCase):
    def setUp(self):
        self.graph = load_graph("graph.json")

    def get_node(self, graph, node_id):
        return next(n for n in graph["nodes"] if n["id"] == node_id)

    def test_null_exposes_acceptance(self):
        report = explain(self.graph)
        self.assertEqual(report["health"]["overall_state"], "EXPOSED")
        top = report["risk_footprints"][0]
        self.assertEqual(top["node_id"], "AR60_CONTACT_POSITION")
        self.assertIn("V21_ACCEPTANCE", top["affected_obligations"])

    def test_cosmetic_null_does_not_expose_acceptance(self):
        report = explain(self.graph)
        paint = next(x for x in report["risk_footprints"] if x["node_id"] == "PAINT_COLOUR")
        self.assertNotIn("V21_ACCEPTANCE", paint["affected_obligations"])
        self.assertEqual(paint["risk_exposure"], 0.0)

    def test_resolving_contact_alone_still_leaves_derived_reachability_unresolved(self):
        g = copy.deepcopy(self.graph)
        n = self.get_node(g, "AR60_CONTACT_POSITION")
        n["value"] = 270.0
        n["state"] = "KNOWN"
        n["authority"] = "SOLIDWORKS_MEASUREMENT"

        report = explain(g)
        self.assertEqual(report["health"]["overall_state"], "EXPOSED")
        blockers = {b["node_id"] for b in report["health"]["acceptance_blockers"]}
        self.assertIn("CONTACT_REACHABLE_WITHIN_TRAVEL", blockers)

    def test_explicit_violation_fails_acceptance(self):
        g = copy.deepcopy(self.graph)
        n = self.get_node(g, "AR60_CONTACT_POSITION")
        n["value"] = 270.0
        n["state"] = "KNOWN"
        n["authority"] = "SOLIDWORKS_MEASUREMENT"

        reachable = self.get_node(g, "CONTACT_REACHABLE_WITHIN_TRAVEL")
        reachable["value"] = False
        reachable["state"] = "VIOLATED"
        reachable["authority"] = "DETERMINISTIC_DERIVATION"

        report = explain(g)
        self.assertEqual(report["health"]["overall_state"], "FAILED")
        self.assertIn("CONTACT_REACHABLE_WITHIN_TRAVEL", report["health"]["known_violations"])


if __name__ == "__main__":
    unittest.main()
