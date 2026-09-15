# CADGrounded Puzzle Solver v0

## Purpose

Treat CAD reasoning as a constrained puzzle rather than as unconstrained model manipulation.

The planner may propose hypotheses, measurements, and candidate moves. It does not establish geometric truth and it does not gain CAD write authority. SOLIDWORKS remains the geometry authority, the registry remains the coordination/audit authority, and the verifier/policy layer decides which operations are admissible.

## Core loop

```text
Observe live state
    -> encode facts + evidence class
    -> propagate hard constraints
    -> identify unknown facts
    -> choose highest-information safe read
    -> re-observe
    -> if goal is known and satisfied: SOLVED
    -> if a hard constraint is violated: BLOCKED
    -> otherwise rank candidate moves
    -> emit proposal only
    -> future protected executor may apply one move
    -> post-write live verification
```

This is deliberately closer to CSP/SAT/search/game solving than to generative CAD.

## Puzzle techniques borrowed

### Constraint propagation

Known facts eliminate impossible actions before search. A candidate that violates a hard constraint is rejected, not merely given a worse score.

### Most-constrained / information-first search

When required facts are unknown, prefer a read that resolves the most goal or constraint predicates at the lowest cost. In v0 this means exact SOLIDWORKS measurements beat speculative movement.

### Branch and bound / A*-style cost

Candidate moves can be ranked by a deterministic cost function such as:

```text
cost =
    translation_mm * movement_weight
  + rotation_deg * rotation_weight
  + modified_components * change_scope_weight
  + risk_penalty
  + uncertainty_penalty
```

Lower-cost candidates are considered first, but cost never overrides a hard constraint.

### State hashing / transposition avoidance

A later solver can hash a normalized state (document revision + relevant transforms + verified measurements) so the same failed state is not explored repeatedly.

### Proof obligations

Every executable action should eventually carry:

- exact document/revision precondition
- uniquely resolved components
- required measurements and their provenance
- hard-constraint verdicts
- expected state transition
- post-action verification plan

The planner proposes. The verifier owns the proof obligations.

## Evidence classes

From weakest to strongest for the current benchmark:

1. `inferred` — planner hypothesis only.
2. `approximate_getbox` — SOLIDWORKS `Component2.GetBox`; useful for screening only.
3. `verified_solidworks_api` — direct typed API measurements such as `ClosestDistance` and `ToolsCheckInterference2`.
4. `human_mechanical_review` — external engineering/mechanical judgment where required.

A weak evidence class must not satisfy a predicate that explicitly requires a stronger class.

## v0 action classes

### Safe reads

- `sw.status`
- `sw.query_components`
- `sw.check_interference_pair`

These can resolve puzzle facts.

### Proposal-only moves

Examples:

- translate a component by a bounded delta
- rotate a component by a bounded delta
- choose a different contact candidate

The v0 solver may rank these but does not submit them to the registry.

### Future protected writes

`sw.set_transform` remains outside v0. When enabled later it must require fresh state, revision/lease/fencing checks, compare-and-set component preconditions, bounded transforms, and post-write verification.

## IXOR v18 first puzzle

Goal:

> Establish valid AR60 wipe-down contact with Bottle 3 while avoiding physical interference with the conveyor and Bottle 4.

Current screening evidence says Bottle 3 is the unique nearby contact candidate, but approximate AABB overlap is not enough to establish contact. Therefore the first solver move is exact read-only measurement using `sw.check_interference_pair`.

The solver should gather these exact facts before proposing any transform:

1. AR60 vs Bottle 3 classification + minimum distance.
2. AR60 vs conveyor classification + minimum distance.
3. AR60 vs Bottle 4 classification + minimum distance.

Only after those predicates are known may a movement proposal be ranked.

## Authority boundary

The important invariant is:

```text
creative search != execution authority
```

The puzzle solver may become increasingly sophisticated without widening the worker allowlist. Search intelligence and execution authority should evolve independently.
