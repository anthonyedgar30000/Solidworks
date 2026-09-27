# CADGrounded — CURRENT LIVE CAD POINTER

**Purpose:** search-first freshness pointer for new chats and handoffs.

**Last verified from live SOLIDWORKS API:** 2026-09-27

## Current active document

`IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`

Exact live path:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`

Source classification: `verified_from_solidworks_api`

A same-session top-level component read returned the same v43 document identity and v43 PRISM geometry, including:

- `FITCHECK_PRISM_REACTION_BASE_70x120x20_V43-1`
- `FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-1`
- `FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-2`
- `FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1`
- `FITCHECK_PRISM_ACTUATOR_ENVELOPE_45x35x35_V43-1`
- `FITCHECK_PRISM_LINK_15x10x25_V43-1`
- `FITCHECK_PRISM_LINK_15x10x25_V43-2`

## Freshness rule

**Do not treat v42 as current.**

v42 and earlier documents are historical observations unless a fresh live read returns them again.

For any new chat or handoff:

1. Prefer a fresh `sw.status` read.
2. If live CAD is unavailable, this file is the last verified live pointer.
3. Historical reality-sync files may supply evidence about their dated checkpoint but may not override this pointer.
4. A newer successful live SOLIDWORKS read supersedes this file immediately.
5. API success or an active-document name does **not** grant mechanical acceptance.

## Mechanical state

The active file name identifies v43 as an **OPERATING_CANDIDATE**. That is a lifecycle/candidate label only.

**Mechanical acceptance is not granted by this pointer.**

SOLIDWORKS remains live geometry/state authority. GitHub remains versioned source/history authority. Google Drive remains mirror/reference/transport.
