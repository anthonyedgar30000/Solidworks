# IXOR Benchmark v41 — Hybrid Sensor/Timer Control-State Model (Draft)

## Status

**Draft engineering reasoning artifact. Not mechanical acceptance. Not a PLC implementation.**

This document translates the current v41 benchmark concept into explicit control states so that timer-based behavior can be separated from states that should be observed directly.

Evidence boundary:

- SOLIDWORKS remains geometry authority.
- The live assembly observed immediately before this draft was `IXOR_Benchmark_v41_MAX_ROLLER2_COMPLIANCE_REFERENCE_PORTABLE`.
- That snapshot contained the IXOR head, SP100, conveyor, bottles, driven wrap belt, two wrap-support rollers, two index-stop fingers, and reference label-wrap facets.
- A fresh SOLIDWORKS read was unavailable while this draft was written because the CAD connector returned a session-level developer-MCP availability error. Therefore this document does **not** claim any new live geometry facts beyond the immediately preceding verified v41 snapshot.
- GitHub contains CAB source assets including a forked light barrier (`5918670_04`) and rotary encoder (`5918979_01`).
- The CAB IXOR+ assembly instructions expose optional CEON/forked sensors, start/stop delay controls, START/I/O/SYNC/APPLY/STOP interfaces, an external start-sensor example, PLC connection/control examples, and an I/O signal diagram.

## Design Principle

**Observed state should gate irreversible or product-sensitive transitions. Timers should control bounded motion after a valid state has been established.**

A timer may answer:

> How long should this already-authorized motion continue?

A timer should not be the only answer to:

> Is the bottle actually here?
> Is the station actually clear?
> Is a label available/present?
> Did the product actually leave?

This retains a low-cost control architecture without turning elapsed time into a substitute for machine state.

## Proposed State Machine

### S0 — READY_IDLE

Known/required conditions:

- labeling head ready;
- no active fault;
- application station available;
- index stop in its safe/ready condition;
- downstream release path not known blocked.

Exit condition:

- product approach is observed.

Preferred evidence:

- product/start sensor.

Timer-only transition: **NO**.

---

### S1 — PRODUCT_APPROACH

Intent:

- admit one product into the indexed application cycle.

Actions that may be timed:

- stop-finger actuation lead time;
- small conveyor/indexing offsets after an observed trigger;
- debounce/filter delay.

Exit condition:

- product is established at the application station.

Preferred evidence:

- dedicated indexed-position sensor, OR
- product sensor geometry arranged so its asserted state corresponds deterministically to the indexed bottle location.

Timer-only transition: **NOT PREFERRED**.

Reason:

Bottle spacing, belt slip, conveyor speed, product diameter, or pneumatic timing can all invalidate a pure elapsed-time assumption.

---

### S2 — PRODUCT_INDEXED

Intent:

- establish the bottle as the active product instance before label presentation/wrap.

Required invariant:

- exactly one intended bottle occupies the application station.

Additional checks:

- upstream product cannot collide with the active cycle;
- bottle restraint/support geometry is valid for the intended product.

Exit condition:

- label lead/presentation is ready and application can begin.

Timer-only transition: **NO** for product occupancy.

---

### S3 — LABEL_READY / LEAD_PRESENTED

Intent:

- establish that usable label media is available at the presentation/application boundary.

Preferred evidence:

- IXOR internal label sensing and/or CAB CEON/forked light-barrier sensing where applicable.

Actions that may be timed:

- commanded feed distance translated into bounded servo/drive motion;
- settling time after feed;
- small mechanical presentation delay.

Exit condition:

- application contact/wrap action is authorized.

Timer-only transition: **NO** if a missing/misfed label would cause a bad product or adhesive/web fault.

---

### S4 — APPLICATION_CONTACT_READY

Intent:

- establish the mechanically intended relation between bottle, presented label, and wrap mechanism.

Current v41 relevance:

- driven wrap belt and support-roller geometry exist in the benchmark;
- current geometry must still be treated as a fit/reference concept unless separately proven mechanically.

Preferred evidence for a production machine:

- inexpensive actuator-end confirmation (reed/prox/limit) where an actuated mechanism establishes contact; OR
- a deterministic hard-stop geometry plus validated actuation window if adding feedback is not justified.

Timer-only transition: **CONDITIONAL**.

A timer can be acceptable here only after mechanical hard-stop behavior, pneumatic/actuator tolerance, and product variation are bounded.

---

### S5 — WRAP_ACTIVE

Intent:

- rotate/translate the bottle relative to the label so the label is wrapped around the cylindrical product.

Primary actuator concept:

- driven wrap belt / driven contact surface;
- support rollers constrain the bottle and provide reaction geometry.

Possible control strategies, cheapest first:

1. fixed-speed drive + calibrated wrap time;
2. fixed-speed drive + encoder count;
3. closed-loop rotation/travel using encoder feedback.

Timer-only transition: **POSSIBLE**, but only if product diameter, traction, belt compliance, wrap speed, and slip are bounded tightly enough.

A timer confirms commanded duration, not completed bottle rotation.

Preferred upgrade path:

- use encoder counts to make wrap completion a measured motion quantity;
- if the encoder measures conveyor/web motion rather than bottle rotation, keep that authority distinction explicit.

---

### S6 — WRAP_COMPLETE

Intent:

- establish that the required wrap motion has completed before releasing the indexed product.

Evidence hierarchy:

1. direct measured bottle/wrap motion;
2. encoder-derived motion on a mechanically coupled drive with validated no-slip assumptions;
3. calibrated timed motion with bounded product/traction envelope.

Timer-only transition: **ACCEPTABLE ONLY AS A VALIDATED LOW-COST MODE**.

Failure mode to detect/document:

- drive commanded for full duration while bottle slips or stalls.

---

### S7 — RELEASE

Intent:

- withdraw/release the indexing mechanism and allow the labeled bottle to leave.

Actions that may be timed:

- stop-finger retract duration;
- small post-wrap dwell;
- restart delay.

Exit condition:

- station becomes clear.

Timer-only transition: **NO** for station-clear if another cycle can start immediately behind it.

---

### S8 — EXIT_CLEAR

Intent:

- prove the previous product has cleared the controlled application envelope before re-arming.

Preferred evidence:

- exit-clear sensor, or
- reuse of a correctly positioned product sensor if its clear transition deterministically proves station vacancy.

Timer-only transition: **NOT PREFERRED**.

Return:

- `S8 -> S0` when station is clear and no fault is active.

---

## Fault / Hold State

Any critical expected state that does not arrive within its watchdog window should enter an explicit hold/fault state instead of silently continuing the timer chain.

Examples:

- product trigger received but index confirmation never appears;
- product indexed but label-ready condition is absent;
- wrap commanded but measured motion is below threshold;
- release commanded but station never becomes clear;
- contradictory sensors indicate two products or a jam.

A watchdog timer is appropriate here because it proves a state transition **failed to occur within a bounded time**; it does not pretend the state occurred.

## Minimum Sensor Architecture

### Absolute minimum practical architecture

1. **Product/start sensor** — establishes arrival and cycle ownership.
2. **Existing label-media/edge sensing** — establishes label readiness/presentation using the IXOR/CAB sensing chain.

This can support a cheap indexed machine if application contact, wrap completion, and release are validated deterministic mechanisms with bounded timed motion.

### Recommended low-cost robust architecture

1. product/start sensor;
2. indexed-position confirmation (can potentially be the same product sensor if geometry makes that unambiguous);
3. label-ready/label-edge sensing;
4. wrap-motion feedback (encoder if mechanically meaningful to bottle rotation/travel);
5. station-clear/exit confirmation (can potentially reuse another sensor depending on geometry).

The goal is **not five sensors by default**. The goal is five observables. One physical sensor may establish more than one observable if its geometry and transition semantics are deterministic.

## Timer-Safe vs State-Critical Table

| Transition / action | Timer suitable? | State observation preferred? | Reason |
|---|---:|---:|---|
| debounce product sensor | Yes | Trigger already observed | Bounded filtering action |
| delay from observed approach to stop actuation | Yes | Yes | Timer refines known product arrival |
| infer bottle arrival from conveyor run time alone | No | Yes | Speed/slip/spacing variation |
| label feed after valid command | Yes, bounded | Yes for final readiness | Feed duration is not label-presence proof |
| actuator settling/contact delay | Yes, conditional | Prefer end confirmation | Pneumatic/mechanical variation |
| bottle wrap duration | Yes, conditional | Encoder preferred | Slip makes time != rotation |
| stop-finger retract duration | Yes | Station-clear still preferred | Retraction command != clear station |
| fault watchdog | Yes | Yes | Timer proves missing state, not achieved state |

## Why this matters for the benchmark

This creates a clean deterministic boundary between:

- **machine state** — facts that should be observed or mechanically proven;
- **motion timing** — bounded execution intervals after authority exists;
- **fault detection** — watchdogs around expected state transitions;
- **AI reasoning** — allowed to diagnose/explain/select tests, but not invent state or bypass transition authority.

That separation directly supports the project-health graph concept already in `agent-registry/reasoning`: unknown state should remain explicit and downstream obligations should remain exposed until evidence resolves it.

## New v41 Acceptance Questions

The next deterministic investigations should answer these questions in order:

1. **APPLICATION_STATION_PRODUCT_IDENTITY** — which exact bottle instance is the active indexed product in v41?
2. **INDEX_STOP_CONTACT_GEOMETRY** — do the stop fingers actually establish the intended product position without interference?
3. **WRAP_SUPPORT_CONTACT_GEOMETRY** — do the driven belt and support rollers constrain the bottle with mechanically plausible contact?
4. **LABEL_LEAD_RELATION** — does the presented label lead intersect the intended bottle/contact envelope correctly?
5. **RELEASE_PATH_CLEARANCE** — can the bottle leave after the stop retracts without colliding with the labeling head, support geometry, or next bottle?
6. **SENSOR_OBSERVABILITY_MAP** — for each required state, identify the cheapest physical sensor or existing IXOR signal that can establish it.
7. **WRAP_COMPLETION_AUTHORITY** — determine whether completion can be accepted by validated time, encoder count, or another measured quantity.

## Proposed Graph Nodes

These are candidates for a v41 runtime epistemic graph. Do not mark them `KNOWN` until supported by admitted evidence or accepted deterministic derivation.

```text
PRODUCT_APPROACH_OBSERVED
PRODUCT_INDEXED
LABEL_READY
APPLICATION_CONTACT_READY
WRAP_MOTION_COMMANDABLE
WRAP_MOTION_OBSERVED
WRAP_COMPLETE
INDEX_STOP_RETRACTED
APPLICATION_STATION_CLEAR
NEXT_PRODUCT_ADMISSIBLE
```

Suggested obligations:

```text
VALID_INDEXED_CYCLE
VALID_APPLICATION_GEOMETRY
VALID_WRAP_GEOMETRY
VALID_RELEASE_GEOMETRY
NO_DOUBLE_FEED
NO_PRODUCT_HEAD_INTERFERENCE
NO_STOP_FINGER_INTERFERENCE
WRAP_COMPLETION_DETECTABLE
FAULT_STATE_DIAGNOSABLE
```

## Evidence Policy

A successful actuator command must never automatically set the corresponding physical state to true.

Examples:

```text
STOP_FINGER_COMMAND = EXTEND
```

does not imply:

```text
PRODUCT_INDEXED = TRUE
```

and:

```text
WRAP_DRIVE_COMMAND = RUN 900 ms
```

does not imply:

```text
WRAP_COMPLETE = TRUE
```

unless a validated deterministic model explicitly grants that derivation for the bounded product/configuration envelope.

That is the same epistemic boundary already used elsewhere in the project: command success, API success, and elapsed time are evidence about **commands and time**, not automatically about mechanical truth.
