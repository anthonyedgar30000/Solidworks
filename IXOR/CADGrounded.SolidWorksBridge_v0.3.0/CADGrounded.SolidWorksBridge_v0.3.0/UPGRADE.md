# Install v0.3.0

This is an updated **source package**, not an already-installed or precompiled bridge.
It adds `sw_insert_component`. The three existing commands remain available.

## Windows installation

1. Extract this ZIP into a new folder. Keep the old v0.1.1 folder for rollback.
2. Save your SOLIDWORKS documents and close SOLIDWORKS. Stop the old Node MCP server
   with Ctrl+C in its PowerShell window. The tunnel can remain running.
3. Open PowerShell **as Administrator** in the new folder containing this file. Run:

   ```powershell
   .\scripts\upgrade.ps1
   ```

   This installs the existing Node dependency versions, runs the Node tests, builds
   against your installed SOLIDWORKS interop DLLs, and registers the new add-in DLL.
   It stops on build failure; do not continue if it reports an error.
4. Reopen SOLIDWORKS, enable CADGrounded in Add-Ins if necessary, and open v12.
5. Start the new server from the new package folder (ordinary PowerShell is sufficient):

   ```powershell
   .\scripts\start-server.ps1 -AllowWrites
   ```

6. In another window, `Invoke-RestMethod http://127.0.0.1:8765/health` should report
   version `0.3.0`. Ask ChatGPT to run `sw_status`; the add-in must ALSO report `0.3.0`.
   Refresh/rescan the custom app's tools if `sw_insert_component` is not yet exposed.
   The MCP endpoint and named pipe are unchanged.

## First use: the MS25 rods

Save the uploaded OEM rod STEP as `MS25_6120069_NATIVE.SLDPRT` once in SOLIDWORKS.
This release accepts native `.SLDPRT` and `.SLDASM`; STEP import and macro execution
are not supported. The native source must have no unsaved changes. Existing open
sources must have the requested configuration active (default request: `Default`).

Keep v12 active. Tell ChatGPT the native rod's full Windows path. It can then:

1. Read status and component state.
2. Call `sw_insert_component` with `apply=false`, the exact active document title/path,
   the native `source_path`, `configuration`, current `expected_source_instances`,
   `rotation9` and `translation_mm`.
3. Copy the returned `preflight_token` into an otherwise identical `apply=true` call.
4. Read the assembly and verify the new instance. Repeat with a fresh preflight and
   updated count for the second rod. Never reuse the first token for the second rod.

Checked candidate targets for the unmodified OEM rod coordinate frame (native Z=0..65 mm):

| Instance | rotation9 (SOLIDWORKS ArrayData 0..8) | translation_mm |
| --- | --- | --- |
| First | `[0,1,0,0,0,1,1,0,0]` | `[-43.76,-207,1022]` |
| Second | `[0,1,0,0,0,1,1,0,0]` | `[-43.76,-311,1022]` |

Use these only with the previously checked v12 head/SP100 transforms. They are a
compact mounting candidate, not validation of a complete operational station.

## Behaviour and limits

- Dry run hashes the saved source and checks assembly identity, counts and transforms;
  it does not load the source, validate its geometry, or prove insertion will succeed.
- Apply opens the native source if necessary, activates the expected assembly, checks
  the fingerprint again, inserts one floating instance and sets its exact transform.
- Source count includes suppressed instances of the same path at the top level.
  A changed count or state blocks stale retries. This is not a cross-path identity system.
- The command checks resulting configuration/transform and existing top-level transforms.
  It does not create mates, fix components, save documents or check interference.
- Native subassemblies may have unresolved/external references; inspect their open warnings
  and geometry. The SHA-256 fingerprints the named source file, not all referenced files.
- A partial failure leaves the inserted component for inspection and reports its name.
  No automatic deletion/rollback is claimed. Query before recovery or retry.
- Pipe timeout is 120 seconds for insertion. A timeout does not cancel a queued/running
  SOLIDWORKS operation. Wait for SOLIDWORKS to finish and query; never retry blindly.
- The local Node write gate is retained. As in v0.1.1, the named pipe is a trusted local
  transport, not a separate authentication or permission boundary.
- Audit intent is written before insertion. Completion audit failures return a warning
  alongside the successful result, rather than pretending insertion failed.

## Validation status

Passed here: Node syntax check and five dependency-free tests covering the write gate,
preflight requirement, dry-run forwarding, enabled-write forwarding and timeout handling.
Not run here: Windows MSBuild, SOLIDWORKS COM insertion, or full MCP HTTP integration.
The Windows build and first live insertion are required acceptance checks.

On Windows, additionally verify: missing source / STEP rejected; stale token rejected;
first rod inserted once; repeating its old apply request adds no duplicate; second rod
inserted using a fresh preflight; both exact transforms and original placements retained.

## Rollback

Close SOLIDWORKS and stop the new Node server. From the old package run its
`scripts\register-addin.ps1` as Administrator, then reopen SOLIDWORKS and restart the
old Node server. This changes bridge software only; it does not undo CAD edits.
