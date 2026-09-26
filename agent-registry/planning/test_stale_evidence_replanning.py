import copy
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT_REGISTRY = HERE.parent
SCHEMA = AGENT_REGISTRY / "reasoning-db" / "schema.sql"
ARCHITECTURE_PATH = (
    AGENT_REGISTRY
    / "reasoning"
    / "reference_cases"
    / "v43_prism_capture_and_rotation.functional-temporal.v1.json"
)
MODULE = HERE / "stale_evidence_replanning.py"
SPEC = importlib.util.spec_from_file_location("stale_evidence_replanning", MODULE)
planner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(planner)

LIVE_EVIDENCE_ID = "E.V43.PRISM.LIVE_STATE.20260926T200826594Z"
WORLD_ID = "ixor-v43"
EVENT_ID = "invalidation:test-v43"
PREVIOUS_RUN = "inspection:before"
CURRENT_RUN = "inspection:after"
DOCUMENT_TITLE = "IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE"
DOCUMENT_PATH = r"C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StaleEvidenceReplanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "reasoning.db"
        connection = sqlite3.connect(self.db)
        try:
            connection.executescript(SCHEMA.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO worlds(id,title,source_path,created_at) VALUES(?,?,?,?)",
                (WORLD_ID, "IXOR v43", DOCUMENT_PATH, "2026-09-26T22:30:00Z"),
            )
            for run_id, raw_sha, state_fp in (
                (PREVIOUS_RUN, "a" * 64, "1" * 64),
                (CURRENT_RUN, "b" * 64, "2" * 64),
            ):
                connection.execute(
                    "INSERT INTO inspection_runs("
                    "id,world_id,recorded_at,source_authority,source_classification,"
                    "document_title,document_path,active_configuration,observation_sha256,"
                    "state_fingerprint,metadata_json"
                    ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        WORLD_ID,
                        "2026-09-26T22:30:00Z",
                        "SOLIDWORKS_LIVE_STATE",
                        "verified_from_solidworks_api",
                        DOCUMENT_TITLE,
                        DOCUMENT_PATH,
                        "V43_WRAP",
                        raw_sha,
                        state_fp,
                        "{}",
                    ),
                )
            connection.execute(
                "INSERT INTO invalidation_events("
                "id,world_id,previous_run_id,current_run_id,changed_dependency_keys_json,"
                "affected_evidence_ids_json,created_at,metadata_json"
                ") VALUES(?,?,?,?,?,?,?,?)",
                (
                    EVENT_ID,
                    WORLD_ID,
                    PREVIOUS_RUN,
                    CURRENT_RUN,
                    json.dumps(["component_name2:FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1"]),
                    json.dumps([LIVE_EVIDENCE_ID]),
                    "2026-09-26T22:31:00Z",
                    json.dumps(
                        {
                            "projection_only": True,
                            "ambiguity_bucket": "STALE_STATE",
                            "mechanical_acceptance_granted": False,
                        }
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO evidence_validity_projection("
                "world_id,evidence_id,record_sha256,validity_state,last_invalidation_event_id,"
                "updated_at,metadata_json"
                ") VALUES(?,?,?,?,?,?,?)",
                (
                    WORLD_ID,
                    LIVE_EVIDENCE_ID,
                    "c" * 64,
                    "STALE",
                    EVENT_ID,
                    "2026-09-26T22:31:00Z",
                    "{}",
                ),
            )
            connection.commit()
        finally:
            connection.close()
        self.architecture = json.loads(ARCHITECTURE_PATH.read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def test_v43_stale_live_evidence_produces_declared_read_only_reacquisition_proposal(self):
        architecture_before = copy.deepcopy(self.architecture)
        db_hash_before = sha256_file(self.db)

        context = planner.load_invalidation_context(self.db, WORLD_ID, EVENT_ID)
        proposal = planner.build_reacquisition_proposal(self.architecture, context)

        self.assertEqual(proposal["status"], "READY_FOR_REVIEW")
        self.assertEqual(proposal["architecture_id"], "IXOR_V43_PRISM_CAPTURE_AND_ROTATION_REFERENCE")
        self.assertEqual(proposal["stale_evidence_ids"], [LIVE_EVIDENCE_ID])
        self.assertTrue(proposal["stale_requirement_ids"])
        self.assertTrue(proposal["candidate_tests"])
        self.assertIsNotNone(proposal["selected_next_test"])
        self.assertEqual(proposal["write_authority"], "NONE")
        self.assertFalse(proposal["cad_write_authorized"])
        self.assertFalse(proposal["mechanical_acceptance_granted"])
        self.assertFalse(proposal["ledger_mutation_performed"])
        self.assertFalse(proposal["execution_performed"])
        self.assertEqual(proposal["ambiguity_bucket"], "STALE_STATE")

        declared_test_ids = {item["id"] for item in self.architecture["next_tests"]}
        returned_test_ids = {item["test_id"] for item in proposal["candidate_tests"]}
        self.assertTrue(returned_test_ids)
        self.assertTrue(returned_test_ids.issubset(declared_test_ids))
        self.assertIn(proposal["selected_next_test"]["test_id"], declared_test_ids)

        stale_requirements = set(proposal["stale_requirement_ids"])
        for candidate in proposal["candidate_tests"]:
            self.assertTrue(
                set(candidate["resolves_requirement_ids"]) & stale_requirements
            )
            request = candidate.get("cad_request")
            if request is not None:
                self.assertEqual(request["write_authority"], "NONE")
            for native in candidate.get("native_read_candidates") or []:
                self.assertEqual(native["write_authority"], "NONE")
                self.assertFalse(native["remote_queue_authorized"])

        self.assertEqual(len(proposal["projected_steps"]), 1)
        self.assertEqual(proposal["projected_steps"][0]["write_authority"], "NONE")
        self.assertEqual(
            proposal["projected_steps"][0]["status"], "PROPOSED_NOT_EXECUTED"
        )
        self.assertEqual(self.architecture, architecture_before)
        self.assertEqual(sha256_file(self.db), db_hash_before)

    def test_stale_evidence_not_bound_to_architecture_is_reported_without_inventing_test(self):
        unrelated = "E.UNRELATED.STALE"
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE invalidation_events SET affected_evidence_ids_json=? WHERE id=?",
                (json.dumps([unrelated]), EVENT_ID),
            )
            connection.execute(
                "DELETE FROM evidence_validity_projection WHERE world_id=?",
                (WORLD_ID,),
            )
            connection.execute(
                "INSERT INTO evidence_validity_projection("
                "world_id,evidence_id,record_sha256,validity_state,last_invalidation_event_id,"
                "updated_at,metadata_json"
                ") VALUES(?,?,?,?,?,?,?)",
                (
                    WORLD_ID,
                    unrelated,
                    "d" * 64,
                    "STALE",
                    EVENT_ID,
                    "2026-09-26T22:31:00Z",
                    "{}",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        context = planner.load_invalidation_context(self.db, WORLD_ID, EVENT_ID)
        proposal = planner.build_reacquisition_proposal(self.architecture, context)

        self.assertEqual(proposal["status"], "NO_BOUND_STALE_REQUIREMENTS")
        self.assertEqual(proposal["stale_not_bound_to_architecture"], [unrelated])
        self.assertEqual(proposal["stale_requirement_ids"], [])
        self.assertEqual(proposal["candidate_tests"], [])
        self.assertIsNone(proposal["selected_next_test"])
        self.assertEqual(proposal["projected_steps"], [])

    def test_missing_validity_projection_for_affected_evidence_fails_closed(self):
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "DELETE FROM evidence_validity_projection WHERE world_id=? AND evidence_id=?",
                (WORLD_ID, LIVE_EVIDENCE_ID),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(planner.StaleReplanningError):
            planner.load_invalidation_context(self.db, WORLD_ID, EVENT_ID)

    def test_current_affected_evidence_does_not_create_reacquisition_work(self):
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE evidence_validity_projection SET validity_state='CURRENT' "
                "WHERE world_id=? AND evidence_id=?",
                (WORLD_ID, LIVE_EVIDENCE_ID),
            )
            connection.commit()
        finally:
            connection.close()

        context = planner.load_invalidation_context(self.db, WORLD_ID, EVENT_ID)
        proposal = planner.build_reacquisition_proposal(self.architecture, context)

        self.assertEqual(proposal["status"], "NO_STALE_EVIDENCE")
        self.assertEqual(proposal["candidate_tests"], [])
        self.assertEqual(proposal["projected_steps"], [])


if __name__ == "__main__":
    unittest.main()
