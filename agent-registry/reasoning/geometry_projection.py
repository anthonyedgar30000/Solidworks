#!/usr/bin/env python3
"""Project safe deterministic geometry facts from admitted identity evidence.

This layer performs only arithmetic on observation-backed approximate axis-aligned
bounding boxes (GetBox-derived fields) and observed transforms. It does not call
SOLIDWORKS, mutate CAD, infer exact body contact, infer interference, or grant
mechanical acceptance.

The output is intentionally conservative:
- observed transforms/envelopes may become KNOWN facts;
- AABB separations/overlaps may become MEASURED_CALCULATED facts;
- contact, clearance acceptance, functional suitability, and operating geometry
  remain unresolved until stronger deterministic checks establish them.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


class GeometryProjectionError(RuntimeError):
    pass


REQUIRED_ROLES = (
    "AR60_ROLLER",
    "AR60_CARRIAGE",
    "CONVEYOR",
    "BOTTLE_1",
    "BOTTLE_2",
    "BOTTLE_3",
    "BOTTLE_4",
    "BOTTLE_5",
)


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise GeometryProjectionError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GeometryProjectionError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GeometryProjectionError(f"Top-level JSON must be an object: {path}")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GeometryProjectionError(f"{label} must be numeric")
    if not math.isfinite(float(value)):
        raise GeometryProjectionError(f"{label} must be finite")
    return float(value)


def _vec3(value: Any, label: str) -> Tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise GeometryProjectionError(f"{label} must be a 3-element array")
    return tuple(_number(v, f"{label}[{i}]") for i, v in enumerate(value))  # type: ignore[return-value]


def _validate_identity_evidence(tx: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    if tx.get("transaction_type") != "semantic_identity_binding":
        raise GeometryProjectionError("Expected semantic_identity_binding transaction")
    if tx.get("mechanical_acceptance_granted") is not False:
        raise GeometryProjectionError("Identity evidence unexpectedly grants mechanical acceptance")

    roles = tx.get("resolved_roles")
    if not isinstance(roles, dict):
        raise GeometryProjectionError("resolved_roles must be an object")

    for role in REQUIRED_ROLES:
        record = roles.get(role)
        if not isinstance(record, dict):
            raise GeometryProjectionError(f"Required role missing: {role}")
        if record.get("identity_status") != "VERIFIED_FROM_SOLIDWORKS":
            raise GeometryProjectionError(f"Role {role} is not verified from SOLIDWORKS")
        name2 = record.get("component_name2")
        if not isinstance(name2, str) or not name2:
            raise GeometryProjectionError(f"Role {role} has no exact component_name2")

    return roles  # type: ignore[return-value]


def _aabb(record: Dict[str, Any], role: str) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    mn = _vec3(record.get("box_min_mm"), f"{role}.box_min_mm")
    mx = _vec3(record.get("box_max_mm"), f"{role}.box_max_mm")
    for axis, lo, hi in zip("XYZ", mn, mx):
        if lo > hi:
            raise GeometryProjectionError(
                f"{role} invalid AABB on {axis}: min {lo} > max {hi}"
            )
    return mn, mx


def _axis_gap(a_min: float, a_max: float, b_min: float, b_max: float) -> float:
    if a_max < b_min:
        return b_min - a_max
    if b_max < a_min:
        return a_min - b_max
    return 0.0


def _overlap_extent(a_min: float, a_max: float, b_min: float, b_max: float) -> float:
    return max(0.0, min(a_max, b_max) - max(a_min, b_min))


def pair_metrics(
    role_a: str,
    record_a: Dict[str, Any],
    role_b: str,
    record_b: Dict[str, Any],
) -> Dict[str, Any]:
    a_min, a_max = _aabb(record_a, role_a)
    b_min, b_max = _aabb(record_b, role_b)

    gaps = [
        _axis_gap(a_min[i], a_max[i], b_min[i], b_max[i])
        for i in range(3)
    ]
    overlaps = [
        _overlap_extent(a_min[i], a_max[i], b_min[i], b_max[i])
        for i in range(3)
    ]

    intersects_or_touches = all(g == 0.0 for g in gaps)
    positive_volume_aabb_overlap = all(o > 0.0 for o in overlaps)

    return {
        "role_a": role_a,
        "role_b": role_b,
        "axis_gap_mm": {"x": gaps[0], "y": gaps[1], "z": gaps[2]},
        "minimum_aabb_separation_mm": math.sqrt(sum(g * g for g in gaps)),
        "aabb_intersects_or_touches": intersects_or_touches,
        "positive_volume_aabb_overlap": positive_volume_aabb_overlap,
        "overlap_extent_mm": {"x": overlaps[0], "y": overlaps[1], "z": overlaps[2]},
    }


def _observed_role_fact(role: str, record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "state": "KNOWN",
        "authority": "SOLIDWORKS_LIVE_STATE",
        "component_name2": record.get("component_name2"),
        "translation_mm": record.get("translation_mm"),
        "rotation9": record.get("rotation9"),
        "transform_array": record.get("transform_array"),
        "transform_source": record.get("transform_source"),
        "box_min_mm": record.get("box_min_mm"),
        "box_max_mm": record.get("box_max_mm"),
        "geometry_note": record.get("geometry_note"),
        "source_classification": record.get("source_classification"),
    }


def build_projection(tx: Dict[str, Any]) -> Dict[str, Any]:
    roles = _validate_identity_evidence(tx)

    ar60 = roles["AR60_ROLLER"]
    carriage = roles["AR60_CARRIAGE"]
    conveyor = roles["CONVEYOR"]
    bottle_roles = [f"BOTTLE_{i}" for i in range(1, 6)]

    bottle_metrics = [
        pair_metrics("AR60_ROLLER", ar60, bottle_role, roles[bottle_role])
        for bottle_role in bottle_roles
    ]
    nearest_bottle = min(
        bottle_metrics,
        key=lambda item: item["minimum_aabb_separation_mm"],
    )

    carriage_metrics = pair_metrics("AR60_ROLLER", ar60, "AR60_CARRIAGE", carriage)
    conveyor_metrics = pair_metrics("AR60_ROLLER", ar60, "CONVEYOR", conveyor)

    all_bottles_disjoint = all(
        not metric["aabb_intersects_or_touches"] for metric in bottle_metrics
    )

    observed_facts = {
        role: _observed_role_fact(role, roles[role])
        for role in REQUIRED_ROLES
    }

    calculated_facts = {
        "AR60_NEAREST_BOTTLE_AABB_SEPARATION": {
            "state": "KNOWN",
            "authority": "MEASURED_CALCULATED",
            "derivation": "deterministic AABB arithmetic on admitted SOLIDWORKS observation",
            "nearest_bottle_role": nearest_bottle["role_b"],
            "minimum_aabb_separation_mm": nearest_bottle["minimum_aabb_separation_mm"],
            "axis_gap_mm": nearest_bottle["axis_gap_mm"],
        },
        "AR60_AABB_DISJOINT_FROM_ALL_BOTTLES": {
            "state": "KNOWN",
            "authority": "MEASURED_CALCULATED",
            "derivation": "deterministic AABB arithmetic on admitted SOLIDWORKS observation",
            "value": all_bottles_disjoint,
            "per_bottle": bottle_metrics,
        },
        "AR60_CARRIAGE_AABB_RELATION": {
            "state": "KNOWN",
            "authority": "MEASURED_CALCULATED",
            "derivation": "deterministic AABB arithmetic on admitted SOLIDWORKS observation",
            **carriage_metrics,
            "engineering_limit": "AABB overlap is not proof of body interference or mechanical fit.",
        },
        "AR60_CONVEYOR_AABB_RELATION": {
            "state": "KNOWN",
            "authority": "MEASURED_CALCULATED",
            "derivation": "deterministic AABB arithmetic on admitted SOLIDWORKS observation",
            **conveyor_metrics,
            "engineering_limit": "AABB separation/overlap is not a precise clearance or interference result.",
        },
    }

    return {
        "transaction_type": "deterministic_geometry_projection",
        "schema_version": 1,
        "document": tx.get("document"),
        "source_evidence": tx.get("source_evidence"),
        "mechanical_acceptance_granted": False,
        "authority": {
            "classification": "MEASURED_CALCULATED",
            "basis": "admitted SOLIDWORKS identity evidence plus deterministic AABB arithmetic",
            "limitations": [
                "GetBox-derived envelopes are approximate axis-aligned bounding boxes.",
                "AABB overlap does not prove body interference.",
                "AABB separation does not establish exact surface clearance.",
                "No contact, seating, restraint, product-flow, or operating-sequence claim is established here.",
            ],
        },
        "observed_facts": observed_facts,
        "calculated_facts": calculated_facts,
        "unresolved_mechanical_claims": [
            "AR60_CONTACT_POSITION",
            "CONTACT_REACHABLE_WITHIN_TRAVEL",
            "BOTTLE_CONTACT_ACHIEVABLE",
            "NO_CONVEYOR_INTERFERENCE",
            "VALID_APPLICATION_GEOMETRY",
            "V21_ACCEPTANCE",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project deterministic AABB facts from admitted v21 identity evidence."
    )
    parser.add_argument("identity_evidence", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    tx = load_json(args.identity_evidence)
    try:
        result = build_projection(tx)
    except GeometryProjectionError as exc:
        raise SystemExit(f"REJECTED: {exc}") from exc

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if args.summary:
        nearest = result["calculated_facts"]["AR60_NEAREST_BOTTLE_AABB_SEPARATION"]
        carriage = result["calculated_facts"]["AR60_CARRIAGE_AABB_RELATION"]
        all_disjoint = result["calculated_facts"]["AR60_AABB_DISJOINT_FROM_ALL_BOTTLES"]
        print(f"DOCUMENT: {result['document']['title']}")
        print(f"NEAREST BOTTLE: {nearest['nearest_bottle_role']}")
        print(f"MIN AABB SEPARATION: {nearest['minimum_aabb_separation_mm']:.3f} mm")
        gaps = nearest["axis_gap_mm"]
        print(f"AXIS GAPS: X={gaps['x']:.3f} Y={gaps['y']:.3f} Z={gaps['z']:.3f} mm")
        print(f"AR60 DISJOINT FROM ALL BOTTLE AABBs: {all_disjoint['value']}")
        print(
            "AR60/CARRIAGE POSITIVE-VOLUME AABB OVERLAP: "
            f"{carriage['positive_volume_aabb_overlap']}"
        )
        print("MECHANICAL ACCEPTANCE: NOT GRANTED")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
