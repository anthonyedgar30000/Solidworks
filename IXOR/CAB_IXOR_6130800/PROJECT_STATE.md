# IXOR Project State

## Current working version
v18 WIP — portable checkpoint created, AR60 insertion not yet completed or mechanically accepted

## Preserved baseline
`v17_PORTABLE/IXOR_Benchmark_v17_CONVEYOR_BOTTLES_WORKING_PORTABLE.SLDASM`

The v17 baseline was verified live and was not overwritten.

## Current working assembly
`v18_PORTABLE/IXOR_Benchmark_v18_WIPEDOWN_CONTACT_WORKING_PORTABLE.SLDASM`

## Current design
- CAB IXOR 6130800 labeling head
- SP100 demand module
- 6120069 mounting rods
- 6130411 tie rod
- 6130737 GHF 120 support
- Bench conveyor
- D48 H180 bottles

## Version lineage
- v11 — canonical baseline
- v12 — SP100 inspection
- v13 — mounting rods
- v14 — portable baseline
- v15 — support stack
- v16 — physical support mates
- v17 — conveyor + bottles; preserved baseline
- v18 — WIP: portable checkpoint created; OEM wipe-down insertion and mechanical review pending

## Source authority
- GitHub — authoritative project files, version history, and handoff state
- Google Drive — active mirror/reference/archive source for `C:\ChatGPT`; IXOR reference folder: `ChatGPT/Solidworks/IXOR/CAB_IXOR_6130800`
- SOLIDWORKS MCP — authoritative live mechanical geometry, mates, transforms, interference, and assembly state

## Google Drive reference
- ChatGPT root folder: https://drive.google.com/drive/folders/1VS1Xeb6CA9HdZPP4RrhG0-8xNgi4Gd54
- IXOR reference folder: https://drive.google.com/drive/folders/1rbDZJkYu7Dkk_x-gHrzECFwYWcIPMyrz
- Upload/indexing status: active and accessible from ChatGPT

## v18 implementation brief
`V18_WIPEDOWN_CONTACT_IMPLEMENTATION.md`

Primary OEM benchmark part:
- CAB `6130460` — AR 60 wipe-down roller
- GitHub/Drive source file: `IXOR/6130460_03_Wipe-down_roller_Andruckrolle_AR_60 (2).zip`

Food/cleanroom alternative:
- CAB `6130621` — ARS 60 wipe-down roller

## Live verification completed on 2026-09-12
- SOLIDWORKS bridge v0.3.0 was live.
- Active baseline was the exact v17 assembly listed above.
- Thirteen expected top-level components were present and unsuppressed.
- OEM manual Figures 47–48 confirm that the AR60 stepped shaft inserts into the SP100 lever and is retained by the lever screw; carriage position and eccentric preload provide the OEM adjustments.
- OEM AR60 STEP measured as one solid, approximately 89.2 × 25 × 25 mm overall, with a Ø25 mm foam roller 61 mm long and a terminal Ø7 mm shaft segment.
- The matching SP100 internal Ø7 mm receiver bore was identified from live B-rep geometry at global axis `X = -164.500 mm`, `Y = -192.000 mm`, with bore end planes at `Z = 1035.866667 mm` and `Z = 1038.500000 mm`.
- Bottle 3 center is `X = -153.750 mm`, `Y = -224.000 mm`; roller/bottle axis distance is about 33.757 mm. With radii 12.5 mm and 24 mm, the nominal radial overlap is about 2.743 mm and must be treated as compliant preload, not hard-solid clearance.

## v18 checkpoint status
- Pack-and-Go created `v18_PORTABLE`.
- The target v18 assembly opens successfully.
- A clean reopen verified that its top-level external references resolve from `v18_PORTABLE`; virtual components remain SOLIDWORKS-managed.
- The OEM STEP was copied to `v18_PORTABLE/6130460_03_Wipe-down_roller_Andruckrolle_AR_60.stp`.
- Native AR60 conversion stopped when the STEP import returned error 1; immediately afterward SOLIDWORKS/CADGrounded went offline.
- No AR60 component was inserted. No mates or component transforms were changed. Bottle-stability and interference checks are still pending.

## Deterministic AR60 placement proposal — not yet applied
Using the measured Ø7 receiver, the OEM shaft shoulder seated at the lower bore face, and the manual-shown downward roller orientation:

- `rotation9 = [0, 0, 1, 1, 0, 0, 0, 1, 0]`
- `translation_mm = [-123.518666439269, -64.228755736082, 1006.359219397215]`
- Proposed foam working span: approximately `Z = 963.166667 ... 1024.166667 mm`

This transform must be revalidated against the live native AR60 part before insertion. After insertion, verify shaft/bore coaxiality and seating, peel-edge spacing, SP100/IXOR/rail/bottle interference, and bottle stability before accepting v18.

## Next CAD action
1. Restart SOLIDWORKS and ensure the CADGrounded add-in is loaded.
2. Run `sw_status` read-only.
3. Confirm or reopen `v18_PORTABLE/IXOR_Benchmark_v18_WIPEDOWN_CONTACT_WORKING_PORTABLE.SLDASM`.
4. Run `sw_query_components`; confirm the 13 expected top-level components and that external paths resolve from `v18_PORTABLE`.
5. Confirm the copied OEM STEP exists and that no AR60 native/component instance exists.
6. Convert the OEM STEP to `6130460_03_AR60_NATIVE_PORTABLE_V18.SLDPRT` without altering the assembly.
7. Revalidate the proposed transform from the native part's live B-rep, then insert once.
8. Verify contact, clearances, interference, remaining degrees of freedom, lateral stability, yaw, tipping, and rotation.
9. Add an opposing restraint only if the measured OEM arrangement proves it is required.
10. Save and read back the accepted v18 assembly.

## Startup prompt
`@GitHub read IXOR/CAB_IXOR_6130800/PROJECT_STATE.md and V18_WIPEDOWN_CONTACT_IMPLEMENTATION.md, @Google Drive use ChatGPT/Solidworks/IXOR and the CAB IXOR manuals/CAD archives as OEM reference, then @CADGrounded SOLIDWORKS run sw_status and resume the documented v18 WIP checkpoint without modifying v17.`
