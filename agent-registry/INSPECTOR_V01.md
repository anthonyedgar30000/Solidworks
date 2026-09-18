# CADGrounded SOLIDWORKS Inspector v0.1

This is the read-only persistence and decision core for the Inspector Task Pane.
It is deliberately separate from the Remote Queue runner and does not expand its
authority.

## Authority boundary

The runtime accepts an observer envelope only when all of the following are true:

- the envelope is successful;
- `source_classification` is `verified_from_solidworks_api`;
- `write_authority` is exactly `NONE`;
- a document title and unique exact `Component2.Name2` values are present.

It never opens SOLIDWORKS, sends a CAD request, changes geometry, marks a
mechanism accepted, or lets an LLM promote a claim to verified.

## First vertical slice

`inspector_runtime.py snapshot` stores an immutable inspection run containing:

- document identity and active configuration;
- exact component identities, paths, parent names, fixed/suppression state, and transforms;
- a deterministic state fingerprint;
- the hash of the received observer envelope.

The same fingerprint reuses the existing run.  A new fingerprint compares its
component snapshot to the preceding run and returns the exact `Name2` values
whose dependent claims require invalidation.

The database schema additionally has explicit tables for:

- ontology and glossary terms;
- exact identity bindings;
- operating states and state-scoped relationship expectations;
- constraints and invariants;
- Allen/RCC8 qualitative relations;
- immutable observations/assertions/derivations;
- claim dependency edges and discovery signals.

## Run locally

Create a world once with `reasoning-db/reasoning_db.py`, then pass a completed
read-only component observer envelope to the Inspector:

```powershell
python .\reasoning-db\reasoning_db.py --db .\reasoning-db\reasoning.db init

python .\inspector_runtime.py --db .\reasoning-db\reasoning.db snapshot `
  --world ixor-v42 `
  --input .\completed-components-observation.json
```

Rank pre-declared investigative tests with the deterministic project formula:

```text
dependency centrality × discrimination power × evidence confidence × unresolved relevance ÷ cost
```

```powershell
python .\inspector_runtime.py rank-next-test --input .\test-candidates.json
```

## Next integration step

The Task Pane should invoke the existing read-only observer, pass its completed
snapshot to this runtime, then render the returned run ID, evidence provenance,
invalidated claims, constraints/invariants, Allen state model, and highest-value
next test.  Task Pane controls must remain inspection controls; they must not
route to transform, insert, or execute-code methods.
