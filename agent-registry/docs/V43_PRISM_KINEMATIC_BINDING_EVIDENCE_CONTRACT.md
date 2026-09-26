# V43 Prism Kinematic-Binding Evidence Contract

## Purpose

This is the execution contract for the next temporal-ledger investigation step: acquire a bounded, local-native observation of the incident mates for the live V43 Prism carrier, link, and arm.

It is a preparation artifact only. No V43 mate observation has been executed or admitted by adding this contract.

## Authority and execution boundary

| Topic | Authority / boundary |
| --- | --- |
| Live geometry, active document, active configuration | SOLIDWORKS |
| Source, policy, evidence contract, and later admitted result | GitHub |
| Command | Local Windows-host worker command `sw.query_mates` |
| Write authority | `NONE` |
| Model mutation | Required to be `false` on every query |
| Remote Queue | Not authorized and not used |
| Forbidden actions | Move, rebuild, save, mate creation/editing, suppression changes, selection changes |

The bounded adapter exposed to this conversation does not provide mate reads. The host script exists so this observation can be independently verified without using the broad maximum-control code surface as a substitute.

## Exact planned target set

- `FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1`
- `FITCHECK_PRISM_LINK_15x10x25_V43-1`
- `FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1`

Required live document:

- Title: `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`
- Path: `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`

The active configuration is recorded before and after. It is only an execution precondition when an operator supplies `-ExpectedConfiguration`; this contract deliberately does not infer `V43_WRAP` from the unadmitted PR #23 narrative.

## Host execution

Run on the SOLIDWORKS Windows host from the worker directory:

```powershell
.\Verify-QueryMates-V43-Prism.ps1
```

The script builds the worker unless `-SkipBuild` is explicitly supplied, then requires:

1. Worker version `0.4.2`.
2. Exact active document title and path.
3. Worker and every mate result to report `write_authority: NONE`.
4. Every mate result to report `model_mutation: false`.
5. Exact resolution of each target component.
6. Before/after equality for target transform/state, active-document identity/configuration/save state, and assembly-file hash/length/timestamp.

A failed assertion produces no PASS evidence artifact.

## Expected evidence output

The script writes:

`verification-output\query-mates-v43-prism\verification-summary.json`

A PASS summary emits `executed_at_utc` after all no-mutation checks complete. A candidate result must retain the raw per-component mate responses alongside the summary. Before it is admitted into the temporal planning ledger, the result must be anchored with its execution timestamp, worker version, exact document identity, observed configuration, and a durable GitHub commit or attached artifact hash.

## What a PASS establishes

A PASS establishes only:

- the exact component identities and observed parent chains;
- the incident active-assembly mate identities, types, and suppression state as returned by the local worker;
- reported mate variation values when exposed;
- no observed document/configuration/save-state, selected target transform/state, or assembly-file change across the read.

## Non-claims

A PASS does not establish:

- physical closure owner or contact/clearance;
- preload, force, stiffness, or contact pressure;
- operating motion, reachable envelope, timing, capture, or release;
- reaction force path;
- mechanical acceptance.

Any later functional conclusion remains conditional until the separately required stroke/closure and reaction-path evidence is acquired and admitted.
