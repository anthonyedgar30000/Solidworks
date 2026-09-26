import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE / "incremental_evidence.py"
SPEC = importlib.util.spec_from_file_location("incremental_evidence", MODULE)
runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime)


def observation(raw_sha: str, *, belt_x: float = 10.0) -> dict:
    return {
        "transaction_type": "cad_observation_evidence",
        "schema_version": 1,
        "admission_status": "ADMITTED_OBSERVATION",
        "mechanical_acceptance_granted": False,
        "source_authority": "SOLIDWORKS_LIVE_STATE",
        "source_classification": "verified_from_solidworks_api",
        "raw_observation": {
            "source_file": "fixture.json",
            "sha256": raw_sha,
            "job_id": "fixture",
            "command": "sw.query_components",
            "state": "completed",
            "worker": "fixture",
            "recorded_at": "2026-09-26T22:00:00Z",
        },
        "document": {
            "title": "IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE",
            "path": r"C:\fixture\IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE.SLDASM",
            "active_configuration": "Default",
            "bridge_version": "fixture",
            "adapter": "fixture",
            "top_level_only": False,
        },
        "component_count": 3,
        "components": [
            {
                "name2": "FITCHECK_DRIVEN_WRAP_BELT-1",
                "path": r"C:\fixture\wrapbelt.SLDPRT",
                "parent_name": None,
                "is_top_level": True,
                "referenced_configuration": "Default",
                "fixed": False,
                "suppressed": False,
                "suppression_state": "resolved",
                "translation_mm": [belt_x, 20.0, 30.0],
                "translation_m": [belt_x / 1000.0, 0.02, 0.03],
                "rotation9": [1,0,0,0,1,0,0,0,1],
                "scale": 1.0,
                "transform_array": [1,0,0,0,1,0,0,0,1,belt_x/1000.0,0.02,0.03,1.0],
                "transform_source": "Component2.Transform2",
                "getbox_mm": [0,0,0,1,1,1],
                "getbox_m": [0,0,0,0.001,0.001,0.001],
                "box_min_mm": [0,0,0],
                "box_max_mm": [1,1,1],
                "bounding_box_mm_approx": True,
                "field_errors": [],
            },
            {
                "name2": "Connector1",
                "path": r"C:\fixture\ixor.SLDASM",
                "parent_name": "Published References",
                "is_top_level": False,
                "referenced_configuration": "Default",
                "fixed": True,
                "suppressed": False,
                "suppression_state": "resolved",
                "translation_mm": [0,0,0],
                "rotation9": [1,0,0,0,1,0,0,0,1],
                "scale": 1.0,
                "transform_array": [1,0,0,0,1,0,0,0,1,0,0,0,1],
                "transform_source": "Component2.Transform2",
                "field_errors": [],
            },
            {
                "name2": "Connector2",
                "path": r"C:\fixture\ixor.SLDASM",
                "parent_name": "Published References",
                "is_top_level": False,
                "referenced_configuration": "Default",
                "fixed": True,
                "suppressed": False,
                "suppression_state": "resolved",
                "translation_mm": [900,0,0],
                "rotation9": [1,0,0,0,1,0,0,0,1],
                "scale": 1.0,
                "transform_array": [1,0,0,0,1,0,0,0,1,0.9,0,0,1],
                "transform_source": "Component2.Transform2",
                "field_errors": [],
            },
        ],
        "prohibited_promotions": [
            "mechanical_acceptance",
            "valid_contact",
            "valid_clearance",
            "operating_sequence",
            "functional_suitability",
        ],
    }


def evidence(evidence_id: str, dependencies: list[str]) -> dict:
    return {
        "schema_version": 1,
        "record_type": "evidence",
        "evidence_id": evidence_id,
        "evidence_type": "solidworks_observation",
        "evidence_state": "VERIFIED",
        "source_authority": "SOLIDWORKS_LIVE_STATE",
        "source_classification": "verified_from_solidworks_api",
        "subject": {
            "subject_type": "fixture",
            "identity_exact": evidence_id,
            "document_title_exact": "IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE",
            "document_path_exact": r"C:\fixture\IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE.SLDASM",
        },
        "provenance": {
            "recorded_at": "2026-09-26T22:00:00Z",
            "source_ref": "fixture",
            "sha256": "c" * 64,
        },
        "dependencies": dependencies,
        "geometry_state": "FIT_CHECK",
        "temporal_scope": {
            "coverage": "POINT_ONLY",
            "validity_state": "CURRENT",
            "state_ids": [],
            "transition_ids": [],
        },
        "mechanical_acceptance_granted": False,
        "payload": {
            "observation_kind": "fixture",
            "document": {
                "title": "IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE",
                "path": r"C:\fixture\IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE.SLDASM",
            },
        },
    }


class IncrementalEvidenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "reasoning.db"
        runtime.SCHEMA = HERE.parent / "reasoning-db" / "schema.sql"
        runtime.init_db(self.db)
        with runtime.db_conn(self.db) as connection:
            connection.execute(
                "INSERT INTO worlds(id,title,source_path,created_at) VALUES(?,?,?,?)",
                (
                    "ixor-v42",
                    "IXOR v42",
                    r"C:\fixture\IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE.SLDASM",
                    "2026-09-26T22:00:00Z",
                ),
            )

    def tearDown(self):
        self.temp.cleanup()

    def test_repeated_identical_state_keeps_state_fingerprint_but_distinct_run_identity(self):
        first = runtime.record_inspection_run(self.db, "ixor-v42", observation("a" * 64))
        second = runtime.record_inspection_run(self.db, "ixor-v42", observation("b" * 64))
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["state_fingerprint"], second["state_fingerprint"])

        delta = runtime.diff_runs(self.db, "ixor-v42", first["run_id"], second["run_id"])
        self.assertTrue(delta["same_state_fingerprint"])
        self.assertEqual(delta["changed_components"], [])
        self.assertEqual(delta["changed_dependency_keys"], [])

    def test_only_changed_component_is_invalidated_and_dependency_closure_propagates(self):
        before = runtime.record_inspection_run(self.db, "ixor-v42", observation("a" * 64))
        after = runtime.record_inspection_run(
            self.db, "ixor-v42", observation("b" * 64, belt_x=10.5)
        )

        belt = evidence(
            "E.BELT.CURRENT",
            ["component_name2:FITCHECK_DRIVEN_WRAP_BELT-1"],
        )
        derived = evidence(
            "E.WRAP.DERIVED",
            ["evidence_id:E.BELT.CURRENT"],
        )
        connector = evidence(
            "E.INTERFACE.CURRENT",
            ["component_name2:Connector1", "component_name2:Connector2"],
        )

        belt_before = copy.deepcopy(belt)
        derived_before = copy.deepcopy(derived)
        connector_before = copy.deepcopy(connector)

        runtime.index_evidence_record(self.db, "ixor-v42", belt)
        runtime.index_evidence_record(self.db, "ixor-v42", derived)
        runtime.index_evidence_record(self.db, "ixor-v42", connector)

        result = runtime.reconcile_runs(
            self.db, "ixor-v42", before["run_id"], after["run_id"]
        )
        self.assertEqual(
            result["changed_components"], ["FITCHECK_DRIVEN_WRAP_BELT-1"]
        )
        self.assertEqual(
            result["changed_dependency_keys"],
            ["component_name2:FITCHECK_DRIVEN_WRAP_BELT-1"],
        )
        self.assertEqual(
            result["affected_evidence_ids"],
            ["E.BELT.CURRENT", "E.WRAP.DERIVED"],
        )
        self.assertEqual(
            result["newly_stale_evidence_ids"],
            ["E.BELT.CURRENT", "E.WRAP.DERIVED"],
        )
        self.assertEqual(result["ambiguity_bucket"], "STALE_STATE")
        self.assertFalse(result["mechanical_acceptance_granted"])

        projection = {
            row["evidence_id"]: row
            for row in runtime.validity_projection(self.db, "ixor-v42")
        }
        self.assertEqual(projection["E.BELT.CURRENT"]["validity_state"], "STALE")
        self.assertEqual(projection["E.WRAP.DERIVED"]["validity_state"], "STALE")
        self.assertEqual(projection["E.INTERFACE.CURRENT"]["validity_state"], "CURRENT")

        self.assertEqual(belt, belt_before)
        self.assertEqual(derived, derived_before)
        self.assertEqual(connector, connector_before)

    def test_reindex_same_record_cannot_resurrect_stale_projection(self):
        before = runtime.record_inspection_run(
            self.db, "ixor-v42", observation("a" * 64)
        )
        after = runtime.record_inspection_run(
            self.db, "ixor-v42", observation("b" * 64, belt_x=10.5)
        )
        record = evidence(
            "E.REINDEX.STALE",
            ["component_name2:FITCHECK_DRIVEN_WRAP_BELT-1"],
        )
        immutable_before = copy.deepcopy(record)

        first_index = runtime.index_evidence_record(
            self.db, "ixor-v42", record
        )
        self.assertEqual(first_index["source_validity_state"], "CURRENT")
        self.assertEqual(first_index["validity_state"], "CURRENT")
        self.assertEqual(
            first_index["admission"]["evidence_state"], "VERIFIED"
        )

        runtime.reconcile_runs(
            self.db, "ixor-v42", before["run_id"], after["run_id"]
        )

        second_index = runtime.index_evidence_record(
            self.db, "ixor-v42", record
        )
        self.assertEqual(record, immutable_before)
        self.assertEqual(
            second_index["record_sha256"], first_index["record_sha256"]
        )
        self.assertEqual(second_index["source_validity_state"], "CURRENT")
        self.assertEqual(second_index["validity_state"], "STALE")
        self.assertIsNotNone(second_index["last_invalidation_event_id"])
        self.assertEqual(
            second_index["admission"]["evidence_state"], "VERIFIED"
        )

        projection = runtime.validity_projection(self.db, "ixor-v42")
        row = next(
            item
            for item in projection
            if item["evidence_id"] == "E.REINDEX.STALE"
        )
        self.assertEqual(row["record_sha256"], first_index["record_sha256"])
        self.assertEqual(row["source_validity_state"], "CURRENT")
        self.assertEqual(row["validity_state"], "STALE")
        self.assertEqual(row["admission"]["evidence_state"], "VERIFIED")
        self.assertTrue(row["projection_only"])

    def test_same_source_artifact_is_idempotent(self):
        first = runtime.record_inspection_run(self.db, "ixor-v42", observation("a" * 64))
        second = runtime.record_inspection_run(self.db, "ixor-v42", observation("a" * 64))
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertTrue(second["reused_source_artifact"])

    def test_rejects_non_authoritative_or_acceptance_promoting_observation(self):
        bad = observation("a" * 64)
        bad["source_authority"] = "GENERAL_REFERENCE"
        with self.assertRaises(runtime.IncrementalEvidenceError):
            runtime.build_inspection_run(bad)

        bad = observation("a" * 64)
        bad["mechanical_acceptance_granted"] = True
        with self.assertRaises(runtime.IncrementalEvidenceError):
            runtime.build_inspection_run(bad)

        bad = observation("a" * 64)
        bad["raw_observation"]["command"] = "sw.transform_component"
        with self.assertRaises(runtime.IncrementalEvidenceError):
            runtime.build_inspection_run(bad)

        bad = observation("a" * 64)
        bad["component_count"] = 999
        with self.assertRaises(runtime.IncrementalEvidenceError):
            runtime.build_inspection_run(bad)

    def test_duplicate_name2_fails_closed(self):
        bad = observation("a" * 64)
        bad["components"].append(copy.deepcopy(bad["components"][0]))
        with self.assertRaises(runtime.IncrementalEvidenceError):
            runtime.build_inspection_run(bad)

    def test_evidence_index_requires_admission_classification(self):
        record = evidence("E.MISSING.STATE", [])
        del record["evidence_state"]
        with self.assertRaises(runtime.IncrementalEvidenceError):
            runtime.index_evidence_record(self.db, "ixor-v42", record)

    def test_evidence_id_is_immutable(self):
        record = evidence("E.IMMUTABLE", ["component_name2:Connector1"])
        runtime.index_evidence_record(self.db, "ixor-v42", record)
        changed = copy.deepcopy(record)
        changed["dependencies"] = ["component_name2:Connector2"]
        with self.assertRaises(runtime.IncrementalEvidenceError):
            runtime.index_evidence_record(self.db, "ixor-v42", changed)


if __name__ == "__main__":
    unittest.main()
