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
- `test_reasoner.py` — sanity tests.

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

The next useful addition is an **evidence transaction** rather than more prompting:

1. the planner requests an investigation;
2. a deterministic/tool adapter performs it;
3. evidence is written as a candidate transaction;
4. authority policy validates the transaction;
5. the graph is updated;
6. project health is recomputed.

That is the point where this PoC can connect cleanly to the SOLIDWORKS bridge without giving the LLM authority over engineering truth.
