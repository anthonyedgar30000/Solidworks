#!/usr/bin/env python3
"""Regression tests for non-mutating CAD interface-consumption calculations."""

import json
import unittest
from pathlib import Path

from cad_interface_consumption import (
    IDENTITY_TRANSFORM16,
    calculate_complementary_asset_proposal,
    calculate_connection_transform,
    calculate_spec_proposal,
    compose_transform16,
    invert_transform16,
)


REASONING = Path(__file__).resolve().parent
CONTRACT = REASONING / "reference_cases" / "v42_product_flow.cad-interface-contract.v1.json"
SPEC = REASONING / "reference_cases" / "v42_disposable_complementary_asset_interface_test.v1.json"
SCHEMA = REASONING.parent / "schemas" / "cad-interface-consumption-test.v1.schema.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def by_id(contract, interface_id):
    return next(item for item in contract["interfaces"] if item["id"] == interface_id)


class CADInterfaceConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_json(CONTRACT)
        self.spec = load_json(SPEC)

    def test_v42_disposable_receiver_identity_frame_uses_declared_exit_transform(self):
        proposal = calculate_spec_proposal(self.contract, self.spec)
        expected = self.spec["expected_calculation"][
            "proposed_asset_to_world_transform16_from_declared_baseline"
        ]

        self.assertEqual(
            proposal["proposed_asset_to_world_transform16"],
            expected,
        )
        self.assertEqual(proposal["current_live_frame_state"], "STALE_STATE")
        self.assertFalse(proposal["cad_write_authorized"])
        self.assertEqual(proposal["materialization_state"], "NOT_AUTHORIZED")
        self.assertFalse(proposal["mechanical_acceptance_granted"])
        self.assertEqual(
            proposal["published_asset_coordinate_system_geometric_coincidence_state"],
            "UNRESOLVED",
        )

    def test_disposable_asset_schema_forbids_materialization_and_acceptance(self):
        schema = load_json(SCHEMA)

        self.assertIs(schema["properties"]["cad_write_authorized"]["const"], False)
        self.assertEqual(
            schema["properties"]["materialization_state"]["const"],
            "NOT_AUTHORIZED",
        )
        self.assertIs(
            schema["properties"]["mechanical_acceptance_granted"]["const"],
            False,
        )

    def test_connection_transform_satisfies_local_connection_equals_target(self):
        target = [
            0.0,
            -1.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            1.0,
            2.0,
            3.0,
            1.0,
            0.0,
            0.0,
            0.0,
        ]
        connection_to_asset = [
            0.0,
            1.0,
            0.0,
            -1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.5,
            -0.25,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
        ]

        asset_to_world = calculate_connection_transform(target, connection_to_asset)
        reconstructed_target = compose_transform16(connection_to_asset, asset_to_world)

        for actual, expected in zip(reconstructed_target, target):
            self.assertAlmostEqual(actual, expected, places=12)

    def test_inverse_is_two_sided_for_rigid_transform(self):
        transform = [
            0.0,
            -1.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            2.0,
            -3.0,
            4.0,
            1.0,
            0.0,
            0.0,
            0.0,
        ]
        inverse = invert_transform16(transform)

        for composition in (
            compose_transform16(transform, inverse),
            compose_transform16(inverse, transform),
        ):
            for actual, expected in zip(composition, IDENTITY_TRANSFORM16):
                self.assertAlmostEqual(actual, expected, places=12)

    def test_fresh_frame_verification_does_not_authorize_materialization(self):
        exit_frame = by_id(self.contract, "V42.PRODUCT_EXIT")["api_frame"]["transform16"]
        proposal = calculate_complementary_asset_proposal(
            self.contract,
            "V42.PRODUCT_EXIT",
            IDENTITY_TRANSFORM16,
            live_verification={"live_verification_state": "VERIFIED_CURRENT"},
        )

        self.assertEqual(proposal["current_live_frame_state"], "VERIFIED_CURRENT")
        self.assertEqual(proposal["proposed_asset_to_world_transform16"], exit_frame)
        self.assertFalse(proposal["cad_write_authorized"])
        self.assertEqual(proposal["materialization_state"], "NOT_AUTHORIZED")
        self.assertFalse(proposal["mechanical_acceptance_granted"])


if __name__ == "__main__":
    unittest.main()
