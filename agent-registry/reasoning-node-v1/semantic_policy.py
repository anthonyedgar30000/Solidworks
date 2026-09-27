from __future__ import annotations

import re
from typing import Any


SEMANTIC_POLICY_TASKS = frozenset({
    "ambiguity_classification",
})


_WS_RE = re.compile(r"\s+")


def normalize_whitespace(value: str) -> str:
    return _WS_RE.sub(" ", value).strip()


def claim_is_grounded(claim: str, evidence: str) -> bool:
    normalized_claim = normalize_whitespace(claim)
    normalized_evidence = normalize_whitespace(evidence)

    if not normalized_claim:
        return False

    return normalized_claim in normalized_evidence


_BUCKET_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "IDENTITY_AMBIGUOUS": (
        re.compile(
            r"\b(?:identity|component|name|handedness)\b.{0,100}"
            r"\b(?:ambiguous|unresolved|unknown|not established|not verified)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:ambiguous|unresolved|unknown)\b.{0,100}"
            r"\b(?:identity|component|name|handedness)\b",
            re.IGNORECASE,
        ),
    ),
    "GEOMETRY_UNRESOLVED": (
        re.compile(
            r"\b(?:geometry|clearance|interference|contact|dimension|position|pose)\b"
            r".{0,100}\b(?:unresolved|unknown|not established|not verified)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:unresolved|unknown|not established|not verified)\b"
            r".{0,100}\b(?:geometry|clearance|interference|contact|dimension|position|pose)\b",
            re.IGNORECASE,
        ),
    ),
    "KINEMATIC_STATE_UNRESOLVED": (
        re.compile(
            r"\b(?:kinematic|motion|movement|sequence|state transition|dof|capture)\b"
            r".{0,120}\b(?:unresolved|unknown|not established|not verified)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:unresolved|unknown|not established|not verified)\b"
            r".{0,120}\b(?:kinematic|motion|movement|sequence|state transition|dof|capture)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bno evidence\b.{0,140}\b(?:kinematic|motion|movement|sequence)\b",
            re.IGNORECASE,
        ),
    ),
    "MEASUREMENT_REQUIRED": (
        re.compile(
            r"\b(?:measurement required|requires measurement|must be measured|needs measurement)\b",
            re.IGNORECASE,
        ),
    ),
    "CAD_READ_REQUIRED": (
        re.compile(
            r"\b(?:cad read required|solidworks read required|requires cad read|requires solidworks read)\b",
            re.IGNORECASE,
        ),
    ),
    "OEM_SOURCE_REQUIRED": (
        re.compile(
            r"\b(?:oem source required|requires oem source|oem evidence required|requires oem evidence)\b",
            re.IGNORECASE,
        ),
    ),
    "SOURCE_CONFLICT": (
        re.compile(
            r"\b(?:source conflict|sources conflict|sources disagree|conflicting evidence|conflicting sources)\b",
            re.IGNORECASE,
        ),
    ),
    "MULTIPLE_PLAUSIBLE_HYPOTHESES": (
        re.compile(
            r"\b(?:multiple plausible hypotheses|multiple hypotheses remain plausible)\b",
            re.IGNORECASE,
        ),
    ),
    "INSUFFICIENT_EVIDENCE": (
        re.compile(
            r"\b(?:insufficient evidence|not enough evidence|no evidence)\b",
            re.IGNORECASE,
        ),
    ),
    "STALE_STATE": (
        re.compile(
            r"\b(?:stale state|state is stale|fresh state required|out[- ]of[- ]date state)\b",
            re.IGNORECASE,
        ),
    ),
    "POLICY_BLOCKED": (
        re.compile(
            r"\b(?:policy blocked|blocked by policy|not permitted by policy|forbidden by policy)\b",
            re.IGNORECASE,
        ),
    ),
    "MECHANICAL_ACCEPTANCE_BLOCKED": (
        re.compile(
            r"\bmechanical acceptance\b.{0,100}"
            r"\b(?:blocked|cannot be granted|cannot proceed)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bblocked\b.{0,100}\bmechanical acceptance\b",
            re.IGNORECASE,
        ),
    ),
}


class SemanticPolicyError(ValueError):
    def __init__(self, violations: list[str]):
        self.violations = tuple(violations)
        super().__init__("; ".join(violations))


def _payload_dict(payload: Any) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump()

    if isinstance(payload, dict):
        return payload

    raise TypeError("payload must be a dict or expose model_dump()")


def _bucket_supported(bucket: str, grounded_claims: list[str]) -> bool:
    # Explicit project bucket token is deterministic evidence of the bucket
    # when the model cites that exact source claim.
    for claim in grounded_claims:
        if bucket in claim:
            return True

    patterns = _BUCKET_PATTERNS.get(bucket, ())

    for claim in grounded_claims:
        for pattern in patterns:
            if pattern.search(claim):
                return True

    return False


def supported_bucket_claim_pairs(evidence: str) -> list[dict[str, str]]:
    """Return deterministic bucket/claim pairs supported by source evidence.

    The catalog is advisory input to the model, not a new evidence source.
    Claims remain exact source sentences and all authority stays with the
    deterministic semantic policy.
    """
    pairs: list[dict[str, str]] = []

    for raw_line in evidence.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue

        claim = line[2:].strip()
        if not claim:
            continue

        for bucket in _BUCKET_PATTERNS:
            if _bucket_supported(bucket, [claim]):
                pairs.append({
                    "bucket": bucket,
                    "claim": claim,
                })

    return pairs


def validate_semantic_admission(
    *,
    task: str,
    evidence: str,
    payload: Any,
) -> None:
    violations: list[str] = []

    if task not in SEMANTIC_POLICY_TASKS:
        raise SemanticPolicyError([
            f"SEMANTIC_POLICY_NOT_IMPLEMENTED:{task}",
        ])

    data = _payload_dict(payload)

    if task == "ambiguity_classification":
        claims = list(data.get("claims_used") or [])
        buckets = list(data.get("ambiguity_buckets") or [])
        inferences = list(data.get("inferences") or [])
        hypotheses = list(data.get("hypotheses") or [])
        next_tests = list(data.get("next_tests") or [])

        if not claims:
            violations.append("CLAIMS_USED_REQUIRED")

        if not buckets:
            violations.append("AMBIGUITY_BUCKET_REQUIRED")

        grounded_claims: list[str] = []

        for index, claim in enumerate(claims):
            if claim_is_grounded(claim, evidence):
                grounded_claims.append(claim)
            else:
                violations.append(
                    f"UNGROUNDED_CLAIM:{index}"
                )

        if inferences:
            violations.append(
                "CLASSIFICATION_INFERENCES_NOT_ALLOWED"
            )

        if hypotheses:
            violations.append(
                "CLASSIFICATION_HYPOTHESES_NOT_ALLOWED"
            )

        if next_tests:
            violations.append(
                "CLASSIFICATION_NEXT_TESTS_NOT_ALLOWED"
            )

        for bucket in buckets:
            if not _bucket_supported(bucket, grounded_claims):
                violations.append(
                    f"UNSUPPORTED_BUCKET:{bucket}"
                )

    if violations:
        raise SemanticPolicyError(violations)
