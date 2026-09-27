import copy
import hashlib
import json
import unittest

from source_freshness import SourceFreshnessError, compare
from source_freshness_bundle import CANONICAL_TITLE, normalize

LIVE = "IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE"
OLDER = "IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE"
PATH = "C:\\ChatGPT\\Solidworks\\IXOR\\" + LIVE + ".SLDASM"


def bundle():
    record = {
        "schema_version": 1, "record_type": "evidence", "evidence_id": "E.test.v43",
        "evidence_type": "solidworks_observation", "evidence_state": "VERIFIED",
        "source_authority": "SOLIDWORKS_LIVE_STATE",
        "source_classification": "verified_from_solidworks_api",
        "mechanical_acceptance_granted": False,
        "subject": {"document_title_exact": LIVE, "document_path_exact": PATH},
        "payload": {"document": {"title": LIVE, "path": PATH}},
    }
    content = json.dumps(record)
    data = content.encode("utf-8")
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    plan_content = json.dumps({
        "schema_version": 1, "project_id": "CADGROUNDED.IXOR",
        "current_evidence_id": "E.test.v43",
    })
    plan_bytes = plan_content.encode("utf-8")
    plan_blob = hashlib.sha1(b"blob " + str(len(plan_bytes)).encode() + b"\0" + plan_bytes).hexdigest()
    return {
        "schema_version": 1,
        "solidworks": {
            "observed_at": "2026-09-27T06:00:00Z",
            "tool": "cadgrounded_solidworks_sw_status",
            "response": {"ok": True, "result": {
                "source_classification": "verified_from_solidworks_api",
                "active_document": {"title": LIVE, "path": PATH, "document_type": "assembly"},
            }},
        },
        "github": {
            "observed_at": "2026-09-27T06:00:01Z",
            "repository_full_name": "example/Solidworks", "commit_sha": "a" * 40,
            "path": "agent-registry/reasoning/runtime/example.json",
            "response": {"content": content, "sha": blob},
            "current_plan_response": {"content": plan_content, "sha": plan_blob},
        },
        "google_drive": {
            "observed_at": "2026-09-27T06:00:02Z",
            "document_id": "canonical-doc-id",
            "response": {
                "documentId": "canonical-doc-id", "revisionId": "revision-one",
                "title": CANONICAL_TITLE,
                "paragraphs": [
                    {"text": "Freshness rule"},
                    {"text": f"The latest live verification observed {OLDER} as the active document."},
                ],
            },
        },
    }


class SourceBundleTests(unittest.TestCase):
    def test_binds_three_sources_and_keeps_read_only_stale_classification(self):
        source = bundle()
        original = copy.deepcopy(source)
        report = compare(normalize(source))
        self.assertEqual(source, original)
        self.assertEqual(report["overall_state"], "STALE_REFERENCE")
        self.assertEqual(report["comparisons"]["google_drive"]["state"], "STALE_REFERENCE")
        self.assertEqual(report["comparisons"]["github"]["state"], "ALIGNED_AT_CHECKPOINT_LEVEL")
        self.assertIn("#blob=", report["comparisons"]["github"]["source_ref"])
        self.assertIn("current_plan_blob=", report["comparisons"]["github"]["source_ref"])
        self.assertIn("revision-one", report["comparisons"]["google_drive"]["source_ref"])
        self.assertEqual(report["input_verification"], "CALLER_SUPPLIED_UNVERIFIED")
        self.assertFalse(report["mechanical_acceptance_granted"])

    def test_rejects_tampered_github_content(self):
        source = bundle()
        source["github"]["response"]["content"] += " "
        with self.assertRaisesRegex(SourceFreshnessError, "blob SHA"):
            normalize(source)

    def test_rejects_old_evidence_after_plan_pointer_moves(self):
        source = bundle()
        plan = json.loads(source["github"]["current_plan_response"]["content"])
        plan["current_evidence_id"] = "E.newer.v43"
        content = json.dumps(plan)
        data = content.encode()
        source["github"]["current_plan_response"] = {
            "content": content,
            "sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
        }
        with self.assertRaisesRegex(SourceFreshnessError, "not CURRENT_PLAN"):
            normalize(source)

    def test_rejects_non_observation_record_even_with_matching_blob(self):
        source = bundle()
        record = json.loads(source["github"]["response"]["content"])
        record["source_classification"] = "inferred"
        content = json.dumps(record)
        data = content.encode()
        source["github"]["response"] = {
            "content": content,
            "sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
        }
        with self.assertRaisesRegex(SourceFreshnessError, "bounded verified"):
            normalize(source)

    def test_rejects_evidence_payload_subject_disagreement(self):
        source = bundle()
        record = json.loads(source["github"]["response"]["content"])
        record["payload"]["document"]["title"] = OLDER
        content = json.dumps(record)
        data = content.encode()
        source["github"]["response"] = {
            "content": content,
            "sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
        }
        with self.assertRaisesRegex(SourceFreshnessError, "disagree"):
            normalize(source)

    def test_rejects_missing_or_ambiguous_drive_freshness_statement(self):
        source = bundle()
        source["google_drive"]["response"]["paragraphs"][0]["text"] = "History"
        with self.assertRaisesRegex(SourceFreshnessError, "missing or ambiguous"):
            normalize(source)
        source = bundle()
        source["google_drive"]["response"]["paragraphs"] *= 2
        with self.assertRaisesRegex(SourceFreshnessError, "missing or ambiguous"):
            normalize(source)

    def test_rejects_wrong_drive_document_and_unbound_live_path(self):
        source = bundle()
        source["google_drive"]["response"]["documentId"] = "another-doc"
        with self.assertRaisesRegex(SourceFreshnessError, "Drive document identity"):
            normalize(source)
        source = bundle()
        source["solidworks"]["response"]["result"]["active_document"]["path"] = "other.SLDASM"
        with self.assertRaisesRegex(SourceFreshnessError, "title and path"):
            normalize(source)


if __name__ == "__main__":
    unittest.main()
