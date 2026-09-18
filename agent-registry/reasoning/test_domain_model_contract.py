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


class DomainModelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = load_schema("cad-read-request.v1.schema.json")
        cls.evidence = load_schema("evidence-record.v1.schema.json")

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
