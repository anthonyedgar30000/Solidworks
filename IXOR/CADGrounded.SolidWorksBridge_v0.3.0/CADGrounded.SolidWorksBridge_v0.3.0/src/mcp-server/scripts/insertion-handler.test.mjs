import test from 'node:test';
import assert from 'node:assert/strict';
import { insertComponent } from '../insertion-handler.mjs';
test('disabled writes never reach the named pipe', async () => {
  const r = await insertComponent({apply:true, preflight_token:'a'.repeat(64)}, {allowWrites:false,call:()=>{throw Error('must not call');}});
  assert.equal(r.Error.Code,'WRITES_DISABLED');
});
test('apply requires a preflight token', async () => {
  const r = await insertComponent({apply:true}, {allowWrites:true,call:()=>{throw Error('must not call');}});
  assert.equal(r.Error.Code,'PREFLIGHT_REQUIRED');
});
test('dry-run is forwarded with writes disabled', async () => {
  const p={apply:false};
  const r=await insertComponent(p,{allowWrites:false,call:async (method,params,options)=>{
    assert.equal(method,'sw_insert_component');assert.equal(params,p);assert.equal(options.timeoutMs,120000);
    return {Ok:true,Result:{applied:false}};
  }});
  assert.equal(r.Result.applied,false);
});
test('enabled apply forwards complete parameters unchanged', async()=>{
  const p={apply:true,preflight_token:'b'.repeat(64),expected_source_instances:1};
  const r=await insertComponent(p,{allowWrites:true,call:async(_,params)=>{assert.equal(params,p);return {Ok:true};}});
  assert.equal(r.Ok,true);
});
test('timeout is reported as uncertain, never retried automatically', async()=>{
  let calls=0;
  const r=await insertComponent({apply:true,preflight_token:'c'.repeat(64)},{allowWrites:true,call:async()=>{calls++;throw Error('timeout');}});
  assert.equal(calls,1);assert.equal(r.Error.Code,'INSERTION_RESPONSE_UNAVAILABLE');
  assert.match(r.Error.Message,/Query the assembly/);
});
