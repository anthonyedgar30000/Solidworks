import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from source_capture import (ALLOWED, CaptureBlocked, REGISTRY, capture_all,
                            candidate_snippets, fetch_source, validate_registry)


HTML = b"<html><body><p>A roller prism sets the product to be labeled in rotation.</p><p>Wrap-around belt and counterpressure plate.</p></body></html>"


def fake_fetch(row):
    return b"%PDF-1.7\nfixture" if row["expected_media_type"] == "application/pdf" else HTML


class SourceCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state"
        self.registry = json.loads(REGISTRY.read_text())

    def capture(self, fetch=fake_fetch):
        return capture_all(self.state, fetch=fetch,
                           frontier_sync=lambda state: {
                               "status": "SOURCE_ACQUISITION_REQUIRED",
                               "source_commit_sha": "a" * 40,
                               "projection": {"plan_id": "PLAN-0010", "execution_authority": "NONE"},
                           })

    def test_capture_is_unadmitted_and_idempotent(self):
        first = self.capture()
        second = self.capture()
        self.assertEqual(first["status"], "CAPTURED")
        self.assertTrue(all(row["new"] for row in first["results"]))
        self.assertTrue(all(not row["new"] for row in second["results"]))
        self.assertEqual(len(list((self.state / "source_blobs").iterdir())), 2)
        self.assertEqual(len(list((self.state / "source_candidates").glob("*/*.json"))), 3)
        for row in first["results"]:
            record = json.loads(Path(row["record"]).read_text())
            self.assertEqual(record["evidence_state"], "UNADMITTED")
            self.assertEqual(record["claim_verification_authority"], "NONE")
            self.assertFalse(record["mechanical_acceptance_granted"])
        self.assertEqual(json.loads((self.state / "last_capture_status.json").read_text())["status"], "CAPTURED")

    def test_dynamic_html_markup_does_not_create_duplicate_record(self):
        first = self.capture()

        def changing(row):
            raw = fake_fetch(row)
            return raw.replace(b"<body>", b"<script>session-token-2</script><body>") if row["expected_media_type"] == "text/html" else raw

        second = self.capture(fetch=changing)
        self.assertEqual(second["status"], "CAPTURED")
        self.assertTrue(all(not item["new"] for item in second["results"]))
        self.assertNotEqual(first["results"][1]["retrieved_raw_sha256"],
                            second["results"][1]["retrieved_raw_sha256"])
        self.assertEqual(first["results"][1]["content_sha256"], second["results"][1]["content_sha256"])
        self.assertEqual(len(list((self.state / "source_blobs").iterdir())), 2)

    def test_registry_cannot_widen_url_or_source_role(self):
        self.registry["sources"][0]["url"] = "https://example.org/instructions.pdf"
        with self.assertRaisesRegex(CaptureBlocked, "SOURCE_AUTHORITY_CHANGED"):
            validate_registry(self.registry)
        self.registry["sources"][0]["url"] = ALLOWED[self.registry["sources"][0]["source_id"]][0]
        self.registry["sources"][0]["source_role"] = "SUBJECT_OEM_DOCUMENT_WITH_CAD_AUTHORITY"
        with self.assertRaisesRegex(CaptureBlocked, "SOURCE_AUTHORITY_CHANGED"):
            validate_registry(self.registry)

    def test_record_tamper_is_blocked_without_rewrite(self):
        result = self.capture()
        record_path = Path(result["results"][0]["record"])
        record = json.loads(record_path.read_text())
        record["evidence_state"] = "VERIFIED"
        record_path.write_text(json.dumps(record))
        second = self.capture()
        self.assertEqual(second["status"], "PARTIAL_BLOCKED")
        self.assertIn("IMMUTABLE_RECORD_DRIFT", second["results"][0]["reason"])

    def test_legacy_pdf_record_remains_immutable_and_reusable(self):
        result = self.capture()
        path = Path(result["results"][0]["record"])
        legacy = json.loads(path.read_text())
        legacy.pop("content_sha256")
        legacy.pop("content_fingerprint_kind")
        path.write_text(json.dumps(legacy), encoding="utf-8")
        before = path.read_bytes()
        second = self.capture()
        self.assertEqual(second["status"], "CAPTURED")
        self.assertFalse(second["results"][0]["new"])
        self.assertEqual(path.read_bytes(), before)

    def test_partial_source_failure_does_not_promote_other_sources(self):
        def failing(row):
            if row["source_id"] == "HERMA.152C.PRODUCT_PAGE":
                raise TimeoutError("unavailable")
            return fake_fetch(row)

        result = self.capture(fetch=failing)
        self.assertEqual(result["status"], "PARTIAL_BLOCKED")
        self.assertEqual(len([row for row in result["results"] if "record" in row]), 2)
        self.assertEqual(len([row for row in result["results"] if row.get("status") == "BLOCKED"]), 1)

    def test_moved_frontier_blocks_all_source_fetches(self):
        def unexpected_fetch(row):
            self.fail("source fetch must not occur after frontier moves")

        result = capture_all(self.state, fetch=unexpected_fetch,
                             frontier_sync=lambda state: {"status": "BLOCKED"})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("FRONTIER_NOT_ACTIVE_OR_FRESH", result["reason"])
        self.assertFalse((self.state / "source_candidates").exists())

    def test_snippets_are_source_text_windows(self):
        snippets = candidate_snippets(HTML, ["roller prism", "counterpressure plate", "absent term"])
        self.assertEqual([s["marker"] for s in snippets], ["roller prism", "counterpressure plate"])
        self.assertIn("sets the product", snippets[0]["source_text_window"])

    @patch("source_capture.urlopen")
    def test_fetch_rejects_redirect_and_media_change(self, urlopen):
        row = self.registry["sources"][1]

        class Response:
            def __init__(self, url, media):
                self.url, self.headers = url, {"Content-Type": media}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def geturl(self):
                return self.url

            def read(self, limit):
                return HTML

        urlopen.return_value = Response("https://example.org/redirect", "text/html")
        with self.assertRaisesRegex(CaptureBlocked, "SOURCE_REDIRECT_REJECTED"):
            fetch_source(row)
        urlopen.return_value = Response(row["url"], "application/pdf")
        with self.assertRaisesRegex(CaptureBlocked, "SOURCE_MEDIA_CHANGED"):
            fetch_source(row)


if __name__ == "__main__":
    unittest.main()
