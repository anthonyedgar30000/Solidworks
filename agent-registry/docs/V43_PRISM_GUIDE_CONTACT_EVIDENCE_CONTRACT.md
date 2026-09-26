# V43 Prism Guide-Contact Evidence Contract

## Purpose

Acquire a bounded, current-pose observation of whether the exact v43 Prism carrier slider is physically adjacent to each exact fixed guide rail.

This contract tests **current-pose topology only**. It does not test or establish allowed motion, stroke, actuation, preload, force, reachable envelope, capture, release, timing, or mechanical acceptance.

## Authority and execution boundary

| Topic | Authority / boundary |
| --- | --- |
| Live geometry, active document, configuration | SOLIDWORKS |
| Source, policy, plan, and admitted result | GitHub |
| Native command | `sw.classify_contact_pair` |
| Write authority | `NONE` |
| Model mutation | Required `false` |
| Remote Queue | Not authorized |
| Forbidden actions | Move, rebuild, save, mate edit/create, suppression, selection, transform |

## Required live document

- Title: `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`
- Path: `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`
- Configuration: `V43_WRAP`

A fresh status/component rebind is required immediately before the contact observations.

## Exact pair set

1. `FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1` ↔ `FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-1`
2. `FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1` ↔ `FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-2`

The pair set is chosen because the live point inventory places the slider AABB on the boundary of both rail AABBs, making exact B-rep/contact classification highly discriminating for the guided-slider hypothesis. AABB tangency is screening evidence only and is not admitted as contact.

## Host execution

From the Windows worker directory:

```powershell
.\Verify-ClassifyContact-V43-Prism-GuideRails.ps1
```

The verifier must require:

1. Worker version `0.4.4`.
2. Exact document title/path/configuration.
3. Exact component identity for the slider and both rails.
4. `write_authority: NONE` and `model_mutation: false` for every query.
5. Exact minimum-distance/contact classification for both pairs.
6. Before/after equality for target transforms/state, active document/configuration/save state, and assembly-file hash/length/timestamp.

A failed assertion produces no PASS evidence artifact.

## PASS boundary

A PASS may establish only the exact pair identities, current-pose minimum distances/classifications, and the bounded no-mutation comparison.

- Positive clearance weakens physical adjacency for that exact pair at that pose.
- Contact/tangency supports current-pose adjacency only.
- Interference is a current-pose geometry conflict requiring separate mechanical interpretation.

No result by itself establishes a prismatic joint, permitted degree of freedom, motion limits, actuator ownership, force path, preload, operating sequence, or mechanical acceptance.
