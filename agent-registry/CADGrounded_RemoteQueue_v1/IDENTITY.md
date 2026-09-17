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

Current v1 read commands:

- `sw.status`
- `sw.query_components`
- `sw.closest_distance_pair`

## Authority boundary

- **SOLIDWORKS** = live geometry and current assembly-state authority.
- **GitHub** = versioned source, policy, implementation, history, and durable handoff authority.
- **Google Drive** = transport / mirror / reference / archive surface.
- Queue results are evidence; API success is not mechanical acceptance.

## Freshness rule

A saved reality-sync or handoff document must never override a newer successful live SOLIDWORKS read.

As of the live verification on **2026-09-17**, the active SOLIDWORKS document was:

`IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE`

Therefore older v21 reality-sync markdowns remain historical evidence but are stale as statements of the current live CAD checkpoint.

## Short form

> **CADGrounded Remote Queue v1**  
> **A governed, read-only CAD evidence pipeline.**
