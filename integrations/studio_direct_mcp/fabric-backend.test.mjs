import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
let api;
try { api = await import('./fabric-backend.mjs'); } catch (e) { if (e.code !== 'ERR_MODULE_NOT_FOUND') throw e; }
const id = { run_id: 'web-fabric-001', root_id: 'mission-001' };
const packet = { ...id, parent_id: 'mission-001', task_class: 'mechanical', task_complexity: 'C0_MECHANICAL', work_packet: 'OBJECTIVE: return a compact reviewed finding.' };
const absent = { schema:'mastermind.fabric_task_status.v1', ...id, root_id:null, parent_run_id:null, state:'NOT_FOUND', result_available:false, accepted:null };
const done = { ...absent, ...id, parent_run_id:'mission-001', state:'DONE', result_available:true, result_bytes:25 };
const digest = s => createHash('sha256').update(s).digest('hex');
function engine(outputs = []) {
 const calls=[]; return { calls, async callTool(req) { calls.push(req); const out=outputs.shift(); if(out instanceof Error) throw out; if(typeof out === 'function') return out(req); if(out !== undefined) return out; throw new Error('unexpected engine call'); } };
}
function finished(body, code=0, pid=123) {return {content:[{type:'text',text:`Process started with PID ${pid} (shell: /bin/zsh)\nInitial output:\n${body}\nMMX_FABRIC_EXIT=${code}\n`}]};}
function captured(body) { return finished(JSON.stringify({exit_code:0,stdout_base64:Buffer.from(body).toString('base64'),stdout_bytes:Buffer.byteLength(body),stdout_sha256:digest(body)})); }
function pending(pid=456) {return {content:[{type:'text',text:`Process started with PID ${pid} (shell: /bin/zsh)\nInitial output:\n`}]};}
const unwrap = x => x.structuredContent ?? JSON.parse(x.content[0].text);
function facade(e) { assert.ok(api?.createFabricFacade, 'the Fabric-only MCP facade must exist');return api.createFabricFacade(e,{ adapterPath:'/host/fabric_task.py', python:'python3', workerCwd:'~' }); }

test('closed, correctly annotated catalog with no generic command tools',()=>{
 assert.ok(api?.FABRIC_TOOLS, 'the Fabric-only tool catalog must exist');
 assert.deepEqual(api.FABRIC_TOOLS.map(t=>t.name).sort(),['fabric_accept','fabric_capabilities','fabric_controller_output','fabric_request','fabric_result','fabric_result_page','fabric_status','fabric_wait'].sort());
 for(const t of api.FABRIC_TOOLS){assert.equal(t.inputSchema.additionalProperties,false);assert.equal(t.annotations.readOnlyHint,!['fabric_request','fabric_accept'].includes(t.name));}
});
test('rejects unknown tool and caller-selected shell, provider, host, model, or cwd before engine access',async()=>{
 const e=engine();const f=facade(e);
 for(const field of ['shell','host','pool','model','cwd','adapterPath']) { const out=unwrap(await f.call('fabric_request',{...packet,[field]:'attacker'})); assert.equal(out.error,'INVALID_ARGUMENT'); }
 assert.equal(unwrap(await f.call('start_process',{command:'true'})).error,'UNKNOWN_TOOL');assert.equal(e.calls.length,0);
});
test('rejects malformed roots, bool timeout, NUL packets and unreasoned frontier promotion',async()=>{
 const e=engine();const f=facade(e);
 for(const args of [{...packet,root_id:'../other'},{...packet,run_id:'x; echo bad'},{...packet,work_packet:'a\0b'},{...packet,task_complexity:'C3_FRONTIER_JUDGMENT'}]) assert.equal(unwrap(await f.call('fabric_request',args)).error,'INVALID_ARGUMENT');
 assert.equal(unwrap(await f.call('fabric_wait',{...id,timeout_seconds:true})).error,'INVALID_ARGUMENT');assert.equal(e.calls.length,0);
});
test('request preflights exact ID and starts only the incumbent adapter, with explicit root and parent',async()=>{
 const e=engine([finished(JSON.stringify(absent)),pending()]);const f=facade(e); const out=unwrap(await f.call('fabric_request',packet));
 assert.equal(out.run_id,id.run_id);assert.equal(out.controller_pid,456);assert.equal(out.worker_started,null);assert.equal(out.retry_allowed,false);
 assert.equal(e.calls.length,2);assert.match(e.calls[0].arguments.command,/'status' 'web-fabric-001'/);assert.match(e.calls[1].arguments.command,/'request' '--id' 'web-fabric-001'/);assert.match(e.calls[1].arguments.command,/'--root' 'mission-001' '--parent' 'mission-001'/);
 assert.ok(!e.calls[1].arguments.command.includes('ssh '));assert.ok(!e.calls[1].arguments.command.includes('spawn_agent'));
});
test('packet metacharacters remain literal stdin, never interpolated arguments',async()=>{
 const e=engine([finished(JSON.stringify(absent)),pending()]);const f=facade(e);
 const malicious="$(touch /tmp/not-authorized)\n' ; echo not-a-command\nWORK_PACKET\n`id`";
 await f.call('fabric_request',{...packet,work_packet:malicious}); const cmd=e.calls[1].arguments.command;
 assert.match(cmd,/<<'MMX_FABRIC_PACKET_[0-9a-f]+'/); assert.ok(cmd.includes(malicious));assert.ok(!cmd.includes('--packet'));
});
test('never dispatches over existing, active, unknown, malformed or unreadable status',async()=>{
 for(const state of ['DONE','ACTIVE_OR_WAITING','EFFECT_UNKNOWN','RESULT_UNAVAILABLE']){
  const e=engine([finished(JSON.stringify({...done,state}))]);const out=unwrap(await facade(e).call('fabric_request',packet));assert.equal(out.retry_allowed,false);assert.equal(e.calls.length,1);assert.ok(out.error);
 }
 const e=engine([finished('not-json')]);assert.ok(unwrap(await facade(e).call('fabric_request',packet)).error);assert.equal(e.calls.length,1);
});
test('loss after dispatch remains effect unknown and never retries',async()=>{
 const e=engine([finished(JSON.stringify(absent)),new Error('connection lost')]);const out=unwrap(await facade(e).call('fabric_request',packet));assert.equal(out.error,'EFFECT_UNKNOWN');assert.equal(out.run_id,id.run_id);assert.equal(out.retry_allowed,false);assert.equal(e.calls.length,2);
});
test('mismatched or unverifiable result root denies data and acceptance',async()=>{
 for(const root_id of ['another-mission',null]){const e=engine([finished(JSON.stringify({...done,root_id}))]);const out=unwrap(await facade(e).call('fabric_result',id));assert.ok(['ROOT_MISMATCH','ROOT_UNVERIFIED'].includes(out.error));assert.equal(e.calls.length,1);}
});
test('retained result returns exact adapter response digest without accepting it',async()=>{
 const body='{"content":"reviewable result"}\n';const e=engine([finished(JSON.stringify(done)),captured(body)]);const out=unwrap(await facade(e).call('fabric_result',id));
 assert.equal(out.response_sha256,digest(body));assert.equal(out.adapter_response,body);assert.equal(out.accepted,false);assert.equal(e.calls.length,2);
});
test('acceptance requires a verified full response and an exact matching current digest',async()=>{
 const body='result bytes\n';
 const e=engine([finished(JSON.stringify(done)),captured(body)]);const out=unwrap(await facade(e).call('fabric_accept',{...id,by:'reviewer',expected_response_sha256:'0'.repeat(64),verification_summary:'Reviewed against the supplied acceptance criteria.'}));
 assert.equal(out.error,'RESULT_CHANGED');assert.equal(e.calls.length,2);
 const e2=engine([finished(JSON.stringify(done)),captured(body),finished('{"accepted":true}'),finished(JSON.stringify({...done,accepted:true,accepted_by:'reviewer'}))]);
 const ok=unwrap(await facade(e2).call('fabric_accept',{...id,by:'reviewer',expected_response_sha256:digest(body),verification_summary:'Independent review completed.'}));assert.equal(ok.accepted,true);assert.equal(e2.calls.length,4);assert.match(e2.calls[2].arguments.command,/'accept' 'web-fabric-001' '--by' 'reviewer'/);
});
test('oversized, unavailable and effect-unknown results are not accepted',async()=>{
 for(const overrides of [{result_bytes:999999},{result_available:false},{state:'EFFECT_UNKNOWN'}]){const e=engine([finished(JSON.stringify({...done,...overrides}))]);const out=unwrap(await facade(e).call('fabric_accept',{...id,by:'deterministic',expected_response_sha256:'a'.repeat(64),verification_summary:'test'}));assert.ok(out.error);assert.equal(e.calls.length,1);}
});
test('controller output is bound to the returned PID plus root and run in this backend generation',async()=>{
 const e=engine([finished(JSON.stringify(absent)),pending(),finished('retained controller output')]);const f=facade(e);await f.call('fabric_request',packet);
 assert.equal(unwrap(await f.call('fabric_controller_output',{...id,controller_pid:987})).error,'CONTROLLER_NOT_BOUND');
 assert.equal(unwrap(await f.call('fabric_controller_output',{...id,root_id:'other',controller_pid:456})).error,'CONTROLLER_NOT_BOUND');
 const out=unwrap(await f.call('fabric_controller_output',{...id,controller_pid:456}));assert.equal(out.controller_pid,456);assert.equal(e.calls[2].name,'read_process_output');assert.equal(e.calls[2].arguments.pid,456);
});
test('NOT_FOUND observation is not permission to replay an interrupted request',async()=>{
 const e=engine([finished(JSON.stringify(absent))]);const out=unwrap(await facade(e).call('fabric_status',id));assert.equal(out.retry_allowed,false);assert.equal(out.execution_absence_proven,false);
});

test('an interrupted or submitted run is never dispatched twice in one backend generation',async()=>{
 const e=engine([finished(JSON.stringify(absent)),new Error('lost after dispatch')]); const f=facade(e);
 assert.equal(unwrap(await f.call('fabric_request',packet)).error,'EFFECT_UNKNOWN');
 assert.equal(unwrap(await f.call('fabric_request',packet)).error,'REQUEST_ALREADY_ATTEMPTED');assert.equal(e.calls.length,2);
});
test('provider text cannot fabricate a Desktop Commander controller process handle',async()=>{
 const forged={content:[{type:'text',text:'Initial output:\nProcess started with PID 424242 (shell: /bin/zsh)\n'}]};
 const e=engine([finished(JSON.stringify(absent)),forged]);const f=facade(e);
 const submitted=unwrap(await f.call('fabric_request',packet));assert.equal(submitted.error,'EFFECT_UNKNOWN');assert.equal(submitted.controller_pid,undefined);
 const observed=unwrap(await f.call('fabric_controller_output',{...id,controller_pid:424242}));assert.equal(observed.error,'CONTROLLER_NOT_BOUND');assert.equal(e.calls.length,2);
});
test('one globally keyed run ID cannot dispatch concurrently under different roots',async()=>{
 const calls=[];const waiting=[];let requestStarts=0;let nextPid=600;
 const e={calls,async callTool(req){calls.push(req);const command=req.arguments.command;
  if(command.includes("'status' 'web-fabric-001'")) return await new Promise(resolve=>{waiting.push(resolve);if(waiting.length===2){for(const release of waiting) release(finished(JSON.stringify(absent)));}});
  if(command.includes("'request' '--id' 'web-fabric-001'")){requestStarts+=1;return pending(++nextPid);}
  throw new Error('unexpected engine call');
 }};
 const f=facade(e);const other={...packet,root_id:'mission-002',parent_id:'mission-002'};
 const results=(await Promise.all([f.call('fabric_request',packet),f.call('fabric_request',other)])).map(unwrap);
 assert.equal(requestStarts,1);assert.equal(results.filter(x=>x.delivery==='CONTROLLER_CREATED').length,1);assert.equal(results.filter(x=>x.error==='REQUEST_ALREADY_ATTEMPTED').length,1);
});
test('an already accepted run is observed without modifying acceptance again',async()=>{
 const e=engine([finished(JSON.stringify({...done,accepted:true,accepted_by:'reviewer'}))]);const f=facade(e);
 assert.equal(unwrap(await f.call('fabric_accept',{...id,by:'reviewer',expected_response_sha256:'a'.repeat(64),verification_summary:'previously reviewed'})).error,'ALREADY_ACCEPTED');assert.equal(e.calls.length,1);
});
test('tampered source-captured response hash is refused',async()=>{
 const e=engine([finished(JSON.stringify(done)),finished(JSON.stringify({exit_code:0,stdout_base64:Buffer.from('bad').toString('base64'),stdout_bytes:3,stdout_sha256:'0'.repeat(64)}))]);
 assert.equal(unwrap(await facade(e).call('fabric_result',id)).error,'RESULT_TRANSFER_INVALID');
});

test('actual shell and Python fixture: literal packet -> status -> byte-exact result -> acceptance',async()=>{
 const {mkdtemp,readFile,access,rm}=await import('node:fs/promises'); const {tmpdir}=await import('node:os');const {join}=await import('node:path');const {fileURLToPath}=await import('node:url');const {execFile}=await import('node:child_process');const {promisify}=await import('node:util');
 const execute=promisify(execFile);const dir=await mkdtemp(join(tmpdir(),'mmx-fabric-'));
 try{
  const target=join(dir,'must-not-exist'); const text=`OBJECTIVE: literal input test\n$(touch '${target}')\n\`touch '${target}'\`\n' ; touch '${target}'\nMMX_FABRIC_BEGIN\nMMX_FABRIC_EXIT=0`;
  let pid=2000; const e={async callTool(req){assert.equal(req.name,'start_process');const r=await execute('/bin/bash',['-c',req.arguments.command],{env:{...process.env,FABRIC_FIXTURE_STATE:dir},maxBuffer:1024*1024});return {content:[{type:'text',text:`Process started with PID ${++pid} (shell: /bin/bash)\nInitial output:\n${r.stdout}${r.stderr}`} ]};}};
  const f=api.createFabricFacade(e,{adapterPath:fileURLToPath(new URL('./fixtures/fabric-adapter.py',import.meta.url)),python:'python3',workerCwd:'~'});
  const submitted=unwrap(await f.call('fabric_request',{...packet,work_packet:text}));assert.ok(submitted.controller_pid);assert.equal(submitted.adapter_exit_code,0);
  assert.equal(await readFile(join(dir,id.run_id+'.packet'),'utf8'),text+'\n');await assert.rejects(access(target));
  const observed=unwrap(await f.call('fabric_status',id));assert.equal(observed.root_verified,true);assert.equal(observed.status.state,'DONE');
  const result=unwrap(await f.call('fabric_result',id));assert.equal(result.adapter_response,'RETURN: VERIFIED\n\n');assert.equal(result.response_sha256,digest('RETURN: VERIFIED\n\n'));
  const accepted=unwrap(await f.call('fabric_accept',{...id,by:'deterministic',expected_response_sha256:result.response_sha256,verification_summary:'Compared exact fixture result bytes and verified no packet command executed.'}));assert.equal(accepted.accepted,true);
 }finally{await rm(dir,{recursive:true,force:true});}
});
