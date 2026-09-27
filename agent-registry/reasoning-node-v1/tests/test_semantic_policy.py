import unittest

from semantic_policy import (
    SemanticPolicyError,
    validate_semantic_admission,
)


EVIDENCE = """
SOURCE STATE:
- System is the CADGrounded v42 bottle-labeling benchmark.
- A static candidate operating pose exists.
- Product handling includes a driven wrap belt and two support rollers.
- Static geometry must not be assumed to represent every operating state.
- Capture kinematic ownership is unresolved.
- Mechanical acceptance has not been granted.
- No evidence supplied here establishes the complete operating motion sequence.
"""


def payload(
    *,
    buckets=None,
    claims=None,
    inferences=None,
    hypotheses=None,
    next_tests=None,
):
    return {
        "ambiguity_buckets": buckets or [],
        "claims_used": claims or [],
        "inferences": inferences or [],
        "hypotheses": hypotheses or [],
        "next_tests": next_tests or [],
        "notes": [],
    }


class AmbiguityClassificationAdmissionTests(unittest.TestCase):

    def test_admits_grounded_kinematic_unresolved(self):
        validate_semantic_admission(
            task="ambiguity_classification",
            evidence=EVIDENCE,
            payload=payload(
                buckets=["KINEMATIC_STATE_UNRESOLVED"],
                claims=[
                    "Capture kinematic ownership is unresolved."
                ],
            ),
        )

    def test_rejects_unsupported_geometry_bucket(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="ambiguity_classification",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["GEOMETRY_UNRESOLVED"],
                    claims=[
                        "Static geometry must not be assumed to represent every operating state."
                    ],
                ),
            )

        self.assertIn(
            "UNSUPPORTED_BUCKET:GEOMETRY_UNRESOLVED",
            ctx.exception.violations,
        )

    def test_rejects_paraphrased_claim(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="ambiguity_classification",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["KINEMATIC_STATE_UNRESOLVED"],
                    claims=[
                        "The bottle capture mechanism has unresolved kinematics."
                    ],
                ),
            )

        self.assertIn(
            "UNGROUNDED_CLAIM:0",
            ctx.exception.violations,
        )

    def test_rejects_empty_claims(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="ambiguity_classification",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["KINEMATIC_STATE_UNRESOLVED"],
                ),
            )

        self.assertIn(
            "CLAIMS_USED_REQUIRED",
            ctx.exception.violations,
        )

    def test_rejects_inference_leakage(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="ambiguity_classification",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["KINEMATIC_STATE_UNRESOLVED"],
                    claims=[
                        "Capture kinematic ownership is unresolved."
                    ],
                    inferences=["A mechanism may be missing."],
                ),
            )

        self.assertIn(
            "CLASSIFICATION_INFERENCES_NOT_ALLOWED",
            ctx.exception.violations,
        )

    def test_rejects_hypothesis_leakage(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="ambiguity_classification",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["KINEMATIC_STATE_UNRESOLVED"],
                    claims=[
                        "Capture kinematic ownership is unresolved."
                    ],
                    hypotheses=[{
                        "statement": "A mechanism may be missing.",
                        "prior": "COMMON",
                        "evidence_status": "UNTESTED",
                        "investigation_status": "ELIGIBLE",
                    }],
                ),
            )

        self.assertIn(
            "CLASSIFICATION_HYPOTHESES_NOT_ALLOWED",
            ctx.exception.violations,
        )

    def test_rejects_next_test_leakage(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="ambiguity_classification",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["KINEMATIC_STATE_UNRESOLVED"],
                    claims=[
                        "Capture kinematic ownership is unresolved."
                    ],
                    next_tests=[{
                        "test": "Inspect motion.",
                        "diagnostic_value": "unknown",
                        "required_authority": "CAD_READ_REQUIRED",
                    }],
                ),
            )

        self.assertIn(
            "CLASSIFICATION_NEXT_TESTS_NOT_ALLOWED",
            ctx.exception.violations,
        )

    def test_rejects_unimplemented_task(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=payload(),
            )

        self.assertIn(
            "SEMANTIC_POLICY_NOT_IMPLEMENTED:hypothesis_generation",
            ctx.exception.violations,
        )



class MechanicalAcceptanceSemanticsTests(unittest.TestCase):

    def test_not_granted_does_not_mean_blocked(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="ambiguity_classification",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["MECHANICAL_ACCEPTANCE_BLOCKED"],
                    claims=[
                        "Mechanical acceptance has not been granted."
                    ],
                ),
            )

        self.assertIn(
            "UNSUPPORTED_BUCKET:MECHANICAL_ACCEPTANCE_BLOCKED",
            ctx.exception.violations,
        )

    def test_explicit_blocked_state_supports_blocked_bucket(self):
        evidence = """
SOURCE STATE:
- Mechanical acceptance is blocked pending deterministic clearance verification.
"""

        validate_semantic_admission(
            task="ambiguity_classification",
            evidence=evidence,
            payload=payload(
                buckets=["MECHANICAL_ACCEPTANCE_BLOCKED"],
                claims=[
                    "Mechanical acceptance is blocked pending deterministic clearance verification."
                ],
            ),
        )


if __name__ == "__main__":
    unittest.main()
