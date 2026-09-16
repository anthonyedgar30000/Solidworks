#!/usr/bin/env python3
"""Validate exact semantic-role bindings against admitted SOLIDWORKS evidence.

This is read-only. It does not call SOLIDWORKS, mutate CAD, or infer mechanical
acceptance. It binds semantic roles only when each configured Component2.Name2
matches exactly one admitted observed component.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


class IdentityBindingError(RuntimeError):
    pass


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise IdentityBindingError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise IdentityBindingError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise IdentityBindingError(f"Top-level JSON must be an object: {path}")
    return value


def validate_transaction(tx: Dict[str, Any], expected_document: str) -> None:
    if tx.get("admission_status") != "ADMITTED_OBSERVATION":
        raise IdentityBindingError("Evidence transaction is not admitted")
    if tx.get("mechanical_acceptance_granted") is not False:
        raise IdentityBindingError("Evidence transaction unexpectedly grants mechanical acceptance")
    doc = tx.get("document")
    if not isinstance(doc, dict):
        raise IdentityBindingError("Evidence transaction has no document object")
    if doc.get("title") != expected_document:
        raise IdentityBindingError(
            f"Document mismatch: observed {doc.get('title')!r}, expected {expected_document!r}"
        )
    components = tx.get("components")
    if not isinstance(components, list):
        raise IdentityBindingError("Evidence transaction components must be an array")


def bind_roles(tx: Dict[str, Any], bindings: Dict[str, Any]) -> Dict[str, Any]:
    expected_document = bindings.get("expected_document")
    if not isinstance(expected_document, str) or not expected_document:
        raise IdentityBindingError("Bindings file has no expected_document")
    validate_transaction(tx, expected_document)

    roles = bindings.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise IdentityBindingError("Bindings file has no roles")

    by_name2: Dict[str, list[dict[str, Any]]] = {}
    for component in tx["components"]:
        if not isinstance(component, dict):
            continue
        name2 = component.get("name2")
        if isinstance(name2, str):
            by_name2.setdefault(name2, []).append(component)

    resolved: Dict[str, Any] = {}
    for role, exact_name2 in roles.items():
        if not isinstance(exact_name2, str) or not exact_name2:
            raise IdentityBindingError(f"Role {role!r} has invalid exact Name2")
        matches = by_name2.get(exact_name2, [])
        if len(matches) == 0:
            raise IdentityBindingError(
                f"Role {role!r} exact Name2 not found: {exact_name2!r}"
            )
        if len(matches) > 1:
            raise IdentityBindingError(
                f"Role {role!r} exact Name2 is not unique: {exact_name2!r}"
            )
        component = matches[0]
        resolved[role] = {
            "identity_status": "VERIFIED_FROM_SOLIDWORKS",
            "identity_basis": "Component2.Name2",
            "component_name2": exact_name2,
            "path": component.get("path"),
            "parent_name": component.get("parent_name"),
            "is_top_level": component.get("is_top_level"),
            "suppressed": component.get("suppressed"),
            "fixed": component.get("fixed"),
            "translation_mm": component.get("translation_mm"),
            "rotation9": component.get("rotation9"),
            "transform_array": component.get("transform_array"),
            "transform_source": component.get("transform_source"),
            "box_min_mm": component.get("box_min_mm"),
            "box_max_mm": component.get("box_max_mm"),
            "getbox_mm": component.get("getbox_mm"),
            "geometry_note": component.get("geometry_note"),
            "source_classification": component.get("source_classification"),
            "field_errors": component.get("field_errors", []),
        }

    return {
        "transaction_type": "semantic_identity_binding",
        "schema_version": 1,
        "document": tx["document"],
        "source_evidence": {
            "raw_sha256": tx.get("raw_observation", {}).get("sha256"),
            "job_id": tx.get("raw_observation", {}).get("job_id"),
            "recorded_at": tx.get("raw_observation", {}).get("recorded_at"),
        },
        "identity_basis": "Component2.Name2",
        "mechanical_acceptance_granted": False,
        "resolved_roles": resolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("bindings", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    tx = load_json(args.evidence)
    bindings = load_json(args.bindings)
    try:
        result = bind_roles(tx, bindings)
    except IdentityBindingError as exc:
        raise SystemExit(f"REJECTED: {exc}") from exc

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if args.summary:
        print(f"DOCUMENT: {result['document']['title']}")
        print(f"IDENTITY BASIS: {result['identity_basis']}")
        print(f"ROLES RESOLVED: {len(result['resolved_roles'])}")
        for role, record in result["resolved_roles"].items():
            print(f"  {role}: {record['component_name2']}")
        print("MECHANICAL ACCEPTANCE: NOT GRANTED")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
