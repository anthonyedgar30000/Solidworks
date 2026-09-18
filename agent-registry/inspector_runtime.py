#!/usr/bin/env python3
"""Read-only persistence and ranking core for CADGrounded Inspector v0.1.

This module deliberately accepts a completed observer envelope only.  It does
not open SOLIDWORKS, execute CAD commands, or grant mechanical acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "reasoning-db" / "schema.sql"


class InspectorError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def connect(db: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    with connect(db) as connection:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))


def _payload(envelope: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(envelope, dict):
        raise InspectorError("Inspector envelope must be an object.")
    for key in ("data", "result"):
        candidate = envelope.get(key)
        if isinstance(candidate, dict):
            return candidate
    return envelope


def _component_value(component: Dict[str, Any], modern: str, legacy: str = None) -> Any:
    if modern in component:
        return component[modern]
    return component.get(legacy) if legacy else None


def normalize_snapshot(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and canonicalize a read-only component snapshot envelope."""
    if envelope.get("ok") is False:
        raise InspectorError("Refusing an unsuccessful observer envelope.")

    payload = _payload(envelope)
    source = payload.get("source_classification") or envelope.get("source_classification")
    if source != "verified_from_solidworks_api":
        raise InspectorError("Inspector requires verified_from_solidworks_api evidence.")

    write_authority = payload.get("write_authority") or envelope.get("write_authority")
    if write_authority != "NONE":
        raise InspectorError("Inspector accepts only write_authority=NONE snapshots.")

    document = payload.get("document") or payload.get("active_document")
    if not isinstance(document, dict) or not document.get("title"):
        # The existing bridge component query supplies document_title separately.
        document = {
            "title": payload.get("document_title"),
            "path": payload.get("document_path"),
            "active_configuration": payload.get("active_configuration"),
        }
    if not document.get("title"):
        raise InspectorError("Snapshot document title is required.")

    raw_components = payload.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise InspectorError("Snapshot must contain at least one component.")

    components: List[Dict[str, Any]] = []
    seen = set()
    for raw in raw_components:
        if not isinstance(raw, dict):
            raise InspectorError("Each component record must be an object.")
        name2 = raw.get("name2")
        if not isinstance(name2, str) or not name2:
            raise InspectorError("Every component requires an exact Name2 identity.")
        if name2 in seen:
            raise InspectorError("Duplicate Component2.Name2: " + name2)
        seen.add(name2)
        components.append({
            "name2": name2,
            "path": raw.get("path"),
            "parent_name": raw.get("parent_name"),
            "fixed_component": _component_value(raw, "fixed_component", "fixed"),
            "suppression_state": _component_value(raw, "suppression_state", "suppressed"),
            "translation_mm": raw.get("translation_mm"),
            "rotation9": raw.get("rotation9"),
        })

    components.sort(key=lambda component: component["name2"])
    document_out = {
        "title": document["title"],
        "path": document.get("path"),
        "active_configuration": document.get("active_configuration") or document.get("configuration"),
    }
    fingerprint_material = {"document": document_out, "components": components}
    return {
        "document": document_out,
        "components": components,
        "source_classification": source,
        "write_authority": write_authority,
        "state_fingerprint": sha256_json(fingerprint_material),
        "input_sha256": sha256_json(envelope),
    }


def changed_components(previous: Iterable[Dict[str, Any]], current: Iterable[Dict[str, Any]]) -> List[str]:
    before = {component["name2"]: component for component in previous}
    after = {component["name2"]: component for component in current}
    return sorted(
        name for name in set(before).union(after)
        if before.get(name) != after.get(name)
    )


def record_snapshot(db: Path, world_id: str, envelope: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = normalize_snapshot(envelope)
    init_db(db)
    with connect(db) as connection:
        world = connection.execute(
            "SELECT title, source_path FROM worlds WHERE id=?", (world_id,)
        ).fetchone()
        if world is None:
            raise InspectorError("Unknown world: " + world_id)
        if world["title"] != snapshot["document"]["title"]:
            raise InspectorError("WORLD/DOCUMENT MISMATCH")
        if world["source_path"] and world["source_path"] != snapshot["document"]["path"]:
            raise InspectorError("WORLD/DOCUMENT PATH MISMATCH")

        existing = connection.execute(
            "SELECT id FROM inspection_runs WHERE world_id=? AND state_fingerprint=?",
            (world_id, snapshot["state_fingerprint"]),
        ).fetchone()
        if existing:
            return {
                "run_id": existing["id"],
                "reused": True,
                "state_fingerprint": snapshot["state_fingerprint"],
                "changed_components": [],
            }

        previous_row = connection.execute(
            "SELECT id FROM inspection_runs WHERE world_id=? ORDER BY captured_at DESC LIMIT 1",
            (world_id,),
        ).fetchone()
        prior_components: List[Dict[str, Any]] = []
        if previous_row:
            rows = connection.execute(
                "SELECT component_json FROM inspection_components WHERE run_id=?",
                (previous_row["id"],),
            ).fetchall()
            prior_components = [json.loads(row["component_json"]) for row in rows]

        run_id = "run-" + snapshot["state_fingerprint"][:32]
        connection.execute(
            "INSERT INTO inspection_runs("
            "id,world_id,captured_at,source_classification,write_authority,"
            "document_title,document_path,active_configuration,state_fingerprint,input_sha256,metadata_json"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id, world_id, utc_now(), snapshot["source_classification"], "NONE",
                snapshot["document"]["title"], snapshot["document"]["path"],
                snapshot["document"]["active_configuration"], snapshot["state_fingerprint"],
                snapshot["input_sha256"], canonical_json({"component_count": len(snapshot["components"])}),
            ),
        )
        for component in snapshot["components"]:
            connection.execute(
                "INSERT INTO inspection_components("
                "run_id,component_name2,component_path,parent_name,fixed_component,"
                "suppression_state,component_json) VALUES(?,?,?,?,?,?,?)",
                (
                    run_id, component["name2"], component["path"], component["parent_name"],
                    None if component["fixed_component"] is None else int(bool(component["fixed_component"])),
                    None if component["suppression_state"] is None else str(component["suppression_state"]),
                    canonical_json(component),
                ),
            )

        return {
            "run_id": run_id,
            "reused": False,
            "state_fingerprint": snapshot["state_fingerprint"],
            "changed_components": changed_components(prior_components, snapshot["components"]),
        }


def rank_next_tests(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank declared test candidates by the project’s deterministic value rule."""
    ranked = []
    required = ("id", "dependency_centrality", "discrimination_power", "evidence_confidence", "unresolved_relevance", "cost")
    for candidate in candidates:
        missing = [key for key in required if key not in candidate]
        if missing:
            raise InspectorError("Test candidate missing: " + ", ".join(missing))
        values = {key: candidate[key] for key in required[1:]}
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values.values()):
            raise InspectorError("Test candidate scores must be finite numbers.")
        if values["cost"] <= 0:
            raise InspectorError("Test candidate cost must be greater than zero.")
        score = (
            values["dependency_centrality"] * values["discrimination_power"] *
            values["evidence_confidence"] * values["unresolved_relevance"] /
            values["cost"]
        )
        ranked.append({**candidate, "value_score": score})
    return sorted(ranked, key=lambda item: (-item["value_score"], item["id"]))


def cmd_snapshot(args: argparse.Namespace) -> None:
    envelope = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    print(json.dumps(record_snapshot(args.db, args.world, envelope), indent=2))


def cmd_rank(args: argparse.Namespace) -> None:
    candidates = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    if not isinstance(candidates, list):
        raise InspectorError("Candidate file must contain a JSON list.")
    print(json.dumps(rank_next_tests(candidates), indent=2))


def cmd_selftest(args: argparse.Namespace) -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        db = Path(temporary) / "inspector.db"
        init_db(db)
        with connect(db) as connection:
            connection.execute(
                "INSERT INTO worlds(id,title,source_path,created_at) VALUES(?,?,?,?)",
                ("w", "ASSEMBLY", "C:\\fixture.SLDASM", utc_now()),
            )
        envelope = {
            "ok": True,
            "source_classification": "verified_from_solidworks_api",
            "write_authority": "NONE",
            "data": {
                "document": {"title": "ASSEMBLY", "path": "C:\\fixture.SLDASM"},
                "components": [
                    {"name2": "B-1", "fixed_component": True, "translation_mm": [1, 2, 3], "rotation9": [1] * 9},
                    {"name2": "A-1", "fixed_component": False, "translation_mm": [4, 5, 6], "rotation9": [1] * 9},
                ],
                "source_classification": "verified_from_solidworks_api",
                "write_authority": "NONE",
            },
        }
        first = record_snapshot(db, "w", envelope)
        assert not first["reused"] and first["changed_components"] == ["A-1", "B-1"]
        second = record_snapshot(db, "w", envelope)
        assert second["reused"]
        envelope["data"]["components"][0]["translation_mm"] = [2, 2, 3]
        third = record_snapshot(db, "w", envelope)
        assert third["changed_components"] == ["B-1"]
        top = rank_next_tests([
            {"id": "low", "dependency_centrality": 1, "discrimination_power": 1, "evidence_confidence": 1, "unresolved_relevance": 1, "cost": 2},
            {"id": "high", "dependency_centrality": 2, "discrimination_power": 2, "evidence_confidence": 1, "unresolved_relevance": 1, "cost": 1},
        ])
        assert top[0]["id"] == "high"
    print("PASS: inspector runtime self-test; read-only snapshots + incremental invalidation + test ranking")


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CADGrounded Inspector v0.1 read-only runtime")
    parser.add_argument("--db", type=Path, default=HERE / "reasoning-db" / "reasoning.db")
    sub = parser.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--world", required=True)
    snapshot.add_argument("--input", required=True)
    snapshot.set_defaults(func=cmd_snapshot)
    rank = sub.add_parser("rank-next-test")
    rank.add_argument("--input", required=True)
    rank.set_defaults(func=cmd_rank)
    sub.add_parser("selftest").set_defaults(func=cmd_selftest)
    return parser


def main() -> int:
    args = parser().parse_args()
    try:
        args.func(args)
        return 0
    except (InspectorError, OSError, sqlite3.Error, json.JSONDecodeError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
