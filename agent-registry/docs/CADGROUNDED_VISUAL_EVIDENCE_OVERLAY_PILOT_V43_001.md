# CADGrounded Visual Evidence Overlay — v43 Pilot Review 001

Date: 2026-09-27  
Assembly: `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`  
Configuration: `V43_WRAP`  
View: `V43-CAPTURE-003-FRONT`  
Geometry lifecycle state: `CANDIDATE_OPERATING`  
Mechanical acceptance: **FALSE**

## Purpose

Test whether a deterministic SOLIDWORKS capture plus a standardized semantic overlay materially improves bounded human/AI interpretation without converting unresolved mechanics into asserted facts.

This review is a visualization/interpretation result only. It is not geometry authority and does not grant mechanical acceptance.

## Source pair

- RAW: `V43-CAPTURE-003-FRONT_RAW.png`
- OVERLAY: `V43-CAPTURE-003-FRONT_OVERLAY.png`

The source CAD image is deterministic SOLIDWORKS output. The overlay is a semantic derivative.

## Bounded question

> Does the visible geometry clearly communicate the intended bottle capture/reaction arrangement while keeping unresolved motion, compliance, and force-path claims explicitly unresolved?

## Pilot result

**PASS — semantic interpretation improved.**

The overlay materially improves interpretation compared with the RAW image by making exact component identity and evidence state explicit while leaving mechanism behavior unresolved.

This PASS applies only to the overlay concept. It does **not** establish contact, preload, compliance, force magnitude, force path, timing, restraint sufficiency, motion sequence, or mechanical acceptance.

## What is recoverable from the RAW image alone

The RAW Front view shows a bottle cross-section, two smaller cylindrical elements, a narrow vertical element to the bottle side, and surrounding candidate capture/reaction structure.

However, from pixels alone the image does not reliably establish:

- exact `Component2.Name2` identity;
- which cylindrical item is support roller 1 versus support roller 2;
- whether apparent tangency is true B-rep contact versus projection coincidence;
- whether the PRISM structure moves, is compliant, is fixed, or only represents a fit-check pose;
- the reaction-force path;
- contact maintenance or preload;
- product-flow direction;
- hidden depth relationships.

## What the overlay adds

The overlay successfully exposes:

- `V-01` exact Bottle 2 identity;
- `V-02` exact driven wrap-belt identity;
- `V-03` and `V-04` exact support-roller identities;
- `V-05` the v43 PRISM reaction/capture region;
- `I-01` through `I-03` as **candidate interfaces only**;
- `U-01` capture-closure motion as unresolved;
- `U-02` compliance/preload as unresolved;
- `U-03` reaction-force path as unresolved;
- an explicit instruction not to infer hidden geometry, compliance, force magnitude, control timing, or unshown motion.

This separation is the principal value of the overlay.

## Visual observations

The Front view is useful for lateral-layout interpretation because Bottle 2 and the two support rollers are visually separable and the driven belt appears as a narrow vertical element adjacent to the bottle.

The same projection is **not suitable for mechanical acceptance of contact** because a 2D apparent tangent relationship may be caused by projection and does not establish 3D B-rep contact or trimmed-face overlap.

The PRISM region is visible but grouped too coarsely for mechanism-level interpretation. Individual PRISM members should be separately identified when their motion ownership, support role, or reaction path is under investigation.

## Overlay defects / refinements

1. Every `I-` marker should carry its evidence state inline, e.g. `I-01 CANDIDATE / UNRESOLVED`, because the word “interface” can otherwise be visually mistaken for verified contact.
2. Candidate-interface markers should remain hollow targets; verified contacts, if later admitted from exact CAD evidence, should use a visibly different symbol.
3. Add a world-coordinate triad and a separate `K-` product-flow arrow where the question involves motion or entry/exit.
4. Add exact individual PRISM `Name2` callouts instead of only a grouped `V-05` box when investigating kinematic ownership.
5. Record occlusion/view limitation explicitly. The Front view compresses depth and must not be used alone for contact acceptance.
6. Preserve paired RAW/OVERLAY images from the same camera for every governed review.

## Highest-value next deterministic test

The three lateral candidate interfaces should be checked by exact deterministic CAD evidence:

- Bottle 2 ↔ driven wrap belt
- Bottle 2 ↔ support roller 1
- Bottle 2 ↔ support roller 2

The current GitHub repository contains a bounded verifier:

`Verify-ContactManifold-FunctionFirst-LateralContacts.ps1`

Its contract requires exact active v43 document/configuration binding and is designed to classify these three lateral pairs using exact/contact-normal evidence, while explicitly refusing to infer preload, compliance, friction, force capacity, or mechanical acceptance.

### Deployment blocker observed during this pilot

The currently deployed local worker is stale:

`CadGrounded.SolidWorksWorker 0.2.0`

The current repository verifier expects worker version `0.4.5`, and the verifier script is not present in the deployed local worker directory.

Therefore the exact three-contact test is **not admitted as current evidence yet**.

Required next action before any contact-state upgrade:

`STALE_STATE / CAD_READ_REQUIRED` — reconcile the deployed read-only worker with the current reviewed GitHub implementation, then execute the verifier against the fresh live v43 state.

## Epistemic outcome

The overlay concept passed its first bounded test because it improves semantic grounding without collapsing uncertainty.

Current candidate contact markers remain:

- `I-01 = UNRESOLVED`
- `I-02 = UNRESOLVED`
- `I-03 = UNRESOLVED`

No candidate interface is upgraded to VERIFIED by this image review.
