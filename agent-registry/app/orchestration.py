from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


TERMINAL_STATES = {"completed", "failed", "unresolved", "blocked", "cancelled"}
WORKER_CLASSES = {
    "coordinator",
    "cad-evidence",
    "geometry",
    "reference-evidence",
    "visual-inspection",
    "cad-single-writer",
}


class WorkflowCreate(BaseModel):
    workflow_id: str | None = Field(default=None, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    checkpoint_document_title: str = Field(min_length=1, max_length=512)
    checkpoint_document_path: str | None = Field(default=None, max_length=2048)
    created_by: str = Field(min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkItemCreate(BaseModel):
    item_id: str | None = Field(default=None, max_length=128)
    parent_item_id: str | None = Field(default=None, max_length=128)
    worker_class: Literal[
        "coordinator",
        "cad-evidence",
        "geometry",
        "reference-evidence",
        "visual-inspection",
        "cad-single-writer",
    ]
    work_type: str = Field(min_length=1, max_length=128)
    resource_id: str | None = Field(default=None, max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)
    state: Literal["queued", "waiting"] = "queued"
    priority: int = Field(default=0, ge=-1000, le=1000)
    idempotency_key: str | None = Field(default=None, max_length=256)


class ClaimNext(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    worker_classes: list[
        Literal[
            "coordinator",
            "cad-evidence",
            "geometry",
            "reference-evidence",
            "visual-inspection",
            "cad-single-writer",
        ]
    ] = Field(min_length=1)
    claim_seconds: int = Field(default=300, ge=30, le=3600)


class WorkItemResult(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    claim_token: str = Field(min_length=1, max_length=128)
    terminal_state: Literal["completed", "failed", "unresolved", "blocked", "cancelled"]
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    fence_token: int | None = Field(default=None, ge=1)


def _parse_json(value: str | None) -> Any:
    return json.loads(value) if value else None


def _row_to_workflow(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _parse_json(item.pop("metadata_json")) or {}
    return item


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = _parse_json(item.pop("payload_json")) or {}
    item["result"] = _parse_json(item.pop("result_json"))
    return item


def _utc_plus(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def register_orchestration(
    app: FastAPI,
    conn_factory: Callable[[], sqlite3.Connection],
    emit: Callable[[sqlite3.Connection, str, str | None, dict[str, Any]], None],
    utc_now: Callable[[], str],
) -> None:
    """Install additive orchestration routes without enabling any CAD write command."""

    def init_orchestration_db() -> None:
        with conn_factory() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    checkpoint_document_title TEXT NOT NULL,
                    checkpoint_document_path TEXT NULL,
                    state TEXT NOT NULL DEFAULT 'active',
                    created_by TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS work_items (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL REFERENCES workflows(id),
                    parent_item_id TEXT NULL REFERENCES work_items(id),
                    worker_class TEXT NOT NULL,
                    work_type TEXT NOT NULL,
                    resource_id TEXT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    state TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT NULL,
                    claimed_by TEXT NULL,
                    claim_token TEXT NULL,
                    claim_expires_at TEXT NULL,
                    lease_fence_token INTEGER NULL,
                    result_json TEXT NULL,
                    error_text TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(workflow_id, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS resource_fences (
                    resource_id TEXT PRIMARY KEY,
                    last_fence_token INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS resource_leases (
                    resource_id TEXT PRIMARY KEY,
                    holder_item_id TEXT NOT NULL REFERENCES work_items(id),
                    holder_agent_id TEXT NOT NULL,
                    fence_token INTEGER NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_work_items_workflow
                    ON work_items(workflow_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_work_items_claim
                    ON work_items(state, worker_class, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_work_items_parent
                    ON work_items(parent_item_id, state);
                """
            )

    @app.on_event("startup")
    def orchestration_startup() -> None:
        init_orchestration_db()

    @app.get("/orchestration/health")
    def orchestration_health() -> dict[str, Any]:
        init_orchestration_db()
        with conn_factory() as c:
            workflow_count = c.execute("SELECT COUNT(*) AS n FROM workflows").fetchone()["n"]
            queued_count = c.execute(
                "SELECT COUNT(*) AS n FROM work_items WHERE state='queued'"
            ).fetchone()["n"]
            running_count = c.execute(
                "SELECT COUNT(*) AS n FROM work_items WHERE state='running'"
            ).fetchone()["n"]
            lease_count = c.execute(
                "SELECT COUNT(*) AS n FROM resource_leases WHERE expires_at > ?",
                (utc_now(),),
            ).fetchone()["n"]
        return {
            "ok": True,
            "service": "cadgrounded-orchestration",
            "version": "0.1.0",
            "cad_write_commands_enabled": False,
            "workflow_count": workflow_count,
            "queued_count": queued_count,
            "running_count": running_count,
            "active_resource_leases": lease_count,
            "worker_classes": sorted(WORKER_CLASSES),
        }

    @app.post("/workflows")
    def create_workflow(body: WorkflowCreate) -> dict[str, Any]:
        init_orchestration_db()
        workflow_id = body.workflow_id or str(uuid.uuid4())
        now = utc_now()
        with conn_factory() as c:
            prior = c.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if prior:
                return _row_to_workflow(prior)
            c.execute(
                """
                INSERT INTO workflows(
                    id, project_id, checkpoint_document_title, checkpoint_document_path,
                    state, created_by, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    body.project_id,
                    body.checkpoint_document_title,
                    body.checkpoint_document_path,
                    body.created_by,
                    json.dumps(body.metadata, separators=(",", ":")),
                    now,
                    now,
                ),
            )
            emit(
                c,
                "workflow.created",
                body.created_by,
                {
                    "workflow_id": workflow_id,
                    "project_id": body.project_id,
                    "checkpoint_document_title": body.checkpoint_document_title,
                },
            )
            row = c.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        return _row_to_workflow(row)

    @app.get("/workflows")
    def list_workflows(limit: int = 100) -> list[dict[str, Any]]:
        init_orchestration_db()
        limit = max(1, min(limit, 500))
        with conn_factory() as c:
            rows = c.execute(
                "SELECT * FROM workflows ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_workflow(row) for row in rows]

    @app.get("/workflows/{workflow_id}")
    def get_workflow(workflow_id: str) -> dict[str, Any]:
        init_orchestration_db()
        with conn_factory() as c:
            workflow = c.execute(
                "SELECT * FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
            if not workflow:
                raise HTTPException(404, "workflow not found")
            rows = c.execute(
                """
                SELECT * FROM work_items
                WHERE workflow_id=?
                ORDER BY priority DESC, created_at ASC
                """,
                (workflow_id,),
            ).fetchall()
        items = [_row_to_item(row) for row in rows]
        counts: dict[str, int] = {}
        for item in items:
            counts[item["state"]] = counts.get(item["state"], 0) + 1
        terminal_count = sum(counts.get(s, 0) for s in TERMINAL_STATES)
        return {
            "workflow": _row_to_workflow(workflow),
            "summary": {
                "total_items": len(items),
                "terminal_items": terminal_count,
                "all_terminal": bool(items) and terminal_count == len(items),
                "states": counts,
            },
            "items": items,
        }

    @app.post("/workflows/{workflow_id}/items")
    def create_work_item(workflow_id: str, body: WorkItemCreate) -> dict[str, Any]:
        init_orchestration_db()
        item_id = body.item_id or str(uuid.uuid4())
        now = utc_now()
        with conn_factory() as c:
            workflow = c.execute(
                "SELECT id FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
            if not workflow:
                raise HTTPException(404, "workflow not found")

            if body.parent_item_id:
                parent = c.execute(
                    "SELECT workflow_id FROM work_items WHERE id=?",
                    (body.parent_item_id,),
                ).fetchone()
                if not parent:
                    raise HTTPException(404, "parent work item not found")
                if parent["workflow_id"] != workflow_id:
                    raise HTTPException(409, "parent belongs to another workflow")

            if body.idempotency_key:
                prior = c.execute(
                    """
                    SELECT * FROM work_items
                    WHERE workflow_id=? AND idempotency_key=?
                    """,
                    (workflow_id, body.idempotency_key),
                ).fetchone()
                if prior:
                    return _row_to_item(prior)

            if body.worker_class == "cad-single-writer" and not body.resource_id:
                raise HTTPException(
                    400, "cad-single-writer items require resource_id"
                )

            c.execute(
                """
                INSERT INTO work_items(
                    id, workflow_id, parent_item_id, worker_class, work_type,
                    resource_id, payload_json, state, priority, idempotency_key,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    workflow_id,
                    body.parent_item_id,
                    body.worker_class,
                    body.work_type,
                    body.resource_id,
                    json.dumps(body.payload, separators=(",", ":")),
                    body.state,
                    body.priority,
                    body.idempotency_key,
                    now,
                    now,
                ),
            )
            emit(
                c,
                "work_item.created",
                "api",
                {
                    "workflow_id": workflow_id,
                    "item_id": item_id,
                    "parent_item_id": body.parent_item_id,
                    "worker_class": body.worker_class,
                    "resource_id": body.resource_id,
                    "state": body.state,
                },
            )
            row = c.execute("SELECT * FROM work_items WHERE id=?", (item_id,)).fetchone()
        return _row_to_item(row)

    @app.get("/work-items/{item_id}")
    def get_work_item(item_id: str) -> dict[str, Any]:
        init_orchestration_db()
        with conn_factory() as c:
            row = c.execute("SELECT * FROM work_items WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise HTTPException(404, "work item not found")
        return _row_to_item(row)

    @app.get("/orchestration/leases")
    def list_resource_leases() -> list[dict[str, Any]]:
        init_orchestration_db()
        now = utc_now()
        with conn_factory() as c:
            c.execute("DELETE FROM resource_leases WHERE expires_at <= ?", (now,))
            rows = c.execute(
                """
                SELECT resource_id, holder_item_id, holder_agent_id,
                       fence_token, acquired_at, expires_at
                FROM resource_leases
                ORDER BY resource_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    @app.post("/work-items/claim-next")
    def claim_next(body: ClaimNext) -> dict[str, Any]:
        init_orchestration_db()
        now = utc_now()
        expires = _utc_plus(body.claim_seconds)
        claim_token = uuid.uuid4().hex

        c = conn_factory()
        try:
            c.isolation_level = None
            c.execute("BEGIN IMMEDIATE")

            c.execute("DELETE FROM resource_leases WHERE expires_at <= ?", (now,))

            stale = c.execute(
                """
                SELECT id, resource_id, lease_fence_token
                FROM work_items
                WHERE state='running'
                  AND claim_expires_at IS NOT NULL
                  AND claim_expires_at <= ?
                """,
                (now,),
            ).fetchall()
            for row in stale:
                if row["resource_id"] and row["lease_fence_token"]:
                    c.execute(
                        """
                        DELETE FROM resource_leases
                        WHERE resource_id=? AND holder_item_id=? AND fence_token=?
                        """,
                        (
                            row["resource_id"],
                            row["id"],
                            row["lease_fence_token"],
                        ),
                    )
                c.execute(
                    """
                    UPDATE work_items
                    SET state='queued', claimed_by=NULL, claim_token=NULL,
                        claim_expires_at=NULL, lease_fence_token=NULL, updated_at=?
                    WHERE id=? AND state='running'
                    """,
                    (now, row["id"]),
                )
                emit(c, "work_item.claim_expired", row["id"], {"item_id": row["id"]})

            placeholders = ",".join("?" for _ in body.worker_classes)
            candidates = c.execute(
                f"""
                SELECT * FROM work_items
                WHERE state='queued'
                  AND worker_class IN ({placeholders})
                ORDER BY priority DESC, created_at ASC
                LIMIT 50
                """,
                tuple(body.worker_classes),
            ).fetchall()

            selected = None
            fence_token = None
            for candidate in candidates:
                resource_id = candidate["resource_id"]
                if resource_id:
                    active = c.execute(
                        """
                        SELECT resource_id FROM resource_leases
                        WHERE resource_id=? AND expires_at > ?
                        """,
                        (resource_id, now),
                    ).fetchone()
                    if active:
                        continue

                    fence = c.execute(
                        "SELECT last_fence_token FROM resource_fences WHERE resource_id=?",
                        (resource_id,),
                    ).fetchone()
                    next_fence = (fence["last_fence_token"] if fence else 0) + 1
                    c.execute(
                        """
                        INSERT INTO resource_fences(resource_id, last_fence_token)
                        VALUES (?, ?)
                        ON CONFLICT(resource_id) DO UPDATE SET
                            last_fence_token=excluded.last_fence_token
                        """,
                        (resource_id, next_fence),
                    )
                    c.execute(
                        """
                        INSERT INTO resource_leases(
                            resource_id, holder_item_id, holder_agent_id,
                            fence_token, acquired_at, expires_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            resource_id,
                            candidate["id"],
                            body.agent_id,
                            next_fence,
                            now,
                            expires,
                        ),
                    )
                    fence_token = next_fence

                updated = c.execute(
                    """
                    UPDATE work_items
                    SET state='running', claimed_by=?, claim_token=?,
                        claim_expires_at=?, lease_fence_token=?, updated_at=?
                    WHERE id=? AND state='queued'
                    """,
                    (
                        body.agent_id,
                        claim_token,
                        expires,
                        fence_token,
                        now,
                        candidate["id"],
                    ),
                )
                if updated.rowcount == 1:
                    selected = c.execute(
                        "SELECT * FROM work_items WHERE id=?", (candidate["id"],)
                    ).fetchone()
                    emit(
                        c,
                        "work_item.claimed",
                        body.agent_id,
                        {
                            "item_id": candidate["id"],
                            "worker_class": candidate["worker_class"],
                            "resource_id": candidate["resource_id"],
                            "fence_token": fence_token,
                        },
                    )
                    break

                if resource_id and fence_token is not None:
                    c.execute(
                        """
                        DELETE FROM resource_leases
                        WHERE resource_id=? AND holder_item_id=? AND fence_token=?
                        """,
                        (resource_id, candidate["id"], fence_token),
                    )
                    fence_token = None

            c.execute("COMMIT")
        except Exception:
            try:
                c.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            c.close()

        if not selected:
            return {"claimed": False, "item": None}

        item = _row_to_item(selected)
        return {
            "claimed": True,
            "item": item,
            "claim": {
                "agent_id": body.agent_id,
                "claim_token": claim_token,
                "claim_expires_at": expires,
                "resource_id": item["resource_id"],
                "fence_token": item["lease_fence_token"],
            },
        }

    @app.post("/work-items/{item_id}/result")
    def finish_work_item(item_id: str, body: WorkItemResult) -> dict[str, Any]:
        init_orchestration_db()
        now = utc_now()
        with conn_factory() as c:
            row = c.execute("SELECT * FROM work_items WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise HTTPException(404, "work item not found")
            if row["state"] != "running":
                raise HTTPException(409, "work item is not running")
            if row["claimed_by"] != body.agent_id:
                raise HTTPException(403, "work item is owned by another agent")
            if row["claim_token"] != body.claim_token:
                raise HTTPException(403, "claim token mismatch")
            if row["claim_expires_at"] and row["claim_expires_at"] <= now:
                raise HTTPException(409, "claim expired")

            resource_id = row["resource_id"]
            stored_fence = row["lease_fence_token"]
            if resource_id:
                if body.fence_token is None or body.fence_token != stored_fence:
                    raise HTTPException(409, "fence token mismatch")
                lease = c.execute(
                    """
                    SELECT holder_item_id, holder_agent_id, fence_token, expires_at
                    FROM resource_leases WHERE resource_id=?
                    """,
                    (resource_id,),
                ).fetchone()
                if (
                    not lease
                    or lease["holder_item_id"] != item_id
                    or lease["holder_agent_id"] != body.agent_id
                    or lease["fence_token"] != stored_fence
                    or lease["expires_at"] <= now
                ):
                    raise HTTPException(409, "resource lease is no longer valid")

            c.execute(
                """
                UPDATE work_items
                SET state=?, result_json=?, error_text=?, claimed_by=NULL,
                    claim_token=NULL, claim_expires_at=NULL, updated_at=?
                WHERE id=?
                """,
                (
                    body.terminal_state,
                    json.dumps(body.output, separators=(",", ":")),
                    body.error,
                    now,
                    item_id,
                ),
            )

            if resource_id and stored_fence is not None:
                c.execute(
                    """
                    DELETE FROM resource_leases
                    WHERE resource_id=? AND holder_item_id=? AND fence_token=?
                    """,
                    (resource_id, item_id, stored_fence),
                )

            emit(
                c,
                f"work_item.{body.terminal_state}",
                body.agent_id,
                {
                    "item_id": item_id,
                    "workflow_id": row["workflow_id"],
                    "resource_id": resource_id,
                    "fence_token": stored_fence,
                },
            )

            parent_id = row["parent_item_id"]
            if parent_id:
                open_children = c.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM work_items
                    WHERE parent_item_id=?
                      AND state NOT IN ('completed','failed','unresolved','blocked','cancelled')
                    """,
                    (parent_id,),
                ).fetchone()["n"]
                if open_children == 0:
                    parent = c.execute(
                        "SELECT state FROM work_items WHERE id=?", (parent_id,)
                    ).fetchone()
                    if parent and parent["state"] == "waiting":
                        c.execute(
                            """
                            UPDATE work_items
                            SET state='queued', updated_at=?
                            WHERE id=? AND state='waiting'
                            """,
                            (now, parent_id),
                        )
                        emit(
                            c,
                            "work_item.fan_in_ready",
                            body.agent_id,
                            {"parent_item_id": parent_id},
                        )

            result_row = c.execute(
                "SELECT * FROM work_items WHERE id=?", (item_id,)
            ).fetchone()
        return _row_to_item(result_row)
