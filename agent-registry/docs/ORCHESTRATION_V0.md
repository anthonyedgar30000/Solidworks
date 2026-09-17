# CADGrounded Orchestration v0

This module adds a coordination plane above the existing read-only CAD registry and
Remote Queue. It does **not** enable any protected CAD write command.

## Purpose

The orchestration layer lets multiple independent ChatGPT chats, local workers, or
other agents share work through the registry instead of depending on one conversation
remaining open.

It provides:

- parent/child work items;
- worker classes;
- atomic claim-next semantics;
- expiring claims;
- fan-in release of a waiting parent after all children reach terminal states;
- exclusive resource leases with monotonically increasing fencing tokens;
- idempotency keys per workflow;
- audit events through the existing registry event stream.

## Worker classes

- `coordinator`
- `cad-evidence`
- `geometry`
- `reference-evidence`
- `visual-inspection`
- `cad-single-writer`

`cad-single-writer` is only an orchestration class. It does not grant CAD authority.
The existing registry command policy remains authoritative, and protected CAD commands
remain disabled until separately reviewed and enabled.

## Single-writer rule

A work item with a `resource_id` receives an exclusive lease when it is atomically
claimed. The lease contains a monotonically increasing `fence_token`.

A result for a leased item is accepted only when:

1. the claim is still current;
2. the reporting agent owns the claim;
3. the claim token matches;
4. the fence token matches; and
5. the resource lease is still active and owned by the same item/agent.

For CAD mutation coordination, use:

`resource_id = "solidworks.mutate"`

This protects the orchestration path from concurrent writers. It does not bypass the
SOLIDWORKS bridge write gate.

## Fan-out / fan-in

Create a parent coordinator item in `waiting`, then create child items whose
`parent_item_id` references it. When the last child reaches one of these terminal
states, the parent is automatically released to `queued`:

- `completed`
- `failed`
- `unresolved`
- `blocked`
- `cancelled`

That lets a coordinator synthesize all evidence after parallel workers finish.

## API

Key endpoints:

- `GET /orchestration/health`
- `POST /workflows`
- `GET /workflows`
- `GET /workflows/{workflow_id}`
- `POST /workflows/{workflow_id}/items`
- `GET /work-items/{item_id}`
- `POST /work-items/claim-next`
- `POST /work-items/{item_id}/result`
- `GET /orchestration/leases`

## Authority boundary

- SOLIDWORKS remains live geometry/state authority.
- Git remains source/history authority.
- Google Drive remains transport/reference/archive.
- Remote Queue remains a governed read-only CAD evidence plane.
- Orchestration coordinates work; it does not turn evidence into mechanical acceptance
  and does not grant write authority.
