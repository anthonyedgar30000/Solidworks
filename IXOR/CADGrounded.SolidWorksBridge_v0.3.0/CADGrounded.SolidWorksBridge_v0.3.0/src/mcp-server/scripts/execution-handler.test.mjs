import test from 'node:test';
import assert from 'node:assert/strict';
import { executeCode } from '../execution-handler.mjs';
const p = { source: 'source', expected_document_title: 'v12', expected_document_path: 'C:\\v12.SLDASM', apply: false };
for (const [allowWrites, maxControl] of [[false,false],[true,false],[false,true]]) {
  test(`execution blocked with gates ${allowWrites}/${maxControl}`, async () => {
    let calls = 0;
    const r = await executeCode(p, { allowWrites, maxControl, call: async () => { calls++; } });
    assert.equal(r.Error.Code, 'MAX_CONTROL_DISABLED'); assert.equal(calls, 0);
  });
}
test('apply without token never reaches pipe', async () => {
  const r = await executeCode({...p, apply:true}, {allowWrites:true,maxControl:true,call:async()=>{assert.fail('called');}});
  assert.equal(r.Error.Code,'PREFLIGHT_REQUIRED');
});
test('compilation forwarded unchanged with timeout', async () => {
  const r = await executeCode(p,{allowWrites:true,maxControl:true,call:async(method,args,opts)=>{
    assert.equal(method,'sw_execute_code'); assert.deepEqual(args,p); assert.equal(opts.timeoutMs,120000);
    return {Ok:true,Result:{compiled:true,executed:false}};
  }}); assert.equal(r.Result.executed,false);
});
test('apply forwards exact source and token', async () => {
  const args = {...p,apply:true,preflight_token:'a'.repeat(32)};
  await executeCode(args,{allowWrites:true,maxControl:true,call:async(m,a)=>{assert.deepEqual(a,args);return {Ok:true};}});
});
test('transport failure never retries and warns execution may continue', async () => {
  let n=0;
  const r=await executeCode({...p,apply:true,preflight_token:'b'.repeat(32)},{allowWrites:true,maxControl:true,call:async()=>{n++;throw Error('timeout');}});
  assert.equal(n,1);assert.equal(r.Error.Code,'EXECUTION_OUTCOME_UNKNOWN');assert.match(r.Error.Message,/does not cancel/);
});
