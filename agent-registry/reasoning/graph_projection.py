#!/usr/bin/env python3
"""Build a runtime epistemic graph from deterministic SOLIDWORKS evidence.

This stage consumes ``deterministic_geometry_projection`` output and creates a
fresh runtime graph. It deliberately does NOT copy the illustrative numeric
placeholders from ``graph.json``.

Authority boundary:
- observation-backed transforms/envelopes -> KNOWN
- deterministic AABB arithmetic -> KNOWN / MEASURED_CALCULATED
- intended operating geometry and mechanical acceptance -> remain unresolved
- no SOLIDWORKS calls or CAD writes occur here
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List


class GraphProjectionError(RuntimeError):
    pass


EXPECTED_DOCUMENT = "IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE"
REQUIRED_OBSERVED_ROLES = (
    "AR60_ROLLER",
    "AR60_CARRIAGE",
    "CONVEYOR",
    "BOTTLE_1",
    "BOTTLE_2",
    "BOTTLE_3",
    "BOTTLE_4",
    "BOTTLE_5",
)
REQUIRED_CALCULATED_FACTS = (
    "AR60_NEAREST_BOTTLE_AABB_SEPARATION",
    "AR60_AABB_DISJOINT_FROM_ALL_BOTTLES",
    "AR60_CARRIAGE_AABB_RELATION",
    "AR60_CONVEYOR_AABB_RELATION",
)


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise GraphProjectionError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GraphProjectionError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GraphProjectionError(f"Top-level JSON must be an object: {path}")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GraphProjectionError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise GraphProjectionError(f"{label} must be finite")
    return number


def validate_projection(projection: Dict[str, Any]) -> None:
    if projection.get("transaction_type") != "deterministic_geometry_projection":
        raise GraphProjectionError("Expected deterministic_geometry_projection transaction")
    if projection.get("mechanical_acceptance_granted") is not False:
        raise GraphProjectionError("Geometry projection unexpectedly grants mechanical acceptance")

    document = projection.get("document")
    if not isinstance(document, dict):
        raise GraphProjectionError("Projection has no document object")
    if document.get("title") != EXPECTED_DOCUMENT:
        raise GraphProjectionError(
            f"Document mismatch: observed {document.get('title')!r}, expected {EXPECTED_DOCUMENT!r}"
        )

    source_evidence = projection.get("source_evidence")
    if not isinstance(source_evidence, dict):
        raise GraphProjectionError("Projection has no source_evidence object")
    raw_sha = source_evidence.get("raw_sha256")
    if not isinstance(raw_sha, str) or not raw_sha:
        raise GraphProjectionError("Projection source evidence has no raw_sha256")

    observed = projection.get("observed_facts")
    if not isinstance(observed, dict):
        raise GraphProjectionError("observed_facts must be an object")
    for role in REQUIRED_OBSERVED_ROLES:
        fact = observed.get(role)
        if not isinstance(fact, dict):
            raise GraphProjectionError(f"Required observed role missing: {role}")
        if fact.get("state") != "KNOWN":
            raise GraphProjectionError(f"Observed role {role} is not KNOWN")
        name2 = fact.get("component_name2")
        if not isinstance(name2, str) or not name2:
            raise GraphProjectionError(f"Observed role {role} has no exact component_name2")

    calculated = projection.get("calculated_facts")
    if not isinstance(calculated, dict):
        raise GraphProjectionError("calculated_facts must be an object")
    for fact_id in REQUIRED_CALCULATED_FACTS:
        fact = calculated.get(fact_id)
        if not isinstance(fact, dict):
            raise GraphProjectionError(f"Required calculated fact missing: {fact_id}")
        if fact.get("state") != "KNOWN":
            raise GraphProjectionError(f"Calculated fact {fact_id} is not KNOWN")

    nearest = calculated["AR60_NEAREST_BOTTLE_AABB_SEPARATION"]
    _finite_number(nearest.get("minimum_aabb_separation_mm"), "minimum_aabb_separation_mm")

    disjoint = calculated["AR60_AABB_DISJOINT_FROM_ALL_BOTTLES"].get("value")
    if not isinstance(disjoint, bool):
        raise GraphProjectionError("AR60_AABB_DISJOINT_FROM_ALL_BOTTLES.value must be boolean")


def _evidence_meta(projection: Dict[str, Any]) -> Dict[str, Any]:
    source = projection["source_evidence"]
    return {
        "source_transaction": "deterministic_geometry_projection",
        "raw_observation_sha256": source.get("raw_sha256"),
        "source_job_id": source.get("job_id"),
        "source_recorded_at": source.get("recorded_at"),
        "document_title": projection["document"].get("title"),
        "mechanical_acceptance_granted": False,
    }


def _known_node(
    node_id: str,
    description: str,
    value: Any,
    authority: str,
    criticality: int,
    metadata: Dict[str, Any],
    *,
    units: str | None = None,
) -> Dict[str, Any]:
    node = {
        "id": node_id,
        "kind": "fact",
        "description": description,
        "value": value,
        "state": "KNOWN",
        "authority": authority,
        "criticality": criticality,
        "metadata": metadata,
    }
    if units:
        node["units"] = units
    return node


def _null_node(
    node_id: str,
    kind: str,
    description: str,
    criticality: int,
    expected_authority: List[str],
    question: str,
    why_it_matters: str,
    *,
    resolution_cost: float = 1.0,
) -> Dict[str, Any]:
    return {
        "id": node_id,
        "kind": kind,
        "description": description,
        "value": None,
        "state": "NULL",
        "authority": None,
        "expected_authority": expected_authority,
        "criticality": criticality,
        "resolution_cost": resolution_cost,
        "metadata": {
            "question": question,
            "why_it_matters": why_it_matters,
        },
    }


def build_runtime_graph(projection: Dict[str, Any]) -> Dict[str, Any]:
    validate_projection(projection)

    observed = projection["observed_facts"]
    calculated = projection["calculated_facts"]
    evidence_meta = _evidence_meta(projection)

    ar60 = observed["AR60_ROLLER"]
    carriage = observed["AR60_CARRIAGE"]
    conveyor = observed["CONVEYOR"]
    bottles = {role: observed[role] for role in REQUIRED_OBSERVED_ROLES if role.startswith("BOTTLE_")}

    nearest = calculated["AR60_NEAREST_BOTTLE_AABB_SEPARATION"]
    disjoint = calculated["AR60_AABB_DISJOINT_FROM_ALL_BOTTLES"]
    carriage_relation = calculated["AR60_CARRIAGE_AABB_RELATION"]
    conveyor_relation = calculated["AR60_CONVEYOR_AABB_RELATION"]

    nodes: List[Dict[str, Any]] = [
        _known_node(
            "AR60_COMPONENT_IDENTITY",
            "Exact live SOLIDWORKS identity of the AR60 roller component.",
            ar60["component_name2"],
            "SOLIDWORKS_LIVE_STATE",
            5,
            dict(evidence_meta),
        ),
        _known_node(
            "AR60_TRANSFORM",
            "Observed AR60 transform in the current v21 fit-check assembly.",
            {
                "translation_mm": ar60.get("translation_mm"),
                "rotation9": ar60.get("rotation9"),
                "transform_array": ar60.get("transform_array"),
                "transform_source": ar60.get("transform_source"),
            },
            "SOLIDWORKS_LIVE_STATE",
            5,
            dict(evidence_meta),
        ),
        _known_node(
            "AR60_APPROX_ENVELOPE",
            "Observed approximate axis-aligned AR60 envelope from SOLIDWORKS GetBox-derived evidence.",
            {"box_min_mm": ar60.get("box_min_mm"), "box_max_mm": ar60.get("box_max_mm")},
            "SOLIDWORKS_LIVE_STATE",
            4,
            {**evidence_meta, "engineering_limit": "Approximate AABB; not exact body geometry."},
        ),
        _known_node(
            "CARRIAGE_COMPONENT_IDENTITY",
            "Exact live SOLIDWORKS identity of the AR carriage component.",
            carriage["component_name2"],
            "SOLIDWORKS_LIVE_STATE",
            5,
            dict(evidence_meta),
        ),
        _known_node(
            "CARRIAGE_TRANSFORM",
            "Observed carriage transform in the current v21 fit-check assembly.",
            {
                "translation_mm": carriage.get("translation_mm"),
                "rotation9": carriage.get("rotation9"),
                "transform_array": carriage.get("transform_array"),
                "transform_source": carriage.get("transform_source"),
            },
            "SOLIDWORKS_LIVE_STATE",
            5,
            dict(evidence_meta),
        ),
        _known_node(
            "CONVEYOR_APPROX_ENVELOPE",
            "Observed approximate conveyor envelope in the current v21 assembly.",
            {"box_min_mm": conveyor.get("box_min_mm"), "box_max_mm": conveyor.get("box_max_mm")},
            "SOLIDWORKS_LIVE_STATE",
            5,
            {**evidence_meta, "engineering_limit": "Approximate AABB; not an exact clearance result."},
        ),
        _known_node(
            "BOTTLE_PATH_APPROX_ENVELOPES",
            "Observed approximate envelopes of the five deterministic bottles in v21.",
            {
                role: {
                    "component_name2": fact.get("component_name2"),
                    "box_min_mm": fact.get("box_min_mm"),
                    "box_max_mm": fact.get("box_max_mm"),
                }
                for role, fact in bottles.items()
            },
            "SOLIDWORKS_LIVE_STATE",
            5,
            {**evidence_meta, "engineering_limit": "Bottle AABBs characterize current placement only; they do not define accepted product flow."},
        ),
        _known_node(
            "AR60_NEAREST_BOTTLE_AABB_SEPARATION",
            "Minimum approximate AABB separation between the current AR60 and the nearest observed bottle candidate.",
            nearest["minimum_aabb_separation_mm"],
            "MEASURED_CALCULATED",
            5,
            {
                **evidence_meta,
                "nearest_bottle_unique": nearest.get("nearest_bottle_unique"),
                "nearest_bottle_role": nearest.get("nearest_bottle_role"),
                "nearest_bottle_roles": nearest.get("nearest_bottle_roles"),
                "axis_gap_mm": nearest.get("axis_gap_mm"),
                "candidate_axis_gaps_mm": nearest.get("candidate_axis_gaps_mm"),
                "engineering_limit": "AABB separation is not exact surface clearance or proof of contact impossibility after repositioning.",
            },
            units="mm",
        ),
        _known_node(
            "AR60_AABB_DISJOINT_FROM_ALL_BOTTLES",
            "Whether the current AR60 approximate AABB is disjoint from all five observed bottle AABBs.",
            disjoint["value"],
            "MEASURED_CALCULATED",
            5,
            {**evidence_meta, "engineering_limit": "Describes the current fit-check state only; not an operating-position verdict."},
        ),
        _known_node(
            "AR60_CARRIAGE_AABB_RELATION",
            "Approximate AABB relationship between the current AR60 and carriage.",
            {
                "axis_gap_mm": carriage_relation.get("axis_gap_mm"),
                "minimum_aabb_separation_mm": carriage_relation.get("minimum_aabb_separation_mm"),
                "aabb_intersects_or_touches": carriage_relation.get("aabb_intersects_or_touches"),
                "positive_volume_aabb_overlap": carriage_relation.get("positive_volume_aabb_overlap"),
                "overlap_extent_mm": carriage_relation.get("overlap_extent_mm"),
            },
            "MEASURED_CALCULATED",
            4,
            {**evidence_meta, "engineering_limit": carriage_relation.get("engineering_limit")},
        ),
        _known_node(
            "AR60_CONVEYOR_AABB_RELATION",
            "Approximate AABB relationship between the current AR60 and conveyor.",
            {
                "axis_gap_mm": conveyor_relation.get("axis_gap_mm"),
                "minimum_aabb_separation_mm": conveyor_relation.get("minimum_aabb_separation_mm"),
                "aabb_intersects_or_touches": conveyor_relation.get("aabb_intersects_or_touches"),
                "positive_volume_aabb_overlap": conveyor_relation.get("positive_volume_aabb_overlap"),
                "overlap_extent_mm": conveyor_relation.get("overlap_extent_mm"),
            },
            "MEASURED_CALCULATED",
            4,
            {**evidence_meta, "engineering_limit": conveyor_relation.get("engineering_limit")},
        ),
        _null_node(
            "INTENDED_APPLICATION_STATION_TRANSFORM",
            "fact",
            "Intended mechanically valid AR60/carriage application-station transform relative to the bottle path, IXOR peel edge, and mounting structure.",
            5,
            ["OEM_CAD", "OEM_MANUAL", "SOLIDWORKS_MEASUREMENT", "DETERMINISTIC_DERIVATION"],
            "What transform places the AR60/carriage in the intended application station while respecting OEM mounting architecture and bottle flow?",
            "The current fit-check transform is remote from the bottles; operating contact, clearance, and reachability cannot be evaluated until the intended station geometry is established.",
        ),
        _null_node(
            "AR60_CONTACT_POSITION",
            "fact",
            "Operating AR60 contact position relative to the intended bottle application condition.",
            5,
            ["SOLIDWORKS_MEASUREMENT", "DETERMINISTIC_DERIVATION"],
            "Where is the deterministic AR60/bottle contact condition after the intended application-station transform is established?",
            "Blocks proof of bottle contact, carriage reachability, and conveyor clearance.",
        ),
        _null_node(
            "AR60_MAX_TRAVEL",
            "fact",
            "Verified usable AR carriage travel along the mechanically relevant adjustment axis.",
            5,
            ["OEM_CAD", "OEM_MANUAL", "SOLIDWORKS_MEASUREMENT"],
            "What is the verified usable carriage travel and axis for this exact AR carriage configuration?",
            "Travel must be verified from authoritative evidence before reachability can be accepted.",
        ),
        _null_node(
            "CONTACT_REACHABLE_WITHIN_TRAVEL",
            "derived_claim",
            "Required operating contact position is reachable within verified AR carriage travel.",
            5,
            ["DETERMINISTIC_DERIVATION"],
            "Does the verified travel range contain the required AR60 contact position?",
            "Directly gates whether the AR60 can reach the intended bottle without inventing unsupported adjustment range.",
        ),
        _null_node(
            "PEEL_EDGE_BOTTLE_RELATION",
            "derived_claim",
            "Deterministic peel-edge relationship to the bottle at the intended application station.",
            5,
            ["OEM_CAD", "SOLIDWORKS_MEASUREMENT", "DETERMINISTIC_DERIVATION"],
            "Where is the IXOR peel edge relative to the bottle and AR60 contact condition?",
            "A plausible application station requires label presentation geometry, not only roller proximity.",
        ),
        _null_node(
            "BOTTLE_RESTRAINT_GEOMETRY",
            "derived_claim",
            "Bottle support/restraint geometry is defined for the intended labeling condition.",
            5,
            ["OEM_CAD", "OEM_MANUAL", "DETERMINISTIC_PROJECT_GEOMETRY", "SOLIDWORKS_MEASUREMENT"],
            "What mechanically supports, locates, and restrains the bottle during label application?",
            "Bottle contact without controlled seating/restraint does not establish an operating arrangement.",
        ),
        _null_node(
            "PRODUCT_FLOW_MECHANICS",
            "derived_claim",
            "Bottle entry, application, release, and downstream flow mechanics are deterministically established.",
            5,
            ["OEM_MANUAL", "OEM_CAD", "DETERMINISTIC_DERIVATION", "SOLIDWORKS_MEASUREMENT"],
            "Can a bottle enter, be labeled under restraint, release, and continue without collision or impossible motion?",
            "Static fit alone is not proof of a workable product-flow sequence.",
        ),
        {
            "id": "NO_CONVEYOR_INTERFERENCE",
            "kind": "invariant",
            "description": "The accepted operating configuration must not structurally interfere with the conveyor or required product-flow envelope.",
            "value": True,
            "state": "ASSERTED",
            "authority": "PROJECT_INVARIANT",
            "criticality": 5,
        },
        {
            "id": "BOTTLE_CONTACT_ACHIEVABLE",
            "kind": "invariant",
            "description": "The application roller must reach the intended bottle contact condition under verified travel and restraint geometry.",
            "value": True,
            "state": "ASSERTED",
            "authority": "PROJECT_INVARIANT",
            "criticality": 5,
        },
        {
            "id": "VALID_APPLICATION_GEOMETRY",
            "kind": "obligation",
            "description": "Application geometry, peel-edge relation, bottle restraint, clearances, and product flow are mechanically coherent enough to advance beyond fit-check.",
            "value": True,
            "state": "ASSERTED",
            "authority": "PROJECT_ACCEPTANCE_RULE",
            "criticality": 5,
        },
        {
            "id": "V21_ACCEPTANCE",
            "kind": "obligation",
            "description": "v21 is acceptable as an operating-configuration candidate rather than only an AR60/carriage fit-check.",
            "value": True,
            "state": "ASSERTED",
            "authority": "PROJECT_ACCEPTANCE_RULE",
            "criticality": 5,
            "acceptance_gate": True,
        },
    ]

    relations = [
        {"from": "INTENDED_APPLICATION_STATION_TRANSFORM", "to": "AR60_TRANSFORM", "type": "depends_on", "strength": 0.8},
        {"from": "INTENDED_APPLICATION_STATION_TRANSFORM", "to": "CARRIAGE_TRANSFORM", "type": "depends_on", "strength": 0.8},
        {"from": "INTENDED_APPLICATION_STATION_TRANSFORM", "to": "BOTTLE_PATH_APPROX_ENVELOPES", "type": "depends_on", "strength": 1.0},
        {"from": "INTENDED_APPLICATION_STATION_TRANSFORM", "to": "CONVEYOR_APPROX_ENVELOPE", "type": "constrained_by", "strength": 1.0},
        {"from": "AR60_CONTACT_POSITION", "to": "INTENDED_APPLICATION_STATION_TRANSFORM", "type": "depends_on", "strength": 1.0},
        {"from": "AR60_CONTACT_POSITION", "to": "BOTTLE_PATH_APPROX_ENVELOPES", "type": "depends_on", "strength": 1.0},
        {"from": "CONTACT_REACHABLE_WITHIN_TRAVEL", "to": "AR60_CONTACT_POSITION", "type": "depends_on", "strength": 1.0},
        {"from": "CONTACT_REACHABLE_WITHIN_TRAVEL", "to": "AR60_MAX_TRAVEL", "type": "depends_on", "strength": 1.0},
        {"from": "NO_CONVEYOR_INTERFERENCE", "to": "INTENDED_APPLICATION_STATION_TRANSFORM", "type": "depends_on", "strength": 1.0},
        {"from": "NO_CONVEYOR_INTERFERENCE", "to": "CONVEYOR_APPROX_ENVELOPE", "type": "depends_on", "strength": 1.0},
        {"from": "BOTTLE_CONTACT_ACHIEVABLE", "to": "CONTACT_REACHABLE_WITHIN_TRAVEL", "type": "depends_on", "strength": 1.0},
        {"from": "BOTTLE_CONTACT_ACHIEVABLE", "to": "BOTTLE_RESTRAINT_GEOMETRY", "type": "depends_on", "strength": 1.0},
        {"from": "PEEL_EDGE_BOTTLE_RELATION", "to": "INTENDED_APPLICATION_STATION_TRANSFORM", "type": "depends_on", "strength": 1.0},
        {"from": "BOTTLE_RESTRAINT_GEOMETRY", "to": "INTENDED_APPLICATION_STATION_TRANSFORM", "type": "depends_on", "strength": 0.8},
        {"from": "PRODUCT_FLOW_MECHANICS", "to": "BOTTLE_RESTRAINT_GEOMETRY", "type": "depends_on", "strength": 1.0},
        {"from": "PRODUCT_FLOW_MECHANICS", "to": "NO_CONVEYOR_INTERFERENCE", "type": "depends_on", "strength": 1.0},
        {"from": "VALID_APPLICATION_GEOMETRY", "to": "NO_CONVEYOR_INTERFERENCE", "type": "depends_on", "strength": 1.0},
        {"from": "VALID_APPLICATION_GEOMETRY", "to": "BOTTLE_CONTACT_ACHIEVABLE", "type": "depends_on", "strength": 1.0},
        {"from": "VALID_APPLICATION_GEOMETRY", "to": "PEEL_EDGE_BOTTLE_RELATION", "type": "depends_on", "strength": 1.0},
        {"from": "VALID_APPLICATION_GEOMETRY", "to": "BOTTLE_RESTRAINT_GEOMETRY", "type": "depends_on", "strength": 1.0},
        {"from": "VALID_APPLICATION_GEOMETRY", "to": "PRODUCT_FLOW_MECHANICS", "type": "depends_on", "strength": 1.0},
        {"from": "V21_ACCEPTANCE", "to": "VALID_APPLICATION_GEOMETRY", "type": "depends_on", "strength": 1.0},
        {"from": "BOTTLE_CONTACT_ACHIEVABLE", "to": "VALID_APPLICATION_GEOMETRY", "type": "before", "strength": 1.0, "algebra": "allen"},
    ]

    return {
        "project": {
            "id": "IXOR_V21_LIVE",
            "name": "IXOR v21 live evidence project-health graph",
            "acceptance_obligation": "V21_ACCEPTANCE",
            "document_title": projection["document"].get("title"),
            "source_raw_sha256": projection["source_evidence"].get("raw_sha256"),
            "graph_basis": "admitted SOLIDWORKS evidence + deterministic geometry projection",
            "mechanical_acceptance_granted": False,
        },
        "nodes": nodes,
        "relations": relations,
        "projection_policy": {
            "toy_placeholder_values_copied": False,
            "known_values_require_observation_or_deterministic_derivation": True,
            "aabb_results_do_not_establish_exact_contact_or_interference": True,
            "llm_may_not_promote_nulls": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a runtime epistemic graph from deterministic v21 geometry evidence."
    )
    parser.add_argument("geometry_projection", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    projection = load_json(args.geometry_projection)
    try:
        graph = build_runtime_graph(projection)
    except GraphProjectionError as exc:
        raise SystemExit(f"REJECTED: {exc}") from exc

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    if args.summary:
        known = sum(1 for node in graph["nodes"] if node.get("state") == "KNOWN")
        unresolved = sum(1 for node in graph["nodes"] if node.get("state") in {"NULL", "CONFLICT"})
        separation = next(
            node for node in graph["nodes"] if node["id"] == "AR60_NEAREST_BOTTLE_AABB_SEPARATION"
        )
        print(f"PROJECT: {graph['project']['name']}")
        print(f"DOCUMENT: {graph['project']['document_title']}")
        print(f"SOURCE SHA256: {graph['project']['source_raw_sha256']}")
        print(f"KNOWN EVIDENCE NODES: {known}")
        print(f"UNRESOLVED MECHANICAL NODES: {unresolved}")
        print(f"CURRENT AR60/NEAREST-BOTTLE AABB SEPARATION: {separation['value']:.3f} mm")
        print("TOY PLACEHOLDER VALUES COPIED: NO")
        print("MECHANICAL ACCEPTANCE: NOT GRANTED")
    else:
        print(json.dumps(graph, indent=2))


if __name__ == "__main__":
    main()
