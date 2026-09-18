#!/usr/bin/env python3
"""Static regression tests for CADGrounded Domain Model v1 contracts.

These tests intentionally use only the Python standard library. They verify
that the JSON contracts preserve the supertype/subtype partition and the
separation between object type and epistemic/lifecycle state.

They do not replace a full JSON Schema validator and do not alter runtime
authority.
"""

import json
import unittest
from pathlib import Path


AGENT_REGISTRY = Path(__file__).resolve().parents[1]
SCHEMAS = AGENT_REGISTRY / "schemas"
REMOTE_QUEUE = AGENT_REGISTRY / "remote-queue-runner-v1"


def load_schema(name: str):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def discriminator_constants(schema, property_name):
    values = []
    for branch in schema["oneOf"]:
        prop = branch["properties"][property_name]
        if "const" in prop:
            values.append(prop["const"])
        elif "enum" in prop:
            values.extend(prop["enum"])
    return values


def request_branches_by_command(schema):
    """Return normalized command subtype branches for legacy or Domain Model v1 schemas."""
    if "oneOf" in schema:
        return {
            branch["properties"]["command_id"]["const"]: branch
            for branch in schema["oneOf"]
        }

    if "allOf" in schema:
        normalized = {}
        for branch in schema["allOf"]:
            command_id = branch["if"]["properties"]["command_id"]["const"]
            normalized[command_id] = branch["then"]
        return normalized

    raise AssertionError("Request schema has neither oneOf nor allOf subtype branches")


class DomainModelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = load_schema("cad-read-request.v1.schema.json")
        cls.evidence = load_schema("evidence-record.v1.schema.json")
        cls.deployed_request = json.loads(
            (REMOTE_QUEUE / "cad-job.schema.json").read_text(encoding="utf-8")
        )

    def test_request_partition_is_exact_and_disjoint(self):
        values = discriminator_constants(self.request, "command_id")
        self.assertEqual(
            values,
            ["sw.status", "sw.query_components", "sw.closest_distance_pair"],
        )
        self.assertEqual(len(values), len(set(values)))

    def test_request_supertype_preserves_read_only_authority(self):
        self.assertEqual(
            self.request["properties"]["write_authority"]["const"],
            "NONE",
        )
        self.assertIn("job_id", self.request["required"])
        self.assertIn("command_id", self.request["required"])

    def test_component_query_has_only_its_subtype_payload(self):
        branch = next(
            b for b in self.request["oneOf"]
            if b["properties"]["command_id"].get("const") == "sw.query_components"
        )
        payload = branch["properties"]["payload"]
        self.assertEqual(payload["required"], ["top_level_only"])
        self.assertFalse(payload["additionalProperties"])
        self.assertIn("document_title_exact", branch["properties"]["preconditions"]["required"])

    def test_distance_query_requires_exact_pair_identities(self):
        branch = next(
            b for b in self.request["oneOf"]
            if b["properties"]["command_id"].get("const") == "sw.closest_distance_pair"
        )
        self.assertEqual(
            branch["properties"]["payload"]["required"],
            ["a_name_exact", "b_name_exact"],
        )


    def test_candidate_request_preserves_deployed_top_level_contract(self):
        deployed = self.deployed_request
        candidate = self.request
        self.assertEqual(set(candidate["required"]), set(deployed["required"]))
        self.assertEqual(set(candidate["properties"]), set(deployed["properties"]))
        self.assertEqual(
            set(candidate["properties"]["command_id"]["enum"]),
            set(deployed["properties"]["command_id"]["enum"]),
        )
        self.assertEqual(
            candidate["properties"]["write_authority"]["const"],
            deployed["properties"]["write_authority"]["const"],
        )
        self.assertEqual(
            set(candidate["properties"]["preconditions"]["properties"]),
            set(deployed["properties"]["preconditions"]["properties"]),
        )

    def test_candidate_request_preserves_deployed_subtype_payload_contracts(self):
        candidate_by_command = request_branches_by_command(self.request)
        deployed_by_command = request_branches_by_command(self.deployed_request)

        self.assertEqual(set(candidate_by_command), set(deployed_by_command))

        for command_id in candidate_by_command:
            candidate_payload = candidate_by_command[command_id]["properties"]["payload"]
            deployed_payload = deployed_by_command[command_id]["properties"]["payload"]

            self.assertEqual(
                set(candidate_payload.get("required", [])),
                set(deployed_payload.get("required", [])),
                command_id,
            )
            self.assertEqual(
                set(candidate_payload.get("properties", {})),
                set(deployed_payload.get("properties", {})),
                command_id,
            )
            self.assertEqual(
                candidate_payload.get("additionalProperties"),
                deployed_payload.get("additionalProperties"),
                command_id,
            )
            self.assertEqual(
                candidate_payload.get("maxProperties"),
                deployed_payload.get("maxProperties"),
                command_id,
            )

            candidate_pre = candidate_by_command[command_id]["properties"].get("preconditions", {})
            deployed_pre = deployed_by_command[command_id]["properties"].get("preconditions", {})
            self.assertEqual(
                set(candidate_pre.get("required", [])),
                set(deployed_pre.get("required", [])),
                command_id,
            )

    def test_source_nonempty_contract_is_runner_aligned(self):
        deployed_source = self.deployed_request["properties"]["source"]
        candidate_source = self.request["properties"]["source"]
        self.assertEqual(candidate_source["minLength"], 1)
        self.assertEqual(deployed_source.get("minLength", 1), 1)
        self.assertEqual(candidate_source["maxLength"], deployed_source["maxLength"])

        runner_text = (REMOTE_QUEUE / "Invoke-CADRemoteQueue.ps1").read_text(encoding="utf-8")
        self.assertIn(
            "source must be a non-empty string up to 128 characters.",
            runner_text,
        )

    def test_existing_remote_queue_examples_fit_candidate_subtypes(self):
        examples = {
            "status.job.json": "sw.status",
            "components-v21.job.json": "sw.query_components",
            "closest-distance-v21.job.json": "sw.closest_distance_pair",
        }
        branches = {
            branch["properties"]["command_id"]["const"]: branch
            for branch in self.request["oneOf"]
        }

        for filename, command_id in examples.items():
            job = json.loads((REMOTE_QUEUE / "examples" / filename).read_text(encoding="utf-8"))
            self.assertEqual(job["command_id"], command_id, filename)
            self.assertEqual(job["write_authority"], "NONE", filename)

            branch = branches[command_id]
            payload_schema = branch["properties"]["payload"]
            self.assertEqual(
                set(payload_schema.get("required", [])) - set(job["payload"]),
                set(),
                filename,
            )
            if payload_schema.get("additionalProperties") is False:
                self.assertEqual(
                    set(job["payload"]) - set(payload_schema.get("properties", {})),
                    set(),
                    filename,
                )

            required_preconditions = set(
                branch["properties"].get("preconditions", {}).get("required", [])
            )
            if required_preconditions:
                self.assertIn("preconditions", job, filename)
                self.assertEqual(
                    required_preconditions - set(job["preconditions"]),
                    set(),
                    filename,
                )

            if "source" in job:
                self.assertIsInstance(job["source"], str, filename)
                self.assertTrue(job["source"], filename)


    def test_evidence_partition_is_disjoint(self):
        values = discriminator_constants(self.evidence, "evidence_type")
        expected = {
            "solidworks_observation",
            "oem_evidence",
            "deterministic_calculation",
            "human_observation",
            "ai_visualization_record",
        }
        self.assertEqual(set(values), expected)
        self.assertEqual(len(values), len(set(values)))

    def test_state_dimensions_are_supertype_attributes_not_subtypes(self):
        props = self.evidence["properties"]
        self.assertIn("evidence_state", props)
        self.assertIn("geometry_state", props)
        self.assertIn("ambiguity_bucket", props)
        branch_titles = {b["title"] for b in self.evidence["oneOf"]}
        self.assertNotIn("VERIFIED", branch_titles)
        self.assertNotIn("FIT_CHECK", branch_titles)
        self.assertNotIn("UNRESOLVED", branch_titles)

    def test_evidence_never_directly_grants_mechanical_acceptance(self):
        self.assertIs(
            self.evidence["properties"]["mechanical_acceptance_granted"]["const"],
            False,
        )

    def test_solidworks_observation_has_live_api_authority(self):
        branch = next(
            b for b in self.evidence["oneOf"]
            if b["properties"]["evidence_type"].get("const") == "solidworks_observation"
        )
        self.assertEqual(
            branch["properties"]["source_authority"]["const"],
            "SOLIDWORKS_LIVE_STATE",
        )
        self.assertEqual(
            branch["properties"]["source_classification"]["const"],
            "verified_from_solidworks_api",
        )

    def test_ai_visualization_cannot_masquerade_as_engineering_evidence(self):
        branch = next(
            b for b in self.evidence["oneOf"]
            if b["properties"]["evidence_type"].get("const") == "ai_visualization_record"
        )
        self.assertEqual(branch["properties"]["source_authority"]["const"], "GENERATIVE_AI")
        self.assertEqual(branch["properties"]["evidence_state"]["const"], "AI_GENERATED")
        self.assertEqual(branch["properties"]["source_classification"]["const"], "ai_generated")


if __name__ == "__main__":
    unittest.main()
