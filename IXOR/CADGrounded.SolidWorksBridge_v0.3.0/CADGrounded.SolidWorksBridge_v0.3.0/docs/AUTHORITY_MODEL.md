# Authority Model — v0.1

The bridge is designed around the CAD-grounded visualization project's authority rules.

## Source classes

Bridge outputs should be interpreted as follows:

- **verified_from_solidworks_api** — a state value read directly from the live SOLIDWORKS document or component API.
- **approximate_from_solidworks_getbox** — a `Component2.GetBox(false,false)` envelope; useful for orientation/sanity checks, not precision metrology.
- **requested_transform** — a transform supplied by the caller. It is a command/proposal, not source evidence.
- **applied_and_reverified** — a requested transform that SOLIDWORKS accepted, rebuilt, and then returned within the bridge tolerance.
- **calculated_elsewhere** — deterministic engineering/calculation input supplied to the bridge; its provenance must be maintained outside the bridge.
- **inferred/hypothetical** — not a geometry authority and must never be silently promoted by this bridge.

## Read/write separation

Read tools may report actual state. Write tools may alter state, but a successful write only establishes that SOLIDWORKS accepted the requested state. It does not prove mechanical correctness.

## Transform write invariant

`sw_set_transform` uses compare/rebuild/re-read behavior:

```text
read before
   |
validate request
   |
if apply=true: require expected document title
   |
if apply=true: require + compare complete expected_before
   |
if apply=false -> return proposal only
   |
if writes disabled -> reject
   |
if component fixed -> reject
   |
assign exact SOLIDWORKS MathTransform
   |
rebuild
   |
read after
   |
compare requested vs actual
   | PASS                       | FAIL
   v                            v
return applied_and_reverified   rollback before transform
                                rebuild
                                return failure
```

## Mechanical authority

The bridge must never report an API operation as evidence that:

- the assembly architecture is mechanically correct;
- a component has the correct OEM identity unless identity has been established independently;
- clearances are valid;
- a conveyor path is valid;
- label-web routing is valid;
- contact physics is valid;
- a bottle can pass unobstructed;
- the configuration is OEM-recommended.

Those require the project's deterministic CAD/mechanical gates.

## Audit log

Applied transform attempts are written to:

```text
%LOCALAPPDATA%\CADGrounded\SolidWorksBridge\audit.jsonl
```

Each record includes UTC time, method, component, before state, requested transform, after state (if available), and success/failure/rollback information.
