import json
import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import tradition_context as tc


FRONTIER = {
    "current_plan_id": "PLAN-0011",
    "current_architecture_id": "IXOR_FUNCTION_FIRST_BOTTLE_HANDLING_REFERENCE",
    "current_plan_status": "ACTIVE_INVESTIGATION_TEST",
    "current_diagnostic": {
        "test_id": "TEST_POP_V43_PRISM_DUAL_PIVOT_EXACT_HYPOTHETICAL_SWEEP"
    },
}


def fake_bundle(tradition_id: str):
    return {
        "authority_boundary": {
            "retrieval_is_engineering_evidence": False,
            "mechanical_acceptance_granted": False,
            "cad_write_authority": "NONE",
        },
        "hits": {
            "AUTHORITATIVE": [
                {
                    "chunk_id": f"{tradition_id}:A1",
                    "source_id": "AUTH.TEST",
                    "authority_class": "TEST_AUTHORITY",
                    "body": "Authoritative source-scoped reference about guarding and restraint.",
                    "source_uri": "https://example.test/auth",
                    "retrieval_score": 5.0,
                    "permitted_effect": "REFERENCE_WITH_SOURCE_SCOPE",
                    "chunk_kind": "NETWORK_SOURCE",
                    "source_record_id": "SRCREC.AUTH",
                    "observed_at_utc": "2026-09-27T00:00:00Z",
                }
            ],
            "PROFESSIONAL_PRACTICE": [
                {
                    "chunk_id": f"{tradition_id}:P1",
                    "source_id": "PRO.TEST",
                    "authority_class": "TEST_PRACTICE",
                    "body": "Professional practice suggests checking service access.",
                    "source_uri": "https://example.test/pro",
                    "retrieval_score": 2.0,
                    "permitted_effect": "HEURISTIC_OR_TEST_IDEA_ONLY",
                    "chunk_kind": "NETWORK_SOURCE",
                    "source_record_id": "SRCREC.PRO",
                    "observed_at_utc": "2026-09-27T00:00:00Z",
                }
            ],
            "FIELD_CHATTER": [
                {
                    "chunk_id": f"{tradition_id}:C1",
                    "source_id": "CHAT.TEST",
                    "authority_class": "TEST_CHATTER",
                    "body": "Practitioner chatter suggests a pivot alternative.",
                    "source_uri": "https://example.test/chat",
                    "retrieval_score": 1.0,
                    "permitted_effect": "HYPOTHESIS_ONLY",
                    "chunk_kind": "NETWORK_SOURCE",
                    "source_record_id": "SRCREC.CHAT",
                    "observed_at_utc": "2026-09-27T00:00:00Z",
                },
                {
                    "chunk_id": f"{tradition_id}:ZERO",
                    "source_id": "CHAT.ZERO",
                    "authority_class": "TEST_CHATTER",
                    "body": "Zero-score noise.",
                    "source_uri": "https://example.test/zero",
                    "retrieval_score": 0.0,
                    "permitted_effect": "HYPOTHESIS_ONLY",
                },
            ],
        },
    }


class TraditionContextTests(unittest.TestCase):
    def runtime_fixture(self, root: Path):
        code = root / "code"
        data = root / "data"
        code.mkdir()
        data.mkdir()
        (data / "active_chunks.jsonl").write_text("{}\n", encoding="utf-8")
        (code / "deployment-manifest.json").write_text(
            json.dumps(
                {
                    "deployment_id": "CADGROUNDED.TRADITION_RAG.RUNTIME.V1",
                    "source_commit": "abc",
                    "tradition_rag_tree": "tree123",
                    "data_root": str(data),
                    "code_update_policy": "MANUAL_REVIEWED_DEPLOY",
                    "corpus_refresh_policy": "STALE_ONLY_AUTOMATIC",
                    "cad_write_authority": "NONE",
                    "mechanical_acceptance_authority": "NONE",
                }
            ),
            encoding="utf-8",
        )
        (data / "last-refresh.json").write_text(
            json.dumps(
                {
                    "state": "COMPLETED",
                    "tradition_rag_tree": "tree123",
                    "completed_at_utc": "2026-09-27T00:00:00Z",
                    "cad_write_authority": "NONE",
                    "mechanical_acceptance_authority": "NONE",
                }
            ),
            encoding="utf-8",
        )
        return code, data

    def test_binds_plan_profile_and_preserves_lane_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code, data = self.runtime_fixture(root)

            seen_queries = {}

            def retrieve(
                data_root,
                tradition_id,
                question,
                authoritative,
                professional,
                chatter,
            ):
                self.assertEqual(data_root, data)
                self.assertIn("bottle capture", question)
                self.assertEqual((authoritative, professional, chatter), (6, 3, 3))
                seen_queries[tradition_id] = question
                return fake_bundle(tradition_id)

            snapshot = tc.load_tradition_context(
                repo_root=root,
                code_root=code,
                data_root=data,
                evidence="- Capture motion is unresolved.",
                frontier_snapshot=FRONTIER,
                tree_resolver=lambda _: "tree123",
                retriever=retrieve,
            )

            self.assertEqual(snapshot["state"], "BOUND_UNADMITTED_ADVISORY")
            self.assertEqual(snapshot["engineering_evidence_admissibility"], "NONE")
            self.assertEqual(snapshot["frontier_mutation_authority"], "NONE")
            self.assertEqual(snapshot["cad_write_authority"], "NONE")
            self.assertEqual(snapshot["mechanical_acceptance_authority"], "NONE")
            self.assertEqual(len(snapshot["selected_traditions"]), 7)
            self.assertEqual(snapshot["total_hits"], 21)
            self.assertIn(
                "alignment adjustment installation service access",
                seen_queries["MILLWRIGHT"],
            )
            self.assertIn(
                "sequence state transition interlock sensor proof",
                seen_queries["CONTROLS_AUTOMATION"],
            )
            self.assertIn(
                "label transfer wrap application product flow",
                seen_queries["PACKAGING_MACHINE_BUILDING"],
            )
            self.assertIn(
                "in-running nip pinch crush guarding hazardous energy",
                seen_queries["MACHINE_SAFETY"],
            )
            self.assertEqual(
                len({
                    row["query_sha256"]
                    for row in snapshot["traditions"]
                }),
                7,
            )

            first = snapshot["traditions"][0]["hits"]
            self.assertEqual(
                [row["source_lane"] for row in first],
                ["AUTHORITATIVE", "PROFESSIONAL_PRACTICE", "FIELD_CHATTER"],
            )
            self.assertEqual(first[2]["permitted_effect"], "HYPOTHESIS_ONLY")

    def test_runtime_tree_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code, data = self.runtime_fixture(root)

            with self.assertRaises(tc.TraditionContextError) as ctx:
                tc.load_tradition_context(
                    repo_root=root,
                    code_root=code,
                    data_root=data,
                    evidence="x",
                    frontier_snapshot=FRONTIER,
                    tree_resolver=lambda _: "different-tree",
                    retriever=lambda *args, **kwargs: fake_bundle("X"),
                )

            self.assertIn(
                "TRADITION_RUNTIME_REPO_TREE_MISMATCH",
                ctx.exception.violations,
            )

    def test_non_none_authority_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code, data = self.runtime_fixture(root)
            manifest = json.loads(
                (code / "deployment-manifest.json").read_text(encoding="utf-8")
            )
            manifest["cad_write_authority"] = "WRITE"
            (code / "deployment-manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            status = tc.tradition_runtime_status(
                repo_root=root,
                code_root=code,
                data_root=data,
                tree_resolver=lambda _: "tree123",
            )

            self.assertEqual(status["status"], "unavailable")
            self.assertIn(
                "TRADITION_RUNTIME_CAD_WRITE_AUTHORITY_NOT_NONE",
                status["violations"],
            )

    def test_render_explicitly_blocks_evidence_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code, data = self.runtime_fixture(root)
            snapshot = tc.load_tradition_context(
                repo_root=root,
                code_root=code,
                data_root=data,
                evidence="- Capture motion is unresolved.",
                frontier_snapshot=FRONTIER,
                tree_resolver=lambda _: "tree123",
                retriever=lambda data_root, tradition_id, *args: fake_bundle(
                    tradition_id
                ),
            )

            rendered = tc.render_tradition_context(snapshot)
            self.assertIn("UNADMITTED advisory context", rendered)
            self.assertIn("Do NOT copy Tradition-RAG text into claims_used", rendered)
            self.assertIn("FIELD_CHATTER has a hard HYPOTHESIS_ONLY effect ceiling", rendered)
            self.assertIn("frontier", rendered.lower())


if __name__ == "__main__":
    unittest.main()
