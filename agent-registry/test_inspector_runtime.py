import importlib.util
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("inspector_runtime", HERE / "inspector_runtime.py")
inspector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspector)


def envelope(write_authority="NONE"):
    return {
        "ok": True,
        "source_classification": "verified_from_solidworks_api",
        "write_authority": write_authority,
        "data": {
            "source_classification": "verified_from_solidworks_api",
            "write_authority": write_authority,
            "document": {"title": "ASSEMBLY", "path": "C:\\fixture.SLDASM"},
            "components": [
                {"name2": "WRAP_BELT-1", "fixed_component": False, "translation_mm": [1, 2, 3], "rotation9": [1] * 9},
                {"name2": "BOTTLE-2", "fixed_component": True, "translation_mm": [4, 5, 6], "rotation9": [1] * 9},
            ],
        },
    }


class InspectorRuntimeTests(unittest.TestCase):
    def make_db(self):
        temporary = tempfile.TemporaryDirectory()
        db = Path(temporary.name) / "inspector.db"
        inspector.init_db(db)
        with inspector.connect(db) as connection:
            connection.execute(
                "INSERT INTO worlds(id,title,source_path,created_at) VALUES(?,?,?,?)",
                ("v42", "ASSEMBLY", "C:\\fixture.SLDASM", inspector.utc_now()),
            )
        return temporary, db

    def test_snapshot_reuses_identical_state_and_detects_component_delta(self):
        temporary, db = self.make_db()
        try:
            first = inspector.record_snapshot(db, "v42", envelope())
            self.assertFalse(first["reused"])
            self.assertEqual(first["changed_components"], ["BOTTLE-2", "WRAP_BELT-1"])

            repeated = inspector.record_snapshot(db, "v42", envelope())
            self.assertTrue(repeated["reused"])

            changed = envelope()
            changed["data"]["components"][0]["translation_mm"] = [1.5, 2, 3]
            current = inspector.record_snapshot(db, "v42", changed)
            self.assertEqual(current["changed_components"], ["WRAP_BELT-1"])
        finally:
            temporary.cleanup()

    def test_rejects_non_read_only_snapshot(self):
        with self.assertRaises(inspector.InspectorError):
            inspector.normalize_snapshot(envelope("WRITE_AUTHORIZED"))

    def test_ranking_uses_declared_deterministic_value_function(self):
        ranked = inspector.rank_next_tests([
            {"id": "cheap-high-value", "dependency_centrality": 4, "discrimination_power": 3, "evidence_confidence": 1, "unresolved_relevance": 2, "cost": 2},
            {"id": "expensive-low-value", "dependency_centrality": 2, "discrimination_power": 1, "evidence_confidence": 1, "unresolved_relevance": 1, "cost": 4},
        ])
        self.assertEqual(ranked[0]["id"], "cheap-high-value")
        self.assertEqual(ranked[0]["value_score"], 12)


if __name__ == "__main__":
    unittest.main()
