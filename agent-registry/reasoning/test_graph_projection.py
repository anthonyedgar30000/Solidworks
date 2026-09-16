import unittest

from graph_projection import GraphProjectionError, build_runtime_graph
from reasoner import explain


def observed(name2, translation=None, mn=None, mx=None):
    return {
        "state": "KNOWN",
        "authority": "SOLIDWORKS_LIVE_STATE",
        "component_name2": name2,
        "translation_mm": translation or [0.0, 0.0, 0.0],
        "rotation9": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "transform_array": [1.0] * 16,
        "transform_source": "Component2.Transform2",
        "box_min_mm": mn or [0.0, 0.0, 0.0],
        "box_max_mm": mx or [10.0, 10.0, 10.0],
        "geometry_note": "approx",
        "source_classification": "solidworks_api",
    }


def fixture():
    roles = {
        "AR60_ROLLER": observed("AR60-1", [500, 500, 1500], [430, 470, 1370], [520, 500, 1400]),
        "AR60_CARRIAGE": observed("CARRIAGE-1", [500, 500, 1500], [514, 473, 1376], [548, 519, 1481]),
        "CONVEYOR": observed("CONVEYOR-1", [-154, -224, 950], [-219, -674, 0], [-89, 226, 990]),
        "BOTTLE_1": observed("B1", [-154, -404, 950], [-178, -428, 950], [-130, -380, 1130]),
        "BOTTLE_2": observed("B2", [-154, -314, 950], [-178, -338, 950], [-130, -290, 1130]),
        "BOTTLE_3": observed("B3", [-154, -224, 950], [-178, -248, 950], [-130, -200, 1130]),
        "BOTTLE_4": observed("B4", [-154, -134, 950], [-178, -158, 950], [-130, -110, 1130]),
        "BOTTLE_5": observed("B5", [-154, -44, 950], [-178, -68, 950], [-130, -20, 1130]),
    }
    return {
        "transaction_type": "deterministic_geometry_projection",
        "schema_version": 1,
        "document": {"title": "IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE"},
        "source_evidence": {
            "raw_sha256": "abc123",
            "job_id": "job-1",
            "recorded_at": "2026-09-16T00:48:11+00:00",
        },
        "mechanical_acceptance_granted": False,
        "authority": {"classification": "MEASURED_CALCULATED"},
        "observed_facts": roles,
        "calculated_facts": {
            "AR60_NEAREST_BOTTLE_AABB_SEPARATION": {
                "state": "KNOWN",
                "authority": "MEASURED_CALCULATED",
                "nearest_bottle_unique": True,
                "nearest_bottle_role": "BOTTLE_5",
                "nearest_bottle_roles": ["BOTTLE_5"],
                "minimum_aabb_separation_mm": 787.268,
                "axis_gap_mm": {"x": 562.788, "y": 494.382, "z": 242.170},
                "candidate_axis_gaps_mm": {"BOTTLE_5": {"x": 562.788, "y": 494.382, "z": 242.170}},
            },
            "AR60_AABB_DISJOINT_FROM_ALL_BOTTLES": {
                "state": "KNOWN",
                "authority": "MEASURED_CALCULATED",
                "value": True,
            },
            "AR60_CARRIAGE_AABB_RELATION": {
                "state": "KNOWN",
                "authority": "MEASURED_CALCULATED",
                "axis_gap_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
                "minimum_aabb_separation_mm": 0.0,
                "aabb_intersects_or_touches": True,
                "positive_volume_aabb_overlap": True,
                "overlap_extent_mm": {"x": 6.0, "y": 27.0, "z": 24.0},
                "engineering_limit": "AABB overlap is not proof of body interference or mechanical fit.",
            },
            "AR60_CONVEYOR_AABB_RELATION": {
                "state": "KNOWN",
                "authority": "MEASURED_CALCULATED",
                "axis_gap_mm": {"x": 519.0, "y": 244.0, "z": 380.0},
                "minimum_aabb_separation_mm": 687.0,
                "aabb_intersects_or_touches": False,
                "positive_volume_aabb_overlap": False,
                "overlap_extent_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
                "engineering_limit": "AABB separation/overlap is not a precise clearance or interference result.",
            },
        },
    }


class GraphProjectionTests(unittest.TestCase):
    def test_runtime_graph_uses_live_evidence_not_toy_geometry(self):
        graph = build_runtime_graph(fixture())
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertNotIn("BOTTLE_CENTERLINE", nodes)
        self.assertNotIn("AR60_RADIUS", nodes)
        self.assertEqual(nodes["AR60_NEAREST_BOTTLE_AABB_SEPARATION"]["value"], 787.268)
        self.assertFalse(graph["projection_policy"]["toy_placeholder_values_copied"])

    def test_unverified_travel_remains_null(self):
        graph = build_runtime_graph(fixture())
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["AR60_MAX_TRAVEL"]["state"], "NULL")
        self.assertIsNone(nodes["AR60_MAX_TRAVEL"]["value"])

    def test_acceptance_remains_exposed(self):
        graph = build_runtime_graph(fixture())
        report = explain(graph)
        self.assertEqual(report["health"]["overall_state"], "EXPOSED")
        self.assertEqual(report["effective_states"]["V21_ACCEPTANCE"], "EXPOSED")
        self.assertEqual(report["health"]["known_violations"], [])

    def test_intended_application_transform_is_highest_value_next_investigation(self):
        graph = build_runtime_graph(fixture())
        report = explain(graph)
        self.assertGreater(len(report["next_investigation_candidates"]), 0)
        self.assertEqual(
            report["next_investigation_candidates"][0]["node_id"],
            "INTENDED_APPLICATION_STATION_TRANSFORM",
        )

    def test_projection_never_grants_acceptance(self):
        graph = build_runtime_graph(fixture())
        self.assertIs(graph["project"]["mechanical_acceptance_granted"], False)

    def test_wrong_document_is_rejected(self):
        tx = fixture()
        tx["document"]["title"] = "wrong"
        with self.assertRaises(GraphProjectionError):
            build_runtime_graph(tx)

    def test_missing_source_hash_is_rejected(self):
        tx = fixture()
        tx["source_evidence"]["raw_sha256"] = None
        with self.assertRaises(GraphProjectionError):
            build_runtime_graph(tx)


if __name__ == "__main__":
    unittest.main()
