# IXOR Project State

## Current working version
v21 — AR60 carriage fit-check checkpoint; live assembly verified, but the AR60/carriage arrangement is not mechanically accepted as an operating label-application configuration.

## Preserved baseline
`v17_PORTABLE/IXOR_Benchmark_v17_CONVEYOR_BOTTLES_WORKING_PORTABLE.SLDASM`

The v17 conveyor+bottle baseline remains a preserved reference and should not be overwritten.

## Current live assembly
`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE.SLDASM`

Live title:
`IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE`

## Current design / top-level content
Verified from the live SOLIDWORKS assembly on 2026-09-15: 15 top-level components, none suppressed.

- `IXOR_6130800_NATIVE_PORTABLE_V17-1`
- `SP100_6130656_NATIVE_PORTABLE_V17-1`
- `6130460_03_AR60_NATIVE_PORTABLE_V18-2`
- `6130649_01_Carriage_Schlitten_AR_NATIVE_PORTABLE_V20-1`
- `6130737_03_GHF_120_NATIVE_PORTABLE_V17-1`
- `6130411_01_Tie_rod_NATIVE_PORTABLE_V17-1`
- `6120069_02_Mounting_rod_NATIVE_PORTABLE_V17-1`
- `6120069_02_Mounting_rod_NATIVE_PORTABLE_V17-2`
- `BENCH_CONVEYOR_L900_W82_H950-1`
- `BENCH_BOTTLE_D48_H180-1`
- `BENCH_BOTTLE_D48_H180-2`
- `BENCH_BOTTLE_D48_H180-3`
- `BENCH_BOTTLE_D48_H180-4`
- `BENCH_BOTTLE_D48_H180-5`
- `5983425_01_Floor_stand_Bodenstativ_1632^IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE-1`

The floor-stand entry is a SOLIDWORKS virtual component and may resolve through a temporary/internal path. Do not treat that alone as a portability failure.

## Version lineage
- v11 — canonical baseline
- v12 — SP100 inspection
- v13 — mounting rods
- v14 — portable baseline
- v15 — support stack
- v16 — physical support mates
- v17 — conveyor + bottles; preserved baseline
- v18 — AR60 introduction work began; historical checkpoint retained below
- v19-v20 — intermediate development checkpoints; do not reconstruct details without Git/CAD evidence
- v21 — current live AR60 carriage fit-check assembly

## Source authority
1. OEM STEP/CAD
2. OEM manuals/specifications
3. OEM photographs
4. Deterministic calculations/geometry created in this project
5. Trusted third-party CAD
6. General web references
7. Generative images — visualization only, never ground truth

Operationally:
- SOLIDWORKS is authoritative for current live geometry and component state.
- GitHub is authoritative for versioned project source, policy, history, and durable handoff state.
- Google Drive is a mirror/reference/archive surface, not the source of live CAD truth.

## Live verification completed on 2026-09-15
Verified from live CAD reads after laptop reboot and stack recovery:

- CADGrounded SOLIDWORKS bridge v0.3.0 is online.
- Active document is `IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE.SLDASM`.
- Active path is `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE.SLDASM`.
- 15 top-level components are present.
- 0 top-level components are suppressed.
- Independent local registry/worker reads and ChatGPT Work MCP reads agreed on the active v21 assembly and component count.
- `6130460_03_AR60_NATIVE_PORTABLE_V18-2` and `6130649_01_Carriage_Schlitten_AR_NATIVE_PORTABLE_V20-1` are present and floating.
- The AR60/carriage are in a remote fit-check workspace rather than an accepted bottle application position.

## Mechanical acceptance status
NOT ACCEPTED.

The current v21 assembly is a fit-check/research state. The following must not yet be claimed:

- accepted AR60-to-bottle application contact
- accepted AR60 shaft seating
- accepted carriage operating position
- accepted bottle restraint / pinning mechanism
- accepted label-web path
- accepted peel-plate relationship
- accepted clearances or interference state for the operating arrangement
- accepted bottle lift/release mechanism
- validated production operating sequence

No AI-generated image may be used as evidence for any of those points.

## Historical v18 evidence retained
The earlier v18 checkpoint documented the following source/CAD findings on 2026-09-12:

- OEM manual Figures 47–48 were used to establish that the AR60 stepped shaft inserts into the SP100 lever and is retained by the lever screw; carriage position and eccentric preload provide adjustment.
- OEM AR60 STEP was measured as one solid, approximately 89.2 × 25 × 25 mm overall, with a Ø25 mm foam roller about 61 mm long and a terminal Ø7 mm shaft segment.
- A matching SP100 internal Ø7 mm receiver bore was identified in live B-rep geometry.

These are historical source/CAD findings. They remain useful design evidence, but any placement coordinates or transforms from v18 must be revalidated against the current v21 live assembly before use.

## Current engineering objective
Determine a mechanically plausible bottle-labeling arrangement using genuine CAB IXOR/AR60 geometry plus deterministic conveyor, bottle, mounting, and restraint geometry.

The current focus is not visualization. First establish and verify the mechanical arrangement deterministically.

## Next CAD action
1. Read the current live transforms and approximate envelopes for the exact AR60, carriage, Bottle 3, conveyor, IXOR head, and SP100 components.
2. Record exact component identities using `Component2.Name2`; do not use loose `AR60` substring selectors because the assembly title/virtual component can create ambiguity.
3. Establish the intended application-station coordinate frame and the OEM-supported mechanical relationships before proposing any move.
4. Verify AR60-to-carriage/SP100 seating, bottle contact geometry, opposing restraint requirements, peel-edge relationship, and product-flow clearance using deterministic CAD evidence.
5. Use closest-distance/interference tools only as measurements; API success alone is not mechanical acceptance.
6. Only after the target transform is mechanically justified, perform a dry-run/preflight transform proposal. Do not write merely because MaxControl is enabled.
7. After any authorized CAD change, reread the live state and record geometry evidence before visualization work.

## Infrastructure / reboot state verified 2026-09-15
- Local Agent Registry: `http://127.0.0.1:18181` — healthy in `read-only-bootstrap` mode.
- Registry worker: `solidworks-bridge-01` — responding.
- CADGrounded MCP: `http://127.0.0.1:8765/mcp` — running with v0.3.0.
- OpenAI tunnel profile: `solidworks-local` — successfully initialized against the local MCP target.
- ChatGPT Work successfully reached the local MCP through the tunnel and returned live SOLIDWORKS status/components.

## Historical implementation brief
`V18_WIPEDOWN_CONTACT_IMPLEMENTATION.md` remains a historical v18 design/evidence document. It is not the current project-state authority.

## Startup prompt
`@GitHub read IXOR/CAB_IXOR_6130800/PROJECT_STATE.md, @Google Drive use the IXOR reference folder and CAB OEM manuals/CAD as supporting evidence, then @CADGrounded SOLIDWORKS run read-only status and component queries. Treat the live v21 SOLIDWORKS assembly as current geometry authority. Do not make CAD changes until the target mechanical relationship is deterministically established and preflighted.`
