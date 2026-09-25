#!/usr/bin/env python3
"""Static regression boundaries for the local native interface-contract probe.

These source-level checks do not substitute for a SOLIDWORKS host observation.
They ensure that the bounded CoordSys and Published References FeatureManager
read paths remain explicit and separate from generic feature surfaces before
native-host verification.
"""

import unittest
from pathlib import Path


REGISTRY = Path(__file__).resolve().parents[1]
WORKER = REGISTRY / "workers" / "CadGrounded.SolidWorksWorker"
PROGRAM = WORKER / "Program.cs"
VERIFY_SCRIPT = WORKER / "Verify-InterfaceContract-V42.ps1"
JSON_FILE_EVIDENCE = WORKER / "JsonFileEvidence.ps1"
JSON_FILE_EVIDENCE_TEST = WORKER / "Test-JsonFileEvidence.ps1"
WORKFLOW = REGISTRY.parent / ".github" / "workflows" / "solidworks-worker-compile.yml"
DIAGNOSTIC_EVIDENCE = WORKER / "InterfaceConnectorDiagnosticEvidence.ps1"
DIAGNOSTIC_EVIDENCE_TEST = WORKER / "Test-InterfaceConnectorDiagnosticEvidence.ps1"
TREE_DIAGNOSTIC_EVIDENCE = WORKER / "FeatureManagerTreeDiagnosticEvidence.ps1"
TREE_DIAGNOSTIC_EVIDENCE_TEST = WORKER / "Test-FeatureManagerTreeDiagnosticEvidence.ps1"
QUEUE_CONFIGS = (
    REGISTRY / "CADGrounded_RemoteQueue_v1" / "queue-config.json",
    REGISTRY / "remote-queue-runner-v1" / "queue-config.json",
)
EXPECTED_COORDSYS_PROVENANCE = (
    "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> "
    "IMathTransform.ArrayData"
)


def coordinate_system_reader(program: str) -> str:
    start = program.index("private static object ReadCoordinateSystemFeature")
    end = program.index("\n    public object QueryMates", start)
    return program[start:end]


class NativeInterfaceContractProbeTests(unittest.TestCase):
    def setUp(self):
        self.program = PROGRAM.read_text(encoding="utf-8")
        self.reader = coordinate_system_reader(self.program)

    def test_coordsys_uses_get_definition_not_specific_feature_getter(self):
        self.assertIn("feature.GetDefinition()", self.reader)
        self.assertIn("ICoordinateSystemFeatureData coordinateSystemData", self.reader)
        self.assertIn("coordinateSystemData.Transform", self.reader)
        self.assertIn("mathTransform.ArrayData", self.reader)
        self.assertNotIn("feature.GetSpecificFeature2()", self.reader)
        self.assertIn("coordinate_system_definition_unavailable", self.reader)
        self.assertIn("coordinate_system_transform_unavailable", self.reader)

    def test_provenance_and_authority_boundaries_match_the_bounded_reader(self):
        self.assertIn(EXPECTED_COORDSYS_PROVENANCE, self.reader)
        self.assertIn(EXPECTED_COORDSYS_PROVENANCE, self.program)
        self.assertIn("model_mutation = false", self.program)
        self.assertIn('write_authority = "NONE"', self.program)
        self.assertIn("mateFeature.GetSpecificFeature2()", self.program)

        for queue_config in QUEUE_CONFIGS:
            contents = queue_config.read_text(encoding="utf-8")
            self.assertNotIn("sw.query_interface_contract", contents, msg=str(queue_config))

    def test_connector_diagnostic_compares_direct_lookup_with_existing_traversal(self):
        verifier = VERIFY_SCRIPT.read_text(encoding="utf-8")
        evidence = DIAGNOSTIC_EVIDENCE.read_text(encoding="utf-8")
        regression = DIAGNOSTIC_EVIDENCE_TEST.read_text(encoding="utf-8")

        for expected in (
            '"sw.diagnose_interface_connectors"',
            "assembly.FeatureByName(exactName)",
            '"ConnectRefMgr"',
            "parent_feature_name",
            "tree_depth",
            "DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT",
            "LIVE_STATE_SOURCE_CONFLICT",
            "remote_queue_authorized = false",
        ):
            self.assertIn(expected, self.program)

        self.assertIn("interface-connectors-diagnostic", verifier)
        self.assertIn("sw.diagnose_interface_connectors.raw.json", verifier)
        self.assertIn("connector-diagnostic-summary.json", verifier)
        self.assertIn("InterfaceConnectorDiagnosticEvidence.ps1", verifier)
        self.assertIn("DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT", regression)
        self.assertIn("Required interface observation field is absent", regression)
        self.assertIn("EXACT_CONNECTOR_NAMES_PLUS_CONNECT_REF_MANAGER", evidence)

        for queue_config in QUEUE_CONFIGS:
            contents = queue_config.read_text(encoding="utf-8")
            self.assertNotIn(
                "sw.diagnose_interface_connectors", contents, msg=str(queue_config)
            )

    def test_interface_reader_uses_exact_feature_manager_published_references_branch(self):
        query_start = self.program.index("public object QueryInterfaceContract")
        query_end = self.program.index("public object DiagnoseInterfaceConnectors", query_start)
        query = self.program[query_start:query_end]

        self.assertIn("var features = EnumerateFeatures().ToArray();", self.program)
        self.assertIn(
            'RequireExactFeature(features, name, "CoordSys", "coordinate system")',
            query,
        )
        self.assertIn(
            "ReadPublishedReferenceBindingFromFeatureManagerTree(",
            query,
        )
        self.assertNotIn(
            'RequireExactFeature(features, name, "MagneticConnectRef", "Published Reference connector")',
            query,
        )
        self.assertNotIn("FeatureByName", query)
        for expected in (
            '"Published References"',
            '"ConnectRefMgr"',
            '"MagneticConnectRef"',
            "GetFeatureTreeRootItem2",
            "GetFirstChild",
            "GetNext",
            "parent_tree_path",
            "published_reference_connector_tree_match_not_unique",
            "feature_manager_tree_object_unavailable",
            "feature_manager_tree_feature_name_mismatch",
            "feature_manager_tree_feature_type_mismatch",
            "VERIFIED_FEATURE_MANAGER_TREE_BRANCH",
        ):
            self.assertIn(expected, self.program)
        self.assertIn(
            "published_reference_manager = publishedReferenceBinding.published_reference_manager",
            query,
        )

    def test_feature_manager_tree_diagnostic_is_bounded_and_separate(self):
        verifier = VERIFY_SCRIPT.read_text(encoding="utf-8")
        evidence = TREE_DIAGNOSTIC_EVIDENCE.read_text(encoding="utf-8")
        regression = TREE_DIAGNOSTIC_EVIDENCE_TEST.read_text(encoding="utf-8")

        for expected in (
            '"sw.diagnose_feature_manager_tree"',
            "_doc.FeatureManager",
            "GetFeatureTreeRootItem2",
            "swFeatMgrPaneBottom",
            "item.Text",
            "item.ObjectType",
            "item.Object",
            "Marshal.IsComObject",
            "object_runtime_dotnet_type",
            "EXACT_DISPLAYED_TREE_TEXTS_ONLY",
            "ALL_REQUESTED_TREE_TEXTS_OBSERVED",
            "NO_REQUESTED_TREE_TEXTS_OBSERVED",
            "remote_queue_authorized = false",
        ):
            self.assertIn(expected, self.program)

        self.assertIn("feature-manager-tree-diagnostic", verifier)
        self.assertIn("sw.diagnose_feature_manager_tree.raw.json", verifier)
        self.assertIn("feature-manager-tree-diagnostic-summary.json", verifier)
        self.assertIn("FeatureManagerTreeDiagnosticEvidence.ps1", verifier)
        self.assertIn("object_is_null", regression)
        self.assertIn("outside the exact requested-text scope", regression)
        self.assertIn("EXACT_DISPLAYED_TREE_TEXTS_ONLY", evidence)

        query_start = self.program.index("public object QueryInterfaceContract")
        query_end = self.program.index("public object DiagnoseInterfaceConnectors", query_start)
        self.assertNotIn("DiagnoseFeatureManagerTree", self.program[query_start:query_end])

        for queue_config in QUEUE_CONFIGS:
            contents = queue_config.read_text(encoding="utf-8")
            self.assertNotIn(
                "sw.diagnose_feature_manager_tree", contents, msg=str(queue_config)
            )

    def test_machine_json_artifacts_use_explicit_utf8_without_bom(self):
        writer = JSON_FILE_EVIDENCE.read_text(encoding="utf-8")
        regression = JSON_FILE_EVIDENCE_TEST.read_text(encoding="utf-8")
        verifier = VERIFY_SCRIPT.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("function Write-JsonFileUtf8NoBom", writer)
        self.assertIn("[System.Text.UTF8Encoding]::new($false)", writer)
        self.assertIn("[System.IO.File]::WriteAllText", writer)
        self.assertIn("ConvertTo-Json -Depth $Depth", writer)
        self.assertIn("JsonFileEvidence.ps1", verifier)
        self.assertNotIn("Set-Content -LiteralPath", verifier)
        self.assertEqual(verifier.count("Write-JsonFileUtf8NoBom -Value"), 6)

        for expected in (
            "ReadAllBytes",
            "EF BB BF",
            "UTF8Encoding]::new($false, $true)",
            "cad_interface_live_verifier.py",
            "--out $reportPath --summary",
            "VERIFIED_CURRENT",
            "geometry_binding_state -cne 'UNRESOLVED'",
            "mechanical_acceptance_granted -ne $false",
        ):
            self.assertIn(expected, regression)

        self.assertIn("Test BOM-free JSON evidence artifacts", workflow)
        self.assertIn(".\\Test-JsonFileEvidence.ps1", workflow)


if __name__ == "__main__":
    unittest.main()
