#!/usr/bin/env python3
"""Static regression boundaries for the local native interface-contract probe.

These source-level checks do not substitute for a SOLIDWORKS host observation.
They ensure that the bounded CoordSys read path remains explicit and separate
from the generic mate-specific-feature path before native-host verification.
"""

import unittest
from pathlib import Path


REGISTRY = Path(__file__).resolve().parents[1]
PROGRAM = REGISTRY / "workers" / "CadGrounded.SolidWorksWorker" / "Program.cs"
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


if __name__ == "__main__":
    unittest.main()
