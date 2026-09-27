# CADGrounded — CURRENT LIVE CAD POINTER

**Purpose:** search-first freshness pointer for new chats and handoffs.

**Latest successful live verification:** 2026-09-27T23:35Z

## Current SOLIDWORKS status

Bridge: `0.3.0`

Source classification: `verified_from_solidworks_api`

**Active document: NONE / null**

There is currently no active SOLIDWORKS document bound to the bridge.

## Last active document observed during this sync

Earlier in the same synchronization cycle, SOLIDWORKS exposed:

`IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE`

Path:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE.SLDASM`

Configuration: `Default`

Observed save flag: `true`

That v27 state is **not current now**. Because the document was dirty, do not assume its unsaved geometry was persisted.

## GitHub project-state cross-reference

GitHub `CURRENT_PLAN.json` remains the durable v43 PLAN-0011 investigation state:

`ACTIVE_INVESTIGATION_V43_DUAL_PIVOT_PATH_DISPROVEN_NEXT_ARCHITECTURE_REQUIRED`

So at the latest read:

- **live CAD = no active document**
- **durable project investigation = v43 PLAN-0011**

Before any v43-specific CAD operation, open/activate the exact v43 assembly and perform a fresh live rebind.

Read `CURRENT_PROJECT_STATE.md` for the full synchronized handoff.

## Mechanical acceptance

**FALSE.**

API success, a stored project plan, or a historical active-document observation does not grant mechanical acceptance.
