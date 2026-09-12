from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
RUNTIME_DIR = ROOT_DIR / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("CAD_REGISTRY_DB", str(RUNTIME_DIR / "registry.db")))

app = FastAPI(
    title="CADGrounded Shared Agent Registry",
    version="0.1.0",
    description="Local coordination plane for ChatGPT, local LLMs, humans, and the SOLIDWORKS bridge.",
)

READ_COMMANDS = {
    "sw.status": ("READ", 1),
    "sw.query_components": ("READ", 1),
}
PROTECTED_COMMANDS = {
    "sw.set_transform": ("WRITE_SAFE", 0),
    "sw.insert_component": ("WRITE_SAFE", 0),
    "sw.execute_code": ("EXEC_PRIVILEGED", 0),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA synchronous = NORMAL")
    return c


def emit(c: sqlite3.Connection, event_type: str, actor_id: str | None, data: dict[str, Any]) -> None:
    c.execute(
        "INSERT INTO events(ts, event_type, actor_id, data_json) VALUES (?, ?, ?, ?)",
        (utc_now(), event_type, actor_id, json.dumps(data, separators=(",", ":"))),
    )


def init_db() -> None:
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                last_seen TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'online'
            );

            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY,
                risk TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                revision INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                command_id TEXT NOT NULL REFERENCES commands(id),
                document_id TEXT NULL REFERENCES documents(id),
                agent_id TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                state TEXT NOT NULL,
                expected_revision INTEGER NULL,
                idempotency_key TEXT NULL UNIQUE,
                claimed_by TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result_json TEXT NULL,
                error_text TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT NULL,
                data_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
            """
        )

        for command_id, (risk, enabled) in {**READ_COMMANDS, **PROTECTED_COMMANDS}.items():
            c.execute(
                """
                INSERT INTO commands(id, risk, enabled, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    risk=excluded.risk,
                    enabled=excluded.enabled
                """,
                (command_id, risk, enabled, "Seeded by registry bootstrap"),
            )


@app.on_event("startup")
def startup() -> None:
    init_db()


class AgentHeartbeat(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    role: Literal["human", "planner", "executor", "reviewer", "bridge"]
    capabilities: list[str] = Field(default_factory=list)


class DocumentCreate(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1)
    status: str = "active"


class JobCreate(BaseModel):
    command_id: str
    agent_id: str
    document_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int | None = None
    idempotency_key: str | None = None


class JobClaim(BaseModel):
    bridge_agent_id: str


class JobResult(BaseModel):
    bridge_agent_id: str
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    with conn() as c:
        c.execute("SELECT 1").fetchone()
    return {
        "ok": True,
        "service": "cad-agent-registry",
        "mode": "read-only-bootstrap",
        "db": str(DB_PATH),
        "time": utc_now(),
    }


@app.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT id, role, capabilities_json, last_seen, status FROM agents ORDER BY id"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "role": r["role"],
            "capabilities": json.loads(r["capabilities_json"]),
            "last_seen": r["last_seen"],
            "status": r["status"],
        }
        for r in rows
    ]


@app.post("/agents/heartbeat")
def heartbeat(body: AgentHeartbeat) -> dict[str, Any]:
    now = utc_now()
    with conn() as c:
        c.execute(
            """
            INSERT INTO agents(id, role, capabilities_json, last_seen, status)
            VALUES (?, ?, ?, ?, 'online')
            ON CONFLICT(id) DO UPDATE SET
                role=excluded.role,
                capabilities_json=excluded.capabilities_json,
                last_seen=excluded.last_seen,
                status='online'
            """,
            (body.id, body.role, json.dumps(body.capabilities), now),
        )
        emit(c, "agent.heartbeat", body.id, {"role": body.role})
    return {"ok": True, "agent_id": body.id, "last_seen": now}


@app.get("/commands")
def list_commands() -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT id, risk, enabled, description FROM commands ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/documents")
def list_documents() -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT id, title, path, revision, status, updated_at FROM documents ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/documents")
def create_document(body: DocumentCreate) -> dict[str, Any]:
    now = utc_now()
    with conn() as c:
        existing = c.execute("SELECT * FROM documents WHERE id = ?", (body.id,)).fetchone()
        if existing:
            return dict(existing)
        c.execute(
            """
            INSERT INTO documents(id, title, path, revision, status, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (body.id, body.title, body.path, body.status, now),
        )
        emit(c, "document.created", "api", {"document_id": body.id, "path": body.path})
        row = c.execute("SELECT * FROM documents WHERE id = ?", (body.id,)).fetchone()
    return dict(row)


@app.get("/jobs")
def list_jobs(state: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    sql = """
        SELECT id, command_id, document_id, agent_id, payload_json, state,
               expected_revision, idempotency_key, claimed_by, created_at,
               updated_at, result_json, error_text
        FROM jobs
    """
    params: list[Any] = []
    if state:
        sql += " WHERE state = ?"
        params.append(state)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with conn() as c:
        rows = c.execute(sql, params).fetchall()

    out = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item.pop("payload_json"))
        item["result"] = json.loads(item["result_json"]) if item["result_json"] else None
        item.pop("result_json")
        out.append(item)
    return out


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not r:
        raise HTTPException(404, "job not found")
    item = dict(r)
    item["payload"] = json.loads(item.pop("payload_json"))
    item["result"] = json.loads(item["result_json"]) if item["result_json"] else None
    item.pop("result_json")
    return item


@app.post("/jobs")
def create_job(body: JobCreate) -> dict[str, Any]:
    now = utc_now()
    with conn() as c:
        command = c.execute(
            "SELECT id, risk, enabled FROM commands WHERE id = ?", (body.command_id,)
        ).fetchone()

        if not command:
            raise HTTPException(404, "unknown command")

        if command["enabled"] != 1 or command["risk"] != "READ":
            raise HTTPException(
                403,
                "bootstrap registry only accepts enabled READ commands",
            )

        agent = c.execute("SELECT id FROM agents WHERE id = ?", (body.agent_id,)).fetchone()
        if not agent:
            raise HTTPException(400, "agent must heartbeat/register before creating jobs")

        if body.document_id:
            doc = c.execute(
                "SELECT id, revision FROM documents WHERE id = ?", (body.document_id,)
            ).fetchone()
            if not doc:
                raise HTTPException(404, "document not found")
            if body.expected_revision is not None and body.expected_revision != doc["revision"]:
                raise HTTPException(409, "STALE_REVISION")

        if body.idempotency_key:
            prior = c.execute(
                "SELECT id FROM jobs WHERE idempotency_key = ?", (body.idempotency_key,)
            ).fetchone()
            if prior:
                return get_job(prior["id"])

        job_id = str(uuid.uuid4())
        c.execute(
            """
            INSERT INTO jobs(
                id, command_id, document_id, agent_id, payload_json, state,
                expected_revision, idempotency_key, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (
                job_id,
                body.command_id,
                body.document_id,
                body.agent_id,
                json.dumps(body.payload, separators=(",", ":")),
                body.expected_revision,
                body.idempotency_key,
                now,
                now,
            ),
        )
        emit(
            c,
            "job.queued",
            body.agent_id,
            {"job_id": job_id, "command_id": body.command_id},
        )
    return get_job(job_id)


@app.post("/jobs/{job_id}/claim")
def claim_job(job_id: str, body: JobClaim) -> dict[str, Any]:
    now = utc_now()
    with conn() as c:
        bridge = c.execute(
            "SELECT role FROM agents WHERE id = ?", (body.bridge_agent_id,)
        ).fetchone()
        if not bridge or bridge["role"] != "bridge":
            raise HTTPException(403, "claiming agent must be registered as role=bridge")

        r = c.execute("SELECT state FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not r:
            raise HTTPException(404, "job not found")
        if r["state"] != "queued":
            raise HTTPException(409, f"job is already {r['state']}")

        updated = c.execute(
            """
            UPDATE jobs
            SET state='running', claimed_by=?, updated_at=?
            WHERE id=? AND state='queued'
            """,
            (body.bridge_agent_id, now, job_id),
        )
        if updated.rowcount != 1:
            raise HTTPException(409, "job claim lost to another worker")

        emit(
            c,
            "job.claimed",
            body.bridge_agent_id,
            {"job_id": job_id},
        )
    return get_job(job_id)


@app.post("/jobs/{job_id}/result")
def finish_job(job_id: str, body: JobResult) -> dict[str, Any]:
    now = utc_now()
    with conn() as c:
        r = c.execute(
            "SELECT state, claimed_by FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not r:
            raise HTTPException(404, "job not found")
        if r["state"] != "running":
            raise HTTPException(409, "job is not running")
        if r["claimed_by"] != body.bridge_agent_id:
            raise HTTPException(403, "job is owned by another bridge")

        state = "completed" if body.success else "failed"
        c.execute(
            """
            UPDATE jobs
            SET state=?, updated_at=?, result_json=?, error_text=?
            WHERE id=?
            """,
            (
                state,
                now,
                json.dumps(body.output, separators=(",", ":")),
                body.error,
                job_id,
            ),
        )
        emit(
            c,
            f"job.{state}",
            body.bridge_agent_id,
            {"job_id": job_id},
        )
    return get_job(job_id)


@app.get("/events")
def list_events(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, ts, event_type, actor_id, data_json
            FROM events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "ts": r["ts"],
            "event_type": r["event_type"],
            "actor_id": r["actor_id"],
            "data": json.loads(r["data_json"]),
        }
        for r in rows
    ]
