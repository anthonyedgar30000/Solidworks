#!/usr/bin/env python3
"""Deterministic, non-mutating CAD interface-consumption calculations.

This module produces a *proposal* for placing a complementary asset frame at a
declared target interface.  It does not create an asset, insert a component,
set a transform, create a mate, or grant mechanical acceptance.  A calculated
frame alignment is intentionally much narrower than a mechanically acceptable
connection.

Transform convention
--------------------

CADGrounded uses the SOLIDWORKS ``IMathTransform.ArrayData`` convention used by
the existing interface contract: the first nine values are the local axes
expressed in the parent frame (row-vector form), values 9--11 are translation
in metres, and values 12--15 are ``[1, 0, 0, 0]``.  With a local row vector
``p``, the transform acts as ``p_parent = p_local * R + t``.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from cad_interface_contract import CADInterfaceContractError, validate_contract
from cad_interface_live_verifier import LIVE_STATE_VERIFIED


class CADInterfaceConsumptionError(ValueError):
    pass


IDENTITY_TRANSFORM16 = [
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
]


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CADInterfaceConsumptionError(f"{label} must be an object")
    return value


def _numbers(value: Any, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise CADInterfaceConsumptionError(f"{label} must contain exactly {length} values")
    result: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise CADInterfaceConsumptionError(f"{label}[{index}] must be a finite number")
        number = float(item)
        if not math.isfinite(number):
            raise CADInterfaceConsumptionError(f"{label}[{index}] must be a finite number")
        result.append(number)
    return result


def _near(a: float, b: float, tolerance: float = 1e-9) -> bool:
    return abs(a - b) <= tolerance


def _matrix(transform16: Sequence[float]) -> list[list[float]]:
    return [list(transform16[0:3]), list(transform16[3:6]), list(transform16[6:9])]


def _translation(transform16: Sequence[float]) -> list[float]:
    return list(transform16[9:12])


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(left * right for left, right in zip(a, b))


def _matmul(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> list[list[float]]:
    return [
        [_dot(row, [right[0][column], right[1][column], right[2][column]]) for column in range(3)]
        for row in left
    ]


def _row_vec_times_matrix(vector: Sequence[float], matrix: Sequence[Sequence[float]]) -> list[float]:
    return [
        vector[0] * matrix[0][column]
        + vector[1] * matrix[1][column]
        + vector[2] * matrix[2][column]
        for column in range(3)
    ]


def _transpose(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[matrix[column][row] for column in range(3)] for row in range(3)]


def _cross(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _validate_rigid_transform(transform16: Any, label: str) -> list[float]:
    transform = _numbers(transform16, 16, label)
    if any(not _near(value, expected) for value, expected in zip(transform[12:16], [1.0, 0.0, 0.0, 0.0])):
        raise CADInterfaceConsumptionError(
            f"{label} must be a unit-scale rigid IMathTransform.ArrayData value"
        )

    matrix = _matrix(transform)
    for index, axis in enumerate(matrix):
        if not _near(_dot(axis, axis), 1.0):
            raise CADInterfaceConsumptionError(f"{label} row {index} is not unit length")
    for left, right in ((0, 1), (0, 2), (1, 2)):
        if not _near(_dot(matrix[left], matrix[right]), 0.0):
            raise CADInterfaceConsumptionError(f"{label} rotation rows are not orthogonal")

    handedness = _dot(_cross(matrix[0], matrix[1]), matrix[2])
    if not _near(handedness, 1.0):
        raise CADInterfaceConsumptionError(f"{label} rotation must be right-handed")
    return transform


def compose_transform16(
    first: Sequence[float], second: Sequence[float]
) -> list[float]:
    """Compose row-vector transforms: ``p * first * second``."""

    first_valid = _validate_rigid_transform(list(first), "first transform16")
    second_valid = _validate_rigid_transform(list(second), "second transform16")
    first_rotation = _matrix(first_valid)
    second_rotation = _matrix(second_valid)
    rotation = _matmul(first_rotation, second_rotation)
    translated = _row_vec_times_matrix(_translation(first_valid), second_rotation)
    translation = [
        translated[index] + _translation(second_valid)[index] for index in range(3)
    ]
    return [
        *rotation[0],
        *rotation[1],
        *rotation[2],
        *translation,
        1.0,
        0.0,
        0.0,
        0.0,
    ]


def invert_transform16(transform16: Sequence[float]) -> list[float]:
    """Invert one right-handed unit-scale row-vector transform."""

    valid = _validate_rigid_transform(list(transform16), "transform16")
    rotation_inverse = _transpose(_matrix(valid))
    translation_inverse = [
        -value for value in _row_vec_times_matrix(_translation(valid), rotation_inverse)
    ]
    return [
        *rotation_inverse[0],
        *rotation_inverse[1],
        *rotation_inverse[2],
        *translation_inverse,
        1.0,
        0.0,
        0.0,
        0.0,
    ]


def calculate_connection_transform(
    target_interface_to_world_transform16: Sequence[float],
    asset_connection_to_asset_transform16: Sequence[float],
) -> list[float]:
    """Calculate the asset-to-world pose that aligns its local connection frame.

    Let ``C`` map connection-frame coordinates into asset coordinates and ``T``
    map target-interface coordinates into world coordinates.  The required
    asset pose ``A`` satisfies ``C * A = T``.  Therefore ``A = inverse(C) * T``
    using this module's row-vector composition convention.
    """

    target = _validate_rigid_transform(
        list(target_interface_to_world_transform16),
        "target_interface_to_world_transform16",
    )
    asset_connection = _validate_rigid_transform(
        list(asset_connection_to_asset_transform16),
        "asset_connection_to_asset_transform16",
    )
    return compose_transform16(invert_transform16(asset_connection), target)


def calculate_complementary_asset_proposal(
    contract: Mapping[str, Any],
    target_interface_id: str,
    asset_connection_to_asset_transform16: Sequence[float],
    *,
    live_verification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a non-materialized complementary-asset connection proposal."""

    validated = validate_contract(contract)
    interface = validated["interfaces"].get(target_interface_id)
    if interface is None:
        raise CADInterfaceConsumptionError(
            f"target interface '{target_interface_id}' is absent from the contract"
        )

    target_frame = interface["api_frame"]
    asset_pose = calculate_connection_transform(
        target_frame["transform16"],
        asset_connection_to_asset_transform16,
    )

    live_state = (
        live_verification.get("live_verification_state")
        if isinstance(live_verification, Mapping)
        else None
    )
    current_live_frame_state = (
        "VERIFIED_CURRENT"
        if live_state == LIVE_STATE_VERIFIED
        else "STALE_STATE"
    )

    return {
        "schema_version": 1,
        "proposal_type": "DISPOSABLE_COMPLEMENTARY_ASSET_INTERFACE_TEST",
        "contract_id": validated["contract_id"],
        "target_interface_id": target_interface_id,
        "target_coordinate_system": target_frame["feature_name"],
        "calculation_authority": "DETERMINISTIC_CALCULATION",
        "calculation_state": "MEASURED_CALCULATED",
        "current_live_frame_state": current_live_frame_state,
        "requires_fresh_live_verification_before_materialization": True,
        "cad_write_authorized": False,
        "materialization_state": "NOT_AUTHORIZED",
        "asset_connection_to_asset_transform16": list(
            _validate_rigid_transform(
                list(asset_connection_to_asset_transform16),
                "asset_connection_to_asset_transform16",
            )
        ),
        "proposed_asset_to_world_transform16": asset_pose,
        "published_asset_coordinate_system_geometric_coincidence_state": "UNRESOLVED",
        "interface_alignment_state": "FRAME_ALIGNMENT_PROPOSAL_ONLY",
        "mechanical_acceptance_granted": False,
        "does_not_establish": [
            "Published Asset connector geometric coincidence",
            "snap or mate success",
            "contact, collision clearance, or interference absence",
            "degrees of freedom, support, force, preload, or temporal operation",
            "mechanical acceptance",
        ],
    }


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CADInterfaceConsumptionError(f"Unable to read '{path}': {error}") from error
    except json.JSONDecodeError as error:
        raise CADInterfaceConsumptionError(f"Invalid JSON in '{path}': {error}") from error
    return _object(value, str(path))


def _asset_connection_transform_from_spec(spec: Mapping[str, Any]) -> list[float]:
    asset = _object(spec.get("complementary_asset"), "spec.complementary_asset")
    connection = _object(asset.get("connection_frame"), "spec.complementary_asset.connection_frame")
    return _validate_rigid_transform(
        connection.get("asset_connection_to_asset_transform16"),
        "spec.complementary_asset.connection_frame.asset_connection_to_asset_transform16",
    )


def calculate_spec_proposal(
    contract: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    live_verification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if spec.get("schema_version") != 1:
        raise CADInterfaceConsumptionError("spec.schema_version must equal 1")
    if spec.get("cad_write_authorized") is not False:
        raise CADInterfaceConsumptionError("disposable test spec must not authorize CAD writes")
    if spec.get("materialization_state") != "NOT_AUTHORIZED":
        raise CADInterfaceConsumptionError(
            "disposable test spec must remain NOT_AUTHORIZED for materialization"
        )
    target_interface_id = spec.get("target_interface_id")
    if not isinstance(target_interface_id, str) or not target_interface_id:
        raise CADInterfaceConsumptionError("spec.target_interface_id must be a non-empty string")
    proposal = calculate_complementary_asset_proposal(
        contract,
        target_interface_id,
        _asset_connection_transform_from_spec(spec),
        live_verification=live_verification,
    )
    proposal["test_id"] = spec.get("test_id")
    proposal["asset_id"] = _object(spec["complementary_asset"], "spec.complementary_asset").get(
        "asset_id"
    )
    return proposal


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="CAD interface contract JSON")
    parser.add_argument("test_spec", type=Path, help="disposable complementary-asset test JSON")
    parser.add_argument(
        "--live-verification",
        type=Path,
        help="optional current cad_interface_live_verifier report",
    )
    parser.add_argument("--out", type=Path, help="write calculated proposal JSON")
    parser.add_argument("--summary", action="store_true", help="print a compact result")
    args = parser.parse_args(argv)

    try:
        contract = _load_json(args.contract)
        spec = _load_json(args.test_spec)
        live_verification = (
            _load_json(args.live_verification)
            if args.live_verification is not None
            else None
        )
        proposal = calculate_spec_proposal(
            contract,
            spec,
            live_verification=live_verification,
        )
    except (CADInterfaceContractError, CADInterfaceConsumptionError) as error:
        parser.error(str(error))

    encoded = json.dumps(proposal, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    if args.summary:
        print(
            "proposal_type={proposal_type} current_live_frame_state={state} "
            "cad_write_authorized=false mechanical_acceptance_granted=false".format(
                proposal_type=proposal["proposal_type"],
                state=proposal["current_live_frame_state"],
            )
        )
    elif args.out is None:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
