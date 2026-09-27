import unittest
from pathlib import Path

from frontier_binding import (
    FrontierBindingError,
    bind_hypotheses,
    frontier_snapshot_metadata,
    load_current_frontier,
    render_frontier_catalog,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def hypothesis(statement, hypothesis_class):
    return {
        "statement": statement,
        "prior": "COMMON",
        "hypothesis_class": hypothesis_class,
        "evidence_status": "UNTESTED",
        "investigation_status": "ELIGIBLE",
        "anchor_buckets": ["KINEMATIC_STATE_UNRESOLVED"],
        "anchor_claims": ["Capture kinematic ownership is unresolved."],
    }


def payload(*hypotheses):
    return {"hypotheses": list(hypotheses)}
class CurrentFrontierLoadTests(unittest.TestCase):

    def setUp(self):
        self.snapshot = load_current_frontier(REPO_ROOT)

    def test_binds_exact_current_plan_architecture(self):
        metadata = frontier_snapshot_metadata(self.snapshot)

        self.assertEqual(metadata["current_plan_id"], "PLAN-0010")
        self.assertEqual(
            metadata["current_architecture_id"],
            "IXOR_FUNCTION_FIRST_BOTTLE_HANDLING_REFERENCE",
        )
        self.assertEqual(metadata["hypothesis_count"], 15)
        self.assertEqual(
            metadata["frontier_sha256"],
            "9f5fdbe87ae5b9e652fd0d7bda0c18ee8c3fb6ab39e178b7684e8d1c325aa033",
        )

    def test_catalog_preserves_disproven_and_dormant_memory(self):
        catalog = render_frontier_catalog(self.snapshot)

        self.assertIn(
            "H_STATIC_FIT_IS_SUFFICIENT_FOR_CAPTURE",
            catalog,
        )
        self.assertIn("evidence=DISPROVEN", catalog)
        self.assertIn("investigation=EXHAUSTED", catalog)
        self.assertIn("H_PNEUMATIC_CAPTURE_ACTUATOR", catalog)
        self.assertIn("investigation=DORMANT", catalog)
class FrontierBindingTests(unittest.TestCase):

    def setUp(self):
        self.snapshot = load_current_frontier(REPO_ROOT)

    def bind_one(self, statement, hypothesis_class):
        return bind_hypotheses(
            payload(hypothesis(statement, hypothesis_class)),
            self.snapshot,
        )[0]

    def test_generic_closure_reuses_existing_owner(self):
        binding = self.bind_one(
            "Hypothesis: a capture carrier may own bottle closure.",
            "CLOSURE_KINEMATICS",
        )

        self.assertEqual(
            binding["frontier_hypothesis_id"],
            "H_CAPTURE_CLOSURE_OWNER",
        )
        self.assertEqual(
            binding["binding_disposition"],
            "KNOWN_ACTIVE",
        )
        self.assertEqual(
            binding["frontier_action"],
            "REUSE_EXISTING_ACTIVE",
        )

    def test_moving_wrap_belt_reuses_specific_existing_hypothesis(self):
        binding = self.bind_one(
            "Hypothesis: The driven wrap-belt assembly may translate, pivot, or otherwise close to establish bottle capture against the support rollers.",
            "CLOSURE_KINEMATICS",
        )
        self.assertEqual(
            binding["frontier_hypothesis_id"],
            "H_MOVING_WRAP_BELT_ASSEMBLY",
        )
        self.assertEqual(
            binding["binding_disposition"],
            "KNOWN_ELIGIBLE",
        )

    def test_pneumatic_hypothesis_preserves_dormant_weakened_state(self):
        binding = self.bind_one(
            "Hypothesis: a pneumatic cylinder may provide capture actuation.",
            "ACTUATION_DRIVE",
        )

        self.assertEqual(
            binding["frontier_hypothesis_id"],
            "H_PNEUMATIC_CAPTURE_ACTUATOR",
        )
        self.assertEqual(
            binding["frontier_evidence_state"],
            "WEAKENED",
        )
        self.assertEqual(
            binding["binding_disposition"],
            "KNOWN_DORMANT",
        )
        self.assertEqual(
            binding["frontier_action"],
            "PRESERVE_DORMANT_STATE",
        )

    def test_source_boundary_reuses_dormant_existing_hypothesis(self):
        binding = self.bind_one(
            "Hypothesis: a nested assembly may contain the capture mechanism.",
            "SOURCE_BOUNDARY",
        )
        self.assertEqual(
            binding["frontier_hypothesis_id"],
            "H_UNBOUND_NESTED_OR_EXTERNAL_CAPTURE_MECHANISM",
        )
        self.assertEqual(
            binding["binding_disposition"],
            "KNOWN_DORMANT",
        )

    def test_novel_sequence_control_is_held_while_common_frontier_open(self):
        binding = self.bind_one(
            "Hypothesis: sensor timing may control bottle release sequencing.",
            "SEQUENCE_CONTROL",
        )

        self.assertTrue(binding["novel"])
        self.assertEqual(
            binding["binding_disposition"],
            "NOVEL_HELD_COMMON_FRONTIER_OPEN",
        )
        self.assertEqual(
            binding["frontier_action"],
            "HOLD_FOR_REVIEW",
        )
        self.assertIn(
            "H_CAPTURE_CLOSURE_OWNER",
            binding["escalation_blockers"],
        )
        self.assertIn(
            "H_TRANSLATING_ROLLER_CARRIER_OR_SLIDE",
            binding["escalation_blockers"],
        )
        self.assertNotIn(
            "H_FUNCTION_FIRST_CONTACT_SET",
            binding["escalation_blockers"],
        )

    def test_static_fit_sufficiency_is_suppressed_from_disproven_memory(self):
        with self.assertRaises(FrontierBindingError) as ctx:
            bind_hypotheses(
                payload(hypothesis(
                    "Hypothesis: a static fit pose may be sufficient to establish operational capture.",
                    "CLOSURE_KINEMATICS",
                )),
                self.snapshot,
            )

        self.assertIn(
            "FRONTIER_HYPOTHESIS_DISPROVEN:0:"
            "H_STATIC_FIT_IS_SUFFICIENT_FOR_CAPTURE",
            ctx.exception.violations,
        )
        self.assertEqual(
            ctx.exception.bindings[0]["frontier_action"],
            "SUPPRESS_DISPROVEN",
        )

    def test_side_wall_and_pinch_belt_bind_to_registered_dormant_hypotheses(self):
        bindings = bind_hypotheses(
            payload(
                hypothesis(
                    "Hypothesis: a moving side wall may advance and rotate the bottle.",
                    "ACTUATION_DRIVE",
                ),
                hypothesis(
                    "Hypothesis: a pinch-belt may constrain the bottle during wrap.",
                    "OTHER_EXPLICIT_MECHANISM",
                ),
            ),
            self.snapshot,
        )

        self.assertEqual(
            bindings[0]["frontier_hypothesis_id"],
            "H_MOVING_SIDE_WALL_OR_BELT_DRIVE",
        )
        self.assertEqual(
            bindings[1]["frontier_hypothesis_id"],
            "H_PINCH_BELT_OR_MULTIROLLER_CAPTURE",
        )
        self.assertEqual(
            bindings[0]["binding_disposition"],
            "KNOWN_DORMANT",
        )
        self.assertEqual(
            bindings[1]["binding_disposition"],
            "KNOWN_DORMANT",
        )


if __name__ == "__main__":
    unittest.main()
