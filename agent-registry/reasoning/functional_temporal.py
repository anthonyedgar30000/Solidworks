#!/usr/bin/env python3
"""Deterministic functional-decomposition and temporal-state architecture.

This module is deliberately a *reasoning contract*, not a machine controller.
It makes machine-level work divisible into bounded subsystems and explicit
interfaces, while preserving the distinction between a point observation and a
claim that must remain true for an operating interval or a reachable motion
set.

Safety boundary:

* It never calls SOLIDWORKS or a queue worker.
* It accepts only existing read-only CADRequest command shapes when a proposed
  next test includes a CAD request.
* It never changes an EvidenceRecord's epistemic state.
* It never grants mechanical acceptance.  A locally verified subsystem remains
  local evidence until a separately governed whole-machine acceptance process
  consumes it.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


class FunctionalTemporalError(RuntimeError):
    """Raised when a functional-temporal architecture is structurally unsafe."""


READ_ONLY_CAD_COMMANDS = {
    "sw.status",
    "sw.query_components",
    "sw.closest_distance_pair",
}
# A native-read candidate is deliberately not a CADRequest. CADRequest is the
# deployed Remote Queue partition; a local capability cannot acquire queue
# authority merely because it has a read-only implementation.
NATIVE_READ_CANDIDATE_COMMANDS = {"sw.query_mates"}
NATIVE_READ_EXECUTION_STATES = {
    "CANDIDATE_UNVERIFIED",
    "LOCAL_NO_MUTATION_VERIFIED",
    "EXHAUSTED_INSUFFICIENT",
}

EVENT_TYPES = {
    "OBSERVED_EVENT",
    "COMMAND_EVENT",
    "PHYSICAL_EVENT",
    "FAULT_EVENT",
}
STATE_TYPES = {"PERSISTENT_STATE", "MODE"}
OPERATING_PHASES = {
    "FREE_APPROACH",
    "CAPTURE_BEGINNING",
    "CAPTURED",
    "LABEL_TRANSFER_INTERVAL",
    "WRAP_ROTATION_INTERVAL",
    "RELEASE",
    "FREE_EXIT",
    "FAULT_HOLD",
    "OTHER",
}
VERIFICATION_STATES = {"VERIFIED", "UNRESOLVED", "VIOLATED"}
EVIDENCE_STATES_USABLE_FOR_PROOF = {"VERIFIED", "MEASURED_CALCULATED"}
EVIDENCE_STATES = {
    "VERIFIED",
    "MEASURED_CALCULATED",
    "INFERRED",
    "HYPOTHETICAL",
    "UNRESOLVED",
    "AI_GENERATED",
}
TEMPORAL_COVERAGE = {
    "POINT_ONLY",
    "THROUGHOUT_SCOPE",
    "REACHABLE_STATE_SET",
}
FRESHNESS_STATES = {"CURRENT", "STALE", "UNKNOWN"}
ALLEN_RELATIONS = {
    "BEFORE",
    "MEETS",
    "OVERLAPS",
    "FINISHED_BY",
    "CONTAINS",
    "STARTS",
    "EQUALS",
    "STARTED_BY",
    "DURING",
    "FINISHES",
    "OVERLAPPED_BY",
    "MET_BY",
    "AFTER",
}
AMBIGUITY_BUCKETS = {
    "IDENTITY_AMBIGUOUS",
    "GEOMETRY_UNRESOLVED",
    "KINEMATIC_STATE_UNRESOLVED",
    "MEASUREMENT_REQUIRED",
    "CAD_READ_REQUIRED",
    "OEM_SOURCE_REQUIRED",
    "SOURCE_CONFLICT",
    "MULTIPLE_PLAUSIBLE_HYPOTHESES",
    "INSUFFICIENT_EVIDENCE",
    "STALE_STATE",
    "POLICY_BLOCKED",
    "MECHANICAL_ACCEPTANCE_BLOCKED",
}
HYPOTHESIS_PRIORS = {"COMMON", "UNCOMMON", "RARE"}
HYPOTHESIS_EVIDENCE_STATES = {
    "UNTESTED",
    "SUPPORTED",
    "WEAKENED",
    "DISPROVEN",
    "UNRESOLVED",
}
HYPOTHESIS_INVESTIGATION_STATES = {
    "DORMANT",
    "ELIGIBLE",
    "ACTIVE",
    "EXHAUSTED",
}


def _as_object(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise FunctionalTemporalError(f"{label} must be an object")
    return value


def _as_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise FunctionalTemporalError(f"{label} must be an array")
    return value


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FunctionalTemporalError(f"{label} must be a non-empty string")
    return value


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FunctionalTemporalError(f"{label} must be numeric")
    number = float(value)
    if minimum is not None and number < minimum:
        raise FunctionalTemporalError(f"{label} must be at least {minimum}")
    return number


def _id_index(items: Sequence[Any], label: str, *, id_field: str = "id") -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for position, item in enumerate(items):
        item_object = _as_object(item, f"{label}[{position}]")
        item_id = _nonempty_string(item_object.get(id_field), f"{label}[{position}].{id_field}")
        if item_id in index:
            raise FunctionalTemporalError(f"Duplicate {label} identifier: {item_id}")
        index[item_id] = item_object
    return index


def _ensure_ids_exist(
    ids: Iterable[Any],
    index: Mapping[str, Any],
    label: str,
) -> None:
    for value in ids:
        item_id = _nonempty_string(value, label)
        if item_id not in index:
            raise FunctionalTemporalError(f"{label} references unknown id: {item_id}")


def _scope(scope_value: Any, *, state_index: Mapping[str, Any], transition_index: Mapping[str, Any], label: str) -> Dict[str, Any]:
    scope = _as_object(scope_value, label)
    coverage = scope.get("required_coverage")
    if coverage not in TEMPORAL_COVERAGE:
        raise FunctionalTemporalError(
            f"{label}.required_coverage must be one of {sorted(TEMPORAL_COVERAGE)}"
        )
    state_ids = _as_list(scope.get("state_ids"), f"{label}.state_ids")
    transition_ids = _as_list(scope.get("transition_ids"), f"{label}.transition_ids")
    if not state_ids and not transition_ids:
        raise FunctionalTemporalError(
            f"{label} must name at least one state or transition interval"
        )
    _ensure_ids_exist(state_ids, state_index, f"{label}.state_ids")
    _ensure_ids_exist(transition_ids, transition_index, f"{label}.transition_ids")
    return scope


def _validate_evidence_record(
    record: Mapping[str, Any],
    *,
    state_index: Mapping[str, Any],
    transition_index: Mapping[str, Any],
    label: str,
) -> None:
    _nonempty_string(record.get("evidence_id"), f"{label}.evidence_id")
    _nonempty_string(record.get("evidence_type"), f"{label}.evidence_type")
    if record.get("evidence_state") not in EVIDENCE_STATES:
        raise FunctionalTemporalError(f"{label}.evidence_state is not recognized")
    authority = _nonempty_string(record.get("source_authority"), f"{label}.source_authority")
    if record.get("mechanical_acceptance_granted") is not False:
        raise FunctionalTemporalError(
            f"{label}.mechanical_acceptance_granted must remain false"
        )

    if authority == "GENERATIVE_AI" and record.get("evidence_state") != "AI_GENERATED":
        raise FunctionalTemporalError(
            f"{label} cannot present generative AI as non-AI engineering evidence"
        )

    temporal_scope = _as_object(record.get("temporal_scope"), f"{label}.temporal_scope")
    coverage = temporal_scope.get("coverage")
    if coverage not in TEMPORAL_COVERAGE:
        raise FunctionalTemporalError(f"{label}.temporal_scope.coverage is not recognized")
    freshness = temporal_scope.get("validity_state")
    if freshness not in FRESHNESS_STATES:
        raise FunctionalTemporalError(f"{label}.temporal_scope.validity_state is not recognized")
    _ensure_ids_exist(
        _as_list(temporal_scope.get("state_ids"), f"{label}.temporal_scope.state_ids"),
        state_index,
        f"{label}.temporal_scope.state_ids",
    )
    _ensure_ids_exist(
        _as_list(temporal_scope.get("transition_ids"), f"{label}.temporal_scope.transition_ids"),
        transition_index,
        f"{label}.temporal_scope.transition_ids",
    )


def validate_read_only_cad_request(request: Mapping[str, Any]) -> None:
    """Validate the CADRequest subset permitted in this candidate model.

    The validation deliberately mirrors the existing v1 read-only partition
    instead of broadening it for temporal modeling.
    """

    if request.get("schema_version") != 1:
        raise FunctionalTemporalError("CADRequest.schema_version must equal 1")
    _nonempty_string(request.get("job_id"), "CADRequest.job_id")
    command = request.get("command_id")
    if command not in READ_ONLY_CAD_COMMANDS:
        raise FunctionalTemporalError(
            "Functional-temporal next tests may only contain existing read-only CAD commands"
        )
    if request.get("write_authority") != "NONE":
        raise FunctionalTemporalError("CADRequest.write_authority must remain NONE")
    payload = _as_object(request.get("payload"), "CADRequest.payload")

    if command == "sw.status" and payload:
        raise FunctionalTemporalError("sw.status requires an empty payload")
    if command == "sw.query_components":
        if set(payload) != {"top_level_only"} or not isinstance(payload["top_level_only"], bool):
            raise FunctionalTemporalError(
                "sw.query_components requires only boolean payload.top_level_only"
            )
    if command == "sw.closest_distance_pair":
        required = {"a_name_exact", "b_name_exact"}
        if set(payload) != required:
            raise FunctionalTemporalError(
                "sw.closest_distance_pair requires only exact pair identities"
            )
        for field in required:
            _nonempty_string(payload.get(field), f"CADRequest.payload.{field}")


def validate_native_read_candidate(candidate: Mapping[str, Any]) -> None:
    """Validate a local-only native observation candidate.

    This is intentionally separate from :func:`validate_read_only_cad_request`.
    A candidate says what a separately reviewed Windows/SOLIDWORKS host may
    test; it is neither a Remote Queue job nor a claim that the command is
    remotely authorized or sufficient for a mechanical conclusion.
    """

    if candidate.get("schema_version") != 1:
        raise FunctionalTemporalError("native_read_candidate.schema_version must equal 1")
    command = candidate.get("command_id")
    if command not in NATIVE_READ_CANDIDATE_COMMANDS:
        raise FunctionalTemporalError(
            "native_read_candidate.command_id is not an independently reviewed local candidate"
        )
    if candidate.get("write_authority") != "NONE":
        raise FunctionalTemporalError("native_read_candidate.write_authority must remain NONE")
    if candidate.get("remote_queue_authorized") is not False:
        raise FunctionalTemporalError(
            "native_read_candidate.remote_queue_authorized must remain false"
        )
    if candidate.get("requires_independent_no_mutation_verification") is not True:
        raise FunctionalTemporalError(
            "native_read_candidate requires independent no-mutation verification"
        )
    if candidate.get("execution_state") not in NATIVE_READ_EXECUTION_STATES:
        raise FunctionalTemporalError("native_read_candidate.execution_state is not recognized")
    _nonempty_string(
        candidate.get("verification_contract_id"),
        "native_read_candidate.verification_contract_id",
    )
    payload = _as_object(candidate.get("payload"), "native_read_candidate.payload")
    if command == "sw.query_mates":
        if set(payload) != {"component_name_exact"}:
            raise FunctionalTemporalError(
                "sw.query_mates candidate requires only payload.component_name_exact"
            )
        _nonempty_string(
            payload.get("component_name_exact"),
            "native_read_candidate.payload.component_name_exact",
        )


def _validate_parent_tree(subsystems: Mapping[str, Mapping[str, Any]]) -> None:
    for subsystem_id, subsystem in subsystems.items():
        parent_id = subsystem.get("parent_id")
        if parent_id is not None and parent_id not in subsystems:
            raise FunctionalTemporalError(
                f"subsystem {subsystem_id} has unknown parent_id {parent_id!r}"
            )

    for subsystem_id in subsystems:
        seen = set()
        cursor = subsystem_id
        while cursor is not None:
            if cursor in seen:
                raise FunctionalTemporalError("Subsystem parent hierarchy contains a cycle")
            seen.add(cursor)
            cursor = subsystems[cursor].get("parent_id")


def validate_architecture(architecture: Mapping[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Validate cross-references and governance invariants of an architecture.

    The JSON schema covers the structural shape.  This deterministic validator
    covers relationships that a JSON schema cannot safely express, such as
    unique cross-domain identities and read-only request links.
    """

    model = _as_object(architecture, "architecture")
    for field in (
        "schema_version",
        "architecture_id",
        "machine_goal",
        "subsystems",
        "obligations",
        "interfaces",
        "events",
        "states",
        "transition_guards",
        "transitions",
        "invariants",
        "duration_constraints",
        "temporal_relations",
        "hypotheses",
        "evidence_catalog",
        "next_tests",
    ):
        if field not in model:
            raise FunctionalTemporalError(f"architecture missing required field: {field}")
    if model.get("schema_version") != 1:
        raise FunctionalTemporalError("architecture.schema_version must equal 1")
    _nonempty_string(model.get("architecture_id"), "architecture.architecture_id")

    goal = _as_object(model.get("machine_goal"), "architecture.machine_goal")
    _nonempty_string(goal.get("id"), "architecture.machine_goal.id")
    _nonempty_string(goal.get("description"), "architecture.machine_goal.description")
    if goal.get("mechanical_acceptance_granted") is not False:
        raise FunctionalTemporalError(
            "functional-temporal architecture must not grant mechanical acceptance"
        )

    subsystems = _id_index(_as_list(model["subsystems"], "architecture.subsystems"), "subsystem")
    obligations = _id_index(_as_list(model["obligations"], "architecture.obligations"), "obligation")
    interfaces = _id_index(_as_list(model["interfaces"], "architecture.interfaces"), "interface")
    events = _id_index(_as_list(model["events"], "architecture.events"), "event")
    states = _id_index(_as_list(model["states"], "architecture.states"), "state")
    guards = _id_index(_as_list(model["transition_guards"], "architecture.transition_guards"), "transition_guard")
    transitions = _id_index(_as_list(model["transitions"], "architecture.transitions"), "transition")
    invariants = _id_index(_as_list(model["invariants"], "architecture.invariants"), "invariant")
    durations = _id_index(_as_list(model["duration_constraints"], "architecture.duration_constraints"), "duration_constraint")
    hypotheses = _id_index(_as_list(model["hypotheses"], "architecture.hypotheses"), "hypothesis")
    evidence = _id_index(
        _as_list(model["evidence_catalog"], "architecture.evidence_catalog"),
        "evidence_record",
        id_field="evidence_id",
    )
    next_tests = _id_index(_as_list(model["next_tests"], "architecture.next_tests"), "next_test")

    all_requirement_ids = set(obligations) | set(guards) | set(invariants)
    if len(all_requirement_ids) != len(obligations) + len(guards) + len(invariants):
        raise FunctionalTemporalError(
            "obligation, guard, and invariant identifiers must be globally unique"
        )

    _validate_parent_tree(subsystems)
    for subsystem_id, subsystem in subsystems.items():
        _nonempty_string(subsystem.get("goal"), f"subsystem {subsystem_id}.goal")
        _ensure_ids_exist(
            _as_list(subsystem.get("local_obligation_ids"), f"subsystem {subsystem_id}.local_obligation_ids"),
            obligations,
            f"subsystem {subsystem_id}.local_obligation_ids",
        )
        _ensure_ids_exist(
            _as_list(subsystem.get("provided_interface_ids"), f"subsystem {subsystem_id}.provided_interface_ids"),
            interfaces,
            f"subsystem {subsystem_id}.provided_interface_ids",
        )
        _ensure_ids_exist(
            _as_list(subsystem.get("consumed_interface_ids"), f"subsystem {subsystem_id}.consumed_interface_ids"),
            interfaces,
            f"subsystem {subsystem_id}.consumed_interface_ids",
        )

    for state_id, state in states.items():
        if state.get("state_type") not in STATE_TYPES:
            raise FunctionalTemporalError(f"state {state_id} has invalid state_type")
        operating_phase = state.get("operating_phase")
        if operating_phase is not None and operating_phase not in OPERATING_PHASES:
            raise FunctionalTemporalError(f"state {state_id} has invalid operating_phase")
        owner = state.get("owner_subsystem_id")
        if owner not in subsystems:
            raise FunctionalTemporalError(f"state {state_id} has unknown owner_subsystem_id")
        _nonempty_string(state.get("description"), f"state {state_id}.description")

    for event_id, event in events.items():
        if event.get("event_type") not in EVENT_TYPES:
            raise FunctionalTemporalError(f"event {event_id} has invalid event_type")
        if event.get("owner_subsystem_id") not in subsystems:
            raise FunctionalTemporalError(f"event {event_id} has unknown owner_subsystem_id")
        if event.get("event_state") not in VERIFICATION_STATES:
            raise FunctionalTemporalError(f"event {event_id} has invalid event_state")
        _ensure_ids_exist(
            _as_list(event.get("evidence_refs"), f"event {event_id}.evidence_refs"),
            evidence,
            f"event {event_id}.evidence_refs",
        )

    def validate_requirement(requirement_id: str, requirement: Mapping[str, Any], kind: str) -> None:
        if requirement.get("owner_subsystem_id") not in subsystems:
            raise FunctionalTemporalError(
                f"{kind} {requirement_id} has unknown owner_subsystem_id"
            )
        _nonempty_string(requirement.get("description"), f"{kind} {requirement_id}.description")
        if requirement.get("verification_state") not in VERIFICATION_STATES:
            raise FunctionalTemporalError(
                f"{kind} {requirement_id} has invalid verification_state"
            )
        if requirement.get("ambiguity_bucket") not in AMBIGUITY_BUCKETS:
            raise FunctionalTemporalError(
                f"{kind} {requirement_id} has invalid ambiguity_bucket"
            )
        _number(requirement.get("criticality"), f"{kind} {requirement_id}.criticality", minimum=0.0)
        _number(requirement.get("resolution_cost"), f"{kind} {requirement_id}.resolution_cost", minimum=0.000001)
        expected_authority = _as_list(
            requirement.get("expected_authority"), f"{kind} {requirement_id}.expected_authority"
        )
        if not expected_authority:
            raise FunctionalTemporalError(f"{kind} {requirement_id} needs expected_authority")
        for authority in expected_authority:
            _nonempty_string(authority, f"{kind} {requirement_id}.expected_authority")
        _ensure_ids_exist(
            _as_list(requirement.get("evidence_refs"), f"{kind} {requirement_id}.evidence_refs"),
            evidence,
            f"{kind} {requirement_id}.evidence_refs",
        )
        _ensure_ids_exist(
            _as_list(
                requirement.get("depends_on_requirement_ids"),
                f"{kind} {requirement_id}.depends_on_requirement_ids",
            ),
            {rid: None for rid in all_requirement_ids},
            f"{kind} {requirement_id}.depends_on_requirement_ids",
        )
        _scope(
            requirement.get("scope"),
            state_index=states,
            transition_index=transitions,
            label=f"{kind} {requirement_id}.scope",
        )

    for requirement_id, requirement in obligations.items():
        validate_requirement(requirement_id, requirement, "obligation")
    for requirement_id, requirement in guards.items():
        validate_requirement(requirement_id, requirement, "transition_guard")
    for requirement_id, requirement in invariants.items():
        validate_requirement(requirement_id, requirement, "invariant")

    all_requirements: Dict[str, Mapping[str, Any]] = {
        **obligations,
        **guards,
        **invariants,
    }
    visiting_requirements = set()
    visited_requirements = set()

    def visit_requirement(requirement_id: str) -> None:
        if requirement_id in visited_requirements:
            return
        if requirement_id in visiting_requirements:
            raise FunctionalTemporalError("Requirement dependency graph contains a cycle")
        visiting_requirements.add(requirement_id)
        for dependency in all_requirements[requirement_id]["depends_on_requirement_ids"]:
            visit_requirement(dependency)
        visiting_requirements.remove(requirement_id)
        visited_requirements.add(requirement_id)

    for requirement_id in all_requirements:
        visit_requirement(requirement_id)

    for interface_id, interface in interfaces.items():
        provider = interface.get("provider_subsystem_id")
        consumer = interface.get("consumer_subsystem_id")
        if provider not in subsystems or consumer not in subsystems:
            raise FunctionalTemporalError(f"interface {interface_id} references unknown subsystem")
        if provider == consumer:
            raise FunctionalTemporalError(
                f"interface {interface_id} must cross a subsystem boundary"
            )
        _nonempty_string(interface.get("contract_type"), f"interface {interface_id}.contract_type")
        _nonempty_string(interface.get("description"), f"interface {interface_id}.description")
        if interface.get("ambiguity_bucket") not in AMBIGUITY_BUCKETS:
            raise FunctionalTemporalError(f"interface {interface_id} has invalid ambiguity_bucket")
        _ensure_ids_exist(
            _as_list(interface.get("required_requirement_ids"), f"interface {interface_id}.required_requirement_ids"),
            {rid: None for rid in all_requirement_ids},
            f"interface {interface_id}.required_requirement_ids",
        )
        _scope(
            interface.get("scope"),
            state_index=states,
            transition_index=transitions,
            label=f"interface {interface_id}.scope",
        )

    for transition_id, transition in transitions.items():
        if transition.get("from_state_id") not in states or transition.get("to_state_id") not in states:
            raise FunctionalTemporalError(f"transition {transition_id} references unknown state")
        if transition.get("trigger_event_id") not in events:
            raise FunctionalTemporalError(f"transition {transition_id} references unknown trigger_event_id")
        _ensure_ids_exist(
            _as_list(transition.get("guard_ids"), f"transition {transition_id}.guard_ids"),
            guards,
            f"transition {transition_id}.guard_ids",
        )
        _ensure_ids_exist(
            _as_list(
                transition.get("required_interface_ids"),
                f"transition {transition_id}.required_interface_ids",
            ),
            interfaces,
            f"transition {transition_id}.required_interface_ids",
        )

    for duration_id, duration in durations.items():
        if duration.get("transition_id") not in transitions:
            raise FunctionalTemporalError(
                f"duration_constraint {duration_id} references unknown transition"
            )
        minimum = _number(duration.get("minimum_duration"), f"duration_constraint {duration_id}.minimum_duration", minimum=0.0)
        maximum = _number(duration.get("maximum_duration"), f"duration_constraint {duration_id}.maximum_duration", minimum=0.0)
        if minimum > maximum:
            raise FunctionalTemporalError(
                f"duration_constraint {duration_id} has minimum_duration > maximum_duration"
            )
        _nonempty_string(duration.get("units"), f"duration_constraint {duration_id}.units")
        _nonempty_string(duration.get("constraint_type"), f"duration_constraint {duration_id}.constraint_type")

    relation_indexes: Dict[str, Mapping[str, Any]] = {
        "state": states,
        "event": events,
        "transition": transitions,
        "obligation": obligations,
        "guard": guards,
        "invariant": invariants,
        "interface": interfaces,
    }
    for position, relation_value in enumerate(_as_list(model["temporal_relations"], "architecture.temporal_relations")):
        relation = _as_object(relation_value, f"temporal_relation[{position}]")
        from_kind = relation.get("from_kind")
        to_kind = relation.get("to_kind")
        if from_kind not in relation_indexes or to_kind not in relation_indexes:
            raise FunctionalTemporalError(f"temporal_relation[{position}] has invalid endpoint kind")
        _ensure_ids_exist([relation.get("from_id")], relation_indexes[from_kind], f"temporal_relation[{position}].from_id")
        _ensure_ids_exist([relation.get("to_id")], relation_indexes[to_kind], f"temporal_relation[{position}].to_id")
        if relation.get("relation") not in ALLEN_RELATIONS:
            raise FunctionalTemporalError(f"temporal_relation[{position}] has invalid Allen relation")

    for evidence_id, record in evidence.items():
        _validate_evidence_record(
            record,
            state_index=states,
            transition_index=transitions,
            label=f"evidence_record {evidence_id}",
        )

    for hypothesis_id, hypothesis in hypotheses.items():
        _nonempty_string(hypothesis.get("description"), f"hypothesis {hypothesis_id}.description")
        if hypothesis.get("prior") not in HYPOTHESIS_PRIORS:
            raise FunctionalTemporalError(f"hypothesis {hypothesis_id} has invalid prior")
        if hypothesis.get("evidence_state") not in HYPOTHESIS_EVIDENCE_STATES:
            raise FunctionalTemporalError(f"hypothesis {hypothesis_id} has invalid evidence_state")
        if hypothesis.get("investigation_state") not in HYPOTHESIS_INVESTIGATION_STATES:
            raise FunctionalTemporalError(
                f"hypothesis {hypothesis_id} has invalid investigation_state"
            )
        _ensure_ids_exist(
            _as_list(hypothesis.get("related_requirement_ids"), f"hypothesis {hypothesis_id}.related_requirement_ids"),
            {rid: None for rid in all_requirement_ids},
            f"hypothesis {hypothesis_id}.related_requirement_ids",
        )
        _ensure_ids_exist(
            _as_list(hypothesis.get("affected_state_ids"), f"hypothesis {hypothesis_id}.affected_state_ids"),
            states,
            f"hypothesis {hypothesis_id}.affected_state_ids",
        )
        required_evidence = _as_list(
            hypothesis.get("required_evidence"),
            f"hypothesis {hypothesis_id}.required_evidence",
        )
        if not required_evidence:
            raise FunctionalTemporalError(
                f"hypothesis {hypothesis_id} needs at least one exact required_evidence item"
            )
        for position, item in enumerate(required_evidence):
            _nonempty_string(
                item,
                f"hypothesis {hypothesis_id}.required_evidence[{position}]",
            )

    for test_id, test in next_tests.items():
        _nonempty_string(test.get("question"), f"next_test {test_id}.question")
        resolved_ids = _as_list(test.get("resolves_requirement_ids"), f"next_test {test_id}.resolves_requirement_ids")
        if not resolved_ids:
            raise FunctionalTemporalError(f"next_test {test_id} must resolve at least one requirement")
        _ensure_ids_exist(
            resolved_ids,
            {rid: None for rid in all_requirement_ids},
            f"next_test {test_id}.resolves_requirement_ids",
        )
        _ensure_ids_exist(
            _as_list(test.get("hypothesis_ids"), f"next_test {test_id}.hypothesis_ids"),
            hypotheses,
            f"next_test {test_id}.hypothesis_ids",
        )
        for field in ("discrimination_power", "evidence_confidence", "unresolved_relevance"):
            value = _number(test.get(field), f"next_test {test_id}.{field}", minimum=0.0)
            if value > 1.0:
                raise FunctionalTemporalError(f"next_test {test_id}.{field} must not exceed 1.0")
        _number(test.get("cost"), f"next_test {test_id}.cost", minimum=0.000001)
        request = test.get("cad_request")
        if request is not None:
            validate_read_only_cad_request(_as_object(request, f"next_test {test_id}.cad_request"))
        native_candidates = test.get("native_read_candidates")
        if native_candidates is not None:
            for position, candidate in enumerate(
                _as_list(native_candidates, f"next_test {test_id}.native_read_candidates")
            ):
                validate_native_read_candidate(
                    _as_object(
                        candidate,
                        f"next_test {test_id}.native_read_candidates[{position}]",
                    )
                )

    return {
        "subsystems": subsystems,
        "obligations": obligations,
        "interfaces": interfaces,
        "events": events,
        "states": states,
        "guards": guards,
        "transitions": transitions,
        "invariants": invariants,
        "durations": durations,
        "hypotheses": hypotheses,
        "evidence": evidence,
        "next_tests": next_tests,
    }


def _coverage_satisfies(required_scope: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    temporal_scope = record["temporal_scope"]
    required_coverage = required_scope["required_coverage"]
    actual_coverage = temporal_scope["coverage"]
    if required_coverage == "POINT_ONLY":
        return actual_coverage in TEMPORAL_COVERAGE
    if required_coverage == "THROUGHOUT_SCOPE":
        if actual_coverage not in {"THROUGHOUT_SCOPE", "REACHABLE_STATE_SET"}:
            return False
    if required_coverage == "REACHABLE_STATE_SET" and actual_coverage != "REACHABLE_STATE_SET":
        return False

    required_states = set(required_scope["state_ids"])
    required_transitions = set(required_scope["transition_ids"])
    actual_states = set(temporal_scope["state_ids"])
    actual_transitions = set(temporal_scope["transition_ids"])
    return required_states.issubset(actual_states) and required_transitions.issubset(actual_transitions)


def _unresolved_bucket(requirement: Mapping[str, Any], evidence_records: Sequence[Mapping[str, Any]]) -> str:
    if any(record["temporal_scope"]["validity_state"] == "STALE" for record in evidence_records):
        return "STALE_STATE"
    return requirement["ambiguity_bucket"]


def evaluate_requirement(requirement: Mapping[str, Any], evidence_index: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Evaluate a bounded requirement without promoting its underlying facts."""

    evidence_records = [evidence_index[evidence_id] for evidence_id in requirement["evidence_refs"]]
    declared = requirement["verification_state"]
    base = {
        "requirement_id": requirement["id"],
        "description": requirement["description"],
        "scope": requirement["scope"],
        "evidence_refs": list(requirement["evidence_refs"]),
        "expected_authority": list(requirement["expected_authority"]),
        "ambiguity_bucket": _unresolved_bucket(requirement, evidence_records),
        "reasons": [],
    }

    if declared == "VIOLATED":
        return {**base, "state": "VIOLATED", "reasons": ["Declared violation is preserved."]}
    if declared != "VERIFIED":
        return {
            **base,
            "state": "UNRESOLVED",
            "reasons": [
                "Requirement is explicitly unresolved; this evaluator may not promote it from context or hypothesis."
            ],
        }
    if not evidence_records:
        return {
            **base,
            "state": "UNRESOLVED",
            "ambiguity_bucket": "INSUFFICIENT_EVIDENCE",
            "reasons": ["A declared verified requirement has no bound EvidenceRecord."],
        }

    failures: List[str] = []
    for record in evidence_records:
        record_id = record["evidence_id"]
        if record["evidence_type"] == "ai_visualization_record" or record["source_authority"] == "GENERATIVE_AI":
            failures.append(f"{record_id} is AI-generated and cannot satisfy an engineering requirement.")
            continue
        if record["evidence_state"] not in EVIDENCE_STATES_USABLE_FOR_PROOF:
            failures.append(f"{record_id} is not in a proof-usable evidence state.")
            continue
        if record["source_authority"] not in requirement["expected_authority"]:
            failures.append(f"{record_id} has an authority not accepted by this requirement.")
            continue
        if record["temporal_scope"]["validity_state"] != "CURRENT":
            failures.append(f"{record_id} is not a current binding for this operating claim.")
            continue
        if not _coverage_satisfies(requirement["scope"], record):
            failures.append(
                f"{record_id} has {record['temporal_scope']['coverage']} coverage, which does not prove "
                f"{requirement['scope']['required_coverage']}."
            )

    if failures:
        return {
            **base,
            "state": "UNRESOLVED",
            "ambiguity_bucket": _unresolved_bucket(requirement, evidence_records),
            "reasons": failures,
        }
    return {**base, "state": "VERIFIED", "ambiguity_bucket": None, "reasons": []}


def _aggregate_states(states: Iterable[str], *, verified_label: str) -> str:
    state_list = list(states)
    if any(state == "VIOLATED" for state in state_list):
        return "FAILED"
    if state_list and all(state == "VERIFIED" for state in state_list):
        return verified_label
    return "EXPOSED"


def _requirement_centrality(
    indexes: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> Dict[str, float]:
    requirements: Dict[str, Mapping[str, Any]] = {
        **indexes["obligations"],
        **indexes["guards"],
        **indexes["invariants"],
    }
    dependents: Dict[str, float] = defaultdict(float)
    for requirement in requirements.values():
        for dependency in requirement["depends_on_requirement_ids"]:
            dependents[dependency] += float(requirement["criticality"])
    for interface in indexes["interfaces"].values():
        for requirement_id in interface["required_requirement_ids"]:
            dependents[requirement_id] += 1.0
    for transition in indexes["transitions"].values():
        for guard_id in transition["guard_ids"]:
            dependents[guard_id] += 1.0

    return {
        requirement_id: max(1.0, float(requirement["criticality"]) + dependents[requirement_id])
        for requirement_id, requirement in requirements.items()
    }


def rank_next_tests(
    architecture: Mapping[str, Any],
    *,
    evaluation: Mapping[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Rank declared tests using the project's explicit value formula.

    value = dependency centrality × discrimination power × evidence confidence
            × unresolved relevance ÷ cost

    The model supplies the candidates; this function never invents a test or
    changes a hypothesis state.
    """

    indexes = validate_architecture(architecture)
    report = evaluation or evaluate_architecture(architecture)
    requirement_states = report["requirement_states"]
    centrality = _requirement_centrality(indexes)
    hypotheses = indexes["hypotheses"]
    ranked: List[Dict[str, Any]] = []

    for test_id, test in indexes["next_tests"].items():
        unresolved_ids = [
            requirement_id
            for requirement_id in test["resolves_requirement_ids"]
            if requirement_states[requirement_id]["state"] != "VERIFIED"
        ]
        dependency_centrality = sum(centrality[requirement_id] for requirement_id in unresolved_ids)
        value = (
            dependency_centrality
            * float(test["discrimination_power"])
            * float(test["evidence_confidence"])
            * float(test["unresolved_relevance"])
            / float(test["cost"])
        )
        active_hypotheses = [
            hypothesis_id
            for hypothesis_id in test["hypothesis_ids"]
            if hypotheses[hypothesis_id]["investigation_state"] in {"ELIGIBLE", "ACTIVE"}
            and hypotheses[hypothesis_id]["evidence_state"] != "DISPROVEN"
        ]
        ranked.append(
            {
                "test_id": test_id,
                "question": test["question"],
                "resolves_requirement_ids": unresolved_ids,
                "active_hypothesis_ids": active_hypotheses,
                "dependency_centrality": round(dependency_centrality, 6),
                "discrimination_power": test["discrimination_power"],
                "evidence_confidence": test["evidence_confidence"],
                "unresolved_relevance": test["unresolved_relevance"],
                "cost": test["cost"],
                "value": round(value, 6),
                "cad_request": test.get("cad_request"),
                "native_read_candidates": test.get("native_read_candidates"),
                "does_not_promote_facts": True,
            }
        )
    return sorted(ranked, key=lambda candidate: (-candidate["value"], candidate["test_id"]))


def evaluate_architecture(architecture: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate local functional/temporal obligations without global acceptance."""

    indexes = validate_architecture(architecture)
    evidence = indexes["evidence"]
    requirements: Dict[str, Mapping[str, Any]] = {
        **indexes["obligations"],
        **indexes["guards"],
        **indexes["invariants"],
    }
    base_requirement_states = {
        requirement_id: evaluate_requirement(requirement, evidence)
        for requirement_id, requirement in requirements.items()
    }
    requirement_states: Dict[str, Dict[str, Any]] = {}
    visiting_requirements = set()

    def resolve_requirement(requirement_id: str) -> Dict[str, Any]:
        if requirement_id in requirement_states:
            return requirement_states[requirement_id]
        if requirement_id in visiting_requirements:
            raise FunctionalTemporalError("Requirement dependency graph contains a cycle")
        visiting_requirements.add(requirement_id)
        base = copy.deepcopy(base_requirement_states[requirement_id])
        if base["state"] == "VERIFIED":
            dependencies = [
                resolve_requirement(dependency)
                for dependency in requirements[requirement_id]["depends_on_requirement_ids"]
            ]
            violated = [item["requirement_id"] for item in dependencies if item["state"] == "VIOLATED"]
            unresolved = [item["requirement_id"] for item in dependencies if item["state"] != "VERIFIED"]
            if violated:
                base["state"] = "VIOLATED"
                base["ambiguity_bucket"] = None
                base["reasons"].append(
                    "Required dependency is violated: " + ", ".join(sorted(violated))
                )
            elif unresolved:
                base["state"] = "UNRESOLVED"
                base["ambiguity_bucket"] = requirements[requirement_id]["ambiguity_bucket"]
                base["reasons"].append(
                    "Required dependency remains unresolved: " + ", ".join(sorted(unresolved))
                )
        visiting_requirements.remove(requirement_id)
        requirement_states[requirement_id] = base
        return base

    for requirement_id in requirements:
        resolve_requirement(requirement_id)

    subsystem_results = []
    for subsystem_id, subsystem in indexes["subsystems"].items():
        local_ids = subsystem["local_obligation_ids"]
        subsystem_results.append(
            {
                "subsystem_id": subsystem_id,
                "goal": subsystem["goal"],
                "local_obligation_ids": local_ids,
                "local_state": _aggregate_states(
                    (requirement_states[requirement_id]["state"] for requirement_id in local_ids),
                    verified_label="LOCAL_VERIFIED",
                ),
                "mechanical_acceptance_granted": False,
            }
        )

    interface_results = []
    for interface_id, interface in indexes["interfaces"].items():
        interface_results.append(
            {
                "interface_id": interface_id,
                "provider_subsystem_id": interface["provider_subsystem_id"],
                "consumer_subsystem_id": interface["consumer_subsystem_id"],
                "contract_type": interface["contract_type"],
                "required_requirement_ids": interface["required_requirement_ids"],
                "state": _aggregate_states(
                    (
                        requirement_states[requirement_id]["state"]
                        for requirement_id in interface["required_requirement_ids"]
                    ),
                    verified_label="VERIFIED",
                ),
                "ambiguity_bucket": interface["ambiguity_bucket"],
            }
        )
    interface_state = {result["interface_id"]: result["state"] for result in interface_results}

    transition_results = []
    for transition_id, transition in indexes["transitions"].items():
        checks = [
            requirement_states[guard_id]["state"] for guard_id in transition["guard_ids"]
        ] + [
            interface_state[interface_id]
            for interface_id in transition["required_interface_ids"]
        ]
        transition_results.append(
            {
                "transition_id": transition_id,
                "from_state_id": transition["from_state_id"],
                "to_state_id": transition["to_state_id"],
                "trigger_event_id": transition["trigger_event_id"],
                "guard_ids": transition["guard_ids"],
                "required_interface_ids": transition["required_interface_ids"],
                "state": _aggregate_states(checks, verified_label="ENABLED"),
            }
        )

    temporal_coherence = _aggregate_states(
        [result["state"] for result in interface_results]
        + [
            "VERIFIED" if result["state"] == "ENABLED" else result["state"]
            for result in transition_results
        ]
        + [requirement_states[requirement_id]["state"] for requirement_id in indexes["invariants"]],
        verified_label="TEMPORALLY_COHERENT",
    )
    report = {
        "architecture_id": architecture["architecture_id"],
        "machine_goal": architecture["machine_goal"],
        "requirement_states": requirement_states,
        "subsystems": subsystem_results,
        "interfaces": interface_results,
        "transitions": transition_results,
        "temporal_coherence_state": temporal_coherence,
        "machine_acceptance_state": "MECHANICAL_ACCEPTANCE_BLOCKED",
        "mechanical_acceptance_granted": False,
        "acceptance_boundary": (
            "Subsystem and temporal results are evidence for a separately governed whole-machine "
            "acceptance process; they do not grant acceptance."
        ),
    }
    report["next_test_candidates"] = rank_next_tests(architecture, evaluation=report)
    return report


def _graph_state(result_state: str) -> str:
    if result_state in {"VERIFIED", "LOCAL_VERIFIED", "ENABLED", "TEMPORALLY_COHERENT"}:
        return "ASSERTED"
    if result_state in {"VIOLATED", "FAILED"}:
        return "VIOLATED"
    return "NULL"


def _evidence_graph_state(record: Mapping[str, Any]) -> str:
    if record["temporal_scope"]["validity_state"] != "CURRENT":
        return "NULL"
    if record["evidence_type"] == "ai_visualization_record":
        return "NULL"
    if record["evidence_state"] in EVIDENCE_STATES_USABLE_FOR_PROOF:
        return "KNOWN"
    return "NULL"


def build_epistemic_graph_fragment(architecture: Mapping[str, Any]) -> Dict[str, Any]:
    """Project the architecture into a dependency-graph fragment.

    The fragment is intentionally unlinked from a caller's project acceptance
    obligation.  A caller may inspect it or merge it into a graph, but this
    projection itself cannot make a machine mechanically accepted.
    """

    indexes = validate_architecture(architecture)
    evaluation = evaluate_architecture(architecture)
    prefix = f"FT::{architecture['architecture_id']}::"
    nodes: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []

    for evidence_id, record in indexes["evidence"].items():
        node_id = f"{prefix}EVIDENCE::{evidence_id}"
        nodes.append(
            {
                "id": node_id,
                "kind": "fact",
                "description": f"EvidenceRecord {evidence_id}",
                "value": record["evidence_state"],
                "state": _evidence_graph_state(record),
                "authority": record["source_authority"],
                "criticality": 1,
                "expected_authority": [record["source_authority"]],
                "metadata": {
                    "evidence_id": evidence_id,
                    "evidence_type": record["evidence_type"],
                    "evidence_state": record["evidence_state"],
                    "temporal_scope": record["temporal_scope"],
                    "ambiguity_bucket": (
                        "STALE_STATE"
                        if record["temporal_scope"]["validity_state"] == "STALE"
                        else None
                    ),
                    "mechanical_acceptance_granted": False,
                },
            }
        )

    requirements: Dict[str, Mapping[str, Any]] = {
        **indexes["obligations"],
        **indexes["guards"],
        **indexes["invariants"],
    }
    for requirement_id, requirement in requirements.items():
        result = evaluation["requirement_states"][requirement_id]
        if requirement_id in indexes["invariants"]:
            kind = "invariant"
        elif requirement_id in indexes["obligations"]:
            kind = "obligation"
        else:
            kind = "derived_claim"
        node_id = f"{prefix}REQUIREMENT::{requirement_id}"
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "description": requirement["description"],
                "value": True if result["state"] == "VERIFIED" else None,
                "state": _graph_state(result["state"]),
                "authority": "FUNCTIONAL_TEMPORAL_EVALUATION",
                "criticality": requirement["criticality"],
                "resolution_cost": requirement["resolution_cost"],
                "expected_authority": requirement["expected_authority"],
                "metadata": {
                    "functional_owner": requirement["owner_subsystem_id"],
                    "temporal_scope": requirement["scope"],
                    "ambiguity_bucket": result["ambiguity_bucket"],
                    "evaluation_reasons": result["reasons"],
                    "mechanical_acceptance_granted": False,
                },
            }
        )
        for evidence_id in requirement["evidence_refs"]:
            relations.append(
                {
                    "from": node_id,
                    "to": f"{prefix}EVIDENCE::{evidence_id}",
                    "type": "depends_on",
                    "strength": 1.0,
                }
            )
        for dependency in requirement["depends_on_requirement_ids"]:
            relations.append(
                {
                    "from": node_id,
                    "to": f"{prefix}REQUIREMENT::{dependency}",
                    "type": "depends_on",
                    "strength": 1.0,
                }
            )

    for result in evaluation["interfaces"]:
        interface_id = result["interface_id"]
        node_id = f"{prefix}INTERFACE::{interface_id}"
        interface = indexes["interfaces"][interface_id]
        nodes.append(
            {
                "id": node_id,
                "kind": "obligation",
                "description": interface["description"],
                "value": True if result["state"] == "VERIFIED" else None,
                "state": _graph_state(result["state"]),
                "authority": "FUNCTIONAL_INTERFACE_CONTRACT",
                "criticality": 5,
                "expected_authority": [],
                "metadata": {
                    "provider_subsystem_id": interface["provider_subsystem_id"],
                    "consumer_subsystem_id": interface["consumer_subsystem_id"],
                    "contract_type": interface["contract_type"],
                    "temporal_scope": interface["scope"],
                    "ambiguity_bucket": interface["ambiguity_bucket"],
                    "mechanical_acceptance_granted": False,
                },
            }
        )
        for requirement_id in interface["required_requirement_ids"]:
            relations.append(
                {
                    "from": node_id,
                    "to": f"{prefix}REQUIREMENT::{requirement_id}",
                    "type": "depends_on",
                    "strength": 1.0,
                }
            )

    for result in evaluation["transitions"]:
        transition_id = result["transition_id"]
        node_id = f"{prefix}TRANSITION::{transition_id}"
        nodes.append(
            {
                "id": node_id,
                "kind": "derived_claim",
                "description": f"Transition {transition_id} is only enabled after its event, guards, and interfaces are valid.",
                "value": True if result["state"] == "ENABLED" else None,
                "state": _graph_state(result["state"]),
                "authority": "FUNCTIONAL_TEMPORAL_EVALUATION",
                "criticality": 4,
                "expected_authority": [],
                "metadata": {
                    "from_state_id": result["from_state_id"],
                    "to_state_id": result["to_state_id"],
                    "trigger_event_id": result["trigger_event_id"],
                    "mechanical_acceptance_granted": False,
                },
            }
        )
        for guard_id in result["guard_ids"]:
            relations.append(
                {
                    "from": node_id,
                    "to": f"{prefix}REQUIREMENT::{guard_id}",
                    "type": "depends_on",
                    "strength": 1.0,
                }
            )
        for interface_id in result["required_interface_ids"]:
            relations.append(
                {
                    "from": node_id,
                    "to": f"{prefix}INTERFACE::{interface_id}",
                    "type": "depends_on",
                    "strength": 1.0,
                }
            )

    for hypothesis_id, hypothesis in indexes["hypotheses"].items():
        hypothesis_state = "NULL"
        if hypothesis["evidence_state"] == "DISPROVEN":
            hypothesis_state = "VIOLATED"
        nodes.append(
            {
                "id": f"{prefix}HYPOTHESIS::{hypothesis_id}",
                "kind": "hypothesis",
                "description": hypothesis["description"],
                "value": None,
                "state": hypothesis_state,
                "authority": "INVESTIGATION_FRONTIER",
                "criticality": 1,
                "expected_authority": [],
                "metadata": {
                    "prior": hypothesis["prior"],
                    "evidence_state": hypothesis["evidence_state"],
                    "investigation_state": hypothesis["investigation_state"],
                    "affected_state_ids": hypothesis["affected_state_ids"],
                    "required_evidence": hypothesis["required_evidence"],
                    "mechanical_acceptance_granted": False,
                },
            }
        )
        for requirement_id in hypothesis["related_requirement_ids"]:
            relations.append(
                {
                    "from": f"{prefix}HYPOTHESIS::{hypothesis_id}",
                    "to": f"{prefix}REQUIREMENT::{requirement_id}",
                    "type": "investigates",
                    "strength": 1.0,
                }
            )

    return {
        "fragment_type": "functional_temporal_epistemic_projection",
        "architecture_id": architecture["architecture_id"],
        "nodes": nodes,
        "relations": relations,
        "mechanical_acceptance_granted": False,
        "machine_acceptance_state": "MECHANICAL_ACCEPTANCE_BLOCKED",
        "projection_policy": {
            "point_observation_does_not_prove_interval_invariant": True,
            "static_pose_does_not_prove_reachable_motion_clearance": True,
            "ai_evidence_cannot_satisfy_engineering_requirement": True,
            "local_subsystem_pass_does_not_grant_machine_acceptance": True,
            "llm_may_not_promote_unresolved_requirements": True,
        },
    }


def merge_into_epistemic_graph(
    graph: Mapping[str, Any],
    architecture: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return a new graph with a functional-temporal fragment attached.

    The existing project's acceptance obligation is intentionally untouched.
    This makes an explicit later whole-machine gate responsible for deciding
    whether local evidence is sufficient.
    """

    base = _as_object(graph, "graph")
    nodes = _as_list(base.get("nodes"), "graph.nodes")
    relations = _as_list(base.get("relations", []), "graph.relations")
    existing_ids = {
        _nonempty_string(_as_object(node, "graph node").get("id"), "graph node.id")
        for node in nodes
    }
    fragment = build_epistemic_graph_fragment(architecture)
    fragment_ids = [node["id"] for node in fragment["nodes"]]
    collisions = sorted(existing_ids.intersection(fragment_ids))
    if collisions:
        raise FunctionalTemporalError(
            "Cannot merge functional-temporal fragment; node id collision: " + ", ".join(collisions)
        )

    merged = copy.deepcopy(base)
    merged["nodes"].extend(copy.deepcopy(fragment["nodes"]))
    merged.setdefault("relations", []).extend(copy.deepcopy(fragment["relations"]))
    project = merged.setdefault("project", {})
    bindings = project.setdefault("functional_temporal_architectures", [])
    bindings.append(
        {
            "architecture_id": architecture["architecture_id"],
            "fragment_type": fragment["fragment_type"],
            "mechanical_acceptance_granted": False,
            "machine_acceptance_state": "MECHANICAL_ACCEPTANCE_BLOCKED",
        }
    )
    return merged


def _load_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise FunctionalTemporalError(f"Could not read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FunctionalTemporalError(f"Invalid JSON {label} {path}: {exc}") from exc
    return _as_object(value, label)


def load_architecture(path: Path) -> Dict[str, Any]:
    return _load_json_object(path, "architecture")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate a CADGrounded functional-decomposition and temporal-state architecture."
    )
    parser.add_argument("architecture", type=Path)
    parser.add_argument("--out", type=Path, help="Write the deterministic evaluation report.")
    parser.add_argument(
        "--base-graph",
        type=Path,
        help="Optional epistemic graph to extend without changing its acceptance obligation.",
    )
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    try:
        architecture = load_architecture(args.architecture)
        report = evaluate_architecture(architecture)
        if args.base_graph:
            base_graph = _load_json_object(args.base_graph, "base graph")
            report["merged_epistemic_graph"] = merge_into_epistemic_graph(base_graph, architecture)
    except FunctionalTemporalError as exc:
        raise SystemExit(f"REJECTED: {exc}") from exc

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.summary:
        print(f"ARCHITECTURE: {report['architecture_id']}")
        print(f"TEMPORAL COHERENCE: {report['temporal_coherence_state']}")
        print(f"MACHINE ACCEPTANCE: {report['machine_acceptance_state']}")
        if report["next_test_candidates"]:
            top = report["next_test_candidates"][0]
            print(f"NEXT TEST: {top['test_id']} (value={top['value']})")
        print("MECHANICAL ACCEPTANCE GRANTED: NO")
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
