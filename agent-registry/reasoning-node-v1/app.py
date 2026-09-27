from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import hashlib
import json
import uuid

import requests
import yaml

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from semantic_policy import (
    SEMANTIC_POLICY_TASKS,
    SemanticPolicyError,
    supported_bucket_claim_pairs,
    supported_hypothesis_anchor_pairs,
    validate_semantic_admission,
)


BASE_DIR = Path(r"C:\CADGrounded\reasoning-node")
NODE_CONFIG = BASE_DIR / "node.yaml"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

with NODE_CONFIG.open("r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

NODE_ID = config["node_id"]
OLLAMA_ENDPOINT = config["ollama"]["endpoint"]
MODEL = config["ollama"]["initial_model"]


app = FastAPI(
    title="CADGrounded Reasoning Node",
    version="0.6.0",
)


TaskType = Literal[
    "ambiguity_classification",
    "hypothesis_generation",
    "hypothesis_categorization",
    "investigation_planning",
    "next_test_proposal",
    "search_exhaustion_detection",
]

AmbiguityBucket = Literal[
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
]

HypothesisPrior = Literal[
    "COMMON",
    "UNCOMMON",
    "RARE",
]

HypothesisClass = Literal[
    "CLOSURE_KINEMATICS",
    "COMPLIANCE_PRELOAD",
    "ACTUATION_DRIVE",
    "SEQUENCE_CONTROL",
    "SOURCE_BOUNDARY",
    "OTHER_EXPLICIT_MECHANISM",
]

EvidenceStatus = Literal[
    "UNTESTED",
    "SUPPORTED",
    "WEAKENED",
    "DISPROVEN",
    "UNRESOLVED",
]

InvestigationStatus = Literal[
    "DORMANT",
    "ELIGIBLE",
    "ACTIVE",
    "EXHAUSTED",
]


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: TaskType
    evidence: str = Field(min_length=1, max_length=30000)


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    prior: HypothesisPrior
    hypothesis_class: HypothesisClass
    evidence_status: EvidenceStatus
    investigation_status: InvestigationStatus
    anchor_buckets: list[AmbiguityBucket]
    anchor_claims: list[str]


class NextTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test: str
    diagnostic_value: str
    required_authority: str


class AdvisoryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambiguity_buckets: list[AmbiguityBucket]
    claims_used: list[str]
    inferences: list[str]
    hypotheses: list[Hypothesis]
    next_tests: list[NextTest]
    notes: list[str]


class ReasonResponse(BaseModel):
    request_id: str
    timestamp_utc: str

    node_id: str
    model: str
    task: TaskType

    evidence_sha256: str

    advisory_only: Literal[True] = True

    solidworks_geometry_authority: Literal["NONE"] = "NONE"
    cad_write_authority: Literal["NONE"] = "NONE"
    mechanical_acceptance_authority: Literal["NONE"] = "NONE"
    evidence_verification_authority: Literal["NONE"] = "NONE"

    schema_validated: Literal[True] = True
    semantic_admitted: Literal[True] = True
    semantic_repair_attempted: bool = False
    semantic_repair_count: int = Field(default=0, ge=0, le=1)

    result: AdvisoryPayload


SYSTEM_BOUNDARY = """
You are a bounded CADGrounded investigation-planning model.

AUTHORITY:
You have NO authority to:
- verify CAD geometry
- claim SOLIDWORKS state is verified
- convert UNKNOWN or unresolved evidence to VERIFIED
- grant mechanical acceptance
- authorize or perform CAD writes
- override OEM evidence
- override deterministic measurements

You may only:
- classify ambiguity
- generate/categorize hypotheses
- propose investigations
- propose high-information next tests
- detect possible investigation/search exhaustion

PRESERVE UNCERTAINTY.

Use ONLY these ambiguity buckets:
IDENTITY_AMBIGUOUS
GEOMETRY_UNRESOLVED
KINEMATIC_STATE_UNRESOLVED
MEASUREMENT_REQUIRED
CAD_READ_REQUIRED
OEM_SOURCE_REQUIRED
SOURCE_CONFLICT
MULTIPLE_PLAUSIBLE_HYPOTHESES
INSUFFICIENT_EVIDENCE
STALE_STATE
POLICY_BLOCKED
MECHANICAL_ACCEPTANCE_BLOCKED

Hypothesis prior must be:
COMMON, UNCOMMON, or RARE.

Hypothesis evidence_status must be:
UNTESTED, SUPPORTED, WEAKENED, DISPROVEN, or UNRESOLVED.

Investigation status must be:
DORMANT, ELIGIBLE, ACTIVE, or EXHAUSTED.

Do not invent observations.

claims_used must contain only claims explicitly present in supplied evidence.

inferences must clearly be inferences, not observations.

Return JSON only.

Required JSON structure:

{
  "ambiguity_buckets": [],
  "claims_used": [],
  "inferences": [],
  "hypotheses": [
    {
      "statement": "Hypothesis: ... may ...",
      "prior": "COMMON",
      "hypothesis_class": "CLOSURE_KINEMATICS",
      "evidence_status": "UNTESTED",
      "investigation_status": "ELIGIBLE",
      "anchor_buckets": [],
      "anchor_claims": []
    }
  ],
  "next_tests": [],
  "notes": []
}
"""


def task_contract(task: str) -> str:
    if task == "ambiguity_classification":
        return """
AMBIGUITY CLASSIFICATION CONTRACT:

- This task is classification only.
- claims_used MUST contain at least one claim copied from the supplied evidence.
- Copy claims verbatim except for insignificant whitespace normalization.
- Do not paraphrase claims_used.
- ambiguity_buckets must contain only buckets directly supported by claims_used.
- When a deterministic allowed-pair catalog is supplied, select only bucket/claim values from that catalog.
- inferences MUST be [].
- hypotheses MUST be [].
- next_tests MUST be [].
- Do not convert an unresolved fact into VERIFIED state.
"""

    if task == "hypothesis_generation":
        return """
HYPOTHESIS GENERATION CONTRACT:

- This task generates candidate explanations only; it does not create findings or observations.
- Select at least one ambiguity bucket/claim pair from the deterministic grounding catalog.
- claims_used MUST contain only exact source claims selected from that catalog.
- Generate between 1 and 3 hypotheses.
- Every hypothesis MUST choose exactly one hypothesis_class from:
  CLOSURE_KINEMATICS, COMPLIANCE_PRELOAD, ACTUATION_DRIVE,
  SEQUENCE_CONTROL, SOURCE_BOUNDARY, OTHER_EXPLICIT_MECHANISM.
- Generated hypotheses MUST use distinct hypothesis_class values; do not produce modal paraphrases of the same explanation.
- Class meanings:
  CLOSURE_KINEMATICS = carrier/slide/pivot/roller/belt/closure geometry or motion ownership.
  COMPLIANCE_PRELOAD = spring/compliance/preload/flex/deflection behavior.
  ACTUATION_DRIVE = actuator/cylinder/pneumatic/motor/drive ownership.
  SEQUENCE_CONTROL = timing/phase/sensor/control/index/release sequencing.
  SOURCE_BOUNDARY = nested/external/unmodeled/configuration-bound mechanism or ownership.
  OTHER_EXPLICIT_MECHANISM = another explicit physical mechanism class not covered above.
- A hypothesis about missing/insufficient data alone is not a mechanical explanation; do not use evidence absence as the causal mechanism.
- Every hypothesis statement MUST begin with "Hypothesis: ".
- Every hypothesis statement MUST use tentative language such as may, might, could, possibly, or potentially.
- Every hypothesis MUST have evidence_status = "UNTESTED".
- Every hypothesis MUST have investigation_status = "ELIGIBLE".
- Every hypothesis MUST include one or more anchor_buckets drawn from the selected top-level ambiguity_buckets.
- Every hypothesis MUST include one or more anchor_claims drawn from the selected top-level claims_used.
- Each anchor bucket must be directly supported by at least one of that hypothesis's anchor claims.
- inferences MUST be [].
- next_tests MUST be [].
- notes MUST be [].
- Do not describe a hypothesis as verified, confirmed, observed, measured, calculated, proven, established, or mechanically accepted.
- Do not convert unresolved evidence into VERIFIED state.
"""

    return """
SEMANTIC ADMISSION NOTICE:

No deterministic semantic-admission policy is implemented for this task yet.
Any output may be schema-valid, but it will be rejected rather than
semantically admitted.
"""


def grounding_catalog(task: str, evidence: str) -> str:
    if task not in {
        "ambiguity_classification",
        "hypothesis_generation",
    }:
        return "No deterministic grounding catalog is implemented for this task."

    if task == "hypothesis_generation":
        pairs = supported_hypothesis_anchor_pairs(evidence)
    else:
        pairs = supported_bucket_claim_pairs(evidence)

    if not pairs:
        return """DETERMINISTICALLY ALLOWED BUCKET/CLAIM PAIRS:
NONE

No bucket/claim pair has deterministic support in the supplied evidence.
Do not invent one."""

    lines = ["DETERMINISTICALLY ALLOWED BUCKET/CLAIM PAIRS:"]

    for index, pair in enumerate(pairs, start=1):
        lines.extend([
            f"PAIR-{index}",
            f"bucket: {pair['bucket']}",
            f"claim: {pair['claim']}",
            "",
        ])

    lines.extend([
        "SELECTION CONTRACT:",
        "- Select one or more pairs only from the allowed list above.",
        "- ambiguity_buckets must contain only selected pair bucket values and each bucket value must appear at most once.",
        "- claims_used must contain only selected pair claim values, copied exactly, with no duplicate claim entries.",
        "- Do not use any evidence sentence that is not in an allowed pair.",
        "- Do not invent another bucket.",
    ])

    if task == "hypothesis_generation":
        lines.extend([
            "- This catalog contains only causal ambiguity anchors eligible for hypothesis generation.",
            "- Do not add routing/gate buckets such as INSUFFICIENT_EVIDENCE, CAD_READ_REQUIRED, OEM_SOURCE_REQUIRED, STALE_STATE, POLICY_BLOCKED, or MECHANICAL_ACCEPTANCE_BLOCKED.",
            "- If only one genuinely distinct physical explanation can be formed, return exactly one hypothesis rather than filling unused slots with paraphrases.",
        ])

    return "\n".join(lines)


def semantic_repair_prompt(
    request: ReasonRequest,
    original_raw: str,
    violations: list[str],
) -> str:
    return f"""
{SYSTEM_BOUNDARY}

REQUESTED TASK:
{request.task}

TASK-SPECIFIC CONTRACT:
{task_contract(request.task)}

SUPPLIED EVIDENCE:
--- BEGIN EVIDENCE ---
{request.evidence}
--- END EVIDENCE ---

DETERMINISTIC GROUNDING CATALOG:
{grounding_catalog(request.task, request.evidence)}

PREVIOUS SCHEMA-VALID PROPOSAL:
{original_raw}

DETERMINISTIC REJECTION VIOLATIONS:
{json.dumps(violations)}

ONE-PASS CORRECTION CONTRACT:
- This is the only semantic repair attempt.
- Return a replacement full JSON object only.
- Correct every listed deterministic violation; do not defend the previous proposal.
- It is valid and preferred to DELETE a rejected duplicate rather than invent a replacement.
- If one valid hypothesis remains, return exactly one hypothesis.
- Never reuse a hypothesis_class.
- Do not add any bucket or claim absent from the deterministic grounding catalog.
- Do not turn missing/insufficient evidence or lack of establishment into a hypothesis.
- Keep all hypotheses UNTESTED and ELIGIBLE.
- Preserve uncertainty and all authority boundaries.

Return only the corrected JSON object.
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def append_log(record: dict):
    log_file = LOG_DIR / "transactions.jsonl"

    with log_file.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                record,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        )


@app.get("/healthz")
def healthz():

    try:
        response = requests.get(
            f"{OLLAMA_ENDPOINT}/api/tags",
            timeout=5,
        )
        response.raise_for_status()
        ollama = "reachable"

    except Exception:
        ollama = "unreachable"

    return {
        "status": "ok",
        "version": "0.6.0",
        "node_id": NODE_ID,
        "role": "bounded_reasoning_node",
        "ollama": ollama,
        "model": MODEL,
        "cad_write_authority": "NONE",
        "mechanical_acceptance_authority": "NONE",
        "evidence_verification_authority": "NONE",
        "semantic_admission_policy": "fail_closed",
        "semantic_policy_tasks": sorted(SEMANTIC_POLICY_TASKS),
        "semantic_repair_policy": {
            "task": "hypothesis_generation",
            "max_attempts": 1,
            "authority": "NONE",
        },
    }


@app.post("/reason", response_model=ReasonResponse)
def reason(request: ReasonRequest):

    request_id = str(uuid.uuid4())
    timestamp = utc_now()
    evidence_hash = sha256_text(request.evidence)

    prompt = f"""
{SYSTEM_BOUNDARY}

REQUESTED TASK:
{request.task}

TASK-SPECIFIC CONTRACT:
{task_contract(request.task)}

SUPPLIED EVIDENCE:
--- BEGIN EVIDENCE ---
{request.evidence}
--- END EVIDENCE ---

DETERMINISTIC GROUNDING CATALOG:
{grounding_catalog(request.task, request.evidence)}

Return only the required JSON object.
"""

    try:
        response = requests.post(
            f"{OLLAMA_ENDPOINT}/api/generate",
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "format": AdvisoryPayload.model_json_schema(),
                "options": {
                    "temperature": 0,
                },
            },
            timeout=120,
        )

        response.raise_for_status()

        raw_result = response.json()["response"]
        decoded = json.loads(raw_result)

        validated = AdvisoryPayload.model_validate(decoded)

    except (
        requests.RequestException,
        json.JSONDecodeError,
        KeyError,
        ValueError,
    ) as exc:

        failure_record = {
            "request_id": request_id,
            "timestamp_utc": timestamp,
            "node_id": NODE_ID,
            "model": MODEL,
            "task": request.task,
            "evidence_sha256": evidence_hash,
            "status": "REJECTED_SCHEMA",
            "schema_validated": False,
            "semantic_admitted": False,
            "reason": type(exc).__name__,
            "authority": {
                "solidworks_geometry": "NONE",
                "cad_write": "NONE",
                "mechanical_acceptance": "NONE",
                "evidence_verification": "NONE",
            },
        }

        append_log(failure_record)

        raise HTTPException(
            status_code=422,
            detail={
                "status": "REJECTED_SCHEMA",
                "message": "Reasoning output failed deterministic schema validation.",
            },
        )

    semantic_repair_attempted = False
    semantic_repair_count = 0
    semantic_repair_record = None
    admission_status = "SEMANTICALLY_ADMITTED"

    try:
        validate_semantic_admission(
            task=request.task,
            evidence=request.evidence,
            payload=validated,
        )

    except SemanticPolicyError as exc:
        initial_violations = list(exc.violations)

        if request.task != "hypothesis_generation":
            failure_record = {
                "request_id": request_id,
                "timestamp_utc": timestamp,
                "node_id": NODE_ID,
                "model": MODEL,
                "task": request.task,
                "evidence_sha256": evidence_hash,
                "proposal_raw_sha256": sha256_text(raw_result),
                "proposal_raw": raw_result,
                "proposal_validated": validated.model_dump(),
                "status": "REJECTED_SEMANTIC_POLICY",
                "schema_validated": True,
                "semantic_admitted": False,
                "semantic_repair_attempted": False,
                "semantic_repair_count": 0,
                "violations": initial_violations,
                "authority": {
                    "solidworks_geometry": "NONE",
                    "cad_write": "NONE",
                    "mechanical_acceptance": "NONE",
                    "evidence_verification": "NONE",
                },
            }

            append_log(failure_record)

            raise HTTPException(
                status_code=422,
                detail={
                    "status": "REJECTED_SEMANTIC_POLICY",
                    "violations": initial_violations,
                },
            )

        semantic_repair_attempted = True
        semantic_repair_count = 1
        semantic_repair_record = {
            "attempted": True,
            "attempt_count": 1,
            "initial_proposal_raw_sha256": sha256_text(raw_result),
            "initial_proposal_raw": raw_result,
            "initial_proposal_validated": validated.model_dump(),
            "initial_violations": initial_violations,
        }

        repair_raw_result = None

        try:
            repair_response = requests.post(
                f"{OLLAMA_ENDPOINT}/api/generate",
                json={
                    "model": MODEL,
                    "prompt": semantic_repair_prompt(
                        request,
                        raw_result,
                        initial_violations,
                    ),
                    "stream": False,
                    "format": AdvisoryPayload.model_json_schema(),
                    "options": {
                        "temperature": 0,
                    },
                },
                timeout=120,
            )

            repair_response.raise_for_status()
            repair_raw_result = repair_response.json()["response"]
            repair_decoded = json.loads(repair_raw_result)
            repair_validated = AdvisoryPayload.model_validate(
                repair_decoded
            )

        except (
            requests.RequestException,
            json.JSONDecodeError,
            KeyError,
            ValueError,
        ) as repair_exc:
            repair_failure = dict(semantic_repair_record)
            repair_failure.update({
                "repair_schema_validated": False,
                "repair_reason": type(repair_exc).__name__,
                "repair_proposal_raw_sha256": (
                    sha256_text(repair_raw_result)
                    if repair_raw_result is not None
                    else None
                ),
                "repair_proposal_raw": repair_raw_result,
            })

            failure_record = {
                "request_id": request_id,
                "timestamp_utc": timestamp,
                "node_id": NODE_ID,
                "model": MODEL,
                "task": request.task,
                "evidence_sha256": evidence_hash,
                "status": "REJECTED_REPAIR_OUTPUT",
                "schema_validated": False,
                "semantic_admitted": False,
                "semantic_repair_attempted": True,
                "semantic_repair_count": 1,
                "semantic_repair": repair_failure,
                "authority": {
                    "solidworks_geometry": "NONE",
                    "cad_write": "NONE",
                    "mechanical_acceptance": "NONE",
                    "evidence_verification": "NONE",
                },
            }

            append_log(failure_record)

            raise HTTPException(
                status_code=422,
                detail={
                    "status": "REJECTED_REPAIR_OUTPUT",
                    "message": "Bounded repair output failed transport/schema validation.",
                },
            )

        try:
            validate_semantic_admission(
                task=request.task,
                evidence=request.evidence,
                payload=repair_validated,
            )

        except SemanticPolicyError as repair_exc:
            repair_violations = list(repair_exc.violations)
            repair_failure = dict(semantic_repair_record)
            repair_failure.update({
                "repair_schema_validated": True,
                "repair_proposal_raw_sha256": sha256_text(
                    repair_raw_result
                ),
                "repair_proposal_raw": repair_raw_result,
                "repair_proposal_validated": (
                    repair_validated.model_dump()
                ),
                "repair_violations": repair_violations,
            })

            failure_record = {
                "request_id": request_id,
                "timestamp_utc": timestamp,
                "node_id": NODE_ID,
                "model": MODEL,
                "task": request.task,
                "evidence_sha256": evidence_hash,
                "proposal_raw_sha256": sha256_text(
                    repair_raw_result
                ),
                "proposal_raw": repair_raw_result,
                "proposal_validated": (
                    repair_validated.model_dump()
                ),
                "status": "REJECTED_SEMANTIC_POLICY_AFTER_REPAIR",
                "schema_validated": True,
                "semantic_admitted": False,
                "semantic_repair_attempted": True,
                "semantic_repair_count": 1,
                "violations": repair_violations,
                "semantic_repair": repair_failure,
                "authority": {
                    "solidworks_geometry": "NONE",
                    "cad_write": "NONE",
                    "mechanical_acceptance": "NONE",
                    "evidence_verification": "NONE",
                },
            }

            append_log(failure_record)

            raise HTTPException(
                status_code=422,
                detail={
                    "status": "REJECTED_SEMANTIC_POLICY_AFTER_REPAIR",
                    "violations": repair_violations,
                },
            )

        semantic_repair_record.update({
            "repair_schema_validated": True,
            "repair_proposal_raw_sha256": sha256_text(
                repair_raw_result
            ),
            "repair_proposal_raw": repair_raw_result,
            "repair_proposal_validated": repair_validated.model_dump(),
            "repair_violations": [],
        })

        raw_result = repair_raw_result
        validated = repair_validated
        admission_status = "SEMANTICALLY_ADMITTED_AFTER_REPAIR"

    result = ReasonResponse(
        request_id=request_id,
        timestamp_utc=timestamp,
        node_id=NODE_ID,
        model=MODEL,
        task=request.task,
        evidence_sha256=evidence_hash,
        semantic_repair_attempted=semantic_repair_attempted,
        semantic_repair_count=semantic_repair_count,
        result=validated,
    )

    success_record = {
        "request_id": request_id,
        "timestamp_utc": timestamp,
        "node_id": NODE_ID,
        "model": MODEL,
        "task": request.task,
        "evidence_sha256": evidence_hash,
        "proposal_raw_sha256": sha256_text(raw_result),
        "proposal_raw": raw_result,
        "proposal_validated": validated.model_dump(),
        "status": admission_status,
        "schema_validated": True,
        "semantic_admitted": True,
        "semantic_repair_attempted": semantic_repair_attempted,
        "semantic_repair_count": semantic_repair_count,
        "authority": {
            "solidworks_geometry": "NONE",
            "cad_write": "NONE",
            "mechanical_acceptance": "NONE",
            "evidence_verification": "NONE",
        },
        "result": validated.model_dump(),
    }

    if semantic_repair_record is not None:
        success_record["semantic_repair"] = semantic_repair_record

    append_log(success_record)

    return result
