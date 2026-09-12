# Changelog

## v0.3.0

- Added sw_insert_component for one native part/assembly at an exact transform.
- Added preflight token binding source SHA-256, assembly state, configuration and requested pose.
- Required source-instance count prevents the same request being replayed after insertion.
- Retained the Node write gate, named-pipe name and add-in GUID.
- Verified inserted transform/configuration and existing top-level transforms after rebuild.
- Partial insertions and timeouts are explicitly reported; no automatic retries or deletion.
- Added Node tests and Windows upgrade/start scripts. No DLL is shipped; compile locally.

## v0.1.1

- Replaced the SDK-style `net48` add-in project with a classic .NET Framework 4.8 MSBuild project.
- Removed the accidental `Microsoft.NET.Sdk` build dependency.
- `build-addin.ps1` now builds directly with MSBuild and verifies required SOLIDWORKS interop DLLs and the output DLL.
- No bridge protocol or CAD write behavior changed.

0.1.0

- Initial private tool-only MCP bridge scaffold.
- In-process SOLIDWORKS C# add-in with UI-thread marshalling.
- Local named-pipe protocol.
- Read tools: `sw_status`, `sw_query_components`.
- Guarded transform tool: `sw_set_transform` with dry-run default, local write gate, exact top-level name matching, fixed-component rejection, optional compare-and-set guard, rebuild/re-read verification, rollback, and audit JSONL.
- IXOR + floor-stand canonical benchmark acceptance values documented.
