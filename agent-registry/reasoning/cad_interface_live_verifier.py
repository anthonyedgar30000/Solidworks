#!/usr/bin/env python3
"""Read-only evidence verifier for CADGrounded CAD interface contracts.

The verifier compares a declared CAD interface contract with one bounded native
SOLIDWORKS observation.  It is deliberately a consumer of evidence, not a CAD
driver: it does not attach to SOLIDWORKS, mutate a document, rebaseline a
contract, or grant mechanical acceptance.

In particular, the bounded native observation implemented for v1 can identify
named ``MagneticConnectRef`` features under the exact FeatureManager
``Published References`` / ``ConnectRefMgr`` branch and named ``CoordSys``
transforms.  It does *not* establish geometric coincidence between a Published
Asset connector and a coordinate system.  That claim stays UNRESOLVED here.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from cad_interface_contract import CADInterfaceContractError, validate_contract


class CADInterfaceLiveVerificationError(ValueError):
    """Raised only for an invalid verifier invocation or malformed baseline."""


EXPECTED_COMMAND_ID = "sw.query_interface_contract"
EXPECTED_SOURCE_CLASSIFICATION = "verified_from_solidworks_api"
EXPECTED_PUBLISHED_REFERENCE_MANAGER_BINDING_STATE = (
    "VERIFIED_FEATURE_MANAGER_TREE_BRANCH"
)
EXPECTED_PUBLISHED_REFERENCE_MANAGER_TEXT = "Published References"
EXPECTED_PUBLISHED_REFERENCE_MANAGER_TYPE = "ConnectRefMgr"
EXPECTED_COORDSYS_API_PROVENANCE = (
    "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> "
    "IMathTransform.ArrayData"
)
EXPECTED_FEATURE_MANAGER_API_PROVENANCE = (
    "IModelDoc2.FeatureManager -> "
    "IFeatureManager.GetFeatureTreeRootItem2(swFeatMgrPaneBottom)"
)
LIVE_STATE_VERIFIED = "VERIFIED_CURRENT"
LIVE_STATE_STALE = "STALE_STATE"
LIVE_STATE_DRIFT = "DRIFT_DETECTED"
LIVE_STATE_AUTHORITY_REJECTED = "AUTHORITY_REJECTED"
LIVE_STATE_OBSERVATION_REJECTED = "OBSERVATION_REJECTED"


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CADInterfaceLiveVerificationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CADInterfaceLiveVerificationError(f"{label} must be an array")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CADInterfaceLiveVerificationError(f"{label} must be a non-empty string")
    return value


def _numbers(value: Any, length: int, label: str) -> list[float]:
    values = _array(value, label)
    if len(values) != length:
        raise CADInterfaceLiveVerificationError(
            f"{label} must contain exactly {length} values"
        )
    result: list[float] = []
    for index, item in enumerate(values):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise CADInterfaceLiveVerificationError(
                f"{label}[{index}] must be a finite number"
            )
        number = float(item)
        if not math.isfinite(number):
            raise CADInterfaceLiveVerificationError(
                f"{label}[{index}] must be a finite number"
            )
        result.append(number)
    return result


def _issue(code: str, message: str, *, path: str | None = None) -> dict[str, str]:
    result = {"code": code, "message": message}
    if path is not None:
        result["path"] = path
    return result


def _report_base(contract: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_contract(contract)
    interfaces = validated["interfaces"]
    geometry = {
        interface_id: "UNRESOLVED" for interface_id in sorted(interfaces)
    }
    return {
        "schema_version": 1,
        "verifier": "CADGrounded Interface Consumption & Live Verification v1",
        "contract_id": validated["contract_id"],
        "expected_command_id": EXPECTED_COMMAND_ID,
        "source_authority_required": "SOLIDWORKS_LIVE_STATE",
        "remote_queue_authorized": False,
        "write_authority": "NONE",
        "model_mutation": False,
        "mechanical_acceptance_granted": False,
        "published_asset_coordinate_system_geometric_coincidence": geometry,
        "interface_alignment_scope": (
            "Coordinate-system identity/orientation comparison only; it is not "
            "a connection, mate, collision, motion, force, or mechanical-acceptance proof."
        ),
    }


def stale_live_verification(
    contract: Mapping[str, Any], reason: str = "No fresh native interface observation was supplied."
) -> dict[str, Any]:
    """Represent unavailable fresh live evidence without propagating old state."""

    report = _report_base(contract)
    report.update(
        {
            "live_verification_state": LIVE_STATE_STALE,
            "interface_alignment_state": "UNRESOLVED",
            "issues": [
                _issue(
                    "FRESH_NATIVE_OBSERVATION_UNAVAILABLE",
                    reason,
                )
            ],
            "observed_document": None,
            "verified_interfaces": [],
            "connection_transform_eligible": False,
        }
    )
    return report


def _expected_interfaces(contract: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    published: dict[str, Mapping[str, Any]] = {}
    frames: dict[str, Mapping[str, Any]] = {}
    for interface in contract["interfaces"]:
        interface_id = interface["id"]
        published[interface["native_published_reference"]["connector_name"]] = {
            "interface_id": interface_id,
            "reference": interface["native_published_reference"],
        }
        frames[interface["api_frame"]["feature_name"]] = {
            "interface_id": interface_id,
            "frame": interface["api_frame"],
        }
    return published, frames


def _validate_published_reference_manager_binding(
    data: Mapping[str, Any],
    authority_issues: list[dict[str, str]],
    drift_issues: list[dict[str, str]],
    observation_issues: list[dict[str, str]],
) -> bool:
    """Validate the bounded FeatureManager branch required for connector identity.

    This is intentionally only an identity/parentage check.  The tree branch
    does not expose or prove connector point/direction geometry.
    """

    if (
        data.get("published_reference_manager_binding_state")
        != EXPECTED_PUBLISHED_REFERENCE_MANAGER_BINDING_STATE
    ):
        authority_issues.append(
            _issue(
                "PUBLISHED_REFERENCE_MANAGER_BINDING_REJECTED",
                "Native observation did not verify the required bounded "
                "FeatureManager Published References branch.",
                path="data.published_reference_manager_binding_state",
            )
        )
        return False

    try:
        manager = _object(
            data.get("published_reference_manager"),
            "observation.data.published_reference_manager",
        )
        displayed_text = _string(
            manager.get("displayed_tree_text"),
            "observation.data.published_reference_manager.displayed_tree_text",
        )
        feature_name = _string(
            manager.get("feature_name"),
            "observation.data.published_reference_manager.feature_name",
        )
        feature_type = _string(
            manager.get("feature_type"),
            "observation.data.published_reference_manager.feature_type",
        )
        _string(
            manager.get("tree_path"),
            "observation.data.published_reference_manager.tree_path",
        )
    except CADInterfaceLiveVerificationError as error:
        observation_issues.append(
            _issue(
                "MALFORMED_OBSERVATION",
                str(error),
                path="data.published_reference_manager",
            )
        )
        return False

    matches = (
        displayed_text == EXPECTED_PUBLISHED_REFERENCE_MANAGER_TEXT
        and feature_name == EXPECTED_PUBLISHED_REFERENCE_MANAGER_TEXT
        and feature_type == EXPECTED_PUBLISHED_REFERENCE_MANAGER_TYPE
    )
    if not matches:
        drift_issues.append(
            _issue(
                "PUBLISHED_REFERENCE_MANAGER_BRANCH_DRIFT",
                "Expected exact FeatureManager manager branch "
                "displayed/name='Published References' and type='ConnectRefMgr'.",
                path="data.published_reference_manager",
            )
        )
        return False
    return True


def _validate_published_reference_parent_branch(
    row: Mapping[str, Any],
    connector_name: str,
    drift_issues: list[dict[str, str]],
    observation_issues: list[dict[str, str]],
) -> bool:
    try:
        _string(
            row.get("tree_path"),
            f"data.published_reference_features[{connector_name}].tree_path",
        )
        parent_tree_text = _string(
            row.get("parent_tree_text"),
            f"data.published_reference_features[{connector_name}].parent_tree_text",
        )
        parent_feature_name = _string(
            row.get("parent_feature_name"),
            f"data.published_reference_features[{connector_name}].parent_feature_name",
        )
        parent_feature_type = _string(
            row.get("parent_feature_type"),
            f"data.published_reference_features[{connector_name}].parent_feature_type",
        )
    except CADInterfaceLiveVerificationError as error:
        observation_issues.append(
            _issue(
                "MALFORMED_OBSERVATION",
                str(error),
                path=f"data.published_reference_features[{connector_name}]",
            )
        )
        return False

    if (
        parent_tree_text != EXPECTED_PUBLISHED_REFERENCE_MANAGER_TEXT
        or parent_feature_name != EXPECTED_PUBLISHED_REFERENCE_MANAGER_TEXT
        or parent_feature_type != EXPECTED_PUBLISHED_REFERENCE_MANAGER_TYPE
    ):
        drift_issues.append(
            _issue(
                "PUBLISHED_REFERENCE_PARENT_BRANCH_DRIFT",
                f"Connector '{connector_name}' must be a direct child of exact "
                "Published References / ConnectRefMgr FeatureManager branch.",
                path=f"data.published_reference_features[{connector_name}]",
            )
        )
        return False
    return True


def _state_for_issues(
    authority_issues: Sequence[Mapping[str, str]],
    drift_issues: Sequence[Mapping[str, str]],
    observation_issues: Sequence[Mapping[str, str]],
) -> str:
    if authority_issues:
        return LIVE_STATE_AUTHORITY_REJECTED
    if drift_issues:
        return LIVE_STATE_DRIFT
    if observation_issues:
        return LIVE_STATE_OBSERVATION_REJECTED
    return LIVE_STATE_VERIFIED


def _index_observed_rows(
    rows: Any,
    name_key: str,
    label: str,
    observation_issues: list[dict[str, str]],
) -> dict[str, Mapping[str, Any]]:
    try:
        row_list = _array(rows, label)
    except CADInterfaceLiveVerificationError as error:
        observation_issues.append(_issue("MALFORMED_OBSERVATION", str(error), path=label))
        return {}

    indexed: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(row_list):
        path = f"{label}[{index}]"
        try:
            row = _object(raw, path)
            name = _string(row.get(name_key), f"{path}.{name_key}")
        except CADInterfaceLiveVerificationError as error:
            observation_issues.append(_issue("MALFORMED_OBSERVATION", str(error), path=path))
            continue
        if name in indexed:
            observation_issues.append(
                _issue(
                    "DUPLICATE_FEATURE_OBSERVATION",
                    f"{label} contains more than one row for exact name '{name}'.",
                    path=path,
                )
            )
            continue
        indexed[name] = row
    return indexed


def _transform_drift(
    expected: Sequence[float],
    observed: Sequence[float],
    transform_tolerance_mm: float,
) -> Iterable[tuple[int, float, float]]:
    for index, (expected_value, observed_value) in enumerate(zip(expected, observed)):
        tolerance = transform_tolerance_mm / 1000.0 if 9 <= index <= 11 else 1e-9
        if abs(expected_value - observed_value) > tolerance:
            yield index, expected_value, observed_value


def _known_geometric_claims(contract: Mapping[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for interface in contract["interfaces"]:
        interface_id = interface["id"]
        native = interface["native_published_reference"]
        pairing = interface["pairing"]
        if native["geometry_binding_state"] != "UNRESOLVED" or pairing[
            "geometric_coincidence_state"
        ] != "UNRESOLVED":
            issues.append(
                _issue(
                    "GEOMETRIC_COINCIDENCE_REQUIRES_SEPARATE_AUTHORITY",
                    (
                        f"{interface_id} claims Published Asset-to-coordinate-system geometry, "
                        "but sw.query_interface_contract v1 does not observe connector geometry."
                    ),
                    path=f"interfaces[{interface_id}]",
                )
            )
    return issues


def verify_live_interface_contract(
    contract: Mapping[str, Any],
    observation: Mapping[str, Any] | None,
    *,
    transform_tolerance_mm: float = 0.001,
) -> dict[str, Any]:
    """Compare one native observation against a contract without rebaselining it.

    A successful result proves only that the exact named feature identities and
    coordinate-system frames did not drift from the declared baseline within the
    stated tolerance.  A missing current observation is deliberately reported
    as ``STALE_STATE`` rather than being filled from historical contract data.
    """

    if transform_tolerance_mm < 0 or not math.isfinite(transform_tolerance_mm):
        raise CADInterfaceLiveVerificationError(
            "transform_tolerance_mm must be a finite non-negative number"
        )

    if observation is None:
        return stale_live_verification(contract)

    report = _report_base(contract)
    authority_issues: list[dict[str, str]] = _known_geometric_claims(contract)
    drift_issues: list[dict[str, str]] = []
    observation_issues: list[dict[str, str]] = []
    observed_document: Mapping[str, Any] | None = None
    verified_interfaces: list[str] = []

    try:
        envelope = _object(observation, "observation")
    except CADInterfaceLiveVerificationError as error:
        observation_issues.append(_issue("MALFORMED_OBSERVATION", str(error)))
        envelope = {}

    if envelope.get("ok") is not True:
        observation_issues.append(
            _issue("OBSERVATION_NOT_OK", "Native observation must have ok=true.", path="ok")
        )
    if envelope.get("command_id") != EXPECTED_COMMAND_ID:
        authority_issues.append(
            _issue(
                "COMMAND_SCOPE_REJECTED",
                f"Expected command_id '{EXPECTED_COMMAND_ID}'.",
                path="command_id",
            )
        )
    if envelope.get("source_classification") != EXPECTED_SOURCE_CLASSIFICATION:
        authority_issues.append(
            _issue(
                "SOURCE_AUTHORITY_REJECTED",
                "Observation is not classified as verified_from_solidworks_api.",
                path="source_classification",
            )
        )

    data: Mapping[str, Any]
    try:
        data = _object(envelope.get("data"), "observation.data")
    except CADInterfaceLiveVerificationError as error:
        observation_issues.append(_issue("MALFORMED_OBSERVATION", str(error), path="data"))
        data = {}

    if data.get("write_authority") != "NONE":
        authority_issues.append(
            _issue(
                "WRITE_AUTHORITY_REJECTED",
                "Native observation must report write_authority=NONE.",
                path="data.write_authority",
            )
        )
    if data.get("model_mutation") is not False:
        authority_issues.append(
            _issue(
                "MUTATION_BOUNDARY_REJECTED",
                "Native observation must report model_mutation=false.",
                path="data.model_mutation",
            )
        )
    if data.get("result_scope") != "EXACT_NAMED_FEATURES_ONLY":
        authority_issues.append(
            _issue(
                "READ_SCOPE_REJECTED",
                "Native observation did not prove the bounded exact-feature read scope.",
                path="data.result_scope",
            )
        )
    if data.get("evidence") != EXPECTED_SOURCE_CLASSIFICATION:
        authority_issues.append(
            _issue(
                "DATA_SOURCE_AUTHORITY_REJECTED",
                "Native observation data must retain verified_from_solidworks_api classification.",
                path="data.evidence",
            )
        )
    if data.get("geometry_binding_state") != "UNRESOLVED":
        authority_issues.append(
            _issue(
                "GEOMETRY_SCOPE_REJECTED",
                "Native query must retain Published Asset connector geometry binding as UNRESOLVED.",
                path="data.geometry_binding_state",
            )
        )

    try:
        _string(
            data.get("published_reference_manager_binding_note"),
            "observation.data.published_reference_manager_binding_note",
        )
        _string(
            data.get("interpretation_note"),
            "observation.data.interpretation_note",
        )
        api_provenance = _string(data.get("api"), "observation.data.api")
    except CADInterfaceLiveVerificationError as error:
        observation_issues.append(
            _issue("MALFORMED_OBSERVATION", str(error), path="data")
        )
    else:
        if EXPECTED_COORDSYS_API_PROVENANCE not in api_provenance:
            authority_issues.append(
                _issue(
                    "COORDSYS_PROVENANCE_REJECTED",
                    "Native observation must retain the bounded CoordSys GetDefinition getter chain.",
                    path="data.api",
                )
            )
        if EXPECTED_FEATURE_MANAGER_API_PROVENANCE not in api_provenance:
            authority_issues.append(
                _issue(
                    "PUBLISHED_REFERENCE_PROVENANCE_REJECTED",
                    "Native observation must retain the bounded FeatureManager-tree getter chain.",
                    path="data.api",
                )
            )

    try:
        observed_document = _object(data.get("document"), "observation.data.document")
        title = _string(observed_document.get("title"), "observation.data.document.title")
        path = _string(observed_document.get("path"), "observation.data.document.path")
        _string(observed_document.get("type"), "observation.data.document.type")
        _string(
            observed_document.get("active_configuration"),
            "observation.data.document.active_configuration",
        )
        if "save_flag" not in observed_document:
            raise CADInterfaceLiveVerificationError(
                "observation.data.document.save_flag is required"
            )
        if title != contract["document"]["title_exact"]:
            drift_issues.append(
                _issue(
                    "DOCUMENT_TITLE_DRIFT",
                    f"Expected title '{contract['document']['title_exact']}', observed '{title}'.",
                    path="data.document.title",
                )
            )
        if path.casefold() != contract["document"]["path_exact"].casefold():
            drift_issues.append(
                _issue(
                    "DOCUMENT_PATH_DRIFT",
                    f"Expected path '{contract['document']['path_exact']}', observed '{path}'.",
                    path="data.document.path",
                )
            )
        if observed_document.get("type") != "assembly":
            drift_issues.append(
                _issue(
                    "DOCUMENT_TYPE_DRIFT",
                    "Interface contract v1 requires an active assembly document.",
                    path="data.document.type",
                )
            )
    except CADInterfaceLiveVerificationError as error:
        observation_issues.append(_issue("MALFORMED_OBSERVATION", str(error), path="data.document"))
        observed_document = None

    expected_connectors, expected_frames = _expected_interfaces(contract)
    manager_binding_verified = _validate_published_reference_manager_binding(
        data,
        authority_issues,
        drift_issues,
        observation_issues,
    )
    observed_connectors = _index_observed_rows(
        data.get("published_reference_features"),
        "connector_name",
        "data.published_reference_features",
        observation_issues,
    )
    observed_frames = _index_observed_rows(
        data.get("coordinate_systems"),
        "feature_name",
        "data.coordinate_systems",
        observation_issues,
    )

    unexpected_connectors = sorted(set(observed_connectors) - set(expected_connectors))
    unexpected_frames = sorted(set(observed_frames) - set(expected_frames))
    if unexpected_connectors:
        authority_issues.append(
            _issue(
                "READ_SCOPE_REJECTED",
                "Observation returned unexpected connector rows: " + ", ".join(unexpected_connectors),
                path="data.published_reference_features",
            )
        )
    if unexpected_frames:
        authority_issues.append(
            _issue(
                "READ_SCOPE_REJECTED",
                "Observation returned unexpected coordinate-system rows: " + ", ".join(unexpected_frames),
                path="data.coordinate_systems",
            )
        )

    connector_verified_by_interface: dict[str, bool] = {}
    for connector_name, expected in expected_connectors.items():
        interface_id = expected["interface_id"]
        row = observed_connectors.get(connector_name)
        if row is None:
            drift_issues.append(
                _issue(
                    "PUBLISHED_REFERENCE_MISSING",
                    f"Expected exact connector '{connector_name}' was not observed.",
                    path="data.published_reference_features",
                )
            )
            connector_verified_by_interface[interface_id] = False
            continue
        if row.get("feature_type") != expected["reference"]["feature_type"]:
            drift_issues.append(
                _issue(
                    "PUBLISHED_REFERENCE_TYPE_DRIFT",
                    (
                        f"Connector '{connector_name}' must have type "
                        f"'{expected['reference']['feature_type']}'."
                    ),
                    path=f"data.published_reference_features[{connector_name}].feature_type",
                )
            )
            connector_verified_by_interface[interface_id] = False
            continue
        if not manager_binding_verified:
            connector_verified_by_interface[interface_id] = False
            continue
        if not _validate_published_reference_parent_branch(
            row,
            connector_name,
            drift_issues,
            observation_issues,
        ):
            connector_verified_by_interface[interface_id] = False
            continue
        connector_verified_by_interface[interface_id] = True

    frame_verified_by_interface: dict[str, bool] = {}
    for feature_name, expected in expected_frames.items():
        interface_id = expected["interface_id"]
        row = observed_frames.get(feature_name)
        if row is None:
            drift_issues.append(
                _issue(
                    "COORDINATE_SYSTEM_MISSING",
                    f"Expected exact coordinate system '{feature_name}' was not observed.",
                    path="data.coordinate_systems",
                )
            )
            frame_verified_by_interface[interface_id] = False
            continue

        if row.get("feature_type") != expected["frame"]["feature_type"]:
            drift_issues.append(
                _issue(
                    "COORDINATE_SYSTEM_TYPE_DRIFT",
                    f"Coordinate system '{feature_name}' must have type CoordSys.",
                    path=f"data.coordinate_systems[{feature_name}].feature_type",
                )
            )
            frame_verified_by_interface[interface_id] = False
            continue

        try:
            observed_transform = _numbers(
                row.get("transform16"),
                16,
                f"data.coordinate_systems[{feature_name}].transform16",
            )
            observed_origin = _numbers(
                row.get("origin_mm"),
                3,
                f"data.coordinate_systems[{feature_name}].origin_mm",
            )
            _string(
                row.get("transform_source"),
                f"data.coordinate_systems[{feature_name}].transform_source",
            )
        except CADInterfaceLiveVerificationError as error:
            observation_issues.append(
                _issue(
                    "MALFORMED_OBSERVATION",
                    str(error),
                    path=f"data.coordinate_systems[{feature_name}]",
                )
            )
            frame_verified_by_interface[interface_id] = False
            continue

        if any(
            abs(observed_origin[index] - observed_transform[9 + index] * 1000.0)
            > transform_tolerance_mm
            for index in range(3)
        ):
            observation_issues.append(
                _issue(
                    "INTERNAL_TRANSFORM_INCONSISTENCY",
                    f"Coordinate system '{feature_name}' origin_mm disagrees with transform16 translation.",
                    path=f"data.coordinate_systems[{feature_name}]",
                )
            )
            frame_verified_by_interface[interface_id] = False
            continue

        expected_transform = [float(value) for value in expected["frame"]["transform16"]]
        transform_drift = list(
            _transform_drift(
                expected_transform,
                observed_transform,
                transform_tolerance_mm,
            )
        )
        if transform_drift:
            index, expected_value, observed_value = transform_drift[0]
            drift_issues.append(
                _issue(
                    "COORDINATE_SYSTEM_TRANSFORM_DRIFT",
                    (
                        f"Coordinate system '{feature_name}' transform16[{index}] drifted: "
                        f"expected {expected_value}, observed {observed_value}."
                    ),
                    path=f"data.coordinate_systems[{feature_name}].transform16[{index}]",
                )
            )
            frame_verified_by_interface[interface_id] = False
            continue

        frame_verified_by_interface[interface_id] = True

    for interface_id in sorted(frame_verified_by_interface):
        if frame_verified_by_interface[interface_id] and connector_verified_by_interface.get(
            interface_id, False
        ):
            verified_interfaces.append(interface_id)

    state = _state_for_issues(authority_issues, drift_issues, observation_issues)
    report.update(
        {
            "live_verification_state": state,
            "interface_alignment_state": (
                "VERIFIED_CURRENT_FRAME_BASELINE_ONLY"
                if state == LIVE_STATE_VERIFIED
                else "UNRESOLVED"
            ),
            "transform_tolerance_mm": transform_tolerance_mm,
            "observed_document": dict(observed_document) if observed_document is not None else None,
            "verified_interfaces": verified_interfaces if state == LIVE_STATE_VERIFIED else [],
            "authority_issues": authority_issues,
            "drift_issues": drift_issues,
            "observation_issues": observation_issues,
            "issues": authority_issues + drift_issues + observation_issues,
            "connection_transform_eligible": state == LIVE_STATE_VERIFIED,
        }
    )
    return report


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CADInterfaceLiveVerificationError(f"Unable to read '{path}': {error}") from error
    except json.JSONDecodeError as error:
        raise CADInterfaceLiveVerificationError(f"Invalid JSON in '{path}': {error}") from error
    return _object(value, str(path))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="CAD interface contract JSON")
    parser.add_argument(
        "observation",
        nargs="?",
        type=Path,
        help="fresh local sw.query_interface_contract envelope JSON",
    )
    parser.add_argument("--out", type=Path, help="write the verification report as JSON")
    parser.add_argument("--summary", action="store_true", help="print a compact status line")
    parser.add_argument(
        "--transform-tolerance-mm",
        type=float,
        default=0.001,
        help="maximum allowed coordinate translation drift in millimetres (default: 0.001)",
    )
    args = parser.parse_args(argv)

    try:
        contract = _load_json(args.contract)
        observation = _load_json(args.observation) if args.observation is not None else None
        report = verify_live_interface_contract(
            contract,
            observation,
            transform_tolerance_mm=args.transform_tolerance_mm,
        )
    except (CADInterfaceContractError, CADInterfaceLiveVerificationError) as error:
        parser.error(str(error))

    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    if args.summary:
        print(
            "live_verification_state={state} verified_interfaces={count} "
            "mechanical_acceptance_granted=false".format(
                state=report["live_verification_state"],
                count=len(report["verified_interfaces"]),
            )
        )
    elif args.out is None:
        print(encoded, end="")
    return 0 if report["live_verification_state"] == LIVE_STATE_VERIFIED else 2


if __name__ == "__main__":
    raise SystemExit(main())
