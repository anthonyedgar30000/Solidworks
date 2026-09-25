#!/usr/bin/env python3
"""Deterministic validator/consumer for CADGrounded CAD interface contracts.

This module is candidate non-runtime reasoning code. It does not command
SOLIDWORKS, grant CAD write authority, or grant mechanical acceptance.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence


class CADInterfaceContractError(ValueError):
    pass


def _obj(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CADInterfaceContractError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list:
    if not isinstance(value, list):
        raise CADInterfaceContractError(f"{label} must be an array")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CADInterfaceContractError(f"{label} must be a non-empty string")
    return value


def _vec(value: Any, length: int, label: str) -> list[float]:
    items = _list(value, label)
    if len(items) != length:
        raise CADInterfaceContractError(f"{label} must contain exactly {length} values")
    out = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise CADInterfaceContractError(f"{label} must contain only numbers")
        out.append(float(item))
    return out


def _near(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: Sequence[float]) -> float:
    return math.sqrt(_dot(v, v))


def _interface_index(contract: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for position, value in enumerate(_list(contract.get("interfaces"), "interfaces")):
        interface = _obj(value, f"interfaces[{position}]")
        interface_id = _string(interface.get("id"), f"interfaces[{position}].id")
        if interface_id in result:
            raise CADInterfaceContractError(f"duplicate interface id: {interface_id}")
        result[interface_id] = interface
    return result


def _frame_axes(transform: Sequence[float]) -> tuple[list[float], list[float], list[float]]:
    return (
        list(transform[0:3]),
        list(transform[3:6]),
        list(transform[6:9]),
    )


def _validate_frame(interface_id: str, frame: Mapping[str, Any]) -> None:
    if frame.get("feature_type") != "CoordSys":
        raise CADInterfaceContractError(f"{interface_id}.api_frame.feature_type must be CoordSys")
    if frame.get("source_authority") != "SOLIDWORKS_LIVE_STATE":
        raise CADInterfaceContractError(
            f"{interface_id}.api_frame.source_authority must be SOLIDWORKS_LIVE_STATE"
        )
    if frame.get("source_classification") != "verified_from_solidworks_api":
        raise CADInterfaceContractError(
            f"{interface_id}.api_frame.source_classification must be verified_from_solidworks_api"
        )
    if frame.get("evidence_state") != "VERIFIED":
        raise CADInterfaceContractError(f"{interface_id}.api_frame.evidence_state must be VERIFIED")

    origin = _vec(frame.get("origin_mm"), 3, f"{interface_id}.api_frame.origin_mm")
    transform = _vec(frame.get("transform16"), 16, f"{interface_id}.api_frame.transform16")

    for i, value in enumerate(origin):
        if not _near(value / 1000.0, transform[9 + i], 1e-12):
            raise CADInterfaceContractError(
                f"{interface_id}.api_frame origin_mm disagrees with transform16 translation"
            )

    x_axis, y_axis, z_axis = _frame_axes(transform)
    for label, axis in (("x", x_axis), ("y", y_axis), ("z", z_axis)):
        if not _near(_norm(axis), 1.0, 1e-9):
            raise CADInterfaceContractError(
                f"{interface_id}.api_frame local {label} axis is not unit length"
            )

    if not _near(_dot(x_axis, y_axis), 0.0, 1e-9):
        raise CADInterfaceContractError(f"{interface_id}.api_frame X/Y axes are not orthogonal")
    if not _near(_dot(x_axis, z_axis), 0.0, 1e-9):
        raise CADInterfaceContractError(f"{interface_id}.api_frame X/Z axes are not orthogonal")
    if not _near(_dot(y_axis, z_axis), 0.0, 1e-9):
        raise CADInterfaceContractError(f"{interface_id}.api_frame Y/Z axes are not orthogonal")

    semantics = _obj(frame.get("axis_semantics"), f"{interface_id}.api_frame.axis_semantics")
    if semantics != {"x": "PRODUCT_FLOW", "y": "LATERAL", "z": "UP"}:
        raise CADInterfaceContractError(
            f"{interface_id}.api_frame axis semantics must be PRODUCT_FLOW/LATERAL/UP"
        )


def derive_local_displacement(
    from_interface: Mapping[str, Any],
    to_interface: Mapping[str, Any],
) -> list[float]:
    """Derive to-from displacement expressed in the source interface frame."""

    from_frame = _obj(from_interface.get("api_frame"), "from_interface.api_frame")
    to_frame = _obj(to_interface.get("api_frame"), "to_interface.api_frame")
    from_transform = _vec(from_frame.get("transform16"), 16, "from_interface.transform16")
    to_transform = _vec(to_frame.get("transform16"), 16, "to_interface.transform16")

    world_delta_mm = [
        (to_transform[9 + i] - from_transform[9 + i]) * 1000.0
        for i in range(3)
    ]
    x_axis, y_axis, z_axis = _frame_axes(from_transform)
    return [
        _dot(world_delta_mm, x_axis),
        _dot(world_delta_mm, y_axis),
        _dot(world_delta_mm, z_axis),
    ]


def validate_contract(contract: Mapping[str, Any]) -> Dict[str, Any]:
    model = _obj(contract, "contract")
    if model.get("schema_version") != 1:
        raise CADInterfaceContractError("schema_version must equal 1")
    _string(model.get("contract_id"), "contract_id")

    if model.get("mechanical_acceptance_granted") is not False:
        raise CADInterfaceContractError("CAD interface contract must not grant mechanical acceptance")

    document = _obj(model.get("document"), "document")
    _string(document.get("title_exact"), "document.title_exact")
    _string(document.get("path_exact"), "document.path_exact")
    if document.get("geometry_state") not in {
        "SOURCE_GEOMETRY",
        "FIT_CHECK",
        "CANDIDATE_OPERATING",
        "MECHANICALLY_ACCEPTED",
    }:
        raise CADInterfaceContractError("document.geometry_state is not recognized")

    convention = _obj(model.get("frame_convention"), "frame_convention")
    expected_convention = {
        "flow_axis": "+X",
        "lateral_axis": "+Y",
        "up_axis": "+Z",
        "handedness": "RIGHT_HANDED",
    }
    if dict(convention) != expected_convention:
        raise CADInterfaceContractError(
            "frame_convention must be +X flow, +Y lateral, +Z up, right-handed"
        )

    interfaces = _interface_index(model)
    roles = {}
    for interface_id, interface in interfaces.items():
        role = _string(interface.get("semantic_role"), f"{interface_id}.semantic_role")
        if role not in {"PRODUCT_ENTRY", "PRODUCT_EXIT", "OTHER"}:
            raise CADInterfaceContractError(f"{interface_id}.semantic_role is not recognized")
        if role in {"PRODUCT_ENTRY", "PRODUCT_EXIT"}:
            if role in roles:
                raise CADInterfaceContractError(f"duplicate semantic role: {role}")
            roles[role] = interface_id

        if interface.get("mechanical_acceptance_granted") is not False:
            raise CADInterfaceContractError(
                f"{interface_id} must not grant mechanical acceptance"
            )

        native = _obj(
            interface.get("native_published_reference"),
            f"{interface_id}.native_published_reference",
        )
        if native.get("feature_type") != "MagneticConnectRef":
            raise CADInterfaceContractError(
                f"{interface_id}.native_published_reference.feature_type must be MagneticConnectRef"
            )
        if native.get("identity_state") != "VERIFIED":
            raise CADInterfaceContractError(
                f"{interface_id}.native_published_reference.identity_state must be VERIFIED"
            )
        if native.get("semantic_binding_authority") != "HUMAN_OBSERVATION":
            raise CADInterfaceContractError(
                f"{interface_id} semantic connector role must retain HUMAN_OBSERVATION authority"
            )
        if native.get("semantic_binding_state") != "VERIFIED":
            raise CADInterfaceContractError(
                f"{interface_id} semantic connector role must be VERIFIED"
            )
        if native.get("geometry_binding_state") not in {"VERIFIED", "UNRESOLVED"}:
            raise CADInterfaceContractError(
                f"{interface_id}.native_published_reference.geometry_binding_state is invalid"
            )

        pairing = _obj(interface.get("pairing"), f"{interface_id}.pairing")
        if pairing.get("semantic_pairing_state") != "VERIFIED":
            raise CADInterfaceContractError(
                f"{interface_id}.pairing.semantic_pairing_state must be VERIFIED"
            )
        if pairing.get("geometric_coincidence_state") not in {"VERIFIED", "UNRESOLVED"}:
            raise CADInterfaceContractError(
                f"{interface_id}.pairing.geometric_coincidence_state is invalid"
            )

        frame = _obj(interface.get("api_frame"), f"{interface_id}.api_frame")
        _validate_frame(interface_id, frame)

    if set(roles) != {"PRODUCT_ENTRY", "PRODUCT_EXIT"}:
        raise CADInterfaceContractError(
            "contract must contain exactly one PRODUCT_ENTRY and one PRODUCT_EXIT"
        )

    relation_results = {}
    relation_ids = set()
    for position, value in enumerate(_list(model.get("relations"), "relations")):
        relation = _obj(value, f"relations[{position}]")
        relation_id = _string(relation.get("id"), f"relations[{position}].id")
        if relation_id in relation_ids:
            raise CADInterfaceContractError(f"duplicate relation id: {relation_id}")
        relation_ids.add(relation_id)

        if relation.get("mechanical_acceptance_granted") is not False:
            raise CADInterfaceContractError(
                f"relation {relation_id} must not grant mechanical acceptance"
            )
        if relation.get("relation_type") != "PRODUCT_FLOW_PATH":
            raise CADInterfaceContractError(
                f"relation {relation_id}.relation_type must be PRODUCT_FLOW_PATH"
            )
        if relation.get("evidence_state") != "MEASURED_CALCULATED":
            raise CADInterfaceContractError(
                f"relation {relation_id}.evidence_state must be MEASURED_CALCULATED"
            )
        if relation.get("source_authority") != "DETERMINISTIC_CALCULATION":
            raise CADInterfaceContractError(
                f"relation {relation_id}.source_authority must be DETERMINISTIC_CALCULATION"
            )

        from_id = _string(relation.get("from_interface_id"), f"relation {relation_id}.from_interface_id")
        to_id = _string(relation.get("to_interface_id"), f"relation {relation_id}.to_interface_id")
        if from_id not in interfaces or to_id not in interfaces:
            raise CADInterfaceContractError(
                f"relation {relation_id} references an unknown interface"
            )

        derived = derive_local_displacement(interfaces[from_id], interfaces[to_id])
        declared = _vec(
            relation.get("derived_local_displacement_mm"),
            3,
            f"relation {relation_id}.derived_local_displacement_mm",
        )
        if any(not _near(a, b, 1e-6) for a, b in zip(derived, declared)):
            raise CADInterfaceContractError(
                f"relation {relation_id} declared displacement disagrees with frame transforms"
            )
        relation_results[relation_id] = derived

    return {
        "contract_id": model["contract_id"],
        "interfaces": interfaces,
        "semantic_roles": roles,
        "relation_local_displacements_mm": relation_results,
        "mechanical_acceptance_granted": False,
    }
