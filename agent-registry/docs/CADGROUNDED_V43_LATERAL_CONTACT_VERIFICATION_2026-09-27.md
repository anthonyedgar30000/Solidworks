# CADGrounded v43 Lateral Contact Verification — 2026-09-27

## Scope

This record documents the bounded deterministic verification performed after the v43 visual-overlay pilot.

Active CAD document:

`IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`

Configuration:

`V43_WRAP`

Geometry lifecycle state:

`CANDIDATE_OPERATING`

Mechanical acceptance granted:

**false**

## Fresh live binding

The test was executed against the live v43 assembly after a fresh SOLIDWORKS identity check.

The verifier was built and executed from an isolated clean GitHub clone rather than the dirty CAD working tree.

Pinned source commit:

`fd171dbf8f2feddc70844533da89e6d5209ea6c3`

Worker:

`CadGrounded.SolidWorksWorker 0.4.5`

Verifier:

`Verify-ContactManifold-FunctionFirst-LateralContacts.ps1`

Verifier result:

**PASS**

Executed at:

`2026-09-27T21:48:33.6807848Z`

Evidence status reported by verifier:

`OBSERVATION_READY_ONLY`

## Verified current-pose contact manifolds

### Bottle 2 ↔ driven wrap belt

Exact identities:

- `BENCH_BOTTLE_D48_H180-2`
- `FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1`

Classification:

`TANGENT_CYLINDER_PLANE_GENERATOR_LINE`

Observed current-pose contact point:

`[-129.42061528267112, -214, 995] mm`

Trimmed assembly-Z overlap:

- Z min: `995 mm`
- Z max: `1088 mm`
- length: `93 mm`

Observed opposing-normal dot:

`-1`

### Bottle 2 ↔ support roller 1

Exact identities:

- `BENCH_BOTTLE_D48_H180-2`
- `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1`

Classification:

`EXTERNAL_TANGENT_PARALLEL_CYLINDER_GENERATOR_LINE`

Observed current-pose contact point:

`[-163.26532216974627, -235.88793609063163, 1088] mm`

Trimmed assembly-Z overlap:

- Z min: `995 mm`
- Z max: `1088 mm`
- length: `93 mm`

Analytic tangency:

- bottle radius: `24 mm`
- roller radius: `15 mm`
- cylinder-axis distance: `39.000000000000007 mm`
- radius sum: `39 mm`
- tangency residual: `7.1054273576010019E-15 mm`
- opposed-normal dot: `-0.9999999989686531`

### Bottle 2 ↔ support roller 2

Exact identities:

- `BENCH_BOTTLE_D48_H180-2`
- `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2`

Classification:

`EXTERNAL_TANGENT_PARALLEL_CYLINDER_GENERATOR_LINE`

Observed current-pose contact point:

`[-172.12743815825996, -198.96488184611289, 1041.686] mm`

Trimmed assembly-Z overlap:

- Z min: `995 mm`
- Z max: `1088 mm`
- length: `93 mm`

Analytic tangency:

- bottle radius: `24 mm`
- roller radius: `15 mm`
- cylinder-axis distance: `39.000000000587747 mm`
- radius sum: `39 mm`
- tangency residual: `5.8774674016603967E-10 mm`
- opposed-normal dot: `-0.99999999978474563`

## Ideal finite-line normal model

The verifier constructed an ideal maintained frictionless finite-line normal-constraint model.

Observed result:

- rank: `5`
- nullity: `1`
- wrap-axis rotation is the null mode: `true`
- wrap-axis max absolute residual: `2.6645352591003757E-14`
- five-DOF restraint excluding wrap rotation: `SUPPORTED_BY_IDEAL_FINITE_LINE_NORMAL_MODEL`

This is a deterministic model result only. It must not be promoted into real maintained restraint without contact-maintenance/preload/compliance evidence.

## What this establishes

The verifier contract establishes:

- exact current-pose analytic surface type for the bottle and opposing face at each of the three lateral contacts;
- trimmed-face assembly-Z extent from bounded closest-point probes on transformed temporary B-rep faces;
- cylinder-plane or parallel-cylinder tangency classification where supported by the observed analytic surfaces;
- positive axial overlap length for each classified generator-line contact;
- rank/nullity of an ideal maintained frictionless finite-line constraint model using two separated samples per observed lateral line contact;
- pre/post document, target-state, and assembly-file no-mutation comparison.

## What remains unresolved

This verification does **not** establish:

- unilateral contact maintenance;
- preload;
- compliance;
- deformation;
- force capacity;
- friction;
- traction;
- driven wrap torque;
- rotation source;
- gravity/up semantics;
- interval-wide contact;
- reachable motion;
- whether the current v43 belt or rollers are required in the final mechanism;
- mechanism selection;
- mechanical acceptance.

The verifier's explicit limitation is:

> Finite-line rank is an ideal rigid maintained-contact geometric model. It must not be promoted into real tilt restraint without contact-maintenance/preload/compliance evidence.

## Visual-overlay implication

The three v43 Front-view interface markers may now be upgraded from `CANDIDATE / UNRESOLVED` to **verified current-pose contact loci**, provided the overlay also states that verification came from deterministic CAD evidence rather than from pixels.

The following remain unresolved on the overlay:

- capture/contact-maintenance motion;
- preload/compliance;
- real reaction-force path and force capacity;
- friction/traction/driven torque;
- interval-wide/reachable motion.

## Deployment reconciliation status

A side-by-side clean worker deployment was successfully built from the pinned GitHub source without modifying the dirty CAD working tree.

The existing scheduled Remote Queue deployment remains on the older task paths. An attempted scheduled-task action switch was rejected by Windows Task Scheduler with:

`The user name or password is incorrect.`

A post-failure reread confirmed both scheduled task actions still point to their original local paths, so no task-action migration is claimed.

Current safe state:

- clean worker 0.4.5: built and verified side-by-side;
- exact contact verifier: PASS;
- scheduled queue deployment: **not yet migrated**;
- CAD model mutation: **none**;
- mechanical acceptance: **false**.
