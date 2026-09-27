import json
from pathlib import Path
import shutil
import tempfile
import unittest

from frontier_runner import INPUTS, PLAN, SCREEN, SOURCE_PROBE, run_once


REPO = Path(__file__).resolve().parents[2]


class FrontierRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.state = Path(self.temp.name) / "state"
        for name in INPUTS:
            destination = self.repo / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / name, destination)

    def change(self, path, modify):
        target = self.repo / path
        value = json.loads(target.read_text(encoding="utf-8-sig"))
        modify(value)
        target.write_text(json.dumps(value), encoding="utf-8")

    def test_new_snapshot_creates_one_immutable_proposal(self):
        first = run_once(self.repo, self.state)
        second = run_once(self.repo, self.state)
        self.assertEqual(first["status"], "SOURCE_ACQUISITION_REQUIRED")
        self.assertTrue(first["new"])
        self.assertFalse(second["new"])
        self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        receipt = json.loads(Path(first["receipt"]).read_text())
        self.assertEqual(receipt["execution_authority"], "NONE")
        self.assertFalse(receipt["mechanical_acceptance_granted"])
        self.assertEqual(len(list((self.state / "receipts").glob("*.json"))), 1)

    def test_new_valid_input_creates_new_receipt_without_rewriting_old(self):
        first = run_once(self.repo, self.state)
        old_bytes = Path(first["receipt"]).read_bytes()
        self.change(PLAN, lambda row: row.update(updated_at_utc="2026-09-27T16:00:00Z"))
        second = run_once(self.repo, self.state)
        self.assertTrue(second["new"])
        self.assertNotEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        self.assertEqual(Path(first["receipt"]).read_bytes(), old_bytes)

    def test_advanced_plan_fails_closed_without_new_receipt(self):
        self.change(PLAN, lambda row: row.update(current_plan_id="PLAN-0011"))
        result = run_once(self.repo, self.state)
        self.assertEqual(result, {"status": "BLOCKED", "reason": "FRONTIER_MOVED", "execution_authority": "NONE"})
        self.assertFalse(self.state.exists())

    def test_stale_probe_fails_closed(self):
        self.change(SOURCE_PROBE, lambda row: row["temporal_scope"].update(validity_state="STALE"))
        self.assertEqual(run_once(self.repo, self.state)["reason"], "PROBE_STALE")

    def test_mechanism_selection_fails_closed(self):
        self.change(SCREEN, lambda row: row["payload"]["result"].update(selection_status="SELECTED"))
        self.assertEqual(run_once(self.repo, self.state)["reason"], "SELECTION_STATE_CHANGED")

    def test_point_observation_cannot_be_promoted_to_interval(self):
        self.change(SOURCE_PROBE, lambda row: row["temporal_scope"].update(coverage="INTERVAL_WIDE"))
        self.assertEqual(run_once(self.repo, self.state)["reason"], "PROBE_SCOPE_CHANGED")

    def test_missing_source_fails_closed(self):
        (self.repo / SCREEN).unlink()
        self.assertEqual(run_once(self.repo, self.state)["status"], "BLOCKED")
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
