#!/usr/bin/env python3
"""Read-only ingestion of CADGrounded SOLIDWORKS component observations.

This module converts a completed ``sw.query_components`` job envelope into a
normalized evidence transaction. It does not call SOLIDWORKS, mutate CAD,
resolve mechanical acceptance, or promote inferred engineering claims.

Authority boundary:
- live SOLIDWORKS observation -> observed evidence only
- deterministic geometry checks -> may derive mechanical facts elsewhere
- LLMs -> may propose investigations, never mark engineering facts verified
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


class EvidenceError(RuntimeError):
    """Raised when an observation cannot be admitted as evidence."""


REQUIRED_ENVELOPE_FIELDS = {
    "job_id",
    "command",
    "state",
    "worker",
    "recorded_at",
    "error",
    "data",
}

REQUIRED_DATA_FIELDS = {
    "component_count",
    "document_path",
    "document_title",
    "bridge_version",
    "adapter",
    "top_level_only",
    "components",
}

OBSERVABLE_COMPONENT_FIELDS = (
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
    "geometry_note",
    "source_classification",
    "field_errors",
)


def _load_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise EvidenceError(f"Could not read observation file {path}: {exc}") from exc


def _load_json_bytes(raw: bytes, path: Path) -> Dict[str, Any]:
    try:
        text = raw.decode("utf-8-sig")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"Invalid UTF-8 JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError("Observation top level must be a JSON object")
    return value


def _require_fields(obj: Dict[str, Any], fields: set[str], where: str) -> None:
    missing = sorted(fields - set(obj))
    if missing:
        raise EvidenceError(f"Missing required {where} field(s): {', '.join(missing)}")


def validate_envelope(
    envelope: Dict[str, Any],
    *,
    expected_document: str | None = None,
    expected_command: str = "sw.query_components",
) -> Dict[str, Any]:
    _require_fields(envelope, REQUIRED_ENVELOPE_FIELDS, "envelope")

    if envelope.get("command") != expected_command:
        raise EvidenceError(
            f"Unexpected command {envelope.get('command')!r}; expected {expected_command!r}"
        )
    if envelope.get("state") != "completed":
        raise EvidenceError(
            f"Observation state is {envelope.get('state')!r}, not 'completed'"
        )
    if envelope.get("error") not in (None, ""):
        raise EvidenceError(f"Observation contains an error: {envelope.get('error')!r}")

    data = envelope.get("data")
    if not isinstance(data, dict):
        raise EvidenceError("Envelope data must be an object")
    _require_fields(data, REQUIRED_DATA_FIELDS, "data")

    if expected_document and data.get("document_title") != expected_document:
        raise EvidenceError(
            "Document identity mismatch: "
            f"observed {data.get('document_title')!r}, expected {expected_document!r}"
        )

    components = data.get("components")
    if not isinstance(components, list):
        raise EvidenceError("data.components must be an array")

    declared_count = data.get("component_count")
    if not isinstance(declared_count, int):
        raise EvidenceError("data.component_count must be an integer")
    if declared_count != len(components):
        raise EvidenceError(
            f"component_count mismatch: declared {declared_count}, observed {len(components)}"
        )

    return data


def normalize_component(component: Any, index: int) -> Dict[str, Any]:
    if not isinstance(component, dict):
        raise EvidenceError(f"components[{index}] must be an object")

    name2 = component.get("name2")
    if not isinstance(name2, str) or not name2.strip():
        raise EvidenceError(f"components[{index}] has no exact non-empty name2")

    normalized = {field: component.get(field) for field in OBSERVABLE_COMPONENT_FIELDS}
    normalized["evidence_kind"] = "solidworks_component_observation"
    normalized["identity_basis"] = "Component2.Name2"

    field_errors = normalized.get("field_errors")
    if field_errors is None:
        normalized["field_errors"] = []
    elif not isinstance(field_errors, list):
        normalized["field_errors"] = [field_errors]

    return normalized


def build_transaction(
    envelope: Dict[str, Any],
    *,
    raw_sha256: str,
    source_file: str,
    expected_document: str | None = None,
) -> Dict[str, Any]:
    data = validate_envelope(envelope, expected_document=expected_document)
    components = [
        normalize_component(component, i)
        for i, component in enumerate(data["components"])
    ]

    transaction = {
        "transaction_type": "cad_observation_evidence",
        "schema_version": 1,
        "admission_status": "ADMITTED_OBSERVATION",
        "mechanical_acceptance_granted": False,
        "source_authority": "SOLIDWORKS_LIVE_STATE",
        "source_classification": "verified_from_solidworks_api",
        "raw_observation": {
            "source_file": source_file,
            "sha256": raw_sha256,
            "job_id": envelope.get("job_id"),
            "command": envelope.get("command"),
            "state": envelope.get("state"),
            "worker": envelope.get("worker"),
            "recorded_at": envelope.get("recorded_at"),
        },
        "document": {
            "title": data.get("document_title"),
            "path": data.get("document_path"),
            "bridge_version": data.get("bridge_version"),
            "adapter": data.get("adapter"),
            "top_level_only": data.get("top_level_only"),
        },
        "component_count": len(components),
        "components": components,
        "prohibited_promotions": [
            "mechanical_acceptance",
            "valid_contact",
            "valid_clearance",
            "operating_sequence",
            "functional_suitability",
        ],
    }
    return transaction


def ingest_file(
    path: Path,
    *,
    expected_document: str | None = None,
) -> Dict[str, Any]:
    raw = _load_bytes(path)
    envelope = _load_json_bytes(raw, path)
    return build_transaction(
        envelope,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        source_file=str(path),
        expected_document=expected_document,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize a read-only sw.query_components observation into an evidence transaction."
    )
    parser.add_argument("observation", type=Path)
    parser.add_argument(
        "--expected-document",
        help="Reject the observation unless document_title exactly matches this value.",
    )
    parser.add_argument("--out", type=Path, help="Write normalized transaction JSON here.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact human-readable summary instead of full JSON.",
    )
    args = parser.parse_args()

    try:
        tx = ingest_file(args.observation, expected_document=args.expected_document)
    except EvidenceError as exc:
        raise SystemExit(f"REJECTED: {exc}") from exc

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(tx, indent=2), encoding="utf-8")

    if args.summary:
        print(f"ADMISSION: {tx['admission_status']}")
        print(f"DOCUMENT: {tx['document']['title']}")
        print(f"PATH: {tx['document']['path']}")
        print(f"COMPONENTS: {tx['component_count']}")
        print(f"RAW SHA256: {tx['raw_observation']['sha256']}")
        print("MECHANICAL ACCEPTANCE: NOT GRANTED")
    else:
        print(json.dumps(tx, indent=2))


if __name__ == "__main__":
    main()
