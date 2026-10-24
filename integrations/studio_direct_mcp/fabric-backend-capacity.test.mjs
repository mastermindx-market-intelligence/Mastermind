import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createFabricFacade} from './fabric-backend.mjs';

// Injected process owner only: no SDK, subprocess, network or provider entry.
const root='capacity-root';
const request=(id, root_id=root)=>({run_id:id,root_id,parent_id:root_id,
  task_class:'mechanical',task_complexity:'C0_MECHANICAL',work_packet:'offline capacity fixture'});
const hash=x=>createHash('sha256').update(x).digest('hex');
const unwrap=x=>x.structuredContent;
function owner() {
  let pid=10000;
  const records=new Map(), calls=[];
  const model={records,calls,starts:0,statusGate:null,metadata:null,retention:null,noPid:false,requestPid:null};
  const text=(value,isError=false)=>({content:[{type:'text',text:value}],...(isError?{isError:true}:{})});
  const captured=value=>{
    const stdout=JSON.stringify(value), capture=JSON.stringify({exit_code:0,stdout_base64:Buffer.from(stdout).toString('base64'),
      stdout_bytes:Buffer.byteLength(stdout),stdout_sha256:hash(stdout)});
    return text(`Process started with PID ${++pid} (shell: /bin/zsh)\nInitial output:\n${capture}\nMMX_FABRIC_EXIT=0\n`);
  };
  model.callTool=async call=>{
    calls.push(call);
    if(call.name==='list_sessions') return model.metadata??text([...records.values()].filter(x=>x.active)
      .map(x=>`PID: ${x.pid}, Blocked: true, Runtime: 1s`).join('\n')||'No active sessions');
    if(call.name==='read_process_output') {
      if(model.retention) return model.retention(call,text);
      const record=[...records.values()].find(x=>x.pid===call.arguments.pid);
      return record?.retained ? text('retained output: MMX_FABRIC_EXIT=0\n✅ Process completed with exit code 0')
        : text(`No session found for PID ${call.arguments.pid}`,true);
    }
    assert.equal(call.name,'start_process','no other owner capability');
    const command=call.arguments.command;
    const observation=/'status' '([^']+)'/.exec(command);
    if(observation) {
      const id=observation[1];
      if(model.statusGate) await model.statusGate(id);
      const value=records.get(id)?.status??{schema:'mastermind.fabric_task_status.v1',run_id:id,state:'NOT_FOUND',result_available:false};
      return captured(value);
    }
    const dispatch=/'request' '--id' '([^']+)'/.exec(command);
    assert.ok(dispatch,'only exact adapter status/request');
    const id=dispatch[1], root_id=/'--root' '([^']+)'/.exec(command)[1];
    model.starts++;
    const controller=model.requestPid??++pid;
    records.set(id,{pid:controller,active:true,retained:true,status:{schema:'mastermind.fabric_task_status.v1',
      run_id:id,root_id,state:'ACTIVE_OR_WAITING',rc:null,signal:null,result_available:false}});
    return model.noPid ? text('response lost after request') : text(`Process started with PID ${controller} (shell: /bin/zsh)\nInitial output:\n`);
  };
  model.finish=(id, changes={})=>{
    const r=records.get(id);r.active=false;r.retained=false;
    Object.assign(r.status,{state:'TERMINAL',rc:0,signal:'ok'},changes);
  };
  model.facade=createFabricFacade(model,{adapterPath:'/fixture/fabric_task.py'});
  return model;
}
async function observe(model,id) {return unwrap(await model.facade.call('fabric_status',{run_id:id,root_id:root}));}
async function fill(model,{terminal=true}={}) {
  for(let i=0;i<512;i++) {
    const id=`held-${i}`;
    assert.equal(unwrap(await model.facade.call('fabric_request',request(id))).delivery,'CONTROLLER_CREATED');
    if(terminal) {model.finish(id);await observe(model,id);}
  }
}

test('513 concurrent preflights cannot exceed the unchanged512 reservations',async()=>{
  const model=owner(),waiting=[];
  model.statusGate=()=>new Promise(resolve=>waiting.push(resolve));
  const pending=Array.from({length:513},(_,n)=>model.facade.call('fabric_request',request(`parallel-${n}`)));
  await new Promise(resolve=>setImmediate(resolve));
  const waitingCount=waiting.length;
  for(const release of waiting) release();
  const results=(await Promise.all(pending)).map(unwrap);
  assert.equal(waitingCount,512);
  assert.equal(model.starts,512);
  assert.equal(results.filter(x=>x.error==='CONTROLLER_TRACKING_CAPACITY').length,1);
});

test('settled expired handles reclaim capacity without ever forgetting the oldID',async()=>{
  const model=owner();await fill(model);
  const oldPid=model.records.get('held-0').pid;
  assert.equal(unwrap(await model.facade.call('fabric_request',request('fresh-513'))).delivery,'CONTROLLER_CREATED');
  model.records.delete('held-0'); // adapter now reports NOT_FOUND; never replay evidence
  const before=model.calls.length;
  assert.equal(unwrap(await model.facade.call('fabric_request',request('held-0','different-root'))).error,'REQUEST_ALREADY_ATTEMPTED');
  assert.equal(model.calls.length,before);
  assert.equal(unwrap(await model.facade.call('fabric_controller_output',{
    run_id:'held-0',root_id:root,controller_pid:oldPid})).error,'CONTROLLER_NOT_BOUND');
  const reads=model.calls.filter(x=>x.name==='read_process_output');
  assert.ok(reads.length>0);
  assert.ok(reads.every(x=>x.arguments.offset===1 && x.arguments.length===1 && x.arguments.timeout_ms===0));
});

for(const fault of ['active','retained','unknown','not-found','wrong-root','unconfirmed',
  'bad-metadata','spoofed-expiration','missing-error-flag','partial-metadata']) {
  test(`retirement refuses ${fault} without losing binding or ID`,async()=>{
    const model=owner();await fill(model);
    const first=model.records.get('held-0'),oldPid=first.pid;
    for(const row of model.records.values()) {
      if(fault==='active') row.active=true;
      if(fault==='retained') row.retained=true;
      if(fault==='unknown') row.status.state='EFFECT_UNKNOWN';
      if(fault==='not-found') row.status.state='NOT_FOUND';
      if(fault==='wrong-root') row.status.root_id='foreign';
      if(fault==='unconfirmed') row.status.continuation={controller_return:'UNCONFIRMED'};
    }
    if(fault==='bad-metadata') model.metadata={content:[{type:'text',text:'MMX_FABRIC_EXIT=0\nNo active sessions'}]};
    if(fault==='partial-metadata') model.metadata={content:[{type:'text',text:'No active sessions'},{type:'text',text:'ignored'}]};
    if(fault==='spoofed-expiration') model.retention=(call,text)=>text('untrusted\nNo session found for PID '+call.arguments.pid,true);
    if(fault==='missing-error-flag') model.retention=(call,text)=>text('No session found for PID '+call.arguments.pid);
    assert.equal(unwrap(await model.facade.call('fabric_request',request('must-not-start'))).error,'CONTROLLER_TRACKING_CAPACITY');
    assert.equal(model.starts,512);
    assert.equal(unwrap(await model.facade.call('fabric_request',request('held-0'))).error,'REQUEST_ALREADY_ATTEMPTED');
    const output=unwrap(await model.facade.call('fabric_controller_output',{run_id:'held-0',root_id:root,controller_pid:oldPid}));
    assert.notEqual(output.error,'CONTROLLER_NOT_BOUND');
  });
}

test('noPID UNKNOWN reservations retain all512 slots',async()=>{
  const model=owner();model.noPid=true;
  for(let i=0;i<512;i++) assert.equal(unwrap(await model.facade.call('fabric_request',request(`unknown-${i}`))).error,'EFFECT_UNKNOWN');
  assert.equal(unwrap(await model.facade.call('fabric_request',request('new-unseen'))).error,'CONTROLLER_TRACKING_CAPACITY');
  assert.equal(model.starts,512);
  assert.equal(model.calls.filter(x=>x.name==='list_sessions').length,0);
});

test('proved preflight-only failures release slots but dispatch uncertainty never does',async()=>{
  const model=owner();
  for(let i=0;i<513;i++) {
    const id=`existing-${i}`;
    model.records.set(id,{status:{schema:'mastermind.fabric_task_status.v1',run_id:id,root_id:root,state:'ACTIVE_OR_WAITING',result_available:false}});
    assert.equal(unwrap(await model.facade.call('fabric_request',request(id))).error,'RUN_EXISTS');
  }
  assert.equal(unwrap(await model.facade.call('fabric_request',request('genuinely-new'))).delivery,'CONTROLLER_CREATED');
  assert.equal(model.starts,1);
});

test('concurrent retirement of one authentic handle frees exactly one slot',async()=>{
  const model=owner();await fill(model,{terminal:false});
  model.finish('held-0');await observe(model,'held-0');
  const waiting=[];
  model.statusGate=id=>id==='held-0'?new Promise(resolve=>waiting.push(resolve)):undefined;
  const calls=Array.from({length:12},(_,i)=>model.facade.call('fabric_request',request(`racing-${i}`)));
  await new Promise(resolve=>setImmediate(resolve));
  for(const release of waiting) release();
  const results=(await Promise.all(calls)).map(unwrap);
  assert.equal(model.starts,513);
  assert.equal(results.filter(x=>x.delivery==='CONTROLLER_CREATED').length,1);
  assert.equal(results.filter(x=>x.error==='CONTROLLER_TRACKING_CAPACITY').length,11);
});

test('retention scan uses at most4 candidates and ONE fresh status',async()=>{
  const model=owner();await fill(model);
  for(const row of model.records.values()) row.retained=true;
  let begin=model.calls.length;
  await model.facade.call('fabric_request',request('no-free-output'));
  let calls=model.calls.slice(begin);
  assert.equal(calls.filter(x=>x.name==='read_process_output').length,4);
  assert.equal(calls.filter(x=>x.name==='start_process').length,0);
  model.retention=(call,text)=>text(`No session found for PID ${call.arguments.pid}`,true);
  for(const row of model.records.values()) row.status.state='EFFECT_UNKNOWN';
  begin=model.calls.length;
  await model.facade.call('fabric_request',request('no-terminal-proof'));
  calls=model.calls.slice(begin);
  assert.equal(calls.filter(x=>x.name==='read_process_output').length,1);
  assert.equal(calls.filter(x=>x.name==='start_process').length,1);
});

test('exact generation history is bounded8192 and no oldID is evicted at the ceiling',async()=>{
  const model=owner();
  for(let i=0;i<8192;i++) {
    const id=`history-${i}`;
    assert.equal(unwrap(await model.facade.call('fabric_request',request(id))).delivery,'CONTROLLER_CREATED');
    model.finish(id);await observe(model,id);
  }
  const before=model.calls.length;
  assert.equal(unwrap(await model.facade.call('fabric_request',request('history-overflow'))).error,'GENERATION_TRACKING_CAPACITY');
  assert.equal(unwrap(await model.facade.call('fabric_request',request('history-0'))).error,'REQUEST_ALREADY_ATTEMPTED');
  assert.equal(model.calls.length,before);
  assert.equal(model.starts,8192);
});

test('reused native PIDs cannot preserve output authority for another operation',async()=>{
  const model=owner();
  const first=unwrap(await model.facade.call('fabric_request',request('prior')));
  model.requestPid=first.controller_pid;
  assert.equal(unwrap(await model.facade.call('fabric_request',request('reused'))).error,'EFFECT_UNKNOWN');
  for(const id of ['prior','reused']) {
    assert.equal(unwrap(await model.facade.call('fabric_controller_output',{
      run_id:id,root_id:root,controller_pid:first.controller_pid})).error,'CONTROLLER_NOT_BOUND');
    assert.equal(unwrap(await model.facade.call('fabric_request',request(id))).error,'REQUEST_ALREADY_ATTEMPTED');
  }
});
