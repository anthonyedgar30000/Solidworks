#!/usr/bin/env python3
"""Phase 2 integrity tests for the CADRequest schema migration.

These tests verify that the canonical Domain Model v1 request schema is the
single source of truth for both Remote Queue v1 package copies, that checksum
manifests match repository-canonical LF-normalized text content across Windows
and Unix checkouts, and that the PowerShell runner has not been changed to
consume the schema at runtime.

No SOLIDWORKS access is required.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


AGENT_REGISTRY = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = AGENT_REGISTRY / "schemas" / "cad-read-request.v1.schema.json"
RUNNER_DIR = AGENT_REGISTRY / "remote-queue-runner-v1"
PACKAGE_DIR = AGENT_REGISTRY / "CADGrounded_RemoteQueue_v1"


def canonical_lf_bytes(path: Path) -> bytes:
    """Return repository-canonical text bytes independent of checkout EOL style."""
    raw = path.read_bytes()
    return raw.replace(b"\r\n", b"\n")


def sha256_canonical_text(path: Path) -> str:
    return hashlib.sha256(canonical_lf_bytes(path)).hexdigest()


def parse_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        digest, filename = line.split(None, 1)
        entries[filename.strip()] = digest
    return entries


class CADReadSchemaMigrationTests(unittest.TestCase):
    def test_packaged_schema_copies_are_byte_identical_to_canonical(self):
        canonical = CANONICAL_SCHEMA.read_bytes()
        self.assertEqual(
            (RUNNER_DIR / "cad-job.schema.json").read_bytes(),
            canonical,
        )
        self.assertEqual(
            (PACKAGE_DIR / "cad-job.schema.json").read_bytes(),
            canonical,
        )

    def test_both_manifests_pin_current_schema_bytes(self):
        expected = sha256_canonical_text(CANONICAL_SCHEMA)
        for directory in (RUNNER_DIR, PACKAGE_DIR):
            manifest = parse_manifest(directory / "SHA256SUMS.txt")
            self.assertIn("cad-job.schema.json", manifest)
            self.assertEqual(
                manifest["cad-job.schema.json"],
                expected,
                directory.name,
            )

    def test_runner_manifest_pins_repaired_runner(self):
        manifest = parse_manifest(RUNNER_DIR / "SHA256SUMS.txt")
        self.assertEqual(
            manifest["Invoke-CADRemoteQueue.ps1"],
            sha256_canonical_text(RUNNER_DIR / "Invoke-CADRemoteQueue.ps1"),
        )

    def test_runner_manifest_pins_expired_identity_regression(self):
        manifest = parse_manifest(RUNNER_DIR / "SHA256SUMS.txt")
        name = "Test-CADRemoteQueueExpiredJobIdentity.ps1"
        self.assertIn(name, manifest)
        self.assertEqual(
            manifest[name],
            sha256_canonical_text(RUNNER_DIR / name),
        )

    def test_phase2_does_not_make_runner_schema_driven(self):
        runner_text = (RUNNER_DIR / "Invoke-CADRemoteQueue.ps1").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("cad-job.schema.json", runner_text)
        self.assertNotIn("cad-read-request.v1.schema.json", runner_text)

    def test_read_only_authority_remains_literal_in_runner(self):
        runner_text = (RUNNER_DIR / "Invoke-CADRemoteQueue.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("write_authority must be exactly 'NONE'.", runner_text)
        self.assertIn("runner_write_authority = 'NONE'", runner_text)


if __name__ == "__main__":
    unittest.main()
