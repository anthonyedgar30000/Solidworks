# v42 capture-owner binding evidence contract

## Decision boundary

The current v42 blocker is evidence acquisition, not placement optimization.
The exact targets are:

- `FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1`
- `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1`
- `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2`

`sw.query_mates` is a **local native candidate**, not a `CADRequest` and not a
Remote Queue capability. The queue remains limited to `sw.status`,
`sw.query_components`, and `sw.closest_distance_pair`, all with
`write_authority: NONE`.

The candidate is intentionally the smallest next read surface: it adds no new
native command and observes only the target components' parentage and incident
active-assembly constraints. It does not open a generic API or create a motion
simulation.

## Required observation contract: `V42_CAPTURE_OWNER_BINDING_V1`

The Windows/SOLIDWORKS host must run the rebuilt v0.3.1 worker through:

```powershell
.\Verify-QueryMates-V42.ps1
```

against the exact active document
`IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE.SLDASM`. The
script fails closed unless each exact target resolves uniquely.

| Contract item | Required observation | What it can establish | What it cannot establish |
|---|---|---|---|
| Document binding | Exact title/path, active configuration, and save flag before and after. | The probe ran against one identified live checkpoint without an observed document/configuration/dirty-state change. | Mechanical validity of that checkpoint. |
| Target identity and parentage | Exact `Name2`, source path, referenced configuration, fixed/suppression state, and direct-to-root parent chain. | Whether the capture part is top-level or belongs to an identifiable assembly context. | That a parent is a closure owner or has usable stiffness/travel. |
| Constraint binding | All active-assembly mate definitions incident to each target: other component identities, mate type/alignment, suppression observation, entity parameters, and exposed variations. | CAD constraint connectivity and any API-exposed variation range. | Physical degrees of freedom, motion direction, actuator force, or preload. |
| Reaction-mount trace | Constraint graph can be reviewed for an explicit path from a target to a carrier/actuator and grounded mounting structure. | A bounded CAD-topology candidate for a reaction path. | Load capacity, contact force, or a complete force analysis. |
| Mutation check | Before/after target state/transforms, document state, and assembly file hash/length/time. Every query must return `write_authority: NONE` and `model_mutation: false`. | No observed SOLIDWORKS state or assembly-file change during the probe. | A universal proof that all API reads are harmless in every future version. |

The script writes a local verification artifact at
`verification-output\query-mates-v42\verification-summary.json`. That artifact
is a candidate `EvidenceRecord` input only after a reviewer confirms the exact
document, pre/post comparison, and returned data. Its mere existence, JSON
validity, or API success is not mechanical acceptance.

## Result interpretation

The output can narrow the capture-owner hypothesis frontier only under these
rules:

1. A returned mate/parent chain that names a carrier, pivot, slide, actuator,
   or mount is an observed CAD binding. It may support the corresponding
   hypothesis, but does not verify closure, preload, contact, interval
   restraint, or whole-machine acceptance.
2. A returned mate variation is only an API-exposed constraint value. It must
   be tied to the target's closure direction, travel limits, reaction mount,
   and an authoritative actuation/preload source before it is used as an
   operating-motion claim.
3. Zero incident mates, an empty parent chain, or a missing named actuator is
   not evidence that the physical mechanism is absent. It leaves
   `H_UNBOUND_NESTED_OR_EXTERNAL_CAPTURE_MECHANISM` and any affected mechanism
   hypothesis unresolved.
4. A spring, compliant part, or cylinder must be identified by an exact
   source/CAD binding with its retention, usable travel, preload or force
   range, and reaction path. Mate data alone cannot satisfy this item.
5. No candidate operating motion, transform, mate change, configuration change,
   suppression change, or geometry edit is created from this probe.

## Minimum conclusion gate

`CAPTURE_KINEMATIC_OWNER` may remain `UNRESOLVED` even after a successful
probe. It can become evidence-supported only when one physical subassembly is
bound to all of the following:

- the exact FITCHECK belt and/or support rollers it drives or positions;
- a closure input (actuator, manual adjustment, or compliant source);
- constrained direction and explicit limits/travel;
- a reaction mount into the support structure; and
- the temporal states it affects, at minimum capture beginning, captured,
  label-transfer/wrap, and release.

Even that local owner binding does not satisfy bottle restraint/contact across
the required interval or reachable-motion clearance. Those remain separate
obligations and no local subsystem result grants whole-machine mechanical
acceptance.
