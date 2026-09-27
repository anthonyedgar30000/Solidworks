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
    SemanticPolicyError,
    supported_bucket_claim_pairs,
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
    version="0.4.0",
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
    evidence_status: EvidenceStatus
    investigation_status: InvestigationStatus


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
  "hypotheses": [],
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

    return """
SEMANTIC ADMISSION NOTICE:

No deterministic semantic-admission policy is implemented for this task yet.
Any output may be schema-valid, but it will be rejected rather than
semantically admitted.
"""


def grounding_catalog(task: str, evidence: str) -> str:
    if task != "ambiguity_classification":
        return "No deterministic grounding catalog is implemented for this task."

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
        "- ambiguity_buckets must contain only selected pair bucket values.",
        "- claims_used must contain only selected pair claim values, copied exactly.",
        "- Do not use any evidence sentence that is not in an allowed pair.",
        "- Do not invent another bucket.",
    ])

    return "\n".join(lines)


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
        "version": "0.4.0",
        "node_id": NODE_ID,
        "role": "bounded_reasoning_node",
        "ollama": ollama,
        "model": MODEL,
        "cad_write_authority": "NONE",
        "mechanical_acceptance_authority": "NONE",
        "evidence_verification_authority": "NONE",
        "semantic_admission_policy": "fail_closed",
        "semantic_policy_tasks": [
            "ambiguity_classification",
        ],
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
                "format": "json",
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

    try:
        validate_semantic_admission(
            task=request.task,
            evidence=request.evidence,
            payload=validated,
        )

    except SemanticPolicyError as exc:
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
            "violations": list(exc.violations),
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
                "violations": list(exc.violations),
            },
        )

    result = ReasonResponse(
        request_id=request_id,
        timestamp_utc=timestamp,
        node_id=NODE_ID,
        model=MODEL,
        task=request.task,
        evidence_sha256=evidence_hash,
        result=validated,
    )

    append_log({
        "request_id": request_id,
        "timestamp_utc": timestamp,
        "node_id": NODE_ID,
        "model": MODEL,
        "task": request.task,
        "evidence_sha256": evidence_hash,
        "proposal_raw_sha256": sha256_text(raw_result),
        "proposal_raw": raw_result,
        "proposal_validated": validated.model_dump(),
        "status": "SEMANTICALLY_ADMITTED",
        "schema_validated": True,
        "semantic_admitted": True,
        "authority": {
            "solidworks_geometry": "NONE",
            "cad_write": "NONE",
            "mechanical_acceptance": "NONE",
            "evidence_verification": "NONE",
        },
        "result": validated.model_dump(),
    })

    return result
