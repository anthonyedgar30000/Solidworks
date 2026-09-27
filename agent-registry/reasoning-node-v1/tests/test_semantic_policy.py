import unittest

from semantic_policy import (
    SemanticPolicyError,
    supported_bucket_claim_pairs,
    supported_hypothesis_anchor_pairs,
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


def candidate_hypothesis(
    *,
    statement="Hypothesis: a capture carrier may own the unresolved closure kinematics.",
    hypothesis_class="CLOSURE_KINEMATICS",
    evidence_status="UNTESTED",
    investigation_status="ELIGIBLE",
    anchor_buckets=None,
    anchor_claims=None,
):
    return {
        "statement": statement,
        "prior": "COMMON",
        "hypothesis_class": hypothesis_class,
        "evidence_status": evidence_status,
        "investigation_status": investigation_status,
        "anchor_buckets": (
            ["KINEMATIC_STATE_UNRESOLVED"]
            if anchor_buckets is None
            else anchor_buckets
        ),
        "anchor_claims": (
            ["Capture kinematic ownership is unresolved."]
            if anchor_claims is None
            else anchor_claims
        ),
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
                task="investigation_planning",
                evidence=EVIDENCE,
                payload=payload(),
            )

        self.assertIn(
            "SEMANTIC_POLICY_NOT_IMPLEMENTED:investigation_planning",
            ctx.exception.violations,
        )


class HypothesisGenerationAdmissionTests(unittest.TestCase):

    def base_payload(self, **overrides):
        data = payload(
            buckets=["KINEMATIC_STATE_UNRESOLVED"],
            claims=[
                "Capture kinematic ownership is unresolved."
            ],
            hypotheses=[candidate_hypothesis()],
        )
        data.update(overrides)
        return data

    def test_admits_grounded_untested_hypothesis(self):
        validate_semantic_admission(
            task="hypothesis_generation",
            evidence=EVIDENCE,
            payload=self.base_payload(),
        )

    def test_admits_three_distinct_hypothesis_classes(self):
        validate_semantic_admission(
            task="hypothesis_generation",
            evidence=EVIDENCE,
            payload=self.base_payload(
                hypotheses=[
                    candidate_hypothesis(
                        statement="Hypothesis: a translating carrier may close the bottle against the rollers.",
                        hypothesis_class="CLOSURE_KINEMATICS",
                    ),
                    candidate_hypothesis(
                        statement="Hypothesis: a spring preload could maintain bottle capture force during variation.",
                        hypothesis_class="COMPLIANCE_PRELOAD",
                    ),
                    candidate_hypothesis(
                        statement="Hypothesis: a nested assembly might contain an external capture owner not represented at top level.",
                        hypothesis_class="SOURCE_BOUNDARY",
                    ),
                ],
            ),
        )

    def test_rejects_noncausal_hypothesis_bucket(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["INSUFFICIENT_EVIDENCE"],
                    claims=[
                        "No evidence supplied here establishes the complete operating motion sequence."
                    ],
                    hypotheses=[candidate_hypothesis(
                        anchor_buckets=["INSUFFICIENT_EVIDENCE"],
                        anchor_claims=[
                            "No evidence supplied here establishes the complete operating motion sequence."
                        ],
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_BUCKET_NOT_CAUSAL_ANCHOR:INSUFFICIENT_EVIDENCE",
            ctx.exception.violations,
        )

    def test_rejects_evidence_absence_claim_as_hypothesis_anchor(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=["KINEMATIC_STATE_UNRESOLVED"],
                    claims=[
                        "No evidence supplied here establishes the complete operating motion sequence."
                    ],
                    hypotheses=[candidate_hypothesis(
                        anchor_claims=[
                            "No evidence supplied here establishes the complete operating motion sequence."
                        ],
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_CLAIM_NOT_CAUSAL_ANCHOR:0",
            ctx.exception.violations,
        )

    def test_rejects_duplicate_hypothesis_bucket(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    ambiguity_buckets=[
                        "KINEMATIC_STATE_UNRESOLVED",
                        "KINEMATIC_STATE_UNRESOLVED",
                    ]
                ),
            )

        self.assertIn(
            "DUPLICATE_AMBIGUITY_BUCKET:1:KINEMATIC_STATE_UNRESOLVED",
            ctx.exception.violations,
        )

    def test_rejects_duplicate_hypothesis_class(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[
                        candidate_hypothesis(
                            statement="Hypothesis: a translating carrier may close the bottle against the rollers.",
                            hypothesis_class="CLOSURE_KINEMATICS",
                        ),
                        candidate_hypothesis(
                            statement="Hypothesis: a pivoting arm could close the bottle against the wrap belt.",
                            hypothesis_class="CLOSURE_KINEMATICS",
                        ),
                    ],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_CLASS_DUPLICATE:1:CLOSURE_KINEMATICS",
            ctx.exception.violations,
        )

    def test_rejects_class_not_supported_by_statement(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        statement="Hypothesis: a pneumatic actuator may close the capture carrier.",
                        hypothesis_class="COMPLIANCE_PRELOAD",
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_CLASS_UNSUPPORTED:0:COMPLIANCE_PRELOAD",
            ctx.exception.violations,
        )

    def test_rejects_epistemic_gap_as_mechanism(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        statement="Hypothesis: sensor timing may be wrong because missing data prevents establishing the sequence.",
                        hypothesis_class="SEQUENCE_CONTROL",
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_EPISTEMIC_GAP_IS_NOT_MECHANISM:0",
            ctx.exception.violations,
        )

    def test_rejects_near_duplicate_hypotheses(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[
                        candidate_hypothesis(
                            statement="Hypothesis: a capture carrier may close the bottle against the rollers during labeling.",
                            hypothesis_class="CLOSURE_KINEMATICS",
                        ),
                        candidate_hypothesis(
                            statement="Hypothesis: a capture carrier guide could close the bottle against the rollers during labeling.",
                            hypothesis_class="OTHER_EXPLICIT_MECHANISM",
                        ),
                    ],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_NEAR_DUPLICATE:0:1",
            ctx.exception.violations,
        )

    def test_rejects_missing_hypothesis(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(hypotheses=[]),
            )

        self.assertIn(
            "HYPOTHESIS_REQUIRED",
            ctx.exception.violations,
        )

    def test_rejects_status_promotion(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        evidence_status="SUPPORTED",
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_EVIDENCE_STATUS_MUST_BE_UNTESTED:0",
            ctx.exception.violations,
        )

    def test_rejects_noneligible_investigation_state(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        investigation_status="ACTIVE",
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_INVESTIGATION_STATUS_MUST_BE_ELIGIBLE:0",
            ctx.exception.violations,
        )

    def test_rejects_missing_tentative_language(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        statement="Hypothesis: a missing capture constraint explains the unresolved kinematic owner.",
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_TENTATIVE_LANGUAGE_REQUIRED:0",
            ctx.exception.violations,
        )

    def test_rejects_forbidden_assertion_language(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        statement="Hypothesis: a verified capture constraint may explain the unresolved kinematic owner.",
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_FORBIDDEN_ASSERTION:0",
            ctx.exception.violations,
        )

    def test_rejects_unselected_anchor_claim(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        anchor_claims=[
                            "No evidence supplied here establishes the complete operating motion sequence."
                        ],
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_ANCHOR_CLAIM_NOT_SELECTED:0:0",
            ctx.exception.violations,
        )

    def test_rejects_anchor_bucket_not_supported_by_anchor_claim(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=payload(
                    buckets=[
                        "KINEMATIC_STATE_UNRESOLVED",
                        "INSUFFICIENT_EVIDENCE",
                    ],
                    claims=[
                        "Capture kinematic ownership is unresolved.",
                        "No evidence supplied here establishes the complete operating motion sequence.",
                    ],
                    hypotheses=[candidate_hypothesis(
                        anchor_buckets=["INSUFFICIENT_EVIDENCE"],
                        anchor_claims=[
                            "Capture kinematic ownership is unresolved."
                        ],
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_ANCHOR_BUCKET_UNSUPPORTED:0:0",
            ctx.exception.violations,
        )

    def test_rejects_more_than_three_hypotheses(self):
        hypotheses = [
            candidate_hypothesis(
                statement=f"Hypothesis: candidate mechanism {index} may explain the unresolved kinematic owner."
            )
            for index in range(4)
        ]

        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(hypotheses=hypotheses),
            )

        self.assertIn(
            "HYPOTHESIS_COUNT_EXCEEDED",
            ctx.exception.violations,
        )

    def test_rejects_missing_anchor_bucket(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        anchor_buckets=[],
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_ANCHOR_BUCKET_REQUIRED:0",
            ctx.exception.violations,
        )

    def test_rejects_missing_anchor_claim(self):
        with self.assertRaises(SemanticPolicyError) as ctx:
            validate_semantic_admission(
                task="hypothesis_generation",
                evidence=EVIDENCE,
                payload=self.base_payload(
                    hypotheses=[candidate_hypothesis(
                        anchor_claims=[],
                    )],
                ),
            )

        self.assertIn(
            "HYPOTHESIS_ANCHOR_CLAIM_REQUIRED:0",
            ctx.exception.violations,
        )


class SupportedPairCatalogTests(unittest.TestCase):

    def test_hypothesis_anchor_catalog_excludes_evidence_absence_claims(self):
        self.assertEqual(
            supported_hypothesis_anchor_pairs(EVIDENCE),
            [{
                "bucket": "KINEMATIC_STATE_UNRESOLVED",
                "claim": "Capture kinematic ownership is unresolved.",
            }],
        )

    def test_catalog_contains_only_deterministically_supported_pairs(self):
        self.assertEqual(
            supported_bucket_claim_pairs(EVIDENCE),
            [
                {
                    "bucket": "KINEMATIC_STATE_UNRESOLVED",
                    "claim": "Capture kinematic ownership is unresolved.",
                },
                {
                    "bucket": "KINEMATIC_STATE_UNRESOLVED",
                    "claim": "No evidence supplied here establishes the complete operating motion sequence.",
                },
                {
                    "bucket": "INSUFFICIENT_EVIDENCE",
                    "claim": "No evidence supplied here establishes the complete operating motion sequence.",
                },
            ],
        )

    def test_not_granted_is_not_cataloged_as_acceptance_blocked(self):
        pairs = supported_bucket_claim_pairs(EVIDENCE)
        buckets = [pair["bucket"] for pair in pairs]

        self.assertNotIn(
            "MECHANICAL_ACCEPTANCE_BLOCKED",
            buckets,
        )

    def test_explicit_blocked_state_is_cataloged(self):
        evidence = """
SOURCE STATE:
- Mechanical acceptance is blocked pending deterministic clearance verification.
"""

        self.assertEqual(
            supported_bucket_claim_pairs(evidence),
            [{
                "bucket": "MECHANICAL_ACCEPTANCE_BLOCKED",
                "claim": "Mechanical acceptance is blocked pending deterministic clearance verification.",
            }],
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
