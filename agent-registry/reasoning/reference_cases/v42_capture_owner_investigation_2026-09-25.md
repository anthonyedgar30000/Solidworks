# v42 `CAPTURE_AND_ROTATION` capture-owner investigation — 2026-09-25

## Decision status

`CAPTURE_AND_ROTATION` is **EXPOSED**. Its physical capture owner,
compliance/preload, required contact, restraint, reaction-force path, and
reachable-motion clearance remain **UNRESOLVED**. This is not a failure claim
and is not mechanical acceptance.

The only current live authority used here was a read-only SOLIDWORKS status and
full component inventory. No SOLIDWORKS transform, mate, feature, suppression,
save, rebuild, insertion, or geometry change was requested or performed.

## Fresh authority reconciliation

| Source | Fresh fact | Scope and limit |
| --- | --- | --- |
| GitHub `main` | Merge commit `fb93b243fc1a93e6e9fc759e12327cb2c30f8480` contains the current v42 functional-temporal capture-owner investigation. | Source, policy, test, and history authority; not live geometry authority. |
| SOLIDWORKS | At `2026-09-25T02:52:41.712318+00:00`, active assembly was exactly `IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE` at `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE.SLDASM`. | Live document/state identity only. |
| SOLIDWORKS | At `2026-09-25T02:58:42.924369+00:00`, read-only `sw.query_components` job `5bbec906-9bd2-4910-baf3-4da8644e405d` returned 55 nested components. | A point inventory; it does not establish physical DOF, capture, contact, preload, or reaction path. |
| SOLIDWORKS | Current-session read-only status plus full inventory again identified the same v42 assembly and 55 components, including the exact belt and both rollers as floating, unsuppressed parts. | Fresh point evidence only; `fixed:false` is not a physical-motion or capture-owner claim. |
| OEM catalog | CAB IXOR catalog, Status 05/2026, documents mechanism classes: demand-module guides/carriages, lever-mounted wipe-down rollers, spring preload adjustment, and distinct pneumatic variants. | Product-family engineering authority only; it does not bind those classes to the custom `FITCHECK` belt/rollers. |
| Project/Drive source audit | Exact-name Drive searches and the six unique uploaded September project documents supplied no v42 FITCHECK drawing, BOM, assembly, or owner binding beyond the historic capture note. | Search absence is not physical absence; historical v21/third-party pattern material is not current v42 binding evidence. |
| Historic v42 distances | The September 18 values (belt `0.329384717 mm`, support roller 2 `0.321626347 mm`) are preserved. | `STALE_STATE`, point-only, and not a current contact/capture conclusion. |

The current full inventory confirms these exact investigation identities:

| Role | Exact `Component2.Name2` | Fixed flag | Reported translation (mm) |
| --- | --- | --- | --- |
| Bottle | `BENCH_BOTTLE_D48_H180-2` | `true` | `[-153.75, -129, 950]` |
| Wrap belt | `FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1` | `false` | `[-126.92061528267112, -139, 995]` |
| Support roller 1 | `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1` | `false` | `[-178.66987158875423, -189, 995]` |
| Support roller 2 | `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2` | `false` | `[-193.071626347073, -129, 995]` |

The same inventory contains `SP100_6130656_NATIVE_PORTABLE_V17-1`, both
`6130648_01` / `6130649_01` carriages, and `6130460_03_AR60...`, but no
authoritative binding connects them to the named FITCHECK belt/rollers.
It also exposes no explicitly named roller carrier/slide, pivot arm, pneumatic
cylinder, spring/preload mechanism, or dedicated closure mount for those
exact FITCHECK components. Name-level absence is not absence proof; the
inventory did not expose parent hierarchy, features, mates, configuration
semantics, external assemblies, force, or DOF.

## Temporal operating model

| Phase | Model state | Required relation / invariant | Current state |
| --- | --- | --- | --- |
| Free approach | `ENTRY` | No capture is asserted. | UNRESOLVED as an operating sequence. |
| Capture beginning | `INDEXED` | Product arrives before capture is established. | UNRESOLVED. |
| Captured | `CAPTURE_AND_ROTATION` | Captured state contains label-transfer and wrap-rotation modes. | UNRESOLVED. |
| Label transfer | `LABEL_TRANSFER_INTERVAL` | Contained by captured state; overlaps wrap rotation when associated with a wrap operation. | UNRESOLVED. |
| Wrap rotation | `WRAP_ACTIVE` | Contained by captured state; no inference from static contact. | UNRESOLVED. |
| Release | `RELEASE` | May occur only after wrap completion and reachable-motion clearance. | UNRESOLVED. |
| Free exit | `EXIT_CLEAR` | Station clear before next-product admission. | UNRESOLVED. |

The following interval-wide invariants remain blocking requirements:

- bottle restraint remains valid through `CAPTURE_AND_ROTATION`,
  `LABEL_TRANSFER_INTERVAL`, and `WRAP_ACTIVE`;
- required wrap contact remains valid through the label-transfer/wrap interval;
- a valid reaction-force path runs through drive, support rollers, bottle, and
  mounting structure; and
- clearance/interference holds over the reachable capture/release motion set,
  not one static pose.

## Ranked capture-owner hypotheses

The rank is investigation priority, not probability or verification.

| Rank | Hypothesis | Prior | Evidence | Investigation state | Exact evidence required | Main downstream effects |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Moving wrap-belt assembly | COMMON | UNRESOLVED | ACTIVE | Bind the named belt to its carrier/actuator, controlled motion, limits, drive relationship, and reaction mount. | Owner, restraint, contact, reaction path, clearance; captured through release. |
| 2 | Translating roller carrier or slide | COMMON | UNRESOLVED | ACTIVE | Bind a named FITCHECK roller to a translating carrier, including travel limits, closure input, and reaction mount. | Owner, restraint, reaction path, clearance; capture beginning through release. |
| 3 | Pivoting roller arm or carrier | COMMON | UNRESOLVED | ACTIVE | Identify pivot axis, angular limits, linkage to a named roller, closure force source, and reaction path. | Owner, restraint, reaction path, clearance; capture beginning through release. |
| 4 | Spring/compliant preload mechanism | COMMON | UNRESOLVED | ACTIVE | Identify exact compliant element, preload/force range, usable travel, retention, and reaction path in the v42 FITCHECK station. | Restraint, contact, reaction path; captured through wrap. |
| 5 | Pneumatic capture actuator | UNCOMMON | WEAKENED | ELIGIBLE | Bind exact cylinder/actuator, rod, stroke, force, valve/control relation, and attachment to a named FITCHECK component. | Owner, restraint, reaction path; capture beginning through wrap. |
| 6 | Other explicit closure mechanism | UNCOMMON | UNRESOLVED | ACTIVE | Identify mechanism input, constrained motion/force path, limits, FITCHECK interface, and affected reachable states. | Owner, restraint, reaction path, clearance; capture beginning through release. |

`H_CAPTURE_CLOSURE_OWNER`, `H_CAPTURE_COMPLIANCE_OR_PRELOAD`, and
`H_UNBOUND_NESTED_OR_EXTERNAL_CAPTURE_MECHANISM` remain active aggregate
hypotheses. `H_STATIC_FIT_IS_SUFFICIENT_FOR_CAPTURE` remains disproven as a
methodological claim: static geometry, a mate, zero distance, or a locally
passing subsystem cannot establish interval-wide or whole-machine acceptance.

The pneumatic hypothesis is weakened—not disproven—because the fresh name-level
inventory lacks a named pneumatic/cylinder component and the current SP100
identity corresponds to the regular SP 100/60L product class, while the OEM
catalog's pneumatic variants are separate classes. Hidden feature/configuration
or external-boundary evidence could still resolve it differently.

## Interfaces and blockers

| Interface / guard | Current state | Why it is blocked |
| --- | --- | --- |
| `TRANSPORT_TO_CAPTURE` | EXPOSED | Product position/index sequence is not verified. |
| `CAPTURE_TO_LABEL` | EXPOSED | Owner, interval restraint/contact, reaction path, and capture-phase containment are unresolved. |
| `LABEL_TO_CAPTURE` | EXPOSED | Label-transfer relation is not verified during its required interval. |
| `CAPTURE_TO_RELEASE` | EXPOSED | Reachable-motion clearance and restraint through release are unresolved. |
| `GUARD_CAPTURE_KINEMATICS` | UNRESOLVED | No authoritative closure/DOF, force/reaction, or motion-envelope binding exists. |

Consequently, `INDEXED_TO_CAPTURE`, `CAPTURE_TO_RELEASE`, and the overall
temporal coherence remain **EXPOSED**. A locally verified future requirement
would still not grant machine-level mechanical acceptance.

## Highest-information next test

`TEST_CAPTURE_KINEMATIC_OWNER` is ranked first by the declared deterministic
formula (current value `30.87`). It requires one of the following before any
further dynamic conclusion:

1. an OEM assembly/BOM/manual identity map that binds the exact FITCHECK belt
   and both rollers to their parent/closure mechanism; or
2. the smallest current local-native candidate: one `sw.query_mates` read for
   each exact target, after the v0.3.1 pre/post no-mutation verification. It
   returns parent hierarchy and active-assembly mate/variation data, but does
   **not** by itself return force, preload, or intended operating motion.

This test has **no** `cad_request`. It has three explicitly local
`native_read_candidates`, each with `write_authority: NONE`,
`remote_queue_authorized: false`, and mandatory independent no-mutation
verification. The deployed Remote Queue still supports only `sw.status`,
`sw.query_components`, and `sw.closest_distance_pair`; no custom broad API call
should be repurposed to bypass that boundary.

The candidate contract is documented in
`agent-registry/docs/V42_CAPTURE_OWNER_BINDING_EVIDENCE_CONTRACT.md`. Until the
Windows/SOLIDWORKS host builds and runs it successfully, its state is
`CANDIDATE_UNVERIFIED`, not new live CAD evidence.

Until that binding is obtained, do not move parts to close the historic gaps,
and do not promote any capture, contact, clearance, or mechanical-acceptance
claim.
