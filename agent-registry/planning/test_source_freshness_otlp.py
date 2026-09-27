import copy
import json
import unittest

from source_freshness import SourceFreshnessError, compare
from source_freshness_otlp import EVENT_NAME, to_otlp_json
from test_source_freshness import snapshot


def log_record(payload):
    return payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]


class SourceFreshnessOtlpTests(unittest.TestCase):
    def test_realistic_stale_classification_is_bounded_named_event(self):
        report = compare(snapshot())
        report["evaluated_at"] = "2026-09-27T06:00:00Z"
        before = copy.deepcopy(report)
        payload = to_otlp_json(report)
        self.assertEqual(report, before)
        record = log_record(payload)
        self.assertEqual(record["eventName"], EVENT_NAME)
        self.assertEqual(record["timeUnixNano"], "1790488800000000000")
        self.assertEqual(record["severityNumber"], 13)
        self.assertEqual(payload["resourceLogs"][0]["resource"]["attributes"][0], {
            "key": "service.name", "value": {"stringValue": "cadgrounded-freshness-monitor"},
        })
        attributes = {item["key"]: item["value"] for item in record["attributes"]}
        self.assertEqual(attributes["cadgrounded.freshness.live.generation"], {"intValue": "43"})
        self.assertEqual(attributes["cadgrounded.freshness.google_drive.generation"], {"intValue": "42"})
        self.assertEqual(attributes["cadgrounded.freshness.mechanical_acceptance_granted"],
                         {"boolValue": False})
        rendered = json.dumps(payload)
        self.assertNotIn("C:\\ChatGPT", rendered)
        self.assertNotIn("drive:test-canonical-identity", rendered)
        self.assertNotIn("OBS:test-live-status", rendered)
        self.assertNotIn("IXOR_Benchmark", rendered)

    def test_aligned_event_is_informational(self):
        data = snapshot()
        data["google_drive"]["document_title_exact"] = data["solidworks"]["document_title_exact"]
        record = log_record(to_otlp_json(compare(data)))
        self.assertEqual(record["severityNumber"], 9)
        self.assertEqual(record["severityText"], "INFO")

    def test_unavailable_source_remains_unknown(self):
        data = snapshot()
        data["google_drive"] = {"retrieval_state": "UNAVAILABLE"}
        record = log_record(to_otlp_json(compare(data)))
        attributes = {item["key"]: item["value"] for item in record["attributes"]}
        self.assertEqual(attributes["cadgrounded.freshness.google_drive.state"],
                         {"stringValue": "UNKNOWN"})
        self.assertNotIn("cadgrounded.freshness.google_drive.generation", attributes)

    def test_rejects_promotion_and_inconsistent_classification(self):
        report = compare(snapshot())
        report["mechanical_acceptance_granted"] = True
        with self.assertRaisesRegex(SourceFreshnessError, "promotion"):
            to_otlp_json(report)
        report = compare(snapshot())
        report["overall_state"] = "ALIGNED_AT_CHECKPOINT_LEVEL"
        with self.assertRaisesRegex(SourceFreshnessError, "does not match"):
            to_otlp_json(report)

    def test_rejects_unscoped_event_and_naive_time(self):
        report = compare(snapshot())
        report["input_verification"] = "VERIFIED"
        with self.assertRaisesRegex(SourceFreshnessError, "provenance"):
            to_otlp_json(report)
        report = compare(snapshot())
        report["evaluated_at"] = "2026-09-27T06:00:00"
        with self.assertRaisesRegex(SourceFreshnessError, "timezone"):
            to_otlp_json(report)


if __name__ == "__main__":
    unittest.main()
