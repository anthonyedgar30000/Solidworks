import argparse
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
RDB = HERE / "reasoning_db.py"
DEFAULT_DB = HERE / "reasoning.db"


def run_rdb(*args):
    cmd = [sys.executable, str(RDB), *args]
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def get_db_row(db, sql, params):
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        return c.execute(sql, params).fetchone()


def observation_exists(db, obs_id):
    return get_db_row(
        db,
        "SELECT id FROM observations WHERE id=?",
        (obs_id,),
    ) is not None


def linked_assertion(db, obs_id, world, subject, predicate, obj):
    return get_db_row(
        db,
        """
        SELECT id
        FROM assertions
        WHERE source_observation_id=?
          AND world_id=?
          AND subject_entity_id=?
          AND predicate=?
          AND object_entity_id=?
        ORDER BY recorded_at
        LIMIT 1
        """,
        (obs_id, world, subject, predicate, obj),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--object", required=True)
    ap.add_argument("--input")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()

    db = Path(args.db)

    if args.input:
        envelope = json.loads(
            Path(args.input).read_text(encoding="utf-8-sig")
        )
    else:
        envelope = json.load(sys.stdin)

    # ------------------------------------------------------------
    # 1. Validate CAD result envelope
    # ------------------------------------------------------------

    if envelope.get("ok") is not True:
        raise SystemExit("Refusing to ingest unsuccessful CAD result.")

    if envelope.get("command_id") != "sw.closest_distance_pair":
        raise SystemExit(
            f"Unsupported command_id: {envelope.get('command_id')}"
        )

    if envelope.get("source_classification") != "verified_from_solidworks_api":
        raise SystemExit("CAD result is not API-verified.")

    data = envelope.get("data") or {}

    if data.get("api") != "IModelDoc2.ClosestDistance":
        raise SystemExit("Unexpected CAD API source.")

    if data.get("write_authority") != "NONE":
        raise SystemExit("Unexpected write authority in read observation.")

    distance = data.get("minimum_distance_mm")

    if not isinstance(distance, (int, float)) or not math.isfinite(distance):
        raise SystemExit("minimum_distance_mm is missing or invalid.")

    if distance < 0:
        raise SystemExit("Negative/failed distance cannot be asserted.")

    # ------------------------------------------------------------
    # 2. Validate world/document binding
    # ------------------------------------------------------------

    world = get_db_row(
        db,
        """
        SELECT id, title, source_path, revision
        FROM worlds
        WHERE id=?
        """,
        (args.world,),
    )

    if world is None:
        raise SystemExit(f"Unknown reasoning world: {args.world}")

    document = data.get("document") or {}
    actual_title = document.get("title")
    actual_path = document.get("path")

    if actual_title != world["title"]:
        raise SystemExit(
            "WORLD/DOCUMENT MISMATCH: "
            f"world '{args.world}' expects '{world['title']}', "
            f"but CAD result came from '{actual_title}'."
        )

    if world["source_path"] and actual_path != world["source_path"]:
        raise SystemExit(
            "WORLD/DOCUMENT PATH MISMATCH: "
            f"expected '{world['source_path']}', "
            f"received '{actual_path}'."
        )

    # ------------------------------------------------------------
    # 3. Validate entity/component binding
    # ------------------------------------------------------------

    subject = get_db_row(
        db,
        """
        SELECT id, world_id, canonical_name
        FROM entities
        WHERE id=?
        """,
        (args.subject,),
    )

    obj = get_db_row(
        db,
        """
        SELECT id, world_id, canonical_name
        FROM entities
        WHERE id=?
        """,
        (args.object,),
    )

    if subject is None:
        raise SystemExit(f"Unknown subject entity: {args.subject}")

    if obj is None:
        raise SystemExit(f"Unknown object entity: {args.object}")

    if subject["world_id"] != args.world or obj["world_id"] != args.world:
        raise SystemExit("Entity/world mismatch.")

    component_a = data.get("component_a") or {}
    component_b = data.get("component_b") or {}

    if component_a.get("name2") != subject["canonical_name"]:
        raise SystemExit(
            "SUBJECT/COMPONENT MISMATCH: "
            f"entity '{args.subject}' maps to "
            f"'{subject['canonical_name']}', "
            f"but CAD returned '{component_a.get('name2')}'."
        )

    if component_b.get("name2") != obj["canonical_name"]:
        raise SystemExit(
            "OBJECT/COMPONENT MISMATCH: "
            f"entity '{args.object}' maps to "
            f"'{obj['canonical_name']}', "
            f"but CAD returned '{component_b.get('name2')}'."
        )

    # ------------------------------------------------------------
    # 4. Create deterministic observation identity
    # ------------------------------------------------------------

    identity = {
        "world": args.world,
        "subject": args.subject,
        "object": args.object,
        "command_id": envelope.get("command_id"),
        "api": data.get("api"),
        "document_title": actual_title,
        "document_path": actual_path,
        "component_a": component_a.get("name2"),
        "component_b": component_b.get("name2"),
        "minimum_distance_mm": distance,
        "closest_point_a_mm": data.get("closest_point_a_mm"),
        "closest_point_b_mm": data.get("closest_point_b_mm"),
        "metric_relation": data.get("metric_relation"),
    }

    digest = hashlib.sha256(
        canonical_json(identity).encode("utf-8")
    ).hexdigest()

    obs_id = "obs-cad-" + digest[:32]

    reused_observation = observation_exists(db, obs_id)

    # ------------------------------------------------------------
    # 5. Append observation only if new
    # ------------------------------------------------------------

    if not reused_observation:
        run_rdb(
            "observe",
            "--id", obs_id,
            "--world", args.world,
            "--source-class", "verified_solidworks_api",
            "--source-ref",
            "CadGrounded.SolidWorksWorker:IModelDoc2.ClosestDistance",
            "--payload",
            canonical_json(envelope),
            "--mapped",
        )

    # ------------------------------------------------------------
    # 6. Derive only what the measurement proves
    # ------------------------------------------------------------

    derived = []

    if distance > 0:
        existing = linked_assertion(
            db,
            obs_id,
            args.world,
            args.subject,
            "physically_interferes",
            args.object,
        )

        if existing:
            assertion_id = existing["id"]
            reused_assertion = True
        else:
            assertion_id = run_rdb(
                "assert",
                "--world", args.world,
                "--subject", args.subject,
                "--predicate", "physically_interferes",
                "--object", args.object,
                "--false-support",
                "--evidence", "verified_solidworks_api",
                "--observation", obs_id,
            )
            reused_assertion = False

        derived.append({
            "assertion_id": assertion_id,
            "predicate": "physically_interferes",
            "truth_support": "false",
            "reused": reused_assertion,
        })

    else:
        derived.append({
            "assertion_id": None,
            "reason":
                "zero distance is ambiguous between contact and overlap; "
                "independent topology/interference evidence is required",
        })

    print(json.dumps({
        "world": args.world,
        "document": actual_title,
        "observation_id": obs_id,
        "observation_reused": reused_observation,
        "minimum_distance_mm": distance,
        "derived": derived,
    }, indent=2))


if __name__ == "__main__":
    main()
