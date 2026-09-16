#!/usr/bin/env python3
import copy
import unittest

from identity_bindings import bind_roles, IdentityBindingError


class IdentityBindingTests(unittest.TestCase):
    def setUp(self):
        self.tx = {
            "admission_status": "ADMITTED_OBSERVATION",
            "mechanical_acceptance_granted": False,
            "document": {"title": "IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE"},
            "raw_observation": {"sha256": "abc", "job_id": "job-1", "recorded_at": "now"},
            "components": [
                {"name2": "6130460_03_AR60_NATIVE_PORTABLE_V18-2", "path": "ar60.SLDPRT"},
                {"name2": "6130649_01_Carriage_Schlitten_AR_NATIVE_PORTABLE_V20-1", "path": "carriage.SLDPRT"},
            ],
        }
        self.bindings = {
            "expected_document": "IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE",
            "roles": {
                "AR60_ROLLER": "6130460_03_AR60_NATIVE_PORTABLE_V18-2",
                "AR60_CARRIAGE": "6130649_01_Carriage_Schlitten_AR_NATIVE_PORTABLE_V20-1",
            },
        }

    def test_exact_unique_bindings_resolve(self):
        result = bind_roles(self.tx, self.bindings)
        self.assertEqual(result["resolved_roles"]["AR60_ROLLER"]["identity_status"], "VERIFIED_FROM_SOLIDWORKS")
        self.assertFalse(result["mechanical_acceptance_granted"])

    def test_missing_name2_is_rejected(self):
        b = copy.deepcopy(self.bindings)
        b["roles"]["AR60_ROLLER"] = "wrong"
        with self.assertRaises(IdentityBindingError):
            bind_roles(self.tx, b)

    def test_duplicate_exact_name2_is_rejected(self):
        tx = copy.deepcopy(self.tx)
        tx["components"].append(copy.deepcopy(tx["components"][0]))
        with self.assertRaises(IdentityBindingError):
            bind_roles(tx, self.bindings)

    def test_wrong_document_is_rejected(self):
        tx = copy.deepcopy(self.tx)
        tx["document"]["title"] = "OTHER"
        with self.assertRaises(IdentityBindingError):
            bind_roles(tx, self.bindings)


if __name__ == "__main__":
    unittest.main()
