# CADGrounded Remote Queue v1

## Canonical identity

**CADGrounded Remote Queue v1 — a governed, read-only CAD evidence pipeline.**

This is the canonical label for the remote-queue infrastructure.

## Role in the larger system

- **CADGrounded** is the broader governed engineering / control architecture.
- **CADGrounded Remote Queue** is its remotely accessible **read / observe evidence plane**.
- It is **not** a remote CAD controller and does not grant CAD-write authority.

## Evidence path

```text
ChatGPT / operator
      |
      v
Google Drive transport
      |
      v
validated JSON remote queue
      |
      v
schema / policy / replay / exact-document preflight
      |
      v
native C# SOLIDWORKS worker
      |
      v
results / evidence / logs
```

## Governance properties

The v1 queue is intentionally narrow and read-only:

- declarative JSON jobs only
- hard local command allowlist
- schema and payload validation
- replay / duplicate protection
- expiry checks
- exact active-document preconditions
- required `write_authority: NONE`
- no downloaded `.ps1`, `.bat`, `.cmd`, or `.exe` execution
- native SOLIDWORKS worker remains the execution boundary

Current v1 read commands include:

- `sw.status`
- `sw.query_components`
- `sw.closest_distance_pair`
- `sw.capture_view`

## Authority boundary

- **SOLIDWORKS** = live geometry and current assembly-state authority.
- **GitHub** = versioned source, policy, implementation, history, and durable handoff authority.
- **Google Drive** = transport / mirror / reference / archive surface.
- Queue results are evidence; API success is not mechanical acceptance.

## Freshness rule — READ THIS BEFORE USING SAVED CHECKPOINTS

A saved reality-sync, handoff, memory, or historical evidence document must never override a newer successful live SOLIDWORKS read.

**Current live verification (2026-09-27, direct SOLIDWORKS API):**

`IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`

Path:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`

The live top-level component read also returned v43 PRISM components, including the PRISM reaction base, guide rails, carrier slider, actuator envelope, links, and arm geometry.

**v42 is historical, not the current live checkpoint.** Older v42 and v21 reality-sync/evidence documents remain valid only as dated historical observations. They must not be used to assert the current active SOLIDWORKS document.

For a new chat:

1. If live SOLIDWORKS access is available, run `sw.status` before asserting the current checkpoint.
2. If live SOLIDWORKS is unavailable, read repository root `CURRENT_LIVE_CAD.md` and describe it only as the **last verified live pointer**, not guaranteed current state.
3. Never infer mechanical acceptance from the checkpoint name or API success.

## Short form

> **CADGrounded Remote Queue v1**  
> **A governed, read-only CAD evidence pipeline.**
