from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

LANES = ("AUTHORITATIVE", "PROFESSIONAL_PRACTICE", "FIELD_CHATTER")
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"

LANE_EFFECT = {
    "AUTHORITATIVE": "REFERENCE_WITH_SOURCE_SCOPE",
    "PROFESSIONAL_PRACTICE": "HEURISTIC_OR_TEST_IDEA_ONLY",
    "FIELD_CHATTER": "HYPOTHESIS_ONLY",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def db_path(data_root: Path, tradition_id: str) -> Path:
    return data_root / "collections" / tradition_id / "index.sqlite3"


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
          chunk_id UNINDEXED,
          source_id UNINDEXED,
          source_lane UNINDEXED,
          authority_class UNINDEXED,
          title,
          body,
          source_uri UNINDEXED,
          content_sha256 UNINDEXED,
          tokenize='unicode61'
        )
        """
    )
    return con


def load_cards(cards_path: Path) -> list[dict]:
    cards = []
    for line in cards_path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            cards.append(json.loads(line))
    return cards


def bootstrap(repo_dir: Path, data_root: Path) -> dict:
    policy = read_json(repo_dir / "traditions.v1.json")
    registry = read_json(repo_dir / "sources.v1.json")
    cards = load_cards(repo_dir / "seed" / "source_cards.v1.jsonl")
    source_by_id = {s["source_id"]: s for s in registry["sources"]}
    counts = {}

    for tradition in policy["traditions"]:
        tid = tradition["tradition_id"]
        con = open_db(db_path(data_root, tid))
        con.execute("DELETE FROM chunks_fts")
        inserted = 0
        lane_counts = {lane: 0 for lane in LANES}
        for card in cards:
            source = source_by_id[card["source_id"]]
            if tid not in source["traditions"]:
                continue
            body = card["summary"]
            content_sha = sha256_text(body)
            chunk_id = f'{card["card_id"]}:{tid}'
            con.execute(
                """
                INSERT INTO chunks_fts(
                  chunk_id, source_id, source_lane, authority_class,
                  title, body, source_uri, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    source["source_id"],
                    source["lane"],
                    source["authority_class"],
                    source["title"],
                    body,
                    source["url"],
                    content_sha,
                ),
            )
            inserted += 1
            lane_counts[source["lane"]] += 1
        con.commit()
        con.close()
        counts[tid] = {"chunks": inserted, "lanes": lane_counts}

    manifest = {
        "service_id": "CADGROUNDED.TRADITION_RAG.V1",
        "retrieval_authority": "REFERENCE_ONLY",
        "mechanical_acceptance_authority": "NONE",
        "cad_write_authority": "NONE",
        "collections": counts,
    }
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def fts_expression(question: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", question.lower())
    tokens = [t for t in tokens if len(t) > 1][:24]
    if not tokens:
        raise ValueError("Question has no searchable tokens")
    return " OR ".join(f'"{t}"' for t in tokens)


def retrieve_lane(
    con: sqlite3.Connection,
    question: str,
    lane: str,
    limit: int,
) -> list[dict]:
    expr = fts_expression(question)
    rows = con.execute(
        """
        SELECT
          chunk_id, source_id, source_lane, authority_class,
          title, body, source_uri, content_sha256,
          bm25(chunks_fts) AS bm25_score
        FROM chunks_fts
        WHERE chunks_fts MATCH ? AND source_lane = ?
        ORDER BY bm25_score
        LIMIT ?
        """,
        (expr, lane, limit),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["retrieval_score"] = -float(item.pop("bm25_score"))
        item["permitted_effect"] = LANE_EFFECT[lane]
        result.append(item)
    return result


def retrieve(
    data_root: Path,
    tradition_id: str,
    question: str,
    authoritative: int = 4,
    professional: int = 3,
    chatter: int = 3,
) -> dict:
    path = db_path(data_root, tradition_id)
    if not path.exists():
        raise FileNotFoundError(
            f"Collection {tradition_id} is not bootstrapped at {path}"
        )
    con = open_db(path)
    try:
        hits = {
            "AUTHORITATIVE": retrieve_lane(
                con, question, "AUTHORITATIVE", authoritative
            ),
            "PROFESSIONAL_PRACTICE": retrieve_lane(
                con, question, "PROFESSIONAL_PRACTICE", professional
            ),
            "FIELD_CHATTER": retrieve_lane(
                con, question, "FIELD_CHATTER", chatter
            ),
        }
    finally:
        con.close()

    return {
        "service_id": "CADGROUNDED.TRADITION_RAG.V1",
        "tradition_id": tradition_id,
        "question": question,
        "authority_boundary": {
            "retrieval_is_engineering_evidence": False,
            "mechanical_acceptance_granted": False,
            "cad_write_authority": "NONE",
            "field_chatter_effect_ceiling": "HYPOTHESIS_ONLY",
        },
        "hits": hits,
    }


def context_text(bundle: dict) -> str:
    lines = [
        "CADGrounded Tradition RAG context",
        f'Tradition: {bundle["tradition_id"]}',
        f'Question: {bundle["question"]}',
        "",
        "RULES:",
        "- Retrieval is reference context, not admitted engineering evidence.",
        "- AUTHORITATIVE material is limited to its source scope.",
        "- PROFESSIONAL_PRACTICE may inform heuristics/tests, not verify project facts.",
        "- FIELD_CHATTER may generate hypotheses/tests only.",
        "- Never infer CAD geometry, OEM intent, force/friction/stiffness, or mechanical acceptance.",
        "",
    ]
    for lane in LANES:
        lines.append(f"## {lane}")
        hits = bundle["hits"][lane]
        if not hits:
            lines.append("(no retrieved context)")
            continue
        for hit in hits:
            lines.append(
                f'[{hit["chunk_id"]}] {hit["title"]} '
                f'({hit["source_id"]}; effect={hit["permitted_effect"]})'
            )
            lines.append(hit["body"])
            lines.append(f'Source: {hit["source_uri"]}')
            lines.append("")
    return "\n".join(lines)


def ollama_generate(
    bundle: dict,
    model: str = DEFAULT_MODEL,
    ollama_base: str = DEFAULT_OLLAMA,
) -> dict:
    prompt = context_text(bundle) + """
Synthesize a bounded answer to the question using only the retrieved context.

Output requirements:
1. Separate source-grounded observations from practitioner hypotheses.
2. Cite every substantive statement with exact retrieved chunk IDs in square brackets.
3. Prefix chatter-derived ideas with "Field-practice hypothesis:".
4. Preserve unresolved facts as unresolved.
5. Do not claim project-specific verification or mechanical acceptance.
6. Do not infer requirements that are not literally supported by the retrieved chunk text.
7. A source-scope summary does not authorize you to invent detailed requirements from the underlying standard.
8. If the retrieved cards do not answer a detail, state that the detail is unresolved.
"""
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "top_p": 0.2},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        ollama_base.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
    response_text = result.get("response", "")
    known_chunk_ids = {
        hit["chunk_id"]
        for lane in LANES
        for hit in bundle["hits"][lane]
    }
    cited_chunk_ids = set(
        re.findall(r"\[([A-Za-z0-9_.:-]+)\]", response_text)
    )
    unknown_citations = sorted(cited_chunk_ids - known_chunk_ids)
    return {
        "model": model,
        "response": response_text,
        "done": result.get("done", False),
        "generation_state": "UNADMITTED_ADVISORY",
        "usable_as_engineering_evidence": False,
        "requires_review": True,
        "citation_integrity_passed": not unknown_citations,
        "unknown_citations": unknown_citations,
        "mechanical_acceptance_granted": False,
        "cad_write_authority": "NONE",
    }


def status(repo_dir: Path, data_root: Path) -> dict:
    policy = read_json(repo_dir / "traditions.v1.json")
    rows = []
    for tradition in policy["traditions"]:
        tid = tradition["tradition_id"]
        path = db_path(data_root, tid)
        counts = {lane: 0 for lane in LANES}
        total = 0
        if path.exists():
            con = open_db(path)
            for row in con.execute(
                "SELECT source_lane, count(*) AS n FROM chunks_fts GROUP BY source_lane"
            ):
                counts[row["source_lane"]] = row["n"]
                total += row["n"]
            con.close()
        rows.append(
            {
                "tradition_id": tid,
                "database": str(path),
                "chunks": total,
                "lanes": counts,
            }
        )
    return {
        "service_id": "CADGROUNDED.TRADITION_RAG.V1",
        "cad_write_authority": "NONE",
        "mechanical_acceptance_authority": "NONE",
        "collections": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CADGrounded Tradition RAG v1")
    parser.add_argument(
        "--repo-dir",
        default=str(Path(__file__).resolve().parent),
        help="Directory containing traditions.v1.json and sources.v1.json",
    )
    parser.add_argument(
        "--data-root",
        default=r"C:\CADGrounded\tradition-rag-data",
        help="Local non-repository data root",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap")
    sub.add_parser("status")

    ask = sub.add_parser("ask")
    ask.add_argument("--tradition", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--authoritative", type=int, default=4)
    ask.add_argument("--professional", type=int, default=3)
    ask.add_argument("--chatter", type=int, default=3)
    ask.add_argument("--generate", action="store_true")
    ask.add_argument("--model", default=DEFAULT_MODEL)
    ask.add_argument("--ollama-base", default=DEFAULT_OLLAMA)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_dir = Path(args.repo_dir)
    data_root = Path(args.data_root)

    if args.command == "bootstrap":
        output = bootstrap(repo_dir, data_root)
    elif args.command == "status":
        output = status(repo_dir, data_root)
    elif args.command == "ask":
        output = retrieve(
            data_root,
            args.tradition,
            args.question,
            args.authoritative,
            args.professional,
            args.chatter,
        )
        if args.generate:
            output["generation"] = ollama_generate(
                output, model=args.model, ollama_base=args.ollama_base
            )
    else:
        raise AssertionError(args.command)

    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
