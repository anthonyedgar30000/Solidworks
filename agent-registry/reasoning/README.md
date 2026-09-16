# HELIX Epistemic Project-Health PoC

This is a deliberately small proof-of-concept for the reasoning architecture we discussed.

It models a project as a graph of:

- facts,
- unresolved (`NULL`) values,
- derived claims,
- constraints/invariants,
- acceptance obligations,
- provenance/authority,
- dependency relationships,
- optional Allen temporal relations.

The important idea is that **a NULL is not treated as an empty hole**. The graph around it lets the system determine what project obligations are exposed by not knowing that value.

## Files

- `graph.json` — small IXOR/AR60 example knowledge graph.
- `reasoner.py` — deterministic project-health and exposure propagation.
- `ollama_worker.py` — optional local LLM planner; it can choose the next investigation but cannot verify facts.
- `evidence_ingest.py` — validates and normalizes completed read-only `sw.query_components` observations into evidence transactions.
- `v21_identity_bindings.json` — exact v21 semantic-role to `Component2.Name2` bindings.
- `identity_bindings.py` — validates those exact bindings against admitted live SOLIDWORKS evidence.
- `geometry_projection.py` — calculates conservative AABB relations from admitted exact-identity evidence.
- `test_reasoner.py` — reasoner regression tests.
- `test_evidence_ingest.py` — evidence-boundary regression tests.
- `test_identity_bindings.py` — exact identity binding regression tests.
- `test_geometry_projection.py` — deterministic AABB projection regression tests.

## Run

From this directory:

```powershell
python .\reasoner.py .\graph.json
```

For machine-readable output:

```powershell
python .\reasoner.py .\graph.json --json
```

Run tests:

```powershell
python -m unittest -v
```

If Ollama is running locally:

```powershell
ollama pull qwen2.5:3b
python .\ollama_worker.py .\graph.json --model qwen2.5:3b
```

The Ollama worker defaults to:

```text
http://127.0.0.1:11434/api/chat
```

## Ingest a live read-only SOLIDWORKS observation

Given a completed CADGrounded `sw.query_components` envelope such as:

```text
C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\LIVE_CAD_ALL_COMPONENTS.json
```

run:

```powershell
python .\evidence_ingest.py `
  "C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\LIVE_CAD_ALL_COMPONENTS.json" `
  --expected-document "IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE" `
  --out .\runtime\v21-components-evidence.json `
  --summary
```

The importer admits only a completed `sw.query_components` observation with no reported error, validates component count and exact `Component2.Name2` identity, preserves transform/GetBox/provenance fields, and records a SHA-256 of the raw observation.

A successful import grants **observation authority only**. It explicitly does not establish valid contact, clearance, mechanical suitability, operating sequence, or project acceptance.

## Bind v21 semantic roles to exact live SOLIDWORKS identities

After the evidence transaction exists, run:

```powershell
python .\identity_bindings.py `
  .\runtime\v21-components-evidence.json `
  .\v21_identity_bindings.json `
  --out .\runtime\v21-identity-evidence.json `
  --summary
```

The binding stage requires each configured `Component2.Name2` to match **exactly one** admitted component. Missing or duplicate exact identities are rejected. It copies observed transform/GetBox/provenance fields into the role record but still grants **no mechanical acceptance**.

The current v21 role registry includes the exact live identities for the IXOR head, SP100, AR60 roller, AR carriage, GHF120, tie rod, two mounting rods, conveyor, and five deterministic bottles.

## Project deterministic geometry facts

After exact identity binding succeeds, run:

```powershell
python .\geometry_projection.py `
  .\runtime\v21-identity-evidence.json `
  --out .\runtime\v21-geometry-projection.json `
  --summary
```

This stage performs deterministic arithmetic on the admitted GetBox-derived approximate axis-aligned bounding boxes. It reports observed transforms/envelopes, per-axis AABB gaps, minimum AABB separation, and AABB overlap relations.

Its authority is intentionally bounded:

- AABB overlap is **not** body interference.
- AABB separation is **not** exact surface clearance.
- It does not establish contact, seating, restraint, product flow, operating sequence, or functional suitability.
- It never grants mechanical acceptance.

The point is to replace toy geometry facts with reproducible calculations while preserving stronger mechanical claims as unresolved until a suitable deterministic SOLIDWORKS check exists.

## Expected initial result

The graph intentionally leaves `AR60_CONTACT_POSITION` unresolved.

The deterministic reasoner should therefore conclude approximately:

```text
PROJECT: IXOR v21 epistemic project-health proof of concept
OVERALL STATE: EXPOSED
KNOWN VIOLATIONS: none
```

The key distinction is:

- the project is **not proven failed**;
- the project is **not ready to advance**;
- a critical unresolved field has a risk footprint that propagates into
  `NO_CONVEYOR_INTERFERENCE`,
  `BOTTLE_CONTACT_ACHIEVABLE`,
  `VALID_APPLICATION_GEOMETRY`,
  and ultimately `V21_ACCEPTANCE`.

Meanwhile `PAINT_COLOUR = NULL` remains unresolved but has no acceptance exposure.

That demonstrates the architecture's central idea:

> Unknownness is evaluated by the project obligations it places at risk, not merely by counting missing fields.

## Evidence insertion rule

Do not let the LLM edit a NULL into a known value merely because it guessed one.

A field should transition from:

```json
{
  "value": null,
  "state": "NULL"
}
```

to something such as:

```json
{
  "value": 270.0,
  "state": "KNOWN",
  "authority": "SOLIDWORKS_MEASUREMENT"
}
```

only after authoritative evidence or an accepted deterministic derivation is available.

## Next architectural increment

The next useful addition is graph admission from deterministic projection output:

1. admit live SOLIDWORKS observations;
2. resolve exact semantic identities;
3. calculate bounded deterministic geometry relations;
4. project only supported observations/calculations into graph facts;
5. preserve contact/clearance/operating claims as `NULL` unless separately proven;
6. run dependency/exposure propagation;
7. choose the next read-only investigation based on remaining risk exposure.

This preserves the boundary that SOLIDWORKS observations establish live state, deterministic checks establish mechanical relationships, and LLMs only help select or formulate investigations.
