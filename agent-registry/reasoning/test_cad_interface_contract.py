#!/usr/bin/env python3
"""Regression tests for the candidate CAD interface contract."""

import copy
import json
import unittest
from pathlib import Path

from cad_interface_contract import (
    CADInterfaceContractError,
    derive_local_displacement,
    validate_contract,
)


REASONING = Path(__file__).resolve().parent
REFERENCE = REASONING / "reference_cases" / "v42_product_flow.cad-interface-contract.v1.json"
SCHEMA = REASONING.parent / "schemas" / "cad-interface-contract.v1.schema.json"


def load_reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def by_role(contract, role):
    return next(item for item in contract["interfaces"] if item["semantic_role"] == role)


class CADInterfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_reference()

    def test_schema_keeps_interface_contract_separate_from_mechanical_acceptance(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertIs(schema["properties"]["mechanical_acceptance_granted"]["const"], False)
        self.assertIs(
            schema["$defs"]["interface"]["properties"]["mechanical_acceptance_granted"]["const"],
            False,
        )
        self.assertIs(
            schema["$defs"]["relation"]["properties"]["mechanical_acceptance_granted"]["const"],
            False,
        )

    def test_v42_reference_validates(self):
        report = validate_contract(self.contract)
        self.assertEqual(report["contract_id"], "V42_PRODUCT_FLOW_INTERFACE_CONTRACT")
        self.assertIs(report["mechanical_acceptance_granted"], False)
        self.assertEqual(
            report["semantic_roles"]["PRODUCT_ENTRY"],
            "V42.PRODUCT_ENTRY",
        )
        self.assertEqual(
            report["semantic_roles"]["PRODUCT_EXIT"],
            "V42.PRODUCT_EXIT",
        )

    def test_published_asset_identity_and_semantic_role_do_not_claim_connector_geometry(self):
        entry = by_role(self.contract, "PRODUCT_ENTRY")
        exit_ = by_role(self.contract, "PRODUCT_EXIT")

        self.assertEqual(
            entry["native_published_reference"]["connector_name"],
            "Connector2",
        )
        self.assertEqual(
            exit_["native_published_reference"]["connector_name"],
            "Connector1",
        )

        for interface in (entry, exit_):
            native = interface["native_published_reference"]
            self.assertEqual(native["identity_state"], "VERIFIED")
            self.assertEqual(native["semantic_binding_authority"], "HUMAN_OBSERVATION")
            self.assertEqual(native["semantic_binding_state"], "VERIFIED")
            self.assertEqual(native["geometry_binding_state"], "UNRESOLVED")
            self.assertEqual(
                interface["pairing"]["geometric_coincidence_state"],
                "UNRESOLVED",
            )

    def test_api_frames_are_live_solidworks_authority(self):
        for interface in self.contract["interfaces"]:
            frame = interface["api_frame"]
            self.assertEqual(frame["feature_type"], "CoordSys")
            self.assertEqual(frame["source_authority"], "SOLIDWORKS_LIVE_STATE")
            self.assertEqual(
                frame["source_classification"],
                "verified_from_solidworks_api",
            )
            self.assertEqual(frame["evidence_state"], "VERIFIED")
            self.assertEqual(
                frame["axis_semantics"],
                {"x": "PRODUCT_FLOW", "y": "LATERAL", "z": "UP"},
            )

    def test_consumer_derives_900_mm_positive_x_product_flow_from_contract_alone(self):
        entry = by_role(self.contract, "PRODUCT_ENTRY")
        exit_ = by_role(self.contract, "PRODUCT_EXIT")

        displacement = derive_local_displacement(entry, exit_)

        self.assertAlmostEqual(displacement[0], 900.0, places=9)
        self.assertAlmostEqual(displacement[1], 0.0, places=9)
        self.assertAlmostEqual(displacement[2], 0.0, places=9)

        report = validate_contract(self.contract)
        declared = report["relation_local_displacements_mm"][
            "V42.ENTRY_TO_EXIT_PRODUCT_FLOW"
        ]
        self.assertAlmostEqual(declared[0], 900.0, places=9)
        self.assertAlmostEqual(declared[1], 0.0, places=9)
        self.assertAlmostEqual(declared[2], 0.0, places=9)

    def test_declared_relation_must_match_frame_transforms(self):
        case = copy.deepcopy(self.contract)
        case["relations"][0]["derived_local_displacement_mm"] = [899.0, 0.0, 0.0]

        with self.assertRaises(CADInterfaceContractError):
            validate_contract(case)

    def test_origin_must_match_transform_translation(self):
        case = copy.deepcopy(self.contract)
        by_role(case, "PRODUCT_ENTRY")["api_frame"]["origin_mm"][1] = 225.0

        with self.assertRaises(CADInterfaceContractError):
            validate_contract(case)

    def test_contract_cannot_grant_mechanical_acceptance(self):
        case = copy.deepcopy(self.contract)
        case["mechanical_acceptance_granted"] = True

        with self.assertRaises(CADInterfaceContractError):
            validate_contract(case)


if __name__ == "__main__":
    unittest.main()
