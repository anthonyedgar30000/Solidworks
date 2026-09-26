#!/usr/bin/env python3
"""Incremental evidence runtime for CADGrounded.

This module is read-only with respect to SOLIDWORKS. It consumes already-admitted
SOLIDWORKS observation transactions and immutable EvidenceRecords, persists
inspection/fingerprint indexes in the existing reasoning DB, and derives a
current-state validity projection. It never mutates an EvidenceRecord, calls
SOLIDWORKS, grants CAD write authority, or grants mechanical acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
SCHEMA = HERE.parent / "reasoning-db" / "schema.sql"

COMPONENT_FINGERPRINT_FIELDS = (
    "name2",
    "path",
    "parent_name",
    "is_top_level",
    "referenced_configuration",
    "fixed",
    "suppressed",
    "suppression_state",
    "translation_mm",
    "translation_m",
    "rotation9",
    "scale",
    "transform_array",
    "transform_source",
    "getbox_mm",
    "getbox_m",
    "box_min_mm",
    "box_max_mm",
    "bounding_box_mm_approx",
    "field_errors",
)


class IncrementalEvidenceError(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IncrementalEvidenceError(f"{label} must be a non-empty string")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _nonempty(value, label)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise IncrementalEvidenceError(f"{label} must be a lowercase SHA-256 hex digest")
    return text


@contextmanager
def db_conn(db: Path):
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    with db_conn(db) as connection:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))


def validate_observation_transaction(transaction: Any) -> dict[str, Any]:
    if not isinstance(transaction, dict):
        raise IncrementalEvidenceError("observation transaction must be an object")
    if transaction.get("transaction_type") != "cad_observation_evidence":
        raise IncrementalEvidenceError("expected cad_observation_evidence transaction")
    if transaction.get("source_authority") != "SOLIDWORKS_LIVE_STATE":
        raise IncrementalEvidenceError("inspection requires SOLIDWORKS_LIVE_STATE authority")
    if transaction.get("source_classification") != "verified_from_solidworks_api":
        raise IncrementalEvidenceError("inspection requires verified_from_solidworks_api evidence")
    if transaction.get("mechanical_acceptance_granted") is not False:
        raise IncrementalEvidenceError("inspection input may not grant mechanical acceptance")

    document = transaction.get("document")
    if not isinstance(document, dict):
        raise IncrementalEvidenceError("transaction.document must be an object")
    _nonempty(document.get("title"), "document.title")
    _nonempty(document.get("path"), "document.path")

    raw = transaction.get("raw_observation")
    if not isinstance(raw, dict):
        raise IncrementalEvidenceError("transaction.raw_observation must be an object")
    _sha256(raw.get("sha256"), "raw_observation.sha256")
    _nonempty(raw.get("recorded_at"), "raw_observation.recorded_at")

    components = transaction.get("components")
    if not isinstance(components, list) or not components:
        raise IncrementalEvidenceError("transaction.components must be a non-empty array")
    seen: set[str] = set()
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise IncrementalEvidenceError(f"components[{index}] must be an object")
        name2 = _nonempty(component.get("name2"), f"components[{index}].name2")
        if name2 in seen:
            raise IncrementalEvidenceError(f"duplicate Component2.Name2 identity: {name2}")
        seen.add(name2)
    return transaction


def component_state(component: dict[str, Any]) -> dict[str, Any]:
    return {field: component.get(field) for field in COMPONENT_FINGERPRINT_FIELDS}


def component_fingerprint(component: dict[str, Any]) -> str:
    return sha256_json(component_state(component))


def build_inspection_run(transaction: dict[str, Any]) -> dict[str, Any]:
    validate_observation_transaction(transaction)
    document = transaction["document"]
    raw = transaction["raw_observation"]
    components = []
    for component in transaction["components"]:
        state = component_state(component)
        components.append(
            {
                "name2": component["name2"],
                "fingerprint": sha256_json(state),
                "state": state,
            }
        )
    components.sort(key=lambda item: item["name2"])

    document_state = {
        "title": document["title"],
        "path": document["path"],
        "active_configuration": document.get("active_configuration")
        or document.get("configuration"),
    }
    state_fingerprint = sha256_json(
        {
            "document": document_state,
            "components": [
                {"name2": item["name2"], "fingerprint": item["fingerprint"]}
                for item in components
            ],
        }
    )
    observation_sha256 = raw["sha256"]
    return {
        "run_id": f"inspection:{observation_sha256}",
        "recorded_at": raw["recorded_at"],
        "source_authority": transaction["source_authority"],
        "source_classification": transaction["source_classification"],
        "document": document_state,
        "observation_sha256": observation_sha256,
        "state_fingerprint": state_fingerprint,
        "components": components,
        "mechanical_acceptance_granted": False,
    }


def _require_world(
    connection: sqlite3.Connection, world_id: str, document: dict[str, Any]
) -> None:
    row = connection.execute(
        "SELECT id,source_path FROM worlds WHERE id=?", (world_id,)
    ).fetchone()
    if row is None:
        raise IncrementalEvidenceError(f"unknown reasoning world: {world_id}")
    if row["source_path"] and row["source_path"] != document["path"]:
        raise IncrementalEvidenceError(
            "world source_path does not match exact observed SOLIDWORKS document path"
        )


def record_inspection_run(
    db: Path, world_id: str, transaction: dict[str, Any]
) -> dict[str, Any]:
    run = build_inspection_run(transaction)
    init_db(db)
    with db_conn(db) as connection:
        _require_world(connection, world_id, run["document"])
        existing = connection.execute(
            "SELECT id,state_fingerprint FROM inspection_runs "
            "WHERE world_id=? AND observation_sha256=?",
            (world_id, run["observation_sha256"]),
        ).fetchone()
        if existing:
            if existing["state_fingerprint"] != run["state_fingerprint"]:
                raise IncrementalEvidenceError(
                    "same observation SHA-256 maps to conflicting inspection state"
                )
            return {
                "run_id": existing["id"],
                "reused_source_artifact": True,
                "state_fingerprint": existing["state_fingerprint"],
            }

        connection.execute(
            "INSERT INTO inspection_runs("
            "id,world_id,recorded_at,source_authority,source_classification,"
            "document_title,document_path,active_configuration,observation_sha256,"
            "state_fingerprint,metadata_json"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                run["run_id"],
                world_id,
                run["recorded_at"],
                run["source_authority"],
                run["source_classification"],
                run["document"]["title"],
                run["document"]["path"],
                run["document"]["active_configuration"],
                run["observation_sha256"],
                run["state_fingerprint"],
                canonical_json({"mechanical_acceptance_granted": False}),
            ),
        )
        for component in run["components"]:
            connection.execute(
                "INSERT INTO inspection_component_fingerprints("
                "run_id,component_name2,component_fingerprint,state_json"
                ") VALUES(?,?,?,?)",
                (
                    run["run_id"],
                    component["name2"],
                    component["fingerprint"],
                    canonical_json(component["state"]),
                ),
            )
    return {
        "run_id": run["run_id"],
        "reused_source_artifact": False,
        "state_fingerprint": run["state_fingerprint"],
    }


def _load_run(
    connection: sqlite3.Connection, world_id: str, run_id: str
) -> tuple[sqlite3.Row, dict[str, str]]:
    row = connection.execute(
        "SELECT * FROM inspection_runs WHERE world_id=? AND id=?",
        (world_id, run_id),
    ).fetchone()
    if row is None:
        raise IncrementalEvidenceError(f"unknown inspection run: {run_id}")
    components = {
        item["component_name2"]: item["component_fingerprint"]
        for item in connection.execute(
            "SELECT component_name2,component_fingerprint "
            "FROM inspection_component_fingerprints WHERE run_id=?",
            (run_id,),
        ).fetchall()
    }
    return row, components


def diff_runs(
    db: Path, world_id: str, previous_run_id: str, current_run_id: str
) -> dict[str, Any]:
    init_db(db)
    with db_conn(db) as connection:
        previous, before = _load_run(connection, world_id, previous_run_id)
        current, after = _load_run(connection, world_id, current_run_id)

    if previous["document_title"] != current["document_title"]:
        raise IncrementalEvidenceError("document title changed; refusing cross-document delta")
    if previous["document_path"] != current["document_path"]:
        raise IncrementalEvidenceError("document path changed; refusing cross-document delta")

    changed_components = sorted(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    keys = [f"component_name2:{name}" for name in changed_components]

    if previous["active_configuration"] != current["active_configuration"]:
        for value in (previous["active_configuration"], current["active_configuration"]):
            if value:
                keys.append(f"configuration:{value}")

    return {
        "previous_run_id": previous_run_id,
        "current_run_id": current_run_id,
        "same_state_fingerprint": previous["state_fingerprint"]
        == current["state_fingerprint"],
        "changed_components": changed_components,
        "changed_dependency_keys": sorted(set(keys)),
    }


def validate_evidence_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise IncrementalEvidenceError("EvidenceRecord must be an object")
    if record.get("record_type") != "evidence":
        raise IncrementalEvidenceError("record_type must be evidence")
    _nonempty(record.get("evidence_id"), "evidence_id")
    dependencies = record.get("dependencies")
    if not isinstance(dependencies, list):
        raise IncrementalEvidenceError("EvidenceRecord.dependencies must be an array")
    if len(dependencies) != len(set(dependencies)):
        raise IncrementalEvidenceError("EvidenceRecord.dependencies must be unique")
    for index, dependency in enumerate(dependencies):
        _nonempty(dependency, f"dependencies[{index}]")
    if record.get("mechanical_acceptance_granted") is not False:
        raise IncrementalEvidenceError(
            "EvidenceRecord may not grant mechanical acceptance"
        )
    scope = record.get("temporal_scope")
    if scope is not None and not isinstance(scope, dict):
        raise IncrementalEvidenceError("temporal_scope must be an object when present")
    return record


def index_evidence_record(
    db: Path, world_id: str, record: dict[str, Any]
) -> dict[str, Any]:
    validate_evidence_record(record)
    init_db(db)
    evidence_id = record["evidence_id"]
    record_sha256 = sha256_json(record)
    scope = record.get("temporal_scope") or {}
    validity = scope.get("validity_state", "UNKNOWN")
    if validity not in {"CURRENT", "STALE", "UNKNOWN"}:
        raise IncrementalEvidenceError(f"invalid temporal validity_state: {validity}")

    with db_conn(db) as connection:
        if connection.execute("SELECT 1 FROM worlds WHERE id=?", (world_id,)).fetchone() is None:
            raise IncrementalEvidenceError(f"unknown reasoning world: {world_id}")

        existing = connection.execute(
            "SELECT record_sha256 FROM evidence_validity_projection "
            "WHERE world_id=? AND evidence_id=?",
            (world_id, evidence_id),
        ).fetchone()
        if existing and existing["record_sha256"] != record_sha256:
            raise IncrementalEvidenceError(
                f"evidence_id {evidence_id} is already indexed with different immutable content"
            )

        connection.execute(
            "INSERT INTO evidence_validity_projection("
            "world_id,evidence_id,record_sha256,validity_state,last_invalidation_event_id,"
            "updated_at,metadata_json"
            ") VALUES(?,?,?,?,NULL,datetime('now'),?) "
            "ON CONFLICT(world_id,evidence_id) DO NOTHING",
            (
                world_id,
                evidence_id,
                record_sha256,
                validity,
                canonical_json(
                    {
                        "projection_only": True,
                        "source_temporal_scope": scope,
                        "mechanical_acceptance_granted": False,
                    }
                ),
            ),
        )
        for dependency in record["dependencies"]:
            connection.execute(
                "INSERT OR IGNORE INTO evidence_dependency_index("
                "world_id,evidence_id,dependency_key,indexed_at"
                ") VALUES(?,?,?,datetime('now'))",
                (world_id, evidence_id, dependency),
            )
    return {
        "evidence_id": evidence_id,
        "record_sha256": record_sha256,
        "dependency_count": len(record["dependencies"]),
        "validity_state": validity,
    }


def _dependency_closure(
    connection: sqlite3.Connection, world_id: str, changed_keys: Iterable[str]
) -> list[str]:
    pending_keys = list(dict.fromkeys(changed_keys))
    seen_keys: set[str] = set()
    affected: set[str] = set()

    while pending_keys:
        key = pending_keys.pop(0)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows = connection.execute(
            "SELECT evidence_id FROM evidence_dependency_index "
            "WHERE world_id=? AND dependency_key=? ORDER BY evidence_id",
            (world_id, key),
        ).fetchall()
        for row in rows:
            evidence_id = row["evidence_id"]
            if evidence_id in affected:
                continue
            affected.add(evidence_id)
            pending_keys.append(f"evidence_id:{evidence_id}")
    return sorted(affected)


def reconcile_runs(
    db: Path, world_id: str, previous_run_id: str, current_run_id: str
) -> dict[str, Any]:
    delta = diff_runs(db, world_id, previous_run_id, current_run_id)
    event_material = {
        "world_id": world_id,
        "previous_run_id": previous_run_id,
        "current_run_id": current_run_id,
        "changed_dependency_keys": delta["changed_dependency_keys"],
    }
    event_id = f"invalidation:{sha256_json(event_material)}"

    with db_conn(db) as connection:
        affected = _dependency_closure(
            connection, world_id, delta["changed_dependency_keys"]
        )
        newly_stale: list[str] = []

        connection.execute(
            "INSERT OR IGNORE INTO invalidation_events("
            "id,world_id,previous_run_id,current_run_id,changed_dependency_keys_json,"
            "affected_evidence_ids_json,created_at,metadata_json"
            ") VALUES(?,?,?,?,?,?,datetime('now'),?)",
            (
                event_id,
                world_id,
                previous_run_id,
                current_run_id,
                canonical_json(delta["changed_dependency_keys"]),
                canonical_json(affected),
                canonical_json(
                    {
                        "projection_only": True,
                        "ambiguity_bucket": "STALE_STATE",
                        "mechanical_acceptance_granted": False,
                    }
                ),
            ),
        )

        for evidence_id in affected:
            row = connection.execute(
                "SELECT validity_state FROM evidence_validity_projection "
                "WHERE world_id=? AND evidence_id=?",
                (world_id, evidence_id),
            ).fetchone()
            if row is None or row["validity_state"] != "CURRENT":
                continue
            connection.execute(
                "UPDATE evidence_validity_projection "
                "SET validity_state='STALE',last_invalidation_event_id=?,"
                "updated_at=datetime('now') WHERE world_id=? AND evidence_id=?",
                (event_id, world_id, evidence_id),
            )
            newly_stale.append(evidence_id)

    return {
        **delta,
        "invalidation_event_id": event_id,
        "affected_evidence_ids": affected,
        "newly_stale_evidence_ids": sorted(newly_stale),
        "ambiguity_bucket": "STALE_STATE" if affected else None,
        "mechanical_acceptance_granted": False,
    }


def validity_projection(db: Path, world_id: str) -> list[dict[str, Any]]:
    init_db(db)
    with db_conn(db) as connection:
        rows = connection.execute(
            "SELECT evidence_id,record_sha256,validity_state,last_invalidation_event_id "
            "FROM evidence_validity_projection WHERE world_id=? ORDER BY evidence_id",
            (world_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IncrementalEvidenceError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise IncrementalEvidenceError(f"{path}: expected a JSON object")
    return value


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CADGrounded incremental evidence runtime")
    p.add_argument("--db", type=Path, default=HERE.parent / "reasoning-db" / "reasoning.db")
    sub = p.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record-run")
    record.add_argument("--world", required=True)
    record.add_argument("--input", type=Path, required=True)

    index = sub.add_parser("index-evidence")
    index.add_argument("--world", required=True)
    index.add_argument("--input", type=Path, required=True)

    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--world", required=True)
    reconcile.add_argument("--previous-run", required=True)
    reconcile.add_argument("--current-run", required=True)

    show = sub.add_parser("show-validity")
    show.add_argument("--world", required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "record-run":
            out = record_inspection_run(args.db, args.world, _load_json(args.input))
        elif args.command == "index-evidence":
            out = index_evidence_record(args.db, args.world, _load_json(args.input))
        elif args.command == "reconcile":
            out = reconcile_runs(
                args.db, args.world, args.previous_run, args.current_run
            )
        else:
            out = validity_projection(args.db, args.world)
        print(json.dumps(out, indent=2))
        return 0
    except (IncrementalEvidenceError, sqlite3.Error, OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
