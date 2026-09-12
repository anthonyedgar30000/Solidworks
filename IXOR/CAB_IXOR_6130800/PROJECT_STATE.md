# IXOR Project State

## Current working version
v17

## Current assembly
`v17_PORTABLE/IXOR_Benchmark_v17_CONVEYOR_BOTTLES_WORKING_PORTABLE.SLDASM`

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
- v17 — conveyor + bottles
- v18 — planned: OEM wipe-down contact geometry and bottle-stability evaluation

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

## Next CAD action
1. Verify v17 live in SOLIDWORKS before modifying.
2. Preserve v17 untouched and create `v18_PORTABLE`.
3. Insert/model the OEM AR 60 wipe-down roller on the existing SP100 lever using actual OEM mating geometry.
4. Establish peel-edge / wipe-down-roller / D48 bottle contact geometry using the OEM adjustment envelope.
5. Evaluate bottle lateral stability, yaw, tipping, and rotation under wipe-down reaction force.
6. Add an opposing restraint only if the v18 contact check proves it is required.
7. Save the result as `IXOR_Benchmark_v18_WIPEDOWN_CONTACT_WORKING_PORTABLE.SLDASM`.

## Startup prompt
`@GitHub read IXOR/CAB_IXOR_6130800/PROJECT_STATE.md and V18_WIPEDOWN_CONTACT_IMPLEMENTATION.md, @Google Drive use ChatGPT/Solidworks/IXOR and the CAB IXOR manuals/CAD archives as OEM reference, then @CADGrounded SOLIDWORKS verify v17 and execute the v18 wipe-down contact implementation.`
