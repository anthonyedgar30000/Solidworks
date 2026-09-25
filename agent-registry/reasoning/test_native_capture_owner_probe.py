#!/usr/bin/env python3
"""Static safety contracts for the local v42 capture-owner mate probe.

These tests do not claim that the C# worker has been built or executed on a
SOLIDWORKS host. They make the source boundary reviewable: the proposed probe
must remain a local-only candidate, preserve the Remote Queue partition, and
contain the pre/post comparison required before any resulting observation is
admitted as evidence.
"""

import json
import unittest
from pathlib import Path


REGISTRY = Path(__file__).resolve().parents[1]
WORKER = REGISTRY / "workers" / "CadGrounded.SolidWorksWorker"
PROGRAM = WORKER / "Program.cs"
VERIFY_SCRIPT = WORKER / "Verify-QueryMates-V42.ps1"
FILE_EVIDENCE = WORKER / "FileEvidence.ps1"
FILE_EVIDENCE_TEST = WORKER / "Test-FileEvidence.ps1"
QUEUE_CONFIGS = (
    REGISTRY / "CADGrounded_RemoteQueue_v1" / "queue-config.json",
    REGISTRY / "remote-queue-runner-v1" / "queue-config.json",
)


class NativeCaptureOwnerProbeContractTests(unittest.TestCase):
    def test_query_mates_remains_local_only_and_outside_remote_queue_allowlists(self):
        program = PROGRAM.read_text(encoding="utf-8")
        self.assertIn('"sw.query_mates"', program)
        self.assertIn('"sw.classify_contact_pair"', program)

        for config_path in QUEUE_CONFIGS:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(
                config["allowed_commands"],
                ["sw.status", "sw.query_components", "sw.closest_distance_pair"],
            )
            self.assertNotIn("sw.query_mates", config["allowed_commands"])

    def test_native_observation_exposes_only_parentage_and_constraint_inputs(self):
        program = PROGRAM.read_text(encoding="utf-8")
        for expected in (
            "parent_chain = parentNames.ToArray()",
            "parent_chain_paths = parentPaths.ToArray()",
            "parentage_errors = parentageErrors.ToArray()",
            "referenced_configuration = Safe(() => c.ReferencedConfiguration)",
            "fixed_component = SafeBool(() => c.IsFixed())",
            "active_configuration = Safe(() => _doc.ConfigurationManager.ActiveConfiguration.Name)",
            "save_flag = Safe(() => (object)_doc.GetSaveFlag())",
            "model_mutation = false",
            'write_authority = "NONE"',
        ):
            self.assertIn(expected, program)

    def test_shared_file_evidence_is_local_read_only_and_regression_tested(self):
        verifier = VERIFY_SCRIPT.read_text(encoding="utf-8")
        evidence = FILE_EVIDENCE.read_text(encoding="utf-8")
        regression = FILE_EVIDENCE_TEST.read_text(encoding="utf-8")

        self.assertIn(". (Join-Path $WorkerRoot 'FileEvidence.ps1')", verifier)
        self.assertNotIn("Get-FileHash", verifier)
        self.assertIn("[System.IO.FileAccess]::Read", evidence)
        self.assertIn("[System.IO.FileShare]::ReadWrite", evidence)
        self.assertNotIn("[System.IO.FileAccess]::Write", evidence)
        self.assertIn("file observation rejected", evidence)
        self.assertIn("Assembly file changed while SHA-256 was being computed", evidence)
        self.assertIn("Start-Job", regression)
        self.assertIn("-ShareName 'ReadWrite'", regression)
        self.assertIn("-ShareName 'None'", regression)

    def test_verification_script_checks_before_after_state_and_declares_limitations(self):
        script = VERIFY_SCRIPT.read_text(encoding="utf-8")
        for expected in (
            "$statusBefore",
            "$statusAfter",
            "$documentStateBefore",
            "$documentStateAfter",
            "$targetStateBefore",
            "$targetStateAfter",
            "$fileBefore",
            "$fileAfter",
            "sw.query_mates did not report write_authority NONE",
            "sw.query_mates did not report model_mutation=false",
            "remote_queue_authorized = $false",
            "does_not_establish",
            "mechanical acceptance",
        ):
            self.assertIn(expected, script)

        for target in (
            "FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1",
            "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1",
            "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2",
        ):
            self.assertIn(target, script)


if __name__ == "__main__":
    unittest.main()
