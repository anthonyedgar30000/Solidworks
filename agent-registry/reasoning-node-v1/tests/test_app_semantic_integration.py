import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import app


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


def advisory(
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


class FakeOllamaResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return {"response": json.dumps(self.payload)}


class SemanticIntegrationTests(unittest.TestCase):

    @patch("app.append_log")
    @patch("app.requests.post")
    def test_grounded_classification_is_semantically_admitted(
        self,
        post,
        append_log,
    ):
        post.return_value = FakeOllamaResponse(
            advisory(
                buckets=["KINEMATIC_STATE_UNRESOLVED"],
                claims=[
                    "Capture kinematic ownership is unresolved."
                ],
            )
        )

        result = app.reason(
            app.ReasonRequest(
                task="ambiguity_classification",
                evidence=EVIDENCE,
            )
        )

        self.assertTrue(result.schema_validated)
        self.assertTrue(result.semantic_admitted)
        self.assertEqual(result.cad_write_authority, "NONE")
        self.assertEqual(
            result.mechanical_acceptance_authority,
            "NONE",
        )
        self.assertEqual(
            result.evidence_verification_authority,
            "NONE",
        )

        record = append_log.call_args.args[0]

        self.assertEqual(
            record["status"],
            "SEMANTICALLY_ADMITTED",
        )
        self.assertTrue(record["schema_validated"])
        self.assertTrue(record["semantic_admitted"])

        expected_payload = advisory(
            buckets=["KINEMATIC_STATE_UNRESOLVED"],
            claims=[
                "Capture kinematic ownership is unresolved."
            ],
        )
        expected_raw = json.dumps(expected_payload)

        self.assertEqual(
            record["proposal_raw"],
            expected_raw,
        )
        self.assertEqual(
            record["proposal_raw_sha256"],
            app.sha256_text(expected_raw),
        )
        self.assertEqual(
            record["proposal_validated"],
            expected_payload,
        )

        request_json = post.call_args.kwargs["json"]
        prompt = request_json["prompt"]

        self.assertEqual(
            request_json["format"],
            app.AdvisoryPayload.model_json_schema(),
        )
        self.assertEqual(
            request_json["options"],
            {"temperature": 0},
        )
        self.assertIn(
            "AMBIGUITY CLASSIFICATION CONTRACT",
            prompt,
        )
        self.assertIn(
            "hypotheses MUST be []",
            prompt,
        )
        self.assertIn(
            "DETERMINISTICALLY ALLOWED BUCKET/CLAIM PAIRS",
            prompt,
        )
        self.assertIn(
            "bucket: KINEMATIC_STATE_UNRESOLVED",
            prompt,
        )
        self.assertIn(
            "claim: Capture kinematic ownership is unresolved.",
            prompt,
        )

        catalog = prompt.split(
            "DETERMINISTIC GROUNDING CATALOG:",
            1,
        )[1].split(
            "Return only the required JSON object.",
            1,
        )[0]

        self.assertNotIn(
            "bucket: GEOMETRY_UNRESOLVED",
            catalog,
        )
        self.assertNotIn(
            "bucket: MECHANICAL_ACCEPTANCE_BLOCKED",
            catalog,
        )

    @patch("app.append_log")
    @patch("app.requests.post")
    def test_unsupported_bucket_is_rejected_after_schema_validation(
        self,
        post,
        append_log,
    ):
        post.return_value = FakeOllamaResponse(
            advisory(
                buckets=["GEOMETRY_UNRESOLVED"],
                claims=[
                    "Static geometry must not be assumed to represent every operating state."
                ],
            )
        )

        with self.assertRaises(HTTPException) as ctx:
            app.reason(
                app.ReasonRequest(
                    task="ambiguity_classification",
                    evidence=EVIDENCE,
                )
            )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(
            ctx.exception.detail["status"],
            "REJECTED_SEMANTIC_POLICY",
        )
        self.assertIn(
            "UNSUPPORTED_BUCKET:GEOMETRY_UNRESOLVED",
            ctx.exception.detail["violations"],
        )

        record = append_log.call_args.args[0]

        self.assertEqual(
            record["status"],
            "REJECTED_SEMANTIC_POLICY",
        )
        self.assertTrue(record["schema_validated"])
        self.assertFalse(record["semantic_admitted"])

        expected_payload = advisory(
            buckets=["GEOMETRY_UNRESOLVED"],
            claims=[
                "Static geometry must not be assumed to represent every operating state."
            ],
        )
        expected_raw = json.dumps(expected_payload)

        self.assertEqual(
            record["proposal_raw"],
            expected_raw,
        )
        self.assertEqual(
            record["proposal_raw_sha256"],
            app.sha256_text(expected_raw),
        )
        self.assertEqual(
            record["proposal_validated"],
            expected_payload,
        )

    @patch("app.append_log")
    @patch("app.requests.post")
    def test_grounded_hypothesis_generation_is_semantically_admitted(
        self,
        post,
        append_log,
    ):
        payload = advisory(
            buckets=["KINEMATIC_STATE_UNRESOLVED"],
            claims=[
                "Capture kinematic ownership is unresolved."
            ],
            hypotheses=[candidate_hypothesis()],
        )
        post.return_value = FakeOllamaResponse(payload)

        result = app.reason(
            app.ReasonRequest(
                task="hypothesis_generation",
                evidence=EVIDENCE,
            )
        )

        self.assertTrue(result.schema_validated)
        self.assertTrue(result.semantic_admitted)
        self.assertFalse(result.semantic_repair_attempted)
        self.assertEqual(result.semantic_repair_count, 0)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(result.cad_write_authority, "NONE")
        self.assertEqual(
            result.mechanical_acceptance_authority,
            "NONE",
        )
        self.assertEqual(
            result.evidence_verification_authority,
            "NONE",
        )

        record = append_log.call_args.args[0]
        self.assertEqual(
            record["status"],
            "SEMANTICALLY_ADMITTED",
        )
        self.assertFalse(record["semantic_repair_attempted"])
        self.assertEqual(record["semantic_repair_count"], 0)
        self.assertEqual(
            record["proposal_validated"],
            payload,
        )

        prompt = post.call_args.kwargs["json"]["prompt"]
        self.assertEqual(
            result.result.hypotheses[0].hypothesis_class,
            "CLOSURE_KINEMATICS",
        )
        self.assertIn(
            "HYPOTHESIS GENERATION CONTRACT",
            prompt,
        )
        self.assertIn(
            "CLOSURE_KINEMATICS",
            prompt,
        )
        self.assertIn(
            "COMPLIANCE_PRELOAD",
            prompt,
        )
        self.assertIn(
            "SOURCE_BOUNDARY",
            prompt,
        )
        self.assertIn(
            "bucket: KINEMATIC_STATE_UNRESOLVED",
            prompt,
        )
        self.assertIn(
            "claim: Capture kinematic ownership is unresolved.",
            prompt,
        )

        catalog = prompt.split(
            "DETERMINISTIC GROUNDING CATALOG:",
            1,
        )[1].split(
            "Return only the required JSON object.",
            1,
        )[0]

        self.assertNotIn(
            "bucket: INSUFFICIENT_EVIDENCE",
            catalog,
        )
        self.assertNotIn(
            "No evidence supplied here establishes the complete operating motion sequence.",
            catalog,
        )

    @patch("app.append_log")
    @patch("app.requests.post")
    def test_hypothesis_generation_repairs_once_and_admits(
        self,
        post,
        append_log,
    ):
        initial_payload = advisory(
            buckets=["KINEMATIC_STATE_UNRESOLVED"],
            claims=[
                "Capture kinematic ownership is unresolved."
            ],
            hypotheses=[
                candidate_hypothesis(
                    statement="Hypothesis: a driven wrap belt may own capture closure.",
                    hypothesis_class="CLOSURE_KINEMATICS",
                ),
                candidate_hypothesis(
                    statement="Hypothesis: support rollers may translate to close capture.",
                    hypothesis_class="CLOSURE_KINEMATICS",
                ),
            ],
        )
        repaired_payload = advisory(
            buckets=["KINEMATIC_STATE_UNRESOLVED"],
            claims=[
                "Capture kinematic ownership is unresolved."
            ],
            hypotheses=[
                candidate_hypothesis(
                    statement="Hypothesis: a driven wrap belt may own capture closure.",
                    hypothesis_class="CLOSURE_KINEMATICS",
                )
            ],
        )
        post.side_effect = [
            FakeOllamaResponse(initial_payload),
            FakeOllamaResponse(repaired_payload),
        ]

        result = app.reason(
            app.ReasonRequest(
                task="hypothesis_generation",
                evidence=EVIDENCE,
            )
        )

        self.assertTrue(result.semantic_admitted)
        self.assertTrue(result.semantic_repair_attempted)
        self.assertEqual(result.semantic_repair_count, 1)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            result.result.model_dump(),
            repaired_payload,
        )

        record = append_log.call_args.args[0]
        self.assertEqual(
            record["status"],
            "SEMANTICALLY_ADMITTED_AFTER_REPAIR",
        )
        self.assertTrue(record["semantic_repair_attempted"])
        self.assertEqual(record["semantic_repair_count"], 1)
        self.assertEqual(
            record["proposal_validated"],
            repaired_payload,
        )
        self.assertEqual(
            record["semantic_repair"]["initial_proposal_validated"],
            initial_payload,
        )
        self.assertIn(
            "HYPOTHESIS_CLASS_DUPLICATE:1:CLOSURE_KINEMATICS",
            record["semantic_repair"]["initial_violations"],
        )
        self.assertEqual(
            record["semantic_repair"]["repair_proposal_validated"],
            repaired_payload,
        )
        self.assertEqual(
            record["semantic_repair"]["repair_violations"],
            [],
        )

        repair_prompt = post.call_args_list[1].kwargs["json"]["prompt"]
        self.assertIn(
            "ONE-PASS CORRECTION CONTRACT",
            repair_prompt,
        )
        self.assertIn(
            "HYPOTHESIS_CLASS_DUPLICATE:1:CLOSURE_KINEMATICS",
            repair_prompt,
        )

    @patch("app.append_log")
    @patch("app.requests.post")
    def test_hypothesis_generation_rejects_supported_status_promotion(
        self,
        post,
        append_log,
    ):
        rejected_payload = advisory(
            buckets=["KINEMATIC_STATE_UNRESOLVED"],
            claims=[
                "Capture kinematic ownership is unresolved."
            ],
            hypotheses=[
                candidate_hypothesis(
                    evidence_status="SUPPORTED",
                )
            ],
        )
        post.side_effect = [
            FakeOllamaResponse(rejected_payload),
            FakeOllamaResponse(rejected_payload),
        ]

        with self.assertRaises(HTTPException) as ctx:
            app.reason(
                app.ReasonRequest(
                    task="hypothesis_generation",
                    evidence=EVIDENCE,
                )
            )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(
            ctx.exception.detail["status"],
            "REJECTED_SEMANTIC_POLICY_AFTER_REPAIR",
        )
        self.assertIn(
            "HYPOTHESIS_EVIDENCE_STATUS_MUST_BE_UNTESTED:0",
            ctx.exception.detail["violations"],
        )
        self.assertEqual(post.call_count, 2)

        record = append_log.call_args.args[0]
        self.assertEqual(
            record["status"],
            "REJECTED_SEMANTIC_POLICY_AFTER_REPAIR",
        )
        self.assertTrue(record["schema_validated"])
        self.assertFalse(record["semantic_admitted"])
        self.assertTrue(record["semantic_repair_attempted"])
        self.assertEqual(record["semantic_repair_count"], 1)
        self.assertIn(
            "HYPOTHESIS_EVIDENCE_STATUS_MUST_BE_UNTESTED:0",
            record["semantic_repair"]["initial_violations"],
        )
        self.assertIn(
            "HYPOTHESIS_EVIDENCE_STATUS_MUST_BE_UNTESTED:0",
            record["semantic_repair"]["repair_violations"],
        )

    @patch("app.append_log")
    @patch("app.requests.post")
    def test_unimplemented_task_fails_closed(
        self,
        post,
        append_log,
    ):
        post.return_value = FakeOllamaResponse(advisory())

        with self.assertRaises(HTTPException) as ctx:
            app.reason(
                app.ReasonRequest(
                    task="investigation_planning",
                    evidence=EVIDENCE,
                )
            )

        self.assertEqual(
            ctx.exception.detail["status"],
            "REJECTED_SEMANTIC_POLICY",
        )
        self.assertIn(
            "SEMANTIC_POLICY_NOT_IMPLEMENTED:investigation_planning",
            ctx.exception.detail["violations"],
        )

        record = append_log.call_args.args[0]

        self.assertEqual(
            record["status"],
            "REJECTED_SEMANTIC_POLICY",
        )
        self.assertFalse(record["semantic_repair_attempted"])
        self.assertEqual(record["semantic_repair_count"], 0)
        self.assertEqual(post.call_count, 1)

    @patch("app.append_log")
    @patch("app.requests.post")
    def test_schema_invalid_output_never_reaches_semantic_admission(
        self,
        post,
        append_log,
    ):
        post.return_value = FakeOllamaResponse({
            "ambiguity_buckets": [
                "KINEMATIC_STATE_UNRESOLVED"
            ],
        })

        with self.assertRaises(HTTPException) as ctx:
            app.reason(
                app.ReasonRequest(
                    task="ambiguity_classification",
                    evidence=EVIDENCE,
                )
            )

        self.assertEqual(
            ctx.exception.detail["status"],
            "REJECTED_SCHEMA",
        )

        record = append_log.call_args.args[0]

        self.assertEqual(
            record["status"],
            "REJECTED_SCHEMA",
        )
        self.assertFalse(record["schema_validated"])
        self.assertFalse(record["semantic_admitted"])


if __name__ == "__main__":
    unittest.main()
