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
    version="0.2.0",
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
      "statement": "",
      "prior": "COMMON",
      "evidence_status": "UNTESTED",
      "investigation_status": "ELIGIBLE"
    }
  ],
  "next_tests": [
    {
      "test": "",
      "diagnostic_value": "",
      "required_authority": ""
    }
  ],
  "notes": []
}
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
        "version": "0.2.0",
        "node_id": NODE_ID,
        "role": "bounded_reasoning_node",
        "ollama": ollama,
        "model": MODEL,
        "cad_write_authority": "NONE",
        "mechanical_acceptance_authority": "NONE",
        "evidence_verification_authority": "NONE",
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

SUPPLIED EVIDENCE:
--- BEGIN EVIDENCE ---
{request.evidence}
--- END EVIDENCE ---

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
            "status": "REJECTED",
            "reason": type(exc).__name__,
        }

        append_log(failure_record)

        raise HTTPException(
            status_code=422,
            detail="Reasoning output failed deterministic validation.",
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
        "status": "ACCEPTED_ADVISORY",
        "authority": {
            "solidworks_geometry": "NONE",
            "cad_write": "NONE",
            "mechanical_acceptance": "NONE",
            "evidence_verification": "NONE",
        },
        "result": validated.model_dump(),
    })

    return result
