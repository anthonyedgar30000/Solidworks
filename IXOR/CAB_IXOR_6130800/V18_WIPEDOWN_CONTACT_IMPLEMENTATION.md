# IXOR v18 — Wipe-down Contact Implementation Brief

## Objective
Advance the v17 conveyor/bottle benchmark by adding the OEM SP100 wipe-down contact hardware and validating the bottle reaction path before designing any custom restraint.

## Baseline to preserve
- Current checkpoint: `v17_PORTABLE/IXOR_Benchmark_v17_CONVEYOR_BOTTLES_WORKING_PORTABLE.SLDASM`
- Bottle: `BENCH_BOTTLE_D48_H180.SLDPRT`
- Conveyor: `BENCH_CONVEYOR_L900_W82_H950.SLDPRT`
- Existing demand module: SP100 / CAB `6130656_01_Demand_module_Spendemodul_SP_100_60L`
- Do not modify or overwrite the v17 checkpoint.

## OEM contact hardware
Primary benchmark choice:
- CAB `6130460` — AR 60 wipe-down roller
- Repository source: `IXOR/6130460_03_Wipe-down_roller_Andruckrolle_AR_60 (2).zip`
- Nominal roller width: 62 mm
- Material/function: open-cell foam, standard applications
- Mounting: installed on the SP demand-module lever

Food/cleanroom alternative, not the default benchmark part:
- CAB `6130621` — ARS 60 wipe-down roller
- Nominal roller width: 62 mm
- FDA-approved silicone, longer-life alternative

## Mechanical interpretation
The dispenser tongue / peel-off plate is the label-release edge. It is not intended to clamp the bottle.

The wipe-down roller is the compliant product-contact element. It is lever-mounted and should press the dispensed label against the bottle after the label leaves the peel edge.

CAB provides three relevant wipe-down adjustments:
1. Distance from wipe-down roller to peel-off plate: 5–40 mm.
2. Lower end position of roller relative to the product.
3. Wipe-down force onto the product by spring preload.

OEM manual Figures 47–48 identify the roller shaft insertion into the lever, the retaining screw, the carriage/guide distance adjustment, the lower-end adjustment screw, and the eccentric preload adjustment.

## Verified v18 geometry
Measured from the live v17 SOLIDWORKS assembly and the OEM `6130460` STEP on 2026-09-12:

- AR60 overall envelope: approximately 89.2 × 25 × 25 mm.
- Foam roller: Ø25 mm, 61 mm axial length.
- Terminal mounting shaft: Ø7 mm.
- Matching SP100 internal receiver bore: Ø7 mm.
- Receiver axis: global `X = -164.500 mm`, `Y = -192.000 mm`.
- Receiver axial limits: global `Z = 1035.866667 ... 1038.500000 mm`.
- Bottle 3 center: global `X = -153.750 mm`, `Y = -224.000 mm`.
- Roller/bottle center distance in the conveyor plane: approximately 33.757 mm.
- Nominal compliant radial overlap: approximately 2.743 mm for a 12.5 mm roller radius and 24 mm bottle radius.

The receiver was selected from the actual SP100 B-rep because it is an internal Ø7 mm cylinder, is nearest the D48 bottle path, and matches the OEM AR60 terminal shaft. The other Ø7 mm SP100 bores are not at the product-contact side.

## Deterministic insertion proposal — not yet applied
For the manual-shown downward roller orientation, with the AR60 shaft shoulder seated at the lower receiver face:

- `rotation9 = [0, 0, 1, 1, 0, 0, 0, 1, 0]`
- `translation_mm = [-123.518666439269, -64.228755736082, 1006.359219397215]`
- Proposed foam working span: approximately `Z = 963.166667 ... 1024.166667 mm`

The transform is a deterministic proposal derived from the measured STEP and receiver geometry. It is not engineering truth until the native AR60 part is loaded and the shaft/bore and shoulder seating are read back from live SOLIDWORKS geometry.

## v18 CAD procedure
1. Open and verify the v17 assembly live before editing.
2. Save a new working assembly as `IXOR_Benchmark_v18_WIPEDOWN_CONTACT_WORKING_PORTABLE.SLDASM` under a new `v18_PORTABLE` folder.
3. Import/convert the OEM `6130460` AR 60 wipe-down roller into a native portable SOLIDWORKS part if required.
4. Attach the AR 60 roller to the existing SP100 lever using the actual OEM mating geometry. Do not position it by visual approximation if reference faces/axes are available.
5. Set the roller so its axis is consistent with the OEM lever geometry and its contact envelope reaches the D48 bottle at the labeling station.
6. Start with a nominal peel-edge-to-roller spacing within the OEM 5–40 mm adjustment range; preserve adjustability rather than hard-locking an arbitrary value.
7. Set the roller lower-end/contact position so the compliant roller intersects the intended bottle tangent only enough to represent preload/contact, not hard solid interference.
8. Preserve the conveyor rails as the primary bottle-path guides.
9. Rebuild and inspect the complete assembly.

## Bottle restraint decision gate
Do **not** add a custom opposing clamp, belt, or backpressure roller before checking the OEM wipe-down arrangement.

Evaluate the D48 bottle under the expected wipe-down reaction direction:
- Is the bottle laterally supported by the opposite guide rail at the labeling station?
- Does the wipe-down roller tend to push the bottle out of the intended path?
- Does the bottle yaw or tip?
- Does contact intentionally or unintentionally rotate the bottle?
- Is that rotation compatible with the eventual label wrap requirement?
- Is there sufficient clearance for adjacent bottles and rails?

If the bottle remains stable and the intended label placement can be achieved, retain the simple OEM wipe-down arrangement.

If the bottle can move away from the applicator, yaw, tip, or rotate unpredictably, the next design step is an opposing passive backpressure roller or controlled side/wrap belt. That restraint should be designed from the measured v18 contact geometry, not guessed in advance.

## Verification checks before accepting v18
- OEM AR 60 component identity confirmed.
- Correct lever/carriage attachment confirmed.
- No unintended interference with the SP100 head, peel tongue, conveyor, rails, or bottle.
- Peel edge, roller, and bottle are in a mechanically plausible application sequence.
- Remaining degrees of freedom are intentional and documented.
- Bottle centerline and conveyor path remain valid.
- Wipe-down preload/contact direction is physically supported.
- Decision recorded: `OEM wipe-down sufficient` or `opposing restraint required`.

## Execution status — 2026-09-12
- v17 was verified live and preserved.
- Pack-and-Go created `v18_PORTABLE` and the exact target v18 assembly.
- After a clean close/reopen, all top-level external references resolved from `v18_PORTABLE`; virtual components remained SOLIDWORKS-managed.
- The OEM AR60 STEP was copied into `v18_PORTABLE`.
- The native conversion attempt returned STEP import error 1, after which the SOLIDWORKS/CADGrounded named pipe disappeared.
- No AR60 component was inserted; no assembly mate or transform was changed.
- Interference, peel-edge spacing, remaining freedom, and bottle-stability checks remain pending.

## Recovery sequence
1. Restart SOLIDWORKS and load the CADGrounded add-in.
2. Run `sw_status` read-only.
3. Confirm or reopen `v18_PORTABLE/IXOR_Benchmark_v18_WIPEDOWN_CONTACT_WORKING_PORTABLE.SLDASM`.
4. Run `sw_query_components` and verify the existing 13 top-level components and `v18_PORTABLE` paths.
5. Confirm `6130460_03_Wipe-down_roller_Andruckrolle_AR_60.stp` exists and no AR60 instance is present.
6. Retry native conversion to `6130460_03_AR60_NATIVE_PORTABLE_V18.SLDPRT` without assembly insertion.
7. Re-query the native AR60 B-rep, revalidate the proposed transform, then insert exactly one instance.
8. Complete the verification checks and decision gate above before accepting v18.

## Expected output
Preserve v17 untouched and produce a mechanically reviewed v18 checkpoint focused only on wipe-down contact geometry and bottle stability. Do not solve wrap-control hardware until this contact test establishes whether it is needed.
