# V43 Prism Full-Chain Mate/Constraint Evidence Contract

## Purpose

Bound one read-only SOLIDWORKS observation of active-assembly mate/constraint evidence for the complete current-pose Prism adjacency chain.

Previously admitted point topology supports:

- slider -> Link-1 -> Arm-1 -> Support roller 1
- slider -> Link-2 -> Arm-2 -> Support roller 2

This contract asks whether SOLIDWORKS also contains exact active-assembly mate definitions, suppression observations, or variation values that justify a candidate kinematic relation. Contact adjacency alone is not a motion law.

## Exact state binding

Required active document:

- title: `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`
- path: `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`
- active configuration: `V43_WRAP`

Required exact targets:

- `FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1`
- `FITCHECK_PRISM_LINK_15x10x25_V43-1`
- `FITCHECK_PRISM_LINK_15x10x25_V43-2`
- `FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1`
- `FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1`
- `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1`
- `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2`

## Allowed execution

Local native worker command only:

- `sw.query_mates`

Write authority: `NONE`

Remote Queue authorization: `false`

Model mutation: `false`

## PASS establishes only

For each exact target at the recorded point:

- exact component identity and state
- active-assembly mate definitions that reference it
- mate API type/alignment and suppression observation when returned
- mate variation values when SOLIDWORKS exposes them
- explicit zero incident mate count as negative evidence when no mate is returned
- unchanged pre/post component, document/configuration/save-state, and assembly-file evidence

## PASS does not establish

- physical joint correctness
- actual DOF if constraints are incomplete or absent
- motion direction, stroke, endpoints, actuator ownership
- preload, force, stiffness, contact pressure, reaction capacity
- reachable-state clearance or sequence
- mechanical acceptance

If the complete chain has no relevant active-assembly mate evidence, the correct result is `KINEMATIC_STATE_UNRESOLVED`, not an invented motion model.
