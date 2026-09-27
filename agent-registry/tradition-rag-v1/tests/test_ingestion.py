import json
import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import ingestion
import tradition_rag as tr


class IngestionTests(unittest.TestCase):
    def test_auto_refresh_respects_recent_failed_check(self):
        registry = ingestion.read_json(HERE / "sources.v1.json")
        policy = ingestion.read_json(HERE / "ingestion-policy.v1.json")
        source = next(
            s for s in registry["sources"]
            if s["source_id"] == "CHAT.ENGTIPS.MECH"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ingestion.append_jsonl(
                ingestion.checks_path(root, source["source_id"]),
                ingestion.check_event(source, "ACCESS_CHALLENGE_BLOCKED"),
            )
            self.assertFalse(
                ingestion.auto_refresh_due(source, policy, root)
            )

    def test_metadata_only_policy_blocks_network_body(self):
        registry = ingestion.read_json(HERE / "sources.v1.json")
        policy = ingestion.read_json(HERE / "ingestion-policy.v1.json")
        source = next(
            s for s in registry["sources"] if s["source_id"] == "AUTH.ISO.12100"
        )
        action = ingestion.source_action(source, policy)
        self.assertFalse(action["network_body_ingestion"])

    def test_html_normalization_excludes_navigation_and_script(self):
        raw = b"""
        <html><head><title>Example Title</title><script>bad()</script></head>
        <body><nav>ignore menu</nav><main><h1>Machine Design</h1>
        <p>Useful   engineering text.</p></main><footer>ignore footer</footer></body>
        </html>
        """
        class Headers:
            def get_content_charset(self):
                return "utf-8"
        title, text = ingestion.extract_visible_text(raw, "text/html", Headers())
        self.assertEqual("Example Title", title)
        self.assertIn("Machine Design", text)
        self.assertIn("Useful engineering text.", text)
        self.assertNotIn("ignore menu", text)
        self.assertNotIn("bad()", text)

    def test_stackexchange_json_preserves_attribution_and_license(self):
        raw = json.dumps(
            {
                "items": [
                    {
                        "title": "PLC &amp; interlock question",
                        "body": "<p>How should this interlock be diagnosed?</p>",
                        "link": "https://electronics.stackexchange.com/q/123",
                        "owner": {"display_name": "Example User"},
                        "tags": ["plc", "industrial"],
                        "content_license": "CC BY-SA 4.0",
                        "last_activity_date": 1790540000,
                    }
                ],
                "quota_remaining": 299,
            }
        ).encode("utf-8")

        class Headers:
            def get_content_charset(self):
                return "utf-8"

        title, text = ingestion.extract_visible_text(
            raw, "application/json", Headers()
        )
        self.assertEqual("Stack Exchange API", title)
        self.assertIn("PLC & interlock question", text)
        self.assertIn("How should this interlock be diagnosed?", text)
        self.assertIn("Author: Example User", text)
        self.assertIn("License: CC BY-SA 4.0", text)
        self.assertIn("https://electronics.stackexchange.com/q/123", text)

    def test_atom_feed_extracts_entries_and_links(self):
        raw = b"""<?xml version='1.0' encoding='UTF-8'?>
        <feed xmlns='http://www.w3.org/2005/Atom'>
          <title>Machinists</title>
          <entry>
            <title>Fixture alignment question</title>
            <updated>2026-09-27T12:00:00Z</updated>
            <link rel='alternate' href='https://example.test/thread/1'/>
            <content type='html'>&lt;p&gt;How do you hold alignment during setup?&lt;/p&gt;</content>
          </entry>
        </feed>"""
        class Headers:
            def get_content_charset(self):
                return "utf-8"
        title, text = ingestion.extract_visible_text(
            raw, "application/atom+xml", Headers()
        )
        self.assertEqual("Machinists", title)
        self.assertIn("Fixture alignment question", text)
        self.assertIn("How do you hold alignment during setup?", text)
        self.assertIn("https://example.test/thread/1", text)

    def test_access_challenge_detection(self):
        self.assertTrue(
            ingestion.looks_like_access_challenge(
                "https://www.example.com/.stile/challenge?return=/forum",
                "Please wait",
                "Checking your browser",
            )
        )
        self.assertFalse(
            ingestion.looks_like_access_challenge(
                "https://www.example.com/forum",
                "Forum",
                "Normal practitioner discussion index.",
            )
        )

    def test_chunking_is_deterministic_and_bounded(self):
        text = "\n".join(
            ["paragraph one " * 20, "paragraph two " * 20, "paragraph three " * 20]
        )
        a = ingestion.paragraph_chunks(text, 180, 20)
        b = ingestion.paragraph_chunks(text, 180, 20)
        self.assertEqual(a, b)
        self.assertTrue(a)
        self.assertTrue(all(len(chunk) <= 180 for chunk in a))

    def test_dedup_does_not_promote_lower_authority_copy(self):
        records = [
            {
                "normalized_sha256": "abc",
                "source_lane": "AUTHORITATIVE",
                "source_id": "AUTH.ONE",
                "source_record_id": "R1",
            },
            {
                "normalized_sha256": "abc",
                "source_lane": "FIELD_CHATTER",
                "source_id": "CHAT.ONE",
                "source_record_id": "R2",
            },
        ]
        annotations = ingestion.dedup_annotations(records)
        self.assertIsNone(annotations["R1"]["duplicate_of_source_record_id"])
        self.assertEqual("R1", annotations["R2"]["duplicate_of_source_record_id"])

    def test_live_projection_replaces_seed_for_same_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = ingestion.read_json(HERE / "sources.v1.json")["sources"][0]
            normalized = "Live millwright conveyor alignment maintenance text."
            normalized_sha = ingestion.sha256_text(normalized)
            txt = ingestion.text_path(root, normalized_sha)
            txt.parent.mkdir(parents=True, exist_ok=True)
            txt.write_text(normalized, encoding="utf-8")

            record_id = "SRCREC.TEST"
            record_path = ingestion.source_record_dir(root, source["source_id"]) / "record.json"
            record = {
                "source_record_id": record_id,
                "source_id": source["source_id"],
                "source_lane": source["lane"],
                "authority_class": source["authority_class"],
                "traditions": source["traditions"],
                "storage_mode": source["storage_mode"],
                "observed_url": source["url"],
                "observed_at_utc": "2026-09-27T00:00:00Z",
                "page_title": source["title"],
                "raw_sha256": "raw123",
                "normalized_sha256": normalized_sha,
                "text_path": str(txt),
            }
            ingestion.write_json_atomic(record_path, record)
            ingestion.write_json_atomic(
                ingestion.latest_pointer_path(root, source["source_id"]),
                {
                    "source_id": source["source_id"],
                    "source_record_id": record_id,
                    "record_path": str(record_path),
                    "raw_sha256": "raw123",
                    "normalized_sha256": normalized_sha,
                    "observed_at_utc": "2026-09-27T00:00:00Z",
                    "last_checked_at_utc": "2026-09-27T00:00:00Z",
                },
            )

            projection = ingestion.build_projection(HERE, root)
            self.assertGreater(projection["chunks"], 0)
            manifest = tr.bootstrap(HERE, root)
            millwright = manifest["collections"]["MILLWRIGHT"]
            self.assertGreater(millwright["live_chunks"], 0)

            con = tr.open_db(tr.db_path(root, "MILLWRIGHT"))
            source_count = con.execute(
                "SELECT count(*) FROM chunks_fts WHERE source_id = ?",
                (source["source_id"],),
            ).fetchone()[0]
            seed_count = con.execute(
                """
                SELECT count(*) FROM chunks_fts
                JOIN chunk_provenance USING(chunk_id)
                WHERE source_id = ? AND chunk_kind = 'SEED_CARD'
                """,
                (source["source_id"],),
            ).fetchone()[0]
            con.close()
            self.assertGreater(source_count, 0)
            self.assertEqual(0, seed_count)


if __name__ == "__main__":
    unittest.main()
