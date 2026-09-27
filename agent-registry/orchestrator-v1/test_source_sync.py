import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from frontier_runner import INPUTS, PLAN
from source_sync import (
    SyncBlocked, download_input, materialize_snapshot, resolve_main, sync_once,
)


REPO = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40


def fixture_fetch(commit, path):
    assert commit == COMMIT
    return (REPO / path).read_bytes()


class SourceSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state"

    def test_repeat_sync_keeps_one_receipt_and_exact_snapshot(self):
        first = sync_once(self.state, resolve=lambda: COMMIT, fetch=fixture_fetch)
        second = sync_once(self.state, resolve=lambda: COMMIT, fetch=fixture_fetch)
        self.assertEqual(first["status"], "SOURCE_ACQUISITION_REQUIRED")
        self.assertTrue(first["projection"]["new"])
        self.assertFalse(second["projection"]["new"])
        self.assertEqual(second["source_commit_sha"], COMMIT)
        self.assertEqual(len(list((self.state / "receipts").glob("*.json"))), 1)
        self.assertEqual(len(list((self.state / "snapshots").glob(COMMIT))), 1)
        self.assertEqual(json.loads((self.state / "last_sync_status.json").read_text())["status"],
                         "SOURCE_ACQUISITION_REQUIRED")

    def test_moved_remote_plan_is_captured_but_no_task_issued(self):
        def moved(commit, path):
            raw = fixture_fetch(commit, path)
            if path == PLAN:
                data = json.loads(raw.decode("utf-8-sig"))
                data["current_plan_id"] = "PLAN-0011"
                return json.dumps(data).encode()
            return raw

        result = sync_once(self.state, resolve=lambda: COMMIT, fetch=moved)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["projection"]["reason"], "FRONTIER_MOVED")
        self.assertFalse((self.state / "receipts").exists())

    def test_existing_snapshot_drift_blocks_without_replacement(self):
        snapshot, _ = materialize_snapshot(COMMIT, self.state, fixture_fetch)
        (snapshot / INPUTS[0]).write_text("{}", encoding="utf-8")
        result = sync_once(self.state, resolve=lambda: COMMIT, fetch=fixture_fetch)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("IMMUTABLE_SNAPSHOT_DRIFT", result["reason"])
        self.assertFalse((self.state / "receipts").exists())

    def test_network_failure_fails_closed_and_records_status(self):
        def unavailable():
            raise TimeoutError("remote unavailable")

        result = sync_once(self.state, resolve=unavailable)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse((self.state / "receipts").exists())
        self.assertEqual(json.loads((self.state / "last_sync_status.json").read_text())["status"],
                         "BLOCKED")

    def test_invalid_commit_and_path_are_rejected_before_download(self):
        with self.assertRaises(SyncBlocked):
            download_input("main", PLAN)
        with self.assertRaises(SyncBlocked):
            download_input(COMMIT, "agent-registry/reasoning-node-v1/app.py")

    @patch("source_sync.urlopen")
    def test_download_is_pinned_to_commit_and_rejects_redirect(self, urlopen):
        class Response:
            def __init__(self, final_url):
                self.final_url = final_url

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def geturl(self):
                return self.final_url

            def read(self, limit):
                self_outer.assertEqual(limit, 1_000_001)
                return b"{}"

        self_outer = self
        expected = f"https://raw.githubusercontent.com/anthonyedgar30000/Solidworks/{COMMIT}/{PLAN}"
        urlopen.return_value = Response(expected)
        self.assertEqual(download_input(COMMIT, PLAN), b"{}")
        self.assertEqual(urlopen.call_args.args[0].full_url, expected)
        urlopen.return_value = Response("https://example.org/unrelated.json")
        with self.assertRaisesRegex(SyncBlocked, "SOURCE_REDIRECT_REJECTED"):
            download_input(COMMIT, PLAN)

    @patch("source_sync.subprocess.run")
    def test_main_ref_is_exact_and_single(self, run):
        run.return_value.stdout = f"{COMMIT}\trefs/heads/main\n"
        self.assertEqual(resolve_main(), COMMIT)
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        run.return_value.stdout = f"{COMMIT}\trefs/heads/other\n"
        with self.assertRaises(SyncBlocked):
            resolve_main()


if __name__ == "__main__":
    unittest.main()
