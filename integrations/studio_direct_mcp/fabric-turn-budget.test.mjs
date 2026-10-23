import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { FABRIC_TOOLS, createFabricFacade } from './fabric-backend.mjs';

const args = {run_id:'budget-fixture',root_id:'root-fixture',parent_id:'parent-fixture',
  task_class:'mechanical',task_complexity:'C0_MECHANICAL',work_packet:'Bounded fixture',max_turns:25};
const absent = {schema:'mastermind.fabric_task_status.v1',run_id:args.run_id,root_id:null,
  state:'NOT_FOUND',result_available:false};
const unwrap = result => result.structuredContent;
function finished(body) {
  return {content:[{type:'text',text:`Process started with PID 123 (shell: /bin/bash)\nInitial output:\n${body}\nMMX_FABRIC_EXIT=0\n`}]};
}
function captured(body, exit=0) {
  return finished(JSON.stringify({exit_code:exit,stdout_base64:Buffer.from(body).toString('base64'),
    stdout_bytes:Buffer.byteLength(body),stdout_sha256:createHash('sha256').update(body).digest('hex')}));
}
function engine(outputs) {
  return {calls:[],async callTool(call) {
    this.calls.push(call);
    assert.ok(outputs.length,'unexpected process call');
    const item=outputs.shift();
    if(item instanceof Error) throw item;
    return item;
  }};
}
function facade(e, quotaFallback=false) {
  return createFabricFacade(e,{adapterPath:'/fixture/adapter.py',quotaFallback});
}
const pending = {content:[{type:'text',text:'Process started with PID 456 (shell: /bin/bash)\nInitial output:\n'}]};

test('turn cap is strictly typed before any engine operation',async()=>{
  const spec=FABRIC_TOOLS.find(t=>t.name==='fabric_request').inputSchema.properties.max_turns;
  assert.equal(spec.type,'integer');assert.equal(spec.minimum,1);assert.equal(spec.maximum,400);
  const e=engine([]);
  for(const max_turns of [0,-1,401,true,false,25.5,'25',null]) {
    assert.equal(unwrap(await facade(e).call('fabric_request',{...args,max_turns})).error,'INVALID_ARGUMENT');
  }
  assert.equal(e.calls.length,0);
});

test('older or unreadable adapter refuses explicit cap before controller creation',async()=>{
  for(const help of [captured('--quota-fallback'),captured('--max-turns',2)]) {
    const e=engine([help]);
    const result=unwrap(await facade(e).call('fabric_request',args));
    assert.equal(result.error,'ADAPTER_TURN_LIMIT_UNAVAILABLE');
    assert.equal(result.retry_allowed,false);assert.equal(e.calls.length,1);
    assert.match(e.calls[0].arguments.command,/'request' '--help'/);
  }
});

test('qualified request forwards exact cap without claiming worker START',async()=>{
  const e=engine([captured('--max-turns'),captured(JSON.stringify(absent)),pending]);
  const result=unwrap(await facade(e).call('fabric_request',args));
  assert.equal(result.controller_pid,456);assert.equal(result.worker_started,null);
  assert.equal(result.requested_max_turns,25);assert.equal(result.retry_allowed,false);
  assert.match(e.calls[2].arguments.command,/'--max-turns' '25'/);
  assert.match(e.calls[2].arguments.command,/'--root' 'root-fixture' '--parent' 'parent-fixture'/);
});

test('continuation and turn cap share one request-help probe',async()=>{
  const e=engine([captured('--quota-fallback --max-turns'),captured('--follow'),
                  captured(JSON.stringify(absent)),pending]);
  const result=unwrap(await facade(e,true).call('fabric_request',args));
  assert.equal(result.controller_pid,456);assert.equal(e.calls.length,4);
  assert.match(e.calls[3].arguments.command,/'--quota-fallback'/);
  assert.match(e.calls[3].arguments.command,/'--max-turns' '25'/);
});

test('lost capped submission remains unknown and is never replayed',async()=>{
  const e=engine([captured('--max-turns'),captured(JSON.stringify(absent)),new Error('lost')]);
  const f=facade(e);
  assert.equal(unwrap(await f.call('fabric_request',args)).error,'EFFECT_UNKNOWN');
  assert.equal(unwrap(await f.call('fabric_request',args)).error,'REQUEST_ALREADY_ATTEMPTED');
  assert.equal(e.calls.length,3);
});

test('actual facade shell transport carries the ceiling to an isolated CLI',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'fabric-turn-budget-'));
  try {
    const adapter=join(dir,'adapter.py');
    await writeFile(adapter,`import sys,json\na=sys.argv[1:]\nif a==['request','--help']: print('--max-turns')\nelif a[0]=='status': print(json.dumps(${JSON.stringify(absent).replaceAll('null','None').replaceAll('false','False')}))\nelif a[0]=='request':\n assert a[a.index('--max-turns')+1]=='25'\n assert a[a.index('--root')+1]=='root-fixture'\n assert sys.stdin.read().strip()=='Bounded fixture'\n print('bounded request observed')\nelse: raise SystemExit(2)\n`);
    const run=promisify(execFile);
    const e={async callTool(call) {
      const {stdout}=await run('/bin/bash',['-c',call.arguments.command],{timeout:10000,maxBuffer:262144});
      return {content:[{type:'text',text:'Process started with PID 123 (shell: /bin/bash)\nInitial output:\n'+stdout}]};
    }};
    const result=unwrap(await createFabricFacade(e,{adapterPath:adapter}).call('fabric_request',args));
    assert.equal(result.adapter_exit_code,0);
    assert.equal(result.requested_max_turns,25);
    assert.equal(result.worker_start_proven,false);
  } finally {await rm(dir,{recursive:true,force:true});}
});


test('turn ceiling and fixed fabric_accept verification codes coexist on one facade',async()=>{
  const request=FABRIC_TOOLS.find(t=>t.name==='fabric_request');
  const accept=FABRIC_TOOLS.find(t=>t.name==='fabric_accept');
  assert.equal(request.inputSchema.properties.max_turns.maximum,400);
  assert.deepEqual(accept.inputSchema.properties.verification_summary.enum,[
    'deterministic_test_evidence','artifact_digest_comparison',
    'manual_result_review','independent_review_evidence']);
  const e=engine([captured('--max-turns'),captured(JSON.stringify(absent)),pending]);
  const f=facade(e);
  const created=unwrap(await f.call('fabric_request',args));
  assert.equal(created.requested_max_turns,25);
  assert.equal(created.worker_start_proven,false);
  for(const [by,verification_summary] of [
    ['reviewer','deterministic_test_evidence'],
    ['deterministic','independent_review_evidence'],
    ['reviewer','Freeform reviewer instructions'],
  ]) {
    const result=unwrap(await f.call('fabric_accept',{
      run_id:args.run_id,root_id:args.root_id,by,
      expected_response_sha256:'a'.repeat(64),verification_summary}));
    assert.equal(result.error,'INVALID_ARGUMENT');
  }
  assert.equal(e.calls.length,3,'invalid acceptance must not dispatch after capped request');
});
