# V43 Prism Arm-to-Support-Roller Current-Pose Contact Evidence Contract

## Purpose

Bound one read-only SOLIDWORKS observation that determines the exact current-pose contact topology between both v43 Prism arms and both named support rollers without assuming that matching suffixes imply mechanical pairing.

This is a **point-topology** test only. It is not a bearing-function, joint, motion, force, stroke, preload, timing, or mechanical-acceptance test.

## Exact state binding

Required active document:

- title: `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`
- path: `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`
- active configuration: `V43_WRAP`

Required exact top-level targets:

- Arm-1: `FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1`
- Arm-2: `FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1`
- Support roller 1: `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1`
- Support roller 2: `FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2`

A fresh exact state rebind is required immediately before execution.

## Allowed execution

Local native worker command only:

- `sw.classify_contact_pair`

Pairs:

1. Arm-1 ↔ Support roller 1
2. Arm-1 ↔ Support roller 2
3. Arm-2 ↔ Support roller 1
4. Arm-2 ↔ Support roller 2

Testing all four combinations is deliberate: numbered correspondence is not admitted as a mechanical fact.

Write authority: `NONE`

Remote Queue authorization: `false`

Model mutation: `false`

## PASS establishes only

For each exact pair at the recorded pose:

- exact identities
- returned minimum distance
- returned current-pose classification
- exact B-rep intersection result when executed
- unchanged pre/post target, document/configuration/save state, and assembly-file evidence

## PASS does not establish

- bearing or support-roller function
- arm-to-roller joint type
- allowed degree of freedom or permitted motion
- stroke or endpoints
- actuator ownership
- preload, force, stiffness, or reaction capacity
- reachable-state clearance
- capture/release sequencing or timing
- mechanical acceptance

No CAD writes are authorized by this contract.
