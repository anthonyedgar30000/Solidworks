# V43 Prism Slider-to-Links Current-Pose Contact Evidence Contract

## Purpose

Bound one read-only SOLIDWORKS observation that asks whether the exact v43 Prism carrier slider is physically adjacent to each exact Prism link at the currently active `V43_WRAP` pose.

This is a **point-topology** test only. It is not a kinematic-motion, force, stroke, preload, timing, or mechanical-acceptance test.

## Exact state binding

Required active document:

- title: `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`
- path: `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`
- active configuration: `V43_WRAP`

Required exact top-level targets:

- slider: `FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1`
- Link-1: `FITCHECK_PRISM_LINK_15x10x25_V43-1`
- Link-2: `FITCHECK_PRISM_LINK_15x10x25_V43-2`

A fresh exact state rebind is required immediately before execution.

## Allowed execution

Local native worker command only:

- `sw.classify_contact_pair`

Pairs:

1. slider ↔ Link-1
2. slider ↔ Link-2

Write authority: `NONE`

Remote Queue authorization: `false`

Model mutation: `false`

## Required no-mutation evidence

The verifier must compare before/after:

- exact target component state and transforms
- SOLIDWORKS process identity
- active document title/path/type
- exact active configuration
- document save flag
- assembly file SHA-256, length, and last-write timestamp

## PASS establishes only

For each exact pair at the recorded pose:

- exact identities
- returned minimum distance
- returned current-pose classification
- exact B-rep intersection result when the worker executes it
- unchanged pre/post state under the verifier contract

Interpretation:

- positive clearance weakens direct physical adjacency for that exact pair at that pose
- contact/coincidence within tolerance supports current-pose adjacency only
- interference is a geometry conflict requiring separate interpretation

## PASS does not establish

- a revolute, prismatic, pin, flexure, or other joint
- allowed degree of freedom
- permitted motion direction
- stroke or endpoints
- actuator ownership
- preload, force, stiffness, or reaction capacity
- reachable-state clearance
- capture/release sequencing or timing
- mechanical acceptance

No CAD writes are authorized by this contract.
