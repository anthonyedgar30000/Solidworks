#!/usr/bin/env python3
"""Bounded admission of the passed v42 Windows-host interface artifact.

This is repository-only reasoning.  It consumes a reviewed host artifact and
creates a schema-shaped EvidenceRecord plus a small dependency graph; it never
opens SOLIDWORKS, sends Remote Queue work, or authorizes a CAD write.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


class AdmissionError(ValueError):
    pass


CURRENT = "CURRENT"
UNRESOLVED = "UNRESOLVED"
STALE = "STALE"
DOCUMENT_TITLE = "IXOR_Benchmark_v42_ASSET_INTERFACE_TEST_PORTABLE"
DOCUMENT_PATH = r"C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v42_ASSET_INTERFACE_TEST_PORTABLE.SLDASM"
CONFIGURATION = "Default"
MERGE_SHA = "9b52604d593f33743bf86f3edff0cb7cedd2b853"
PR20_HEAD_SHA = "04ef98bb1769dfc6af6d890f9338bafd42be517e"

CURRENT_CLAIMS = (
    "V42.PRODUCT_ENTRY_INTERFACE_IDENTITY",
    "V42.PRODUCT_EXIT_INTERFACE_IDENTITY",
    "PRODUCT_ENTRY_CS_FRAME_BASELINE",
    "PRODUCT_EXIT_CS_FRAME_BASELINE",
    "CONNECTOR2_PUBLISHED_REFERENCE_IDENTITY",
    "CONNECTOR1_PUBLISHED_REFERENCE_IDENTITY",
)
UNRESOLVED_CLAIMS = (
    "PUBLISHED_ASSET_CONNECTOR_COORDSYS_GEOMETRIC_COINCIDENCE",
    "CONNECTOR_POINT_DIRECTION_GEOMETRY",
    "PHYSICAL_CONTACT",
    "CLEARANCE_INTERFERENCE",
    "MATE_BEHAVIOR",
    "MOTION_DOF",
    "PRELOAD_FORCE_REACTION_PATH",
    "TEMPORAL_OPERATING_STATE_VALIDITY",
    "WHOLE_SYSTEM_MECHANICAL_ACCEPTANCE",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"Expected object in {path}")
    return value


def _require(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if "const" in schema and value != schema["const"]:
        raise AdmissionError(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise AdmissionError(f"{path} has an unsupported value")
    expected_type = schema.get("type")
    if expected_type == "string":
        if not isinstance(value, str): raise AdmissionError(f"{path} must be a string")
        if len(value) < schema.get("minLength", 0): raise AdmissionError(f"{path} is too short")
        if "pattern" in schema and not re.match(schema["pattern"], value): raise AdmissionError(f"{path} pattern mismatch")
    elif expected_type == "boolean" and not isinstance(value, bool):
        raise AdmissionError(f"{path} must be boolean")
    elif expected_type == "array":
        if not isinstance(value, list): raise AdmissionError(f"{path} must be an array")
        if schema.get("uniqueItems") and len(value) != len(set(value)): raise AdmissionError(f"{path} must be unique")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value): _require(item, item_schema, f"{path}[{i}]")
    elif expected_type == "object":
        if not isinstance(value, dict): raise AdmissionError(f"{path} must be an object")
        for name in schema.get("required", []):
            if name not in value: raise AdmissionError(f"{path}.{name} is required")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(props)
            if extras: raise AdmissionError(f"{path} has unsupported properties: {sorted(extras)}")
        for name, child in props.items():
            if name in value: _require(value[name], child, f"{path}.{name}")


def validate_evidence_record(record: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    """Validate the EvidenceRecord's applicable SolidWorksObservation branch.

    The repository intentionally has no third-party schema runtime.  This
    deterministic reader enforces the selected schema's supertype and the
    SolidWorksObservation ``oneOf`` branch, including strict top-level keys.
    """
    _require(record, schema, "record")
    branch = next(b for b in schema["oneOf"] if b["title"] == "SolidWorksObservation")
    _require(record, {"type": "object", "properties": branch["properties"]}, "record")


def admit_host_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    if artifact.get("result") != "PASS": raise AdmissionError("Host artifact did not pass")
    if artifact.get("write_authority") != "NONE" or artifact.get("model_mutation") is not False:
        raise AdmissionError("Host artifact is not read-only")
    if artifact.get("remote_queue_authorized") is not False:
        raise AdmissionError("Host artifact must not authorize Remote Queue")
    document = artifact.get("expected_document", {})
    if document.get("title") != DOCUMENT_TITLE or document.get("path") != DOCUMENT_PATH:
        raise AdmissionError("Host artifact exact document binding mismatch")
    for state in (artifact.get("document_state_before", {}), artifact.get("document_state_after", {})):
        if state.get("active_configuration") != CONFIGURATION:
            raise AdmissionError("Host artifact configuration binding mismatch")

    observation = artifact.get("interface_observation", {})
    if observation.get("published_reference_manager", {}).get("feature_type") != "ConnectRefMgr":
        raise AdmissionError("Published References manager type mismatch")
    connectors = {x.get("connector_name"): x for x in observation.get("published_reference_features", [])}
    frames = {x.get("feature_name"): x for x in observation.get("coordinate_systems", [])}
    for name in ("Connector1", "Connector2"):
        row = connectors.get(name, {})
        if row.get("feature_type") != "MagneticConnectRef" or row.get("parent_feature_name") != "Published References" or row.get("parent_feature_type") != "ConnectRefMgr":
            raise AdmissionError(f"{name} parentage/type mismatch")
    for name in ("PRODUCT_ENTRY_CS", "PRODUCT_EXIT_CS"):
        if frames.get(name, {}).get("feature_type") != "CoordSys": raise AdmissionError(f"{name} missing")

    return {
        "schema_version": 1, "record_type": "evidence",
        "evidence_id": "v42.interface.host-observation.2026-09-25",
        "evidence_type": "solidworks_observation", "evidence_state": "VERIFIED",
        "source_authority": "SOLIDWORKS_LIVE_STATE", "source_classification": "verified_from_solidworks_api",
        "subject": {"subject_type": "SOLIDWORKS_ASSEMBLY_INTERFACE", "identity_exact": DOCUMENT_TITLE, "document_title_exact": DOCUMENT_TITLE, "document_path_exact": DOCUMENT_PATH},
        "provenance": {"recorded_at": artifact["recorded_at"], "source_ref": artifact["artifact_ref"], "tool_path": "Verify-InterfaceContract-V42.ps1", "job_id": "PR-20-WINDOWS-HOST-VERIFY"},
        "dependencies": [f"github:pull/20/head/{PR20_HEAD_SHA}", f"github:commit/{MERGE_SHA}"],
        "geometry_state": "FIT_CHECK", "temporal_scope": {"coverage": "POINT_ONLY", "validity_state": "CURRENT", "state_ids": ["V42.INTERFACE_READ"], "transition_ids": []},
        "ambiguity_bucket": "MECHANICAL_ACCEPTANCE_BLOCKED", "mechanical_acceptance_granted": False,
        "payload": {"observation_kind": "v42_bounded_interface_identity_and_frame_baseline", "document": {"title": DOCUMENT_TITLE, "path": DOCUMENT_PATH, "active_configuration": CONFIGURATION}, "current_claim_ids": list(CURRENT_CLAIMS), "unresolved_claim_ids": list(UNRESOLVED_CLAIMS), "write_authority": "NONE", "remote_queue_authorized": False, "model_mutation": False},
    }


def build_dependency_graph(record: Mapping[str, Any]) -> dict[str, Any]:
    evidence_id = record["evidence_id"]
    nodes = [{"id": evidence_id, "kind": "evidence", "state": CURRENT, "mechanical_acceptance_granted": False}]
    edges = []
    for claim in CURRENT_CLAIMS:
        nodes.append({"id": claim, "kind": "finding", "state": CURRENT, "mechanical_acceptance_granted": False})
        edges.append({"from": evidence_id, "to": claim, "relation": "SUPPORTS", "stale_on_source_change": True})
    for claim in UNRESOLVED_CLAIMS:
        nodes.append({"id": claim, "kind": "finding", "state": UNRESOLVED, "mechanical_acceptance_granted": False})
    return {"graph_type": "v42_interface_evidence_dependency_graph", "write_authority": "NONE", "remote_queue_authorized": False, "nodes": nodes, "edges": edges}


def supersede_evidence(graph: Mapping[str, Any], evidence_id: str) -> dict[str, Any]:
    result = json.loads(json.dumps(graph))
    dependent_ids = {e["to"] for e in result["edges"] if e["from"] == evidence_id and e["stale_on_source_change"]}
    for node in result["nodes"]:
        if node["id"] == evidence_id: node["state"] = "SUPERSEDED"
        elif node["id"] in dependent_ids: node["state"] = STALE
    return result
