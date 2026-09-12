export async function executeCode(params, { allowWrites, maxControl, call }) {
  const fail = (Code, Message) => ({ Ok: false, Error: { Code, Message } });
  if (!maxControl || !allowWrites)
    return fail('MAX_CONTROL_DISABLED', 'Start the server with scripts/start-server.ps1 -MaxControl. This enables trusted C# execution in SOLIDWORKS.');
  if (params.apply && !/^[a-f0-9]{32}$/.test(params.preflight_token ?? ''))
    return fail('PREFLIGHT_REQUIRED', 'Compile with apply=false first, then pass its token and unchanged source/document.');
  try { return await call('sw_execute_code', params, { timeoutMs: 120000 }); }
  catch (error) {
    return fail('EXECUTION_OUTCOME_UNKNOWN', `${error.message} Timeout/disconnection does not cancel queued or running code. Do not retry; inspect SOLIDWORKS and the audit log first.`);
  }
}
