# CADGrounded Interface Consumption & Live Verification v1

## Purpose

This v1 architecture consumes a declared CAD interface contract through a bounded local native observation, detects drift without silently rewriting the contract, and calculates a disposable complementary-asset frame proposal.

It is not a CAD editing workflow. No component is inserted, transformed, mated, suppressed, saved, rebuilt, or otherwise modified by this architecture.

## Evidence contract

The source contract remains `reasoning/reference_cases/v42_product_flow.cad-interface-contract.v1.json`. It records the intended semantic pairing:

| Interface | Published Reference | Coordinate system |
| --- | --- | --- |
| `V42.PRODUCT_ENTRY` | `Connector2` | `PRODUCT_ENTRY_CS` |
| `V42.PRODUCT_EXIT` | `Connector1` | `PRODUCT_EXIT_CS` |

The local worker command is `sw.query_interface_contract`.

Its request requires exact coordinate-system feature names and exact connector feature names. It returns only exact matching `CoordSys` transform records and `MagneticConnectRef` name/type records. A missing, duplicate, wrong-type, or unreadable target fails closed. The command is in the C# worker's local read-only allowlist only; it is not a `CADRequest`, is not in either Remote Queue allowlist/schema, and has `write_authority: NONE`.

The command uses a bounded `IFeature` traversal and `IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData` getter chain for `CoordSys` features. It does not call a generic execute-code interface.

When exact Published Reference discovery fails, the separate local-only
`sw.diagnose_interface_connectors` command compares
`IAssemblyDoc.FeatureByName("Connector1"/"Connector2")` with that recursive
traversal. It records direct name/type results and any traversal observation of
`ConnectRefMgr`, `Connector1`, or `Connector2`, including parent/tree depth. A
direct exact `MagneticConnectRef` with no traversal match is reported as
`DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT`; it is diagnostic evidence only and does
not silently change the exact reader. If neither path observes a connector, it
is `LIVE_STATE_SOURCE_CONFLICT`, not connector evidence.

## Live verifier outcome states

`reasoning/cad_interface_live_verifier.py` validates the source contract, then compares one fresh worker envelope without updating either source of truth.

| Result | Meaning | Required response |
| --- | --- | --- |
| `VERIFIED_CURRENT` | Exact document, requested feature identities/types, and coordinate-system transforms match the declared baseline within tolerance. | It is eligible only as an input to deterministic frame calculation. |
| `STALE_STATE` | No fresh native feature/frame observation was supplied. | Do not consume the old frame as current live state. |
| `DRIFT_DETECTED` | The document or an observed feature/frame differs from the declared contract. | Stop propagation; review live state and dependency graph before any rebaseline. |
| `AUTHORITY_REJECTED` | Source classification, command scope, write/mutation declaration, or observation scope is invalid. | Reject the observation. |
| `OBSERVATION_REJECTED` | Required observation fields are absent or internally inconsistent. | Reject the observation. |

The Windows host script `Verify-InterfaceContract-V42.ps1` adds a no-mutation gate: exact active document/configuration/save flag, stable shared-read assembly-file evidence, and complete component state are compared before and after the connector diagnostic and the local interface query. `sw.diagnose_interface_connectors.raw.json` and `connector-diagnostic-summary.json` are written before the unchanged exact interface query runs, so they remain available if that query fails closed. A successful script result is an evidence artifact for review, not an automatic `EvidenceRecord` admission or mechanical acceptance.

## Authority and unresolved geometry

- SOLIDWORKS remains the authority for a fresh assembly, named feature identity, and coordinate-system transform state.
- The Published Reference semantic role retains its human-observation authority.
- Deterministic code may calculate a transform only from accepted frame inputs.
- GitHub source/tests describe policy and are not live CAD evidence.
- Remote Queue authorization remains `NONE` for the new command.

The v1 native query cannot read the physical geometry behind a `MagneticConnectRef`. Therefore Published Asset ↔ coordinate-system geometric coincidence remains `UNRESOLVED`, even when the named connector and named coordinate system are both observed in the same document. Neither API success, a static zero distance, a mate, nor coordinate-frame alignment changes that state.

## Disposable complementary asset test

`reasoning/reference_cases/v42_disposable_complementary_asset_interface_test.v1.json` defines a design-only receiver asset with a local identity connection frame. It is deliberately marked:

```json
{
  "cad_write_authorized": false,
  "materialization_state": "NOT_AUTHORIZED",
  "remote_queue_authorized": false,
  "mechanical_acceptance_granted": false
}
```

`reasoning/cad_interface_consumption.py` uses the existing SOLIDWORKS row-vector transform convention. If `C` maps the complementary asset's local connection frame into asset coordinates and `T` maps the target interface into world coordinates, it calculates:

```text
T_asset_to_world = inverse(C) * T_target_interface_to_world
```

For the v42 identity-frame test, the proposed asset-to-world transform equals the declared `PRODUCT_EXIT_CS` transform. That is a deterministic result from the declared baseline, not fresh live proof. Until the native verifier produces `VERIFIED_CURRENT`, its current-live-frame state is `STALE_STATE`; even then, materialization still needs separate explicit CAD-write authorization.

Frame alignment does not establish connector coincidence, snap/mate behavior, contact, clearance, interference absence, support, degrees of freedom, force, preload, temporal operating behavior, or whole-machine mechanical acceptance.

## Regression coverage

- `test_cad_interface_live_verifier.py` covers stale evidence, document/type/transform drift, source/mutation rejection, required-field failure, bounded result scope, and the preserved geometry-coincidence boundary.
- `test_cad_interface_consumption.py` proves transform composition and inverse algebra, the v42 declared transform, and non-authorization after a fresh frame check.
- `Test-InterfaceContractEvidence.ps1` exercises strict PowerShell normalization of a local worker envelope.
- `Test-InterfaceConnectorDiagnosticEvidence.ps1` exercises strict direct-lookup/traversal diagnostic normalization without promoting connector evidence.
- GitHub Actions compiles the Windows worker and runs the PowerShell normalization tests, plus deterministic Python tests.
