# CADGrounded Visual Evidence Overlay v0.2

Status: **candidate visualization/inspection contract**

Supersedes the visualization conventions in v0.1 for new overlay work.  
v0.1 remains preserved as historical design input.

## Purpose

Define a repeatable visual annotation language for deterministic CAD captures so a human or AI reviewer can distinguish:

- exact verified component identity;
- measured/calculated relationships;
- candidate interfaces;
- verified contact evidence;
- unresolved motion/compliance/force-path questions;
- rejected/interference conditions;
- reference-only geometry;
- camera/projection limitations.

The overlay is a semantic derivative of authoritative CAD. It is not engineering geometry authority and cannot grant mechanical acceptance.

## Core authority rule

A visual annotation may describe or point to evidence, but it may not create stronger evidence than its underlying deterministic source.

In particular:

- apparent 2D tangency is not 3D contact evidence;
- a candidate-interface target is not a verified contact;
- a motion arrow is not kinematic proof;
- a reaction arrow is not a verified force path;
- a grouped annotation does not establish internal kinematic ownership.

## Canonical artifact set

Each governed evidence view SHOULD have:

- `<VIEW_ID>_RAW.png`
- `<VIEW_ID>_OVERLAY.png`
- `<VIEW_ID>.json`

RAW and OVERLAY must use the same deterministic scene and camera.

## Required header

```text
CADGROUNDED VISUAL EVIDENCE
ASSEMBLY: <exact document title>
CONFIGURATION: <exact configuration>
VIEW_ID: <stable id>
GEOMETRY_STATE: <lifecycle state>
MECH_ACCEPTANCE: <TRUE|FALSE>
SOURCE: <authority/classification>
CAMERA: <camera/view id>
PROJECTION: <projection class>
VIEW_PURPOSE: <bounded purpose>
```

## Required view-limitation field

Every overlay sidecar MUST declare a bounded limitation statement.

Example:

```json
{
  "view_limitations": [
    "front orthographic projection compresses depth",
    "apparent tangency is not accepted as 3D contact evidence"
  ],
  "contact_acceptance_from_image": false
}
```

## Visual vocabulary

Do not rely on color alone.

| Meaning | Preferred visual treatment | ID prefix |
|---|---|---|
| Verified identity/source geometry | green solid outline + filled circle | `V-` |
| Measured/calculated | cyan dashed/solid + diamond | `M-` |
| Candidate/hypothesis | yellow dashed outline + triangle | `C-` |
| Unresolved/question | orange dotted outline + question mark | `U-` |
| Rejected/interference | red outline/cross-hatch + X | `X-` |
| Motion/kinematic intent | blue directional arrow | `K-` |
| Interface/contact locus | magenta target | `I-` |
| Reference-only | gray thin outline | `R-` |

## Interface/contact evidence-state rule

Every `I-` annotation MUST display its evidence state inline.

Examples:

```text
I-01  CANDIDATE / UNRESOLVED
I-02  VERIFIED_CONTACT
I-03  DISPROVEN
```

A bare `I-01 INTERFACE` label is not permitted.

### Candidate interface rendering

- hollow magenta target;
- label includes `CANDIDATE / UNRESOLVED`;
- sidecar contains `evidence_state = UNRESOLVED`;
- must include a statement equivalent to `contact not asserted`.

### Verified contact rendering

A contact may be rendered as verified only when an admitted deterministic source establishes the relationship.

Verified-contact rendering SHOULD differ visibly from candidate rendering, for example:

- solid/double magenta target;
- label `VERIFIED_CONTACT`;
- provenance to exact CAD evidence record / verifier artifact.

The image itself is never the verification source.

## Identity rule

Use exact SOLIDWORKS `Component2.Name2` identities when available.

Human-friendly aliases may be shown, but the sidecar MUST retain the exact identity.

## Group annotation rule

A grouped annotation such as a mechanism envelope or subsystem MUST list its exact included members in the sidecar.

Example:

```json
{
  "id": "V-05",
  "type": "component_group",
  "alias": "PRISM reaction/capture set",
  "members_name2": [
    "FITCHECK_PRISM_REACTION_BASE_70x120x20_V43-1",
    "FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-1"
  ]
}
```

Do not use a grouped label to imply motion ownership or restraint function.

## Motion rule

Every motion arrow MUST state:

- subject;
- motion meaning;
- evidence state.

Example:

```text
K-01  PRODUCT_FLOW  VERIFIED_FROM_INTERFACE_FRAME
K-02  CAPTURE_CLOSURE  UNRESOLVED
```

## Force/reaction rule

Reaction-force arrows are prohibited unless supported by a stated deterministic mechanics model or accepted evidence.

Otherwise show the question as unresolved:

```text
U-03  REACTION_FORCE_PATH ?
```

## Projection/contact rule

Orthographic or perspective screenshots may support:

- identity;
- topology/orientation communication;
- review focus;
- hypothesis localization.

They may not alone establish:

- B-rep contact;
- tangency;
- clearance;
- interference;
- trimmed-face overlap;
- force path;
- preload;
- restraint sufficiency.

When those matter, the next test must use exact CAD/B-rep or accepted deterministic calculation.

## Coordinate context

When motion, flow, or directional relationships are under review, include:

- world-coordinate triad where practical;
- product-flow arrow as a separate semantic object.

Never conflate product flow with a world axis.

## Registration provenance

The sidecar SHOULD record how each annotation was registered.

Allowed examples:

- exact component transform projected into known camera;
- exact selected component + fixed camera;
- deterministic landmark registration;
- manually placed semantic callout anchored to a verified visible component.

The sidecar SHOULD distinguish:

```text
REGISTRATION_VERIFIED
REGISTRATION_APPROXIMATE
REGISTRATION_MANUAL
```

## Bounded Question-for-AI block

A capture MAY include:

```text
QUESTION FOR AI
Q-<n>: <specific bounded question>

DO NOT INFER:
<explicit exclusions>
```

The question should target visual interpretation, ambiguity detection, or test selection—not invite mechanical invention.

## Minimum sidecar additions in v0.2

```json
{
  "projection": "ORTHOGRAPHIC_FRONT",
  "contact_acceptance_from_image": false,
  "view_limitations": [],
  "registration_state": "REGISTRATION_VERIFIED",
  "annotations": [
    {
      "id": "I-01",
      "type": "interface_locus",
      "evidence_state": "UNRESOLVED",
      "contact_asserted": false
    }
  ]
}
```

## v43 pilot lesson

The first bounded v43 Front-view pilot demonstrated that semantic overlays substantially improve component-role interpretation, but also showed that apparent tangent relationships in a 2D projection can be mistaken for contact evidence.

Accordingly:

- identity overlays may be verified from exact live CAD identity;
- interface loci remain unresolved until deterministic contact evidence is admitted;
- Front-view screenshots are communication aids, not contact-acceptance tools;
- PRISM members should be individually identified when kinematic ownership is investigated.

## Acceptance condition for the overlay system

The overlay system is useful only if it:

1. improves interpretation;
2. preserves exact identity/provenance;
3. makes uncertainty more visible rather than less;
4. keeps RAW and OVERLAY separable;
5. never upgrades evidence from pixels alone;
6. routes geometry/contact questions back to deterministic CAD tests;
7. preserves mechanical acceptance as an independent gate.
