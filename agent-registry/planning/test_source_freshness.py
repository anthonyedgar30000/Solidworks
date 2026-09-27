import copy
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("source_freshness", HERE / "source_freshness.py")
monitor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(monitor)

LIVE = "IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE"
PATH = "C:\\ChatGPT\\Solidworks\\IXOR\\CAB_IXOR_6130800\\" + LIVE + ".SLDASM"
OLDER = "IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE"


def snapshot():
    return {
        "schema_version": 1,
        "solidworks": {
            "retrieval_state": "OK", "source_ref": "OBS:test-live-status",
            "observed_at": "2026-09-27T01:00:00Z", "document_title_exact": LIVE,
            "document_path_exact": PATH, "configuration_exact": "V43_WRAP",
        },
        "github": {
            "retrieval_state": "OK", "reference_kind": "admitted_evidence",
            "source_ref": "E:test-v43-evidence@commit", "observed_at": "2026-09-27T01:01:00Z",
            "document_title_exact": LIVE,
        },
        "google_drive": {
            "retrieval_state": "OK", "reference_kind": "canonical_identity",
            "source_ref": "drive:test-canonical-identity", "observed_at": "2026-09-27T01:02:00Z",
            "document_title_exact": OLDER,
        },
    }


class SourceFreshnessTests(unittest.TestCase):
    def test_v43_live_and_evidence_v42_drive_is_stale_reference(self):
        inputs = snapshot()
        before = copy.deepcopy(inputs)
        report = monitor.compare(inputs)
        self.assertEqual(inputs, before)
        self.assertEqual(report["overall_state"], "STALE_REFERENCE")
        self.assertEqual(report["comparisons"]["github"]["state"], "ALIGNED_AT_CHECKPOINT_LEVEL")
        self.assertEqual(report["comparisons"]["google_drive"]["state"], "STALE_REFERENCE")
        self.assertEqual(report["ambiguity_bucket"], "STALE_STATE")
        self.assertEqual(report["write_authority"], "NONE")
        self.assertFalse(report["mechanical_acceptance_granted"])
        self.assertFalse(report["evidence_admission_performed"])

    def test_same_generation_different_identity_is_conflict(self):
        inputs = snapshot()
        inputs["github"]["document_title_exact"] = "IXOR_Benchmark_v43_OTHER_CANDIDATE"
        report = monitor.compare(inputs)
        self.assertEqual(report["overall_state"], "SOURCE_CONFLICT")
        self.assertEqual(report["comparisons"]["github"]["reason"], "DIFFERENT_CHECKPOINT_IDENTITY")

    def test_missing_drive_does_not_become_alignment(self):
        inputs = snapshot()
        inputs["google_drive"] = {"retrieval_state": "UNAVAILABLE"}
        report = monitor.compare(inputs)
        self.assertEqual(report["overall_state"], "UNKNOWN")
        self.assertEqual(report["comparisons"]["google_drive"]["state"], "UNKNOWN")

    def test_repo_head_cannot_masquerade_as_admitted_evidence(self):
        inputs = snapshot()
        inputs["github"]["reference_kind"] = "repo_head"
        with self.assertRaises(monitor.SourceFreshnessError):
            monitor.compare(inputs)

    def test_configuration_conflict_only_when_both_bound(self):
        inputs = snapshot()
        inputs["github"]["configuration_exact"] = "V43_ENTRY"
        self.assertEqual(monitor.compare(inputs)["comparisons"]["github"]["reason"],
                         "DIFFERENT_CONFIGURATION")
        del inputs["solidworks"]["configuration_exact"]
        self.assertEqual(monitor.compare(inputs)["comparisons"]["github"]["state"],
                         "ALIGNED_AT_CHECKPOINT_LEVEL")


if __name__ == "__main__":
    unittest.main()
