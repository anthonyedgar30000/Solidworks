#!/usr/bin/env python3
"""Regression tests for CAD interface live verification drift boundaries."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from cad_interface_live_verifier import (
    CADInterfaceLiveVerificationError,
    LIVE_STATE_AUTHORITY_REJECTED,
    LIVE_STATE_DRIFT,
    LIVE_STATE_OBSERVATION_REJECTED,
    LIVE_STATE_STALE,
    LIVE_STATE_VERIFIED,
    _load_json,
    stale_live_verification,
    verify_live_interface_contract,
)


REASONING = Path(__file__).resolve().parent
REFERENCE = REASONING / "reference_cases" / "v42_product_flow.cad-interface-contract.v1.json"
SCHEMA = REASONING.parent / "schemas" / "cad-interface-live-observation.v1.schema.json"
REMOTE_QUEUE_CONFIGS = [
    REASONING.parent / "CADGrounded_RemoteQueue_v1" / "queue-config.json",
    REASONING.parent / "remote-queue-runner-v1" / "queue-config.json",
]


def load_reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def current_observation(contract):
    return {
        "ok": True,
        "command_id": "sw.query_interface_contract",
        "source_classification": "verified_from_solidworks_api",
        "data": {
            "write_authority": "NONE",
            "model_mutation": False,
            "result_scope": "EXACT_NAMED_FEATURES_ONLY",
            "evidence": "verified_from_solidworks_api",
            "request": {
                "coordinate_system_feature_names": [
                    interface["api_frame"]["feature_name"]
                    for interface in contract["interfaces"]
                ],
                "published_reference_connector_names": [
                    interface["native_published_reference"]["connector_name"]
                    for interface in contract["interfaces"]
                ],
            },
            "published_reference_manager_binding_state": "VERIFIED_FEATURE_MANAGER_TREE_BRANCH",
            "published_reference_manager_binding_note": (
                "Exact Published References / ConnectRefMgr FeatureManager branch only."
            ),
            "published_reference_manager": {
                "displayed_tree_text": "Published References",
                "feature_name": "Published References",
                "feature_type": "ConnectRefMgr",
                "tree_path": "0.8",
            },
            "geometry_binding_state": "UNRESOLVED",
            "interpretation_note": "Interface alignment observation only.",
            "api": (
                "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> "
                "IMathTransform.ArrayData; IModelDoc2.FeatureManager -> "
                "IFeatureManager.GetFeatureTreeRootItem2(swFeatMgrPaneBottom) -> "
                "ITreeControlItem.Text/GetFirstChild/GetNext/Object -> IFeature.Name/GetTypeName2"
            ),
            "document": {
                "title": contract["document"]["title_exact"],
                "path": contract["document"]["path_exact"],
                "type": "assembly",
                "active_configuration": "Default",
                "save_flag": 0,
            },
            "published_reference_features": [
                {
                    "connector_name": interface["native_published_reference"]["connector_name"],
                    "feature_type": interface["native_published_reference"]["feature_type"],
                    "tree_path": (
                        "0.8.2"
                        if interface["native_published_reference"]["connector_name"] == "Connector2"
                        else "0.8.1"
                    ),
                    "parent_tree_text": "Published References",
                    "parent_feature_name": "Published References",
                    "parent_feature_type": "ConnectRefMgr",
                }
                for interface in contract["interfaces"]
            ],
            "coordinate_systems": [
                {
                    "feature_name": interface["api_frame"]["feature_name"],
                    "feature_type": interface["api_frame"]["feature_type"],
                    "transform16": interface["api_frame"]["transform16"],
                    "origin_mm": interface["api_frame"]["origin_mm"],
                    "transform_source": "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData",
                }
                for interface in contract["interfaces"]
            ],
        },
    }


class CADInterfaceLiveVerifierTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_reference()
        self.observation = current_observation(self.contract)

    def test_exact_current_observation_verifies_only_interface_frame_baseline(self):
        report = verify_live_interface_contract(self.contract, self.observation)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_VERIFIED)
        self.assertEqual(
            report["interface_alignment_state"],
            "VERIFIED_CURRENT_FRAME_BASELINE_ONLY",
        )
        self.assertTrue(report["connection_transform_eligible"])
        self.assertFalse(report["mechanical_acceptance_granted"])
        self.assertFalse(report["remote_queue_authorized"])
        self.assertEqual(
            report["published_asset_coordinate_system_geometric_coincidence"],
            {
                "V42.PRODUCT_ENTRY": "UNRESOLVED",
                "V42.PRODUCT_EXIT": "UNRESOLVED",
            },
        )

    def test_live_observation_schema_enforces_read_only_and_unresolved_geometry(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        data = schema["$defs"]["data"]["properties"]

        self.assertEqual(schema["properties"]["command_id"]["const"], "sw.query_interface_contract")
        self.assertIs(data["model_mutation"]["const"], False)
        self.assertEqual(data["write_authority"]["const"], "NONE")
        self.assertEqual(data["geometry_binding_state"]["const"], "UNRESOLVED")
        self.assertEqual(
            data["published_reference_manager_binding_state"]["const"],
            "VERIFIED_FEATURE_MANAGER_TREE_BRANCH",
        )
        self.assertEqual(
            schema["$defs"]["publishedReferenceManager"]["properties"]["feature_type"][
                "const"
            ],
            "ConnectRefMgr",
        )

    def test_utf8_bom_is_rejected_not_silently_normalized_by_the_python_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observation.json"
            path.write_bytes(b"\xef\xbb\xbf{}")

            with self.assertRaisesRegex(
                CADInterfaceLiveVerificationError, "Unexpected UTF-8 BOM"
            ):
                _load_json(path)

    def test_native_interface_query_is_not_promoted_to_either_remote_queue(self):
        for queue_config in REMOTE_QUEUE_CONFIGS:
            self.assertNotIn(
                "sw.query_interface_contract",
                queue_config.read_text(encoding="utf-8"),
                msg=str(queue_config),
            )

    def test_unavailable_fresh_observation_is_stale_not_verified_from_contract(self):
        report = stale_live_verification(self.contract)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_STALE)
        self.assertEqual(report["interface_alignment_state"], "UNRESOLVED")
        self.assertFalse(report["connection_transform_eligible"])
        self.assertFalse(report["mechanical_acceptance_granted"])

    def test_document_identity_drift_fails_without_rebaselining(self):
        case = copy.deepcopy(self.observation)
        case["data"]["document"]["title"] = "OTHER_ASSEMBLY"

        report = verify_live_interface_contract(self.contract, case)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_DRIFT)
        self.assertIn(
            "DOCUMENT_TITLE_DRIFT",
            {issue["code"] for issue in report["drift_issues"]},
        )
        self.assertFalse(report["connection_transform_eligible"])

    def test_coordinate_transform_drift_fails_without_rebaselining(self):
        case = copy.deepcopy(self.observation)
        frame = case["data"]["coordinate_systems"][0]
        frame["transform16"][10] += 0.01
        frame["origin_mm"][1] += 10.0

        report = verify_live_interface_contract(self.contract, case)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_DRIFT)
        self.assertIn(
            "COORDINATE_SYSTEM_TRANSFORM_DRIFT",
            {issue["code"] for issue in report["drift_issues"]},
        )

    def test_missing_required_transform_is_observation_rejected(self):
        case = copy.deepcopy(self.observation)
        del case["data"]["coordinate_systems"][0]["transform16"]

        report = verify_live_interface_contract(self.contract, case)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_OBSERVATION_REJECTED)
        self.assertIn(
            "MALFORMED_OBSERVATION",
            {issue["code"] for issue in report["observation_issues"]},
        )

    def test_connector_feature_type_drift_fails(self):
        case = copy.deepcopy(self.observation)
        case["data"]["published_reference_features"][0]["feature_type"] = "CoordSys"

        report = verify_live_interface_contract(self.contract, case)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_DRIFT)
        self.assertIn(
            "PUBLISHED_REFERENCE_TYPE_DRIFT",
            {issue["code"] for issue in report["drift_issues"]},
        )

    def test_connector_outside_exact_published_references_branch_fails(self):
        case = copy.deepcopy(self.observation)
        case["data"]["published_reference_features"][0][
            "parent_feature_type"
        ] = "OtherFeature"

        report = verify_live_interface_contract(self.contract, case)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_DRIFT)
        self.assertIn(
            "PUBLISHED_REFERENCE_PARENT_BRANCH_DRIFT",
            {issue["code"] for issue in report["drift_issues"]},
        )

    def test_published_references_manager_type_drift_fails(self):
        case = copy.deepcopy(self.observation)
        case["data"]["published_reference_manager"]["feature_type"] = "OtherFeature"

        report = verify_live_interface_contract(self.contract, case)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_DRIFT)
        self.assertIn(
            "PUBLISHED_REFERENCE_MANAGER_BRANCH_DRIFT",
            {issue["code"] for issue in report["drift_issues"]},
        )

    def test_wrong_authority_or_mutation_claim_is_rejected(self):
        case = copy.deepcopy(self.observation)
        case["source_classification"] = "llm_inference"
        case["data"]["model_mutation"] = True

        report = verify_live_interface_contract(self.contract, case)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_AUTHORITY_REJECTED)
        codes = {issue["code"] for issue in report["authority_issues"]}
        self.assertIn("SOURCE_AUTHORITY_REJECTED", codes)
        self.assertIn("MUTATION_BOUNDARY_REJECTED", codes)

    def test_unexpected_feature_row_rejects_bounded_read_scope(self):
        case = copy.deepcopy(self.observation)
        case["data"]["published_reference_features"].append(
            {"connector_name": "UNREQUESTED", "feature_type": "MagneticConnectRef"}
        )

        report = verify_live_interface_contract(self.contract, case)

        self.assertEqual(report["live_verification_state"], LIVE_STATE_AUTHORITY_REJECTED)
        self.assertIn(
            "READ_SCOPE_REJECTED",
            {issue["code"] for issue in report["authority_issues"]},
        )

    def test_unproven_geometric_coincidence_cannot_be_promoted_by_frame_query(self):
        contract = copy.deepcopy(self.contract)
        contract["interfaces"][0]["native_published_reference"][
            "geometry_binding_state"
        ] = "VERIFIED"
        contract["interfaces"][0]["pairing"]["geometric_coincidence_state"] = "VERIFIED"

        report = verify_live_interface_contract(contract, current_observation(contract))

        self.assertEqual(report["live_verification_state"], LIVE_STATE_AUTHORITY_REJECTED)
        self.assertEqual(
            report["published_asset_coordinate_system_geometric_coincidence"][
                "V42.PRODUCT_ENTRY"
            ],
            "UNRESOLVED",
        )
        self.assertIn(
            "GEOMETRIC_COINCIDENCE_REQUIRES_SEPARATE_AUTHORITY",
            {issue["code"] for issue in report["authority_issues"]},
        )


if __name__ == "__main__":
    unittest.main()
