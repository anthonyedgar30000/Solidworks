import copy
import json
import unittest
from pathlib import Path

from diagnostic_binding import (
    DiagnosticBindingError,
    bind_current_diagnostic,
    diagnostic_snapshot_metadata,
    render_diagnostic_state,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
CURRENT_PLAN_PATH = REPO_ROOT / "agent-registry/planning/CURRENT_PLAN.json"


def current_plan():
    return json.loads(CURRENT_PLAN_PATH.read_text(encoding="utf-8-sig"))


class DiagnosticBindingTests(unittest.TestCase):

    def test_current_executed_sweep_attempt_is_bound_exactly(self):
        diagnostic = bind_current_diagnostic(
            REPO_ROOT,
            current_plan(),
        )

        self.assertIsNotNone(diagnostic)
        self.assertEqual(diagnostic["plan_id"], "PLAN-0011")
        self.assertEqual(diagnostic["step_id"], "P0011.4")
        self.assertEqual(
            diagnostic["test_id"],
            "TEST_POP_V43_PRISM_DUAL_PIVOT_EXACT_HYPOTHETICAL_SWEEP",
        )
        self.assertEqual(
            diagnostic["diagnostic_state"],
            "EXECUTED_RESULT_REVIEW_REQUIRED",
        )
        self.assertEqual(
            diagnostic["next_action_mode"],
            "REVIEW_DIAGNOSTIC_RESULT",
        )
        self.assertEqual(
            diagnostic["mechanical_effect"],
            "NO_AUTOMATIC_HYPOTHESIS_STATE_CHANGE",
        )
        self.assertEqual(
            diagnostic["ambiguity_buckets"],
            [],
        )
        self.assertEqual(
            diagnostic["attempt_id"],
            "ATTEMPT.PLAN-0011.V43_DUAL_PIVOT_EXACT_SWEEP.20260927T231617920Z",
        )
        self.assertEqual(
            diagnostic["execution_result"],
            "TERMINATED_FAIL_FAST_PHYSICAL_INTERFERENCE_DETECTED",
        )
        self.assertEqual(
            diagnostic["document_title_exact"],
            "IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE",
        )
        self.assertEqual(
            diagnostic["configuration_reference"],
            "V43_WRAP",
        )
        self.assertEqual(diagnostic["cad_write_authority"], "NONE")
        self.assertEqual(diagnostic["state_mutation_authority"], "NONE")
        self.assertEqual(
            diagnostic["mechanical_acceptance_authority"],
            "NONE",
        )

    def test_metadata_preserves_exact_provenance_without_claim_promotion(self):
        diagnostic = bind_current_diagnostic(
            REPO_ROOT,
            current_plan(),
        )
        metadata = diagnostic_snapshot_metadata(diagnostic)

        self.assertEqual(len(metadata["preflight_sha256"]), 64)
        self.assertEqual(len(metadata["attempt_sha256"]), 64)
        self.assertEqual(
            metadata["mechanical_effect"],
            "NO_AUTOMATIC_HYPOTHESIS_STATE_CHANGE",
        )
        self.assertEqual(metadata["state_mutation_authority"], "NONE")
        self.assertEqual(metadata["cad_write_authority"], "NONE")
        self.assertEqual(
            metadata["mechanical_acceptance_authority"],
            "NONE",
        )
    def test_render_preserves_blocked_read_as_nonmechanical(self):
        plan = copy.deepcopy(current_plan())
        plan["current_verification_attempt_id"] = (
            "ATTEMPT.PLAN-0011.V43_DUAL_PIVOT_EXACT_SWEEP.20260927T222600Z"
        )
        plan["current_verification_attempt_path"] = (
            "agent-registry/reasoning/runtime/"
            "v43-dual-pivot-exact-sweep-attempt-20260927T222600Z.json"
        )
        diagnostic = bind_current_diagnostic(
            REPO_ROOT,
            plan,
        )
        rendered = render_diagnostic_state(diagnostic)

        self.assertIn(
            "BLOCKED_FRESH_CAD_REBIND_REQUIRED",
            rendered,
        )
        self.assertIn(
            "REBIND_LIVE_CAD_BEFORE_DIAGNOSTIC",
            rendered,
        )
        self.assertIn("STALE_STATE,CAD_READ_REQUIRED", rendered)
        self.assertIn(
            "blocked evidence-acquisition attempt is not negative mechanical evidence",
            rendered,
        )
        self.assertIn(
            "No hypothesis evidence/investigation state is changed automatically",
            rendered,
        )

    def test_attempt_identity_mismatch_fails_closed(self):
        plan = copy.deepcopy(current_plan())
        plan["current_verification_attempt_id"] = "WRONG_ATTEMPT"

        with self.assertRaises(DiagnosticBindingError) as ctx:
            bind_current_diagnostic(REPO_ROOT, plan)

        self.assertIn(
            "DIAGNOSTIC_ATTEMPT_ID_MISMATCH",
            ctx.exception.violations,
        )

    def test_preflight_path_traversal_fails_closed(self):
        plan = copy.deepcopy(current_plan())
        plan["current_candidate_preflight_path"] = "../outside.json"

        with self.assertRaises(DiagnosticBindingError) as ctx:
            bind_current_diagnostic(REPO_ROOT, plan)

        self.assertIn(
            "CURRENT_CANDIDATE_PREFLIGHT_PATH_TRAVERSAL_NOT_ALLOWED",
            ctx.exception.violations,
        )

    def test_missing_attempt_pointer_pair_fails_closed(self):
        plan = copy.deepcopy(current_plan())
        plan["current_verification_attempt_path"] = None

        with self.assertRaises(DiagnosticBindingError) as ctx:
            bind_current_diagnostic(REPO_ROOT, plan)

        self.assertIn(
            "DIAGNOSTIC_ATTEMPT_POINTER_INCOMPLETE",
            ctx.exception.violations,
        )


if __name__ == "__main__":
    unittest.main()
