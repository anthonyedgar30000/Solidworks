from __future__ import annotations

import re
from typing import Any


SEMANTIC_POLICY_TASKS = frozenset({
    "ambiguity_classification",
    "hypothesis_generation",
})

HYPOTHESIS_ANCHOR_BUCKETS = frozenset({
    "IDENTITY_AMBIGUOUS",
    "GEOMETRY_UNRESOLVED",
    "KINEMATIC_STATE_UNRESOLVED",
})


_WS_RE = re.compile(r"\s+")
_HYPOTHESIS_TENTATIVE_RE = re.compile(
    r"\b(?:may|might|could|possibly|potentially)\b",
    re.IGNORECASE,
)
_HYPOTHESIS_FORBIDDEN_ASSERTION_RE = re.compile(
    r"\b(?:verified|confirmed|observed|measured|calculated|proven|established|mechanically accepted)\b",
    re.IGNORECASE,
)
_HYPOTHESIS_EPISTEMIC_GAP_RE = re.compile(
    r"\b(?:missing data|insufficient data|lack of evidence|no evidence|not enough evidence|insufficient evidence)\b",
    re.IGNORECASE,
)
_HYPOTHESIS_CLASS_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "CLOSURE_KINEMATICS": (
        re.compile(
            r"\b(?:closures?|captures?|carriers?|slides?|sliding|pivots?|pivoting|arms?|rollers?|belts?|translate|translates|translating|translation)\b",
            re.IGNORECASE,
        ),
    ),
    "COMPLIANCE_PRELOAD": (
        re.compile(
            r"\b(?:spring|compliant|compliance|preload|preloaded|deflect|deflection|flex|flexible|elastic)\b",
            re.IGNORECASE,
        ),
    ),
    "ACTUATION_DRIVE": (
        re.compile(
            r"\b(?:actuator|actuation|cylinder|pneumatic|motor|servo|drive|driven)\b",
            re.IGNORECASE,
        ),
    ),
    "SEQUENCE_CONTROL": (
        re.compile(
            r"\b(?:timing|phase|sensor|control|index|indexing|trigger|stepwise|state transition|release)\b",
            re.IGNORECASE,
        ),
    ),
    "SOURCE_BOUNDARY": (
        re.compile(
            r"\b(?:nested|external|unmodeled|unmodelled|configuration|assembly boundary|feature boundary|hidden assembly|hidden feature)\b",
            re.IGNORECASE,
        ),
    ),
    "OTHER_EXPLICIT_MECHANISM": (
        re.compile(
            r"\b(?:linkage|cam|follower|clamp|guide|restraint|lever|mechanical linkage)\b",
            re.IGNORECASE,
        ),
    ),
}
_HYPOTHESIS_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_HYPOTHESIS_SIMILARITY_STOPWORDS = frozenset({
    "hypothesis", "a", "an", "the", "may", "might", "could",
    "possibly", "potentially", "be", "have", "has", "is", "are",
    "to", "of", "for", "and", "or", "that", "this", "due", "because",
})


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


def supported_hypothesis_anchor_pairs(
    evidence: str,
) -> list[dict[str, str]]:
    """Return supported pairs eligible to anchor causal hypotheses.

    Routing/gate buckets and explicit evidence-absence claims remain useful for
    classification, but they are not causal explanations and cannot seed a
    hypothesis.
    """
    return [
        pair
        for pair in supported_bucket_claim_pairs(evidence)
        if pair["bucket"] in HYPOTHESIS_ANCHOR_BUCKETS
        and not _HYPOTHESIS_EPISTEMIC_GAP_RE.search(pair["claim"])
    ]


def _hypothesis_class_supported(
    hypothesis_class: str,
    statement: str,
) -> bool:
    patterns = _HYPOTHESIS_CLASS_PATTERNS.get(
        hypothesis_class,
        (),
    )
    return any(pattern.search(statement) for pattern in patterns)


def _hypothesis_content_tokens(statement: str) -> set[str]:
    return {
        token.lower()
        for token in _HYPOTHESIS_TOKEN_RE.findall(statement)
        if token.lower() not in _HYPOTHESIS_SIMILARITY_STOPWORDS
    }


def _hypothesis_similarity(
    statement_a: str,
    statement_b: str,
) -> float:
    tokens_a = _hypothesis_content_tokens(statement_a)
    tokens_b = _hypothesis_content_tokens(statement_b)

    if not tokens_a or not tokens_b:
        return 0.0

    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


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
        seen_claims: set[str] = set()

        for index, claim in enumerate(claims):
            normalized_claim = normalize_whitespace(claim)
            if normalized_claim in seen_claims:
                violations.append(
                    f"DUPLICATE_CLAIM:{index}"
                )
            seen_claims.add(normalized_claim)

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

        seen_buckets: set[str] = set()
        for index, bucket in enumerate(buckets):
            if bucket in seen_buckets:
                violations.append(
                    f"DUPLICATE_AMBIGUITY_BUCKET:{index}:{bucket}"
                )
            seen_buckets.add(bucket)

            if not _bucket_supported(bucket, grounded_claims):
                violations.append(
                    f"UNSUPPORTED_BUCKET:{bucket}"
                )

    elif task == "hypothesis_generation":
        claims = list(data.get("claims_used") or [])
        buckets = list(data.get("ambiguity_buckets") or [])
        inferences = list(data.get("inferences") or [])
        hypotheses = list(data.get("hypotheses") or [])
        next_tests = list(data.get("next_tests") or [])
        notes = list(data.get("notes") or [])

        if not claims:
            violations.append("CLAIMS_USED_REQUIRED")

        if not buckets:
            violations.append("AMBIGUITY_BUCKET_REQUIRED")

        if not hypotheses:
            violations.append("HYPOTHESIS_REQUIRED")

        if len(hypotheses) > 3:
            violations.append("HYPOTHESIS_COUNT_EXCEEDED")

        grounded_claims: list[str] = []
        seen_claims: set[str] = set()
        eligible_anchor_claims = {
            normalize_whitespace(pair["claim"])
            for pair in supported_hypothesis_anchor_pairs(evidence)
        }

        for index, claim in enumerate(claims):
            normalized_claim = normalize_whitespace(claim)
            if normalized_claim in seen_claims:
                violations.append(
                    f"DUPLICATE_CLAIM:{index}"
                )
            seen_claims.add(normalized_claim)

            if claim_is_grounded(claim, evidence):
                grounded_claims.append(claim)
            else:
                violations.append(
                    f"UNGROUNDED_CLAIM:{index}"
                )

            if normalized_claim not in eligible_anchor_claims:
                violations.append(
                    f"HYPOTHESIS_CLAIM_NOT_CAUSAL_ANCHOR:{index}"
                )

        seen_buckets: set[str] = set()
        for index, bucket in enumerate(buckets):
            if bucket in seen_buckets:
                violations.append(
                    f"DUPLICATE_AMBIGUITY_BUCKET:{index}:{bucket}"
                )
            seen_buckets.add(bucket)

            if not _bucket_supported(bucket, grounded_claims):
                violations.append(
                    f"UNSUPPORTED_BUCKET:{bucket}"
                )
            if bucket not in HYPOTHESIS_ANCHOR_BUCKETS:
                violations.append(
                    f"HYPOTHESIS_BUCKET_NOT_CAUSAL_ANCHOR:{bucket}"
                )

        if inferences:
            violations.append(
                "HYPOTHESIS_GENERATION_INFERENCES_NOT_ALLOWED"
            )

        if next_tests:
            violations.append(
                "HYPOTHESIS_GENERATION_NEXT_TESTS_NOT_ALLOWED"
            )

        if notes:
            violations.append(
                "HYPOTHESIS_GENERATION_NOTES_NOT_ALLOWED"
            )

        normalized_claims = {
            normalize_whitespace(claim)
            for claim in claims
        }
        seen_statements: set[str] = set()
        seen_classes: set[str] = set()
        prior_statements: list[tuple[int, str]] = []

        for index, hypothesis in enumerate(hypotheses):
            statement = str(hypothesis.get("statement") or "").strip()
            hypothesis_class = str(
                hypothesis.get("hypothesis_class") or ""
            ).strip()
            evidence_status = hypothesis.get("evidence_status")
            investigation_status = hypothesis.get("investigation_status")
            anchor_buckets = list(hypothesis.get("anchor_buckets") or [])
            anchor_claims = list(hypothesis.get("anchor_claims") or [])

            if not statement.startswith("Hypothesis: "):
                violations.append(
                    f"HYPOTHESIS_PREFIX_REQUIRED:{index}"
                )

            if not _HYPOTHESIS_TENTATIVE_RE.search(statement):
                violations.append(
                    f"HYPOTHESIS_TENTATIVE_LANGUAGE_REQUIRED:{index}"
                )

            if _HYPOTHESIS_FORBIDDEN_ASSERTION_RE.search(statement):
                violations.append(
                    f"HYPOTHESIS_FORBIDDEN_ASSERTION:{index}"
                )

            if _HYPOTHESIS_EPISTEMIC_GAP_RE.search(statement):
                violations.append(
                    f"HYPOTHESIS_EPISTEMIC_GAP_IS_NOT_MECHANISM:{index}"
                )

            if not _hypothesis_class_supported(
                hypothesis_class,
                statement,
            ):
                violations.append(
                    f"HYPOTHESIS_CLASS_UNSUPPORTED:{index}:{hypothesis_class or 'EMPTY'}"
                )

            if hypothesis_class in seen_classes:
                violations.append(
                    f"HYPOTHESIS_CLASS_DUPLICATE:{index}:{hypothesis_class}"
                )
            seen_classes.add(hypothesis_class)

            normalized_statement = normalize_whitespace(statement)
            if normalized_statement in seen_statements:
                violations.append(
                    f"DUPLICATE_HYPOTHESIS:{index}"
                )
            seen_statements.add(normalized_statement)

            for prior_index, prior_statement in prior_statements:
                similarity = _hypothesis_similarity(
                    prior_statement,
                    statement,
                )
                if similarity >= 0.60:
                    violations.append(
                        f"HYPOTHESIS_NEAR_DUPLICATE:{prior_index}:{index}"
                    )
            prior_statements.append((index, statement))

            statement_body = statement.removeprefix("Hypothesis: ")
            if normalize_whitespace(statement_body) in normalized_claims:
                violations.append(
                    f"HYPOTHESIS_RESTATES_CLAIM:{index}"
                )

            if evidence_status != "UNTESTED":
                violations.append(
                    f"HYPOTHESIS_EVIDENCE_STATUS_MUST_BE_UNTESTED:{index}"
                )

            if investigation_status != "ELIGIBLE":
                violations.append(
                    f"HYPOTHESIS_INVESTIGATION_STATUS_MUST_BE_ELIGIBLE:{index}"
                )

            if not anchor_buckets:
                violations.append(
                    f"HYPOTHESIS_ANCHOR_BUCKET_REQUIRED:{index}"
                )

            if not anchor_claims:
                violations.append(
                    f"HYPOTHESIS_ANCHOR_CLAIM_REQUIRED:{index}"
                )

            grounded_anchor_claims: list[str] = []

            for claim_index, anchor_claim in enumerate(anchor_claims):
                normalized_anchor = normalize_whitespace(anchor_claim)

                if normalized_anchor not in normalized_claims:
                    violations.append(
                        f"HYPOTHESIS_ANCHOR_CLAIM_NOT_SELECTED:{index}:{claim_index}"
                    )

                if claim_is_grounded(anchor_claim, evidence):
                    grounded_anchor_claims.append(anchor_claim)
                else:
                    violations.append(
                        f"HYPOTHESIS_ANCHOR_CLAIM_UNGROUNDED:{index}:{claim_index}"
                    )

            for bucket_index, anchor_bucket in enumerate(anchor_buckets):
                if anchor_bucket not in buckets:
                    violations.append(
                        f"HYPOTHESIS_ANCHOR_BUCKET_NOT_SELECTED:{index}:{bucket_index}"
                    )

                if not _bucket_supported(
                    anchor_bucket,
                    grounded_anchor_claims,
                ):
                    violations.append(
                        f"HYPOTHESIS_ANCHOR_BUCKET_UNSUPPORTED:{index}:{bucket_index}"
                    )

    if violations:
        raise SemanticPolicyError(violations)
