#!/usr/bin/env python3
import copy
import json
import unittest
from pathlib import Path

from v42_interface_evidence_admission import (AdmissionError, CURRENT, STALE, UNRESOLVED, CURRENT_CLAIMS, UNRESOLVED_CLAIMS, admit_host_artifact, build_dependency_graph, supersede_evidence, validate_evidence_record)

ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "reference_cases" / "v42_passed_windows_host_interface_artifact.v1.json"
SCHEMA = ROOT.parent / "schemas" / "evidence-record.v1.schema.json"


class V42InterfaceEvidenceAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        # Test-only stand-in. Production admission fails closed until the actual
        # Windows-host file digest is supplied by the operator.
        self.artifact["artifact_sha256"] = "a" * 64
        self.artifact["recorded_at"] = "2026-09-25T22:10:54Z"
        self.record = admit_host_artifact(self.artifact)
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_record_validates_against_evidence_record_schema(self):
        validate_evidence_record(self.record, self.schema)
        self.assertEqual(self.record["evidence_type"], "solidworks_observation")
        self.assertFalse(self.record["mechanical_acceptance_granted"])
        self.assertEqual(self.record["provenance"]["sha256"], "a" * 64)
        self.assertTrue(self.record["evidence_id"].endswith("a" * 64))

    def test_external_digest_is_a_fail_closed_admission_precondition(self):
        artifact = copy.deepcopy(self.artifact)
        del artifact["artifact_sha256"]
        with self.assertRaisesRegex(AdmissionError, "SHA-256"):
            admit_host_artifact(artifact)

    def test_only_bounded_identity_and_frame_claims_are_current(self):
        graph = build_dependency_graph(self.record)
        states = {node["id"]: node["state"] for node in graph["nodes"]}
        self.assertTrue(all(states[c] == CURRENT for c in CURRENT_CLAIMS))
        self.assertTrue(all(states[c] == UNRESOLVED for c in UNRESOLVED_CLAIMS))
        self.assertFalse(any(node["mechanical_acceptance_granted"] for node in graph["nodes"]))

    def test_superseded_evidence_reopens_dependents(self):
        graph = supersede_evidence(build_dependency_graph(self.record), self.record["evidence_id"])
        states = {node["id"]: node["state"] for node in graph["nodes"]}
        self.assertTrue(all(states[c] == STALE for c in CURRENT_CLAIMS))
        self.assertTrue(all(states[c] == UNRESOLVED for c in UNRESOLVED_CLAIMS))

    def test_admission_does_not_add_remote_queue_or_write_authority(self):
        graph = build_dependency_graph(self.record)
        self.assertEqual(self.record["payload"]["write_authority"], "NONE")
        self.assertFalse(self.record["payload"]["remote_queue_authorized"])
        self.assertEqual(graph["write_authority"], "NONE")
        self.assertFalse(graph["remote_queue_authorized"])


if __name__ == "__main__":
    unittest.main()
