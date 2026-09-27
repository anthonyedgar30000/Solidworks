# CADGrounded.Tools

`CADGrounded.Tools` is the governed PowerShell engineering-command layer above the existing CADGrounded native SOLIDWORKS worker and project-state graph.

It is intentionally **not** a generic PowerShell agent and does not grant CAD write authority.

## Authority boundary

- SOLIDWORKS remains live geometry/state authority.
- GitHub remains versioned source/policy/test/reasoning authority.
- These commands are orchestration and evidence helpers.
- API/command success is not mechanical acceptance.
- `mechanical_acceptance_granted` remains false unless a separately governed acceptance process establishes it.
- Unknown remains unknown.

## Why this layer exists

An AI agent should not repeatedly reinvent low-level worker calls. It should ask bounded engineering questions through stable commands such as:

```powershell
Get-CGState
Get-CGComponentBinding
Test-CGContactPair
Test-CGTopologyChain
Get-CGMateBinding
Get-CGInvestigationFrontier
```

Higher-level bottle-labeler capabilities are registered separately and remain `PLANNED` until their deterministic primitives exist.

## Import

From the repository root:

```powershell
Import-Module .\agent-registry\powershell\CADGrounded.Tools\CADGrounded.Tools.psd1 -Force
```

The existing SQLite reasoning database (`agent-registry/reasoning-db/schema.sql`)
already indexes immutable EvidenceRecord IDs, exact record hashes, dependencies,
inspection fingerprints, and current validity projections. Do not create a
second evidence catalog. `agent-registry/reasoning/incremental_evidence.py`
populates this derived index from admitted records; JSON EvidenceRecords remain
the source of evidence. An index alone does not establish live CAD freshness.

For the offline PowerShell quality gate, install Pester 6 and PSScriptAnalyzer,
then run `agent-registry/tests/Test-PowerShellQuality.ps1` from the repo root.
The Pester tests replay one admitted snapshot and inject invalid authority and
state. The analyzer initially gates a narrow set of unsafe scripting patterns
in the governed module and its quality tests. The existing capability contract
remains a separate CI check.

Inspect the allowed surface:

```powershell
Get-CGCapabilityCatalog
Get-CGCapabilityCatalog -Status IMPLEMENTED
Get-CGCapability -Id cg.contact.pair
```

## Implemented commands

### Get-CGState

Reads exact current SOLIDWORKS document/configuration state through the native worker.
Each `sw.status` call is bounded to 15 seconds. After a timeout the command
terminates only its short-lived worker process, confirms exit, and makes at
most one new attempt. It never retries an ambiguous worker exit, invalid JSON,
or `no_active_document`. Other CAD commands are not retried. `Get-CGState`
requires two matching status reads and stable shared-read SHA-256 file evidence;
it fails with `STALE_STATE` if either binding changes. Its result includes
`data.file_state` and per-read `data.status_probes`. These observations do not
establish geometry or mechanical acceptance.

```powershell
Get-CGState -ExpectedConfiguration V43_WRAP
```

### Get-CGComponentBinding

Fails closed unless one exact `Component2.Name2` resolves.

```powershell
Get-CGComponentBinding -Name2 'FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1'
```

### Test-CGContactPair

Runs the reviewed `sw.classify_contact_pair` primitive against two exact component identities and performs pre/post document, component-state, and assembly-file comparisons.

```powershell
Test-CGContactPair `
  -AName2 'FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1' `
  -BName2 'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1' `
  -ExpectedConfiguration V43_WRAP
```

### Test-CGTopologyChain

Composes exact adjacent pair contact checks over an explicitly ordered chain. It does not infer that numbering or proximity implies mechanical pairing.

```powershell
Test-CGTopologyChain -Name2 @(
  'FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1',
  'FITCHECK_PRISM_LINK_15x10x25_V43-1',
  'FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1',
  'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1'
) -ExpectedConfiguration V43_WRAP
```

### Get-CGMateBinding

Queries active-assembly mate evidence for one or more exact components. Zero returned mates are retained as negative evidence; they are not converted into an inferred free DOF.

```powershell
Get-CGMateBinding -Name2 @(
  'FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1',
  'FITCHECK_PRISM_LINK_15x10x25_V43-1',
  'FITCHECK_PRISM_LINK_15x10x25_V43-2'
) -ExpectedConfiguration V43_WRAP
```


### Get-CGBottleContactConstraintMap

Projects admitted bottle contact-point and face-normal evidence into a mechanism-neutral first-order constraint map. It calculates lateral normal-line concurrence, positive compressive normal closure in assembly XY, and normal-force moment about the derived common-axis candidate.

By default it also requires the currently active assembly/configuration and assembly-file SHA-256 to match the admitted observation. Use `-EvidenceOnly` only for deterministic replay/CI of the admitted snapshot.

```powershell
Get-CGBottleContactConstraintMap -AsJson
```

This command deliberately does **not** establish gravity/up semantics, tilt restraint, frictional drive torque, preload, interval-wide contact, mechanism selection, or mechanical acceptance.

### Get-CGCurrentPlan / Get-CGInvestigationFrontier

Reads the durable GitHub project-state files from the checked-out repository.

```powershell
Get-CGCurrentPlan
Get-CGInvestigationFrontier
```

### Invoke-CGRegisteredVerifier

Runs only a verifier explicitly registered as `IMPLEMENTED`, `registered_verifier`, and `write_authority: NONE`. The caller cannot provide an arbitrary script path.

```powershell
Invoke-CGRegisteredVerifier -CapabilityId cg.verifier.v43.full-chain-mates
```

## Structured output

CAD-facing commands emit a common envelope with fields including:

- `capability_id`
- `result`
- `source_authority`
- `source_classification`
- `data`
- `establishes`
- `does_not_establish`
- `ambiguity_bucket`
- `mechanical_acceptance_granted`
- `model_mutation`
- `write_authority`

Use `-AsJson` when an external agent needs a JSON payload.

## Capability maturity

The registry deliberately distinguishes:

- `IMPLEMENTED` — reviewed callable surface exists.
- `PLANNED` — desired engineering question is registered, but required deterministic primitives are incomplete.
- `BLOCKED` — a capability cannot be executed until its declared blocker is resolved.

Examples currently registered as planned include bottle restraint, product entry/exit paths, wrap contact, peel-edge binding, label-transfer path, hard-stop/indexing, reaction-path evidence, motion candidates/sweeps, mechanical acceptance, and the visualization gate.

An agent must never substitute a generic shell command or an LLM guess for a `PLANNED` CADGrounded capability.

## Agent usage rule

A local agent such as Copilot may:

1. read `Get-CGInvestigationFrontier`;
2. inspect `Get-CGCapabilityCatalog -Status IMPLEMENTED`;
3. choose a permitted diagnostic command;
4. execute it;
5. consume the structured result;
6. update a proposal or investigation state only within its authority.

It may not convert unresolved evidence into verified geometry, authorize CAD writes, declare mechanical acceptance, or open the visualization gate.
