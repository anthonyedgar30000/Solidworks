// Keep the local write gate at the MCP boundary, as for sw_set_transform.
export async function insertComponent(params, { allowWrites, call }) {
  const failure = (Code, Message) => ({ Ok: false, Error: { Code, Message } });
  if (params.apply && !allowWrites)
    return failure("WRITES_DISABLED", "Local MCP server write gate is disabled (SWBRIDGE_ALLOW_WRITES=1 required).");
  if (params.apply && !/^[a-f0-9]{64}$/.test(params.preflight_token ?? ""))
    return failure("PREFLIGHT_REQUIRED", "Run apply=false and pass its preflight_token unchanged.");
  try {
    return await call("sw_insert_component", params, { timeoutMs: 120000 });
  } catch (error) {
    return failure("INSERTION_RESPONSE_UNAVAILABLE", `${error.message} Execution may still be pending or complete. Query the assembly before retrying; do not assume nothing changed.`);
  }
}
