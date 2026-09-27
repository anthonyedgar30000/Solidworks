from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class DiagnosticBindingError(ValueError):
    def __init__(self, violations: list[str]):
        self.violations = tuple(violations)
        super().__init__("; ".join(self.violations))


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8-sig")), _sha256_bytes(raw)


def _require(condition: bool, violation: str) -> None:
    if not condition:
        raise DiagnosticBindingError([violation])


def _relative_project_path(value: Any, field: str) -> Path:
    _require(
        isinstance(value, str) and bool(value.strip()),
        f"{field}_MISSING",
    )
    path = Path(value)
    _require(not path.is_absolute(), f"{field}_MUST_BE_RELATIVE")
    _require(".." not in path.parts, f"{field}_TRAVERSAL_NOT_ALLOWED")
    return path


def _read_project_json(
    repo_root: Path,
    relative: Path,
) -> tuple[dict[str, Any], str]:
    root = repo_root.resolve()
    path = (root / relative).resolve()
    _require(
        path == root or root in path.parents,
        "DIAGNOSTIC_PATH_OUTSIDE_REPOSITORY",
    )
    _require(path.is_file(), f"DIAGNOSTIC_FILE_MISSING:{relative.as_posix()}")
    return _read_json(path)
def _validate_preflight(
    plan: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    expected_preflight_id = plan.get("current_candidate_preflight_id")
    _require(
        preflight.get("preflight_id") == expected_preflight_id,
        "DIAGNOSTIC_PREFLIGHT_ID_MISMATCH",
    )
    _require(
        preflight.get("plan_id") == plan.get("current_plan_id"),
        "DIAGNOSTIC_PREFLIGHT_PLAN_MISMATCH",
    )
    _require(
        preflight.get("step_id") == plan.get("current_step_id"),
        "DIAGNOSTIC_PREFLIGHT_STEP_MISMATCH",
    )

    selected_candidate = plan.get("selected_first_pop_test_candidate")
    if selected_candidate:
        _require(
            preflight.get("candidate_id") == selected_candidate,
            "DIAGNOSTIC_PREFLIGHT_CANDIDATE_MISMATCH",
        )

    authority = preflight.get("authority") or {}
    _require(
        authority.get("cad_write_authority") == "NONE",
        "DIAGNOSTIC_PREFLIGHT_WRITE_AUTHORITY_NOT_NONE",
    )
    _require(
        authority.get("model_mutation_performed") is False,
        "DIAGNOSTIC_PREFLIGHT_MODEL_MUTATION_NOT_FALSE",
    )
    _require(
        authority.get("mechanical_acceptance_granted") is False,
        "DIAGNOSTIC_PREFLIGHT_MECHANICAL_ACCEPTANCE_NOT_FALSE",
    )

    required_test = preflight.get("required_next_read_only_test")
    _require(
        isinstance(required_test, dict),
        "DIAGNOSTIC_REQUIRED_TEST_MISSING",
    )
    _require(
        isinstance(required_test.get("test_id"), str)
        and bool(required_test["test_id"].strip()),
        "DIAGNOSTIC_REQUIRED_TEST_ID_MISSING",
    )
    _require(
        required_test.get("write_authority") == "NONE",
        "DIAGNOSTIC_REQUIRED_TEST_WRITE_AUTHORITY_NOT_NONE",
    )

    state_binding = preflight.get("state_binding") or {}
    _require(
        isinstance(state_binding.get("live_document_title_exact"), str)
        and bool(state_binding["live_document_title_exact"]),
        "DIAGNOSTIC_DOCUMENT_TITLE_MISSING",
    )
    _require(
        isinstance(state_binding.get("live_document_path_exact"), str)
        and bool(state_binding["live_document_path_exact"]),
        "DIAGNOSTIC_DOCUMENT_PATH_MISSING",
    )

    return {
        "test_id": required_test["test_id"],
        "purpose": required_test.get("purpose"),
        "write_authority": required_test["write_authority"],
        "no_mutation_contract": list(
            required_test.get("no_mutation_contract") or []
        ),
        "state_samples": required_test.get("state_samples"),
        "obstacle_set": list(required_test.get("obstacle_set") or []),
        "document_title_exact": state_binding["live_document_title_exact"],
        "document_path_exact": state_binding["live_document_path_exact"],
        "configuration_reference": state_binding.get(
            "configuration_reference"
        ),
        "candidate_id": preflight.get("candidate_id"),
        "candidate_motion_variant_id": preflight.get(
            "candidate_motion_variant_id"
        ),
        "preflight_status": preflight.get("status"),
    }
def _validate_attempt(
    plan: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> dict[str, Any]:
    _require(
        attempt.get("attempt_id") == plan.get("current_verification_attempt_id"),
        "DIAGNOSTIC_ATTEMPT_ID_MISMATCH",
    )
    _require(
        attempt.get("plan_id") == plan.get("current_plan_id"),
        "DIAGNOSTIC_ATTEMPT_PLAN_MISMATCH",
    )
    _require(
        attempt.get("step_id") == plan.get("current_step_id"),
        "DIAGNOSTIC_ATTEMPT_STEP_MISMATCH",
    )
    _require(
        attempt.get("candidate_preflight_id")
        == plan.get("current_candidate_preflight_id"),
        "DIAGNOSTIC_ATTEMPT_PREFLIGHT_MISMATCH",
    )
    _require(
        attempt.get("test_id") == diagnostic.get("test_id"),
        "DIAGNOSTIC_ATTEMPT_TEST_MISMATCH",
    )
    _require(
        attempt.get("write_authority") == "NONE",
        "DIAGNOSTIC_ATTEMPT_WRITE_AUTHORITY_NOT_NONE",
    )
    _require(
        attempt.get("model_mutation") is False,
        "DIAGNOSTIC_ATTEMPT_MODEL_MUTATION_NOT_FALSE",
    )
    _require(
        attempt.get("mechanical_acceptance_granted") is False,
        "DIAGNOSTIC_ATTEMPT_MECHANICAL_ACCEPTANCE_NOT_FALSE",
    )

    execution_result = attempt.get("execution_result")
    ambiguity_buckets = list(attempt.get("ambiguity_buckets") or [])

    if execution_result == "BLOCKED_BEFORE_GEOMETRY_EVALUATION":
        _require(
            "STALE_STATE" in ambiguity_buckets
            or "CAD_READ_REQUIRED" in ambiguity_buckets,
            "DIAGNOSTIC_BLOCKED_ATTEMPT_MISSING_READ_BLOCKER",
        )
        state = "BLOCKED_FRESH_CAD_REBIND_REQUIRED"
        next_action_mode = "REBIND_LIVE_CAD_BEFORE_DIAGNOSTIC"
        mechanical_effect = "NO_HYPOTHESIS_STATE_CHANGE"
    else:
        state = "EXECUTED_RESULT_REVIEW_REQUIRED"
        next_action_mode = "REVIEW_DIAGNOSTIC_RESULT"
        mechanical_effect = "NO_AUTOMATIC_HYPOTHESIS_STATE_CHANGE"

    return {
        "attempt_id": attempt.get("attempt_id"),
        "attempted_at_utc": attempt.get("attempted_at_utc"),
        "execution_result": execution_result,
        "ambiguity_buckets": ambiguity_buckets,
        "resume_condition": attempt.get("resume_condition"),
        "diagnostic_state": state,
        "next_action_mode": next_action_mode,
        "mechanical_effect": mechanical_effect,
        "admitted_project_state": list(
            attempt.get("admitted_project_state") or []
        ),
        "explicitly_not_claimed": list(
            attempt.get("explicitly_not_claimed") or []
        ),
    }
def bind_current_diagnostic(
    repo_root: Path,
    plan: Mapping[str, Any],
) -> dict[str, Any] | None:
    preflight_path_value = plan.get("current_candidate_preflight_path")
    if not preflight_path_value:
        return None

    preflight_relative = _relative_project_path(
        preflight_path_value,
        "CURRENT_CANDIDATE_PREFLIGHT_PATH",
    )
    preflight, preflight_sha256 = _read_project_json(
        repo_root,
        preflight_relative,
    )
    required = _validate_preflight(plan, preflight)

    result: dict[str, Any] = {
        **required,
        "plan_id": plan.get("current_plan_id"),
        "plan_status": plan.get("status"),
        "step_id": plan.get("current_step_id"),
        "preflight_id": plan.get("current_candidate_preflight_id"),
        "preflight_path": preflight_relative.as_posix(),
        "preflight_sha256": preflight_sha256,
        "diagnostic_state": "READY_FOR_READ_ONLY_EXECUTION",
        "next_action_mode": "RUN_BOUND_READ_ONLY_DIAGNOSTIC",
        "mechanical_effect": "NO_AUTOMATIC_HYPOTHESIS_STATE_CHANGE",
        "state_mutation_authority": "NONE",
        "cad_write_authority": "NONE",
        "mechanical_acceptance_authority": "NONE",
    }

    attempt_path_value = plan.get("current_verification_attempt_path")
    attempt_id = plan.get("current_verification_attempt_id")

    if bool(attempt_path_value) != bool(attempt_id):
        raise DiagnosticBindingError([
            "DIAGNOSTIC_ATTEMPT_POINTER_INCOMPLETE"
        ])

    if attempt_path_value:
        attempt_relative = _relative_project_path(
            attempt_path_value,
            "CURRENT_VERIFICATION_ATTEMPT_PATH",
        )
        attempt, attempt_sha256 = _read_project_json(
            repo_root,
            attempt_relative,
        )
        attempt_projection = _validate_attempt(
            plan,
            result,
            attempt,
        )
        result.update(attempt_projection)
        result.update({
            "attempt_path": attempt_relative.as_posix(),
            "attempt_sha256": attempt_sha256,
        })
    else:
        result.update({
            "attempt_id": None,
            "attempt_path": None,
            "attempt_sha256": None,
            "attempted_at_utc": None,
            "execution_result": None,
            "ambiguity_buckets": [],
            "resume_condition": None,
            "admitted_project_state": [],
            "explicitly_not_claimed": [],
        })

    return result
def diagnostic_snapshot_metadata(
    diagnostic: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if diagnostic is None:
        return None

    return {
        "plan_id": diagnostic.get("plan_id"),
        "plan_status": diagnostic.get("plan_status"),
        "step_id": diagnostic.get("step_id"),
        "candidate_id": diagnostic.get("candidate_id"),
        "candidate_motion_variant_id": diagnostic.get(
            "candidate_motion_variant_id"
        ),
        "preflight_id": diagnostic.get("preflight_id"),
        "preflight_path": diagnostic.get("preflight_path"),
        "preflight_sha256": diagnostic.get("preflight_sha256"),
        "test_id": diagnostic.get("test_id"),
        "diagnostic_state": diagnostic.get("diagnostic_state"),
        "next_action_mode": diagnostic.get("next_action_mode"),
        "mechanical_effect": diagnostic.get("mechanical_effect"),
        "attempt_id": diagnostic.get("attempt_id"),
        "attempt_path": diagnostic.get("attempt_path"),
        "attempt_sha256": diagnostic.get("attempt_sha256"),
        "execution_result": diagnostic.get("execution_result"),
        "ambiguity_buckets": list(
            diagnostic.get("ambiguity_buckets") or []
        ),
        "resume_condition": diagnostic.get("resume_condition"),
        "document_title_exact": diagnostic.get("document_title_exact"),
        "document_path_exact": diagnostic.get("document_path_exact"),
        "configuration_reference": diagnostic.get(
            "configuration_reference"
        ),
        "state_mutation_authority": "NONE",
        "cad_write_authority": "NONE",
        "mechanical_acceptance_authority": "NONE",
    }


def render_diagnostic_state(
    diagnostic: Mapping[str, Any] | None,
) -> str:
    if diagnostic is None:
        return (
            "CURRENT DIAGNOSTIC STATE:\n"
            "diagnostic_state: NONE_BOUND\n"
            "next_action_mode: FRONTIER_DERIVED\n"
        )

    lines = [
        "CURRENT DIAGNOSTIC STATE:",
        f"plan_id: {diagnostic.get('plan_id')}",
        f"plan_status: {diagnostic.get('plan_status')}",
        f"step_id: {diagnostic.get('step_id')}",
        f"test_id: {diagnostic.get('test_id')}",
        f"diagnostic_state: {diagnostic.get('diagnostic_state')}",
        f"next_action_mode: {diagnostic.get('next_action_mode')}",
        f"mechanical_effect: {diagnostic.get('mechanical_effect')}",
        f"attempt_id: {diagnostic.get('attempt_id')}",
        "ambiguity_buckets: "
        + ",".join(diagnostic.get("ambiguity_buckets") or []),
        f"resume_condition: {diagnostic.get('resume_condition')}",
        "",
        "DIAGNOSTIC CONTRACT:",
        "- This binding is read-only project state.",
        "- A blocked evidence-acquisition attempt is not negative mechanical evidence.",
        "- No hypothesis evidence/investigation state is changed automatically.",
        "- A successful fresh CAD rebind is a prerequisite when the diagnostic state requires it.",
        "- Geometry, mechanical acceptance, and CAD-write authority remain NONE.",
    ]
    return "\n".join(lines)
