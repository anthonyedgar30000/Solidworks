# CADGrounded Epistemic Model v0

CADGrounded should distinguish truth from awareness.

## Four epistemic buckets

| Bucket | Meaning in CADGrounded | Example |
|---|---|---|
| Known-known | The fact is modeled and has evidence-backed value. | `ar60_bottle3.classification = clearance` |
| Known-unknown | The fact is modeled but its value is not yet known. | `ar60_bottle3.classification = null` |
| Unknown-known candidate | Evidence/value exists in runtime state, but the puzzle never declared the fact. | A component path is available in a snapshot but the planner never modeled component identity. |
| Unknown-unknown | The fact/question itself is absent from the model. It can only be inferred through an anomaly, contradiction, ambiguity, or unexpected observation. | A hidden nested bracket causes interference although no bracket-related fact exists. |

`null` therefore means a **known unknown**, not a generic failure and not `false`.

## Discovery transition

Unknown unknowns cannot be directly stored as facts because, by definition, the model does not yet know what the fact is.

The safe transition is:

```text
unexpected observation
        ↓
discovery trigger
        ↓
form discovery question
        ↓
create new modeled fact with value = null
        ↓
known unknown
        ↓
bounded read / measurement
        ↓
known known
```

This is model expansion, not normal search.

## Discovery triggers

`epistemic-audit.py` currently recognizes:

- document identity mismatch
- ambiguous component selectors
- unexplained observations
- conflicting evidence histories
- explicit anomaly events such as unexpected interference or verifier contradiction

A trigger is not proof that a particular missing fact exists. It is evidence that the current puzzle model may be incomplete and should enter discovery mode.

## Unknown-knowns

The practical CAD meaning of an unknown-known is usually **orphan evidence**: data exists in a state/evidence package but has not been promoted into the declared puzzle model.

Examples:

- exact `Name2` already observed but the solver still uses a broad substring
- source path already returned by SOLIDWORKS but identity matching ignores it
- a previous exact distance exists in a state snapshot but the goal still appears unknown

The audit reports undeclared state facts with non-null values as `unknown_known_candidates`.

## Latent knowns

The audit separately reports `latent_known` facts: modeled facts with values that are not currently referenced by goals, hard constraints, candidate-move preconditions, or knowledge-action outputs. These are not necessarily bugs; they are facts the current reasoning path is not consuming.

## Current IXOR lesson

A read requested selector `AR60` while the active assembly was:

`IXOR_Benchmark_v21_AR60_CARRIAGE_FIT_CHECK_PORTABLE`

Two top-level components matched because one virtual floor-stand component's `Name2` inherited the assembly title containing `AR60`, while the actual wipe-down roller was:

`6130460_03_AR60_NATIVE_PORTABLE_V18-2`

The worker refused to choose between the two. That is the desired behavior.

Epistemically, this produced two discovery signals:

1. **Selector ambiguity** — component identity was under-modeled.
2. **Document drift** — a puzzle originally framed around v18 was being evaluated while v21 was active.

The correct response is not to weaken uniqueness. It is to strengthen identity and scope assumptions.

## Safety invariant

Discovery can expand questions and evidence requirements. It does **not** expand execution authority.

```text
Discovery engine
      │
      ├── may add known-unknown facts
      ├── may request approved reads
      └── may invalidate a puzzle as incomplete

      X may not grant itself CAD write authority
```

The verifier/registry authority model remains independent.
