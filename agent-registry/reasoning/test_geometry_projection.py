import unittest

from geometry_projection import GeometryProjectionError, build_projection


def role(name2, mn, mx):
    return {
        "identity_status": "VERIFIED_FROM_SOLIDWORKS",
        "component_name2": name2,
        "translation_mm": [0.0, 0.0, 0.0],
        "rotation9": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "transform_array": [1.0] * 16,
        "transform_source": "Component2.Transform2",
        "box_min_mm": list(mn),
        "box_max_mm": list(mx),
        "geometry_note": "approx",
        "source_classification": "solidworks_api",
    }


def fixture():
    roles = {
        "AR60_ROLLER": role("AR60-1", [100, 100, 100], [120, 120, 120]),
        "AR60_CARRIAGE": role("CARRIAGE-1", [115, 110, 105], [140, 150, 130]),
        "CONVEYOR": role("CONVEYOR-1", [-50, -50, 0], [50, 50, 80]),
        "BOTTLE_1": role("B1", [0, 0, 0], [20, 20, 50]),
        "BOTTLE_2": role("B2", [0, 30, 0], [20, 50, 50]),
        "BOTTLE_3": role("B3", [0, 60, 0], [20, 80, 50]),
        "BOTTLE_4": role("B4", [0, 90, 0], [20, 110, 50]),
        "BOTTLE_5": role("B5", [0, 120, 0], [20, 140, 50]),
    }
    return {
        "transaction_type": "semantic_identity_binding",
        "schema_version": 1,
        "document": {"title": "fixture"},
        "source_evidence": {"raw_sha256": "abc"},
        "mechanical_acceptance_granted": False,
        "resolved_roles": roles,
    }


class GeometryProjectionTests(unittest.TestCase):
    def test_projection_never_grants_mechanical_acceptance(self):
        result = build_projection(fixture())
        self.assertIs(result["mechanical_acceptance_granted"], False)
        self.assertIn("AR60_CONTACT_POSITION", result["unresolved_mechanical_claims"])
        self.assertNotIn("contact_valid", result["calculated_facts"])

    def test_nearest_bottle_is_selected_by_aabb_distance(self):
        result = build_projection(fixture())
        nearest = result["calculated_facts"]["AR60_NEAREST_BOTTLE_AABB_SEPARATION"]
        self.assertEqual(nearest["nearest_bottle_role"], "BOTTLE_5")
        self.assertGreater(nearest["minimum_aabb_separation_mm"], 0.0)

    def test_all_bottle_aabbs_are_reported_disjoint(self):
        result = build_projection(fixture())
        fact = result["calculated_facts"]["AR60_AABB_DISJOINT_FROM_ALL_BOTTLES"]
        self.assertIs(fact["value"], True)

    def test_carriage_aabb_overlap_is_not_promoted_to_interference(self):
        result = build_projection(fixture())
        relation = result["calculated_facts"]["AR60_CARRIAGE_AABB_RELATION"]
        self.assertIs(relation["positive_volume_aabb_overlap"], True)
        self.assertIn("not proof", relation["engineering_limit"])

    def test_invalid_aabb_is_rejected(self):
        tx = fixture()
        tx["resolved_roles"]["AR60_ROLLER"]["box_min_mm"] = [200, 100, 100]
        with self.assertRaises(GeometryProjectionError):
            build_projection(tx)

    def test_missing_required_role_is_rejected(self):
        tx = fixture()
        del tx["resolved_roles"]["BOTTLE_5"]
        with self.assertRaises(GeometryProjectionError):
            build_projection(tx)


if __name__ == "__main__":
    unittest.main()
