# CADGrounded Shared Agent Registry v1

The shared agent registry coordinates ChatGPT, local LLM agents, human operators, and SOLIDWORKS execution bridges without replacing SOLIDWORKS as the geometry authority.

## Authority model

1. **SOLIDWORKS** is authoritative for actual CAD geometry and live document state.
2. **SQLite registry** is authoritative for live coordination state: jobs, revisions, leases, locks, heartbeats, and audit events.
3. **GitHub** is authoritative for versioned command definitions, schemas, policy, implementation source, tests, and durable engineering intent.
4. **Google Drive** is a project mirror / document backup surface, not a lock server or transaction coordinator.

## v1 safety invariants

- Every write requires the expected document revision.
- Every write requires a valid write lease and fencing token.
- Timed-out or failed writes require a live state reread before retry.
- Write jobs use idempotency keys so retries cannot silently duplicate work.
- Versioned CAD baselines are immutable unless explicitly authorized.
- Execution success is not mechanical verification.
- Raw arbitrary-code execution is privileged and is not granted to normal executor agents.
- Every accepted write produces an auditable state transition.
- Manual/out-of-band SOLIDWORKS edits must invalidate or advance registry state before further writes are accepted.

## Initial rollout

The first vertical slice is deliberately read-only:

- `sw.status`
- `sw.query_components`

After the registry can reliably identify the active document and current component state, the first protected write will be `sw.set_transform` with revision, lease/fencing, and component compare-and-set guards.

## Repository layout

```text
agent-registry/
  commands/      versioned command definitions
  policies/      role/capability and CAD safety policy
  schemas/       JSON schemas for registry entities
  docs/          architecture and protocol notes
  runtime/       local SQLite/log state (ignored by Git)
```

## Transport independence

MCP, local REST, CLI, PowerShell, and local LLMs are adapters. They produce the same internal job contract. The registry does not treat MCP as the architecture itself.

## Current IXOR integration boundary

The registry must store both a logical `document_id` and the exact live SOLIDWORKS path. Repository paths, Drive mirror paths, and live CAD paths are related provenance records but are never assumed to be interchangeable.
