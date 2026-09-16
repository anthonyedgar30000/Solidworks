#!/usr/bin/env python3
import copy
import unittest

from evidence_ingest import EvidenceError, build_transaction, validate_envelope


class EvidenceIngestTests(unittest.TestCase):
    def setUp(self):
        self.envelope = {
            "job_id": "job-1",
            "command": "sw.query_components",
            "state": "completed",
            "worker": "solidworks-bridge-01",
            "recorded_at": "2026-09-16T00:48:11+00:00",
            "error": None,
            "data": {
                "component_count": 1,
                "document_path": r"C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE.SLDASM",
                "document_title": "IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE",
                "bridge_version": "0.3.0",
                "adapter": "solidworks-api",
                "top_level_only": False,
                "components": [
                    {
                        "translation_mm": [1.0, 2.0, 3.0],
                        "translation_m": [0.001, 0.002, 0.003],
                        "parent_name": None,
                        "transform_array": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0.001, 0.002, 0.003, 1, 0, 0, 0],
                        "bounding_box_mm_approx": {"min": [0, 0, 0], "max": [10, 10, 10]},
                        "getbox_mm": [0, 0, 0, 10, 10, 10],
                        "name2": "Example-1",
                        "fixed": False,
                        "geometry_note": "Approximate component envelope",
                        "suppressed": False,
                        "box_max_mm": [10, 10, 10],
                        "getbox_m": [0, 0, 0, 0.01, 0.01, 0.01],
                        "suppression_state": 2,
                        "scale": 1,
                        "field_errors": [],
                        "transform_source": "Component2.Transform2",
                        "source_classification": "verified_from_solidworks_api",
                        "rotation9": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                        "path": r"C:\example.SLDPRT",
                        "box_min_mm": [0, 0, 0],
                        "is_top_level": True,
                        "referenced_configuration": "Default",
                    }
                ],
            },
        }

    def test_completed_observation_is_admitted(self):
        tx = build_transaction(
            self.envelope,
            raw_sha256="abc123",
            source_file="LIVE_CAD_ALL_COMPONENTS.json",
            expected_document="IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE",
        )
        self.assertEqual(tx["admission_status"], "ADMITTED_OBSERVATION")
        self.assertFalse(tx["mechanical_acceptance_granted"])
        self.assertEqual(tx["component_count"], 1)
        self.assertEqual(tx["components"][0]["name2"], "Example-1")
        self.assertEqual(tx["components"][0]["identity_basis"], "Component2.Name2")

    def test_non_completed_job_is_rejected(self):
        env = copy.deepcopy(self.envelope)
        env["state"] = "failed"
        with self.assertRaises(EvidenceError):
            validate_envelope(env)

    def test_error_payload_is_rejected(self):
        env = copy.deepcopy(self.envelope)
        env["error"] = "bridge failure"
        with self.assertRaises(EvidenceError):
            validate_envelope(env)

    def test_wrong_document_is_rejected(self):
        with self.assertRaises(EvidenceError):
            validate_envelope(self.envelope, expected_document="some_other_assembly")

    def test_count_mismatch_is_rejected(self):
        env = copy.deepcopy(self.envelope)
        env["data"]["component_count"] = 2
        with self.assertRaises(EvidenceError):
            validate_envelope(env)

    def test_missing_exact_name2_is_rejected(self):
        env = copy.deepcopy(self.envelope)
        env["data"]["components"][0]["name2"] = None
        with self.assertRaises(EvidenceError):
            build_transaction(
                env,
                raw_sha256="abc123",
                source_file="LIVE_CAD_ALL_COMPONENTS.json",
            )

    def test_observation_does_not_promote_contact_or_acceptance(self):
        tx = build_transaction(
            self.envelope,
            raw_sha256="abc123",
            source_file="LIVE_CAD_ALL_COMPONENTS.json",
        )
        self.assertFalse(tx["mechanical_acceptance_granted"])
        self.assertIn("valid_contact", tx["prohibited_promotions"])
        self.assertIn("valid_clearance", tx["prohibited_promotions"])


if __name__ == "__main__":
    unittest.main()
