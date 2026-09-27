# CADGrounded Visual Evidence Overlay v0.1

Status: **governed visualization / interpretation aid**  
Authority: **non-geometric, non-mechanical**  
Applies to: SOLIDWORKS captures, deterministic Blender renders, and later AI-enriched comparison images.

## Purpose

Provide a consistent, machine-readable visual annotation layer that helps humans and AI interpret authoritative CAD views without converting annotations into engineering evidence.

The overlay may communicate:

- exact identity labels;
- evidence state;
- motion intent;
- candidate contact/interface locations;
- unresolved questions;
- view purpose;
- capture provenance.

The overlay **must not** create or upgrade geometry, dimensions, contact, restraint, kinematics, mechanical acceptance, or operating-sequence claims.

## Authority rule

Underlying deterministic CAD/source geometry remains authoritative according to the project hierarchy.

An overlay is a semantic aid only.

A screenshot annotation saying "contact", "motion", "clearance", "accepted", or similar is not proof of that condition unless the claim is independently backed by admitted authoritative evidence.

## Canonical capture trio

For each governed view, preserve:

```text
<VIEW_ID>_RAW.png
<VIEW_ID>_OVERLAY.png
<VIEW_ID>.json
```

The RAW and OVERLAY images must use the same camera pose, projection, crop, and source CAD state.

## Required header fields

Each OVERLAY image should expose, when available:

```text
CADGROUNDED VISUAL EVIDENCE
ASSEMBLY: <exact live document title>
VIEW_ID: <stable identifier>
GEOMETRY_STATE: <SOURCE_GEOMETRY | FIT_CHECK | CANDIDATE_OPERATING | MECHANICALLY_ACCEPTED>
MECHANICAL_ACCEPTANCE: <TRUE | FALSE>
SOURCE: <SOLIDWORKS_LIVE_STATE | DETERMINISTIC_RENDER | OTHER_EXPLICIT_SOURCE>
CAMERA: <stable camera/view identifier>
VIEW_PURPOSE: <short bounded purpose>
```

If an exact value is unknown, preserve UNKNOWN/UNRESOLVED rather than inventing it.

## Overlay vocabulary

Do not rely on color alone. Every semantic overlay uses:

**color + line style + symbol + explicit ID**

| Meaning | Visual treatment | Prefix |
|---|---|---|
| Verified identity/interface | green solid outline + circle | `V-` |
| Measured/calculated | cyan solid/dashed + diamond | `M-` |
| Candidate/hypothesis | yellow dashed outline + triangle | `C-` |
| Unresolved/question | orange dotted outline + question mark | `U-` |
| Rejected/interference/blocker | red cross-hatch/outline + X | `X-` |
| Motion/kinematics | blue arrow | `K-` |
| Contact/interface target | magenta target/circle | `I-` |
| Reference only | gray thin outline | `R-` |

Color is presentation only. The prefix and text carry the semantic meaning.

## Annotation rules

1. Use exact SOLIDWORKS `Component2.Name2` identities when an annotation refers to a known component.
2. Place contact/interface markers adjacent to the visible surface and connect them with a leader; do not cover the geometry.
3. Motion arrows must state what moves, for example:
   - `K-01 PRODUCT_FLOW`
   - `K-02 BOTTLE_ROTATION`
   - `K-03 BELT_SURFACE_VELOCITY`
4. Unknown distances must not be drawn as numeric dimensions.
5. Candidate clearances may be shown only when backed by a deterministic measurement/calculation record.
6. Hidden geometry, compliance, forces, sequencing, and ownership must not be inferred from an image.
7. A `MECHANICALLY_ACCEPTED` label may be used only when that state is independently granted by the project acceptance process.
8. Historic captures retain their original assembly binding and date; never relabel an old image as a newer checkpoint.

## World and flow references

Where practical, include:

- world-coordinate triad;
- explicit product-flow arrow;
- camera/view identifier.

These references must be visually distinct from mechanical motion arrows.

## Question-for-AI block

A governed capture may include one bounded question:

```text
QUESTION FOR AI
Q-01:
<one narrowly scoped question>

DO NOT INFER:
<explicit hidden/unresolved relationships>
```

The question constrains interpretation; it does not change evidence state.

## Sidecar JSON minimum contract

Example:

```json
{
  "schema_version": "0.1",
  "view_id": "V43-CAPTURE-001",
  "source": "SOLIDWORKS_LIVE_STATE",
  "document_title": "IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE",
  "geometry_state": "CANDIDATE_OPERATING",
  "mechanical_acceptance_granted": false,
  "camera": "CAPTURE_OBLIQUE_01",
  "view_purpose": "capture_reaction_path",
  "annotations": [
    {
      "id": "I-01",
      "type": "contact_interface",
      "subject_a": "BENCH_BOTTLE_D48_H180-2",
      "subject_b": "FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1",
      "state": "UNRESOLVED"
    }
  ]
}
```

The sidecar is metadata about the capture and annotation layer. It is not mechanical evidence by itself.

## Initial v43 pilot

First governed pilot view:

`V43-CAPTURE-001`

Target visible region:

- Bottle 2;
- driven wrap belt;
- support rollers;
- v43 PRISM reaction/capture hardware;
- nearby hard-stop/indexing geometry when visible.

Initial bounded interpretation question:

> Does the visible geometry clearly communicate the intended bottle capture/reaction arrangement while keeping unresolved motion, compliance, and force-path claims explicitly unresolved?

Required status:

```text
ASSEMBLY: IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE
GEOMETRY_STATE: CANDIDATE_OPERATING
MECHANICAL_ACCEPTANCE: FALSE
SOURCE: SOLIDWORKS_LIVE_STATE
VIEW_PURPOSE: CAPTURE / REACTION PATH
```

## Acceptance criteria for v0.1

The overlay method is useful only if it:

- improves component/relationship identification;
- reduces ambiguity versus the RAW image;
- preserves exact source/checkpoint identity;
- does not obscure critical CAD geometry;
- does not cause annotations to be mistaken for evidence;
- makes UNKNOWN/UNRESOLVED visually explicit;
- allows the same semantic IDs to be reused in evidence records and later deterministic Blender renders.

