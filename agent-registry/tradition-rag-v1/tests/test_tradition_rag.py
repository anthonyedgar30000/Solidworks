import json
import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import tradition_rag as tr


class TraditionRagTests(unittest.TestCase):
    def test_each_tradition_has_authoritative_and_chatter_source(self):
        policy = tr.read_json(HERE / "traditions.v1.json")
        registry = tr.read_json(HERE / "sources.v1.json")
        sources = registry["sources"]

        for tradition in policy["traditions"]:
            tid = tradition["tradition_id"]
            lanes = {
                source["lane"]
                for source in sources
                if tid in source["traditions"]
            }
            self.assertIn("AUTHORITATIVE", lanes, tid)
            self.assertIn("FIELD_CHATTER", lanes, tid)

    def test_bootstrap_creates_all_collections_and_preserves_lanes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = tr.bootstrap(HERE, root)
            self.assertEqual(13, len(manifest["collections"]))
            self.assertEqual("NONE", manifest["cad_write_authority"])
            self.assertEqual("NONE", manifest["mechanical_acceptance_authority"])

            status = tr.status(HERE, root)
            for collection in status["collections"]:
                self.assertGreater(collection["chunks"], 0)
                self.assertGreater(collection["lanes"]["AUTHORITATIVE"], 0)
                self.assertGreater(collection["lanes"]["FIELD_CHATTER"], 0)

    def test_retrieval_never_promotes_chatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tr.bootstrap(HERE, root)
            bundle = tr.retrieve(
                root,
                "PACKAGING_MACHINE_BUILDING",
                "packaging conveyor actuator safety motion",
            )
            self.assertFalse(
                bundle["authority_boundary"]["mechanical_acceptance_granted"]
            )
            self.assertEqual(
                "HYPOTHESIS_ONLY",
                bundle["authority_boundary"]["field_chatter_effect_ceiling"],
            )
            for hit in bundle["hits"]["FIELD_CHATTER"]:
                self.assertEqual("HYPOTHESIS_ONLY", hit["permitted_effect"])


if __name__ == "__main__":
    unittest.main()
