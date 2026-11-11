import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createFabricFacade } from './fabric-backend.mjs';

const execute = promisify(execFile);
const digest = b => createHash('sha256').update(b).digest('hex');
const identity = {run_id:'synthetic-oversized-review',root_id:'synthetic-root'};
const packet = {...identity,parent_id:'synthetic-root',task_class:'mechanical',
  task_complexity:'C0_MECHANICAL',work_packet:'SYNTHETIC TEST: no provider or real review run.'};
const unwrap = r => r.structuredContent ?? JSON.parse(r.content[0].text);
const fixture = fileURLToPath(new URL('./fixtures/fabric-adapter.py', import.meta.url));


const completed = value => ({content:[{type:'text',text:
  'Process started with PID 99 (shell: /bin/zsh)\nInitial output:\n' +
  JSON.stringify(value) + '\nMMX_FABRIC_EXIT=0\n'}]});
const capturedStatus = value => {
  const bytes=Buffer.from(JSON.stringify(value));
  return completed({exit_code:0,stdout_base64:bytes.toString('base64'),
    stdout_bytes:bytes.length,stdout_sha256:digest(bytes)});
};

test('synthetic 100979- and 196317-byte retained results are paged exactly; partial delivery never enables acceptance', async t => {
 for(const total of [100979,196317]) await t.test(String(total),async()=>{
  const dir=await mkdtemp(join(tmpdir(),'mmx-fabric-paging-'));
  try {
   let pid=4000;
   const engine={async callTool(req){
    assert.equal(req.name,'start_process');
    const r=await execute('/bin/bash',['-c',req.arguments.command],{
      env:{...process.env,FABRIC_FIXTURE_STATE:dir,FABRIC_FIXTURE_RESULT_BYTES:String(total)},maxBuffer:1024*1024});
    return {content:[{type:'text',text:`Process started with PID ${++pid} (shell: /bin/bash)\nInitial output:\n${r.stdout}${r.stderr}`}]};
   }};
   const f=createFabricFacade(engine,{adapterPath:fixture,python:'python3',workerCwd:'~'});
   const request=unwrap(await f.call('fabric_request',packet));
   assert.equal(request.action,'fabric_request');
   const denied=unwrap(await f.call('fabric_result',{...identity,max_bytes:65536}));
   assert.equal(denied.error,'RESULT_TOO_LARGE');
   const expected=Buffer.from('SYNTHETIC RESULT\n'+'R'.repeat(total-Buffer.byteLength('SYNTHETIC RESULT\n')));
   assert.equal(expected.length,total);
   let output=[], expectedDigest=null, next=0, pages=0;
   while(next<total) {
    const page=unwrap(await f.call('fabric_result_page',{...identity,offset:next,max_bytes:4096,
      ...(expectedDigest?{expected_response_sha256:expectedDigest}:{})}));
    assert.equal(page.error,undefined,JSON.stringify(page));
    assert.equal(page.root_id,identity.root_id);
    assert.equal(page.response_bytes,total);
    assert.equal(page.offset,next);
    assert.ok(page.page_bytes>0 && page.page_bytes<=4096);
    assert.equal(page.response_sha256,digest(expected));
    expectedDigest=page.response_sha256;
    const bytes=Buffer.from(page.page_base64,'base64');
    assert.equal(bytes.length,page.page_bytes);
    assert.equal(digest(bytes),page.page_sha256);
    output.push(bytes);
    next=page.next_offset;
    pages+=1;
    if(pages===1) {
      const premature=unwrap(await f.call('fabric_accept',{...identity,by:'deterministic',
        expected_response_sha256:expectedDigest,verification_summary:'artifact_digest_comparison'}));
      assert.equal(premature.error,'RESULT_NOT_FULLY_DELIVERED');
    }
   }
   assert.ok(pages>1);
   assert.deepEqual(Buffer.concat(output),expected);
   assert.equal(digest(Buffer.concat(output)),expectedDigest);
   const accepted=unwrap(await f.call('fabric_accept',{...identity,by:'deterministic',
     expected_response_sha256:expectedDigest,verification_summary:'artifact_digest_comparison'}));
   assert.equal(accepted.accepted,true,JSON.stringify(accepted));
   const status=unwrap(await f.call('fabric_status',identity));
   assert.equal(status.status.accepted,true);
  } finally { await rm(dir,{recursive:true,force:true}); }
 });
});

test('paged result parameters and root must be verified before adapter access', async()=>{
 const calls=[];
 const engine={async callTool(req){calls.push(req);
  return capturedStatus({schema:'mastermind.fabric_task_status.v1',...identity,state:'TERMINAL',result_available:true,result_bytes:196317,accepted:false});}};
 const f=createFabricFacade(engine,{adapterPath:'/fixed/fixture.py',python:'python3',workerCwd:'~'});
 for(const fields of [{offset:-1},{max_bytes:4097},{expected_response_sha256:'not-a-digest'}]){
  const out=unwrap(await f.call('fabric_result_page',{...identity,...fields}));
  assert.equal(out.error,'INVALID_ARGUMENT');
 }
 assert.equal(calls.length,0);
 const wrong=unwrap(await f.call('fabric_result_page',{...identity,root_id:'wrong-root'}));
 assert.equal(wrong.error,'ROOT_MISMATCH');
 assert.equal(calls.length,1);
});

test('synthetic changed retained bytes with the same length cannot extend delivery or be accepted',async()=>{
 const {writeFile}=await import('node:fs/promises');
 const dir=await mkdtemp(join(tmpdir(),'mmx-fabric-mutation-'));
 try {
  let pid=7000;
  const engine={async callTool(req){
   assert.equal(req.name,'start_process');
   const r=await execute('/bin/bash',['-c',req.arguments.command],{
     env:{...process.env,FABRIC_FIXTURE_STATE:dir,FABRIC_FIXTURE_RESULT_BYTES:'100979'},maxBuffer:1024*1024});
   return {content:[{type:'text',text:`Process started with PID ${++pid} (shell: /bin/bash)\nInitial output:\n${r.stdout}${r.stderr}`}]};
  }};
  const f=createFabricFacade(engine,{adapterPath:fixture,python:'python3',workerCwd:'~'});
  assert.equal(unwrap(await f.call('fabric_request',packet)).action,'fabric_request');
  const page=unwrap(await f.call('fabric_result_page',{...identity,offset:0,max_bytes:4096}));
  assert.equal(page.page_bytes,4096);
  const changed=Buffer.from('CHANGED!'.padEnd(100979,'R'));
  await writeFile(join(dir,identity.run_id+'.result'),changed);
  const follow=unwrap(await f.call('fabric_result_page',{...identity,offset:4096,
    max_bytes:4096,expected_response_sha256:page.response_sha256}));
  assert.equal(follow.error,'RESULT_CHANGED');
  const accept=unwrap(await f.call('fabric_accept',{...identity,by:'deterministic',
    expected_response_sha256:page.response_sha256,verification_summary:'artifact_digest_comparison'}));
  assert.equal(accept.error,'RESULT_NOT_FULLY_DELIVERED');
  changed[50]=0xff;
  await writeFile(join(dir,identity.run_id+'.result'),changed);
  const badUtf8=unwrap(await f.call('fabric_result_page',{...identity,offset:0,max_bytes:4096}));
  assert.equal(badUtf8.error,'RESULT_NOT_UTF8');
 }finally{await rm(dir,{recursive:true,force:true});}
});

test('synthetic 8-MiB adapter ceiling refuses before reading retained bytes',async()=>{
 let calls=0;
 const status={schema:'mastermind.fabric_task_status.v1',...identity,state:'TERMINAL',result_available:true,
   result_bytes:8_388_609,accepted:false};
 const f=createFabricFacade({async callTool(){calls++;return capturedStatus(status);}},
  {adapterPath:'/fixed/fixture.py',python:'python3',workerCwd:'~'});
 const o=unwrap(await f.call('fabric_result_page',identity));
 assert.equal(o.error,'RESULT_EXCEEDS_ADAPTER_LIMIT');
 assert.equal(calls,1);
});

function leafStatus(runId, body, accepted=false) {
  return {schema:'mastermind.fabric_task_status.v1',run_id:runId,
    root_id:identity.root_id,state:'TERMINAL',result_available:true,
    result_bytes:body.length,accepted,accepted_by:accepted?'deterministic':null};
}
function continuation(status, controllerReturn='RECORDED') {
  return {schema:'mastermind.fabric_continuation.v1',
    requested_run_id:identity.run_id,effective_run_id:status.run_id,
    effective_status:status,prior_attempts:[],controller_return:controllerReturn};
}
function capturedPage(body, offset, length=4096) {
  const page=body.subarray(offset,offset+length);
  return completed({exit_code:0,response_bytes:body.length,
    response_sha256:digest(body),offset,page_bytes:page.length,
    page_sha256:digest(page),page_base64:page.toString('base64')});
}
function scriptedFacade(outputs) {
  const calls=[];
  const engine={async callTool(request) {
    calls.push(request);
    assert.equal(request.name,'start_process');
    assert.ok(outputs.length,'unexpected adapter call');
    return outputs.shift();
  }};
  return {calls,facade:createFabricFacade(engine,{
    adapterPath:'/fixed/fixture.py',python:'python3',workerCwd:'~',quotaFallback:true,
  })};
}

test('paged capture rejects malformed or oversized envelopes before recording delivery',async t=>{
  const body=Buffer.alloc(65_537,'F');
  const status=leafStatus(identity.run_id,body);
  const page=body.subarray(0,4096);
  const valid={exit_code:0,response_bytes:body.length,response_sha256:digest(body),
    offset:0,page_bytes:page.length,page_sha256:digest(page),page_base64:page.toString('base64')};
  const cases=[
    ['extra field',{...valid,unexpected:true}],
    ['non-integer exit',{...valid,exit_code:0.5}],
    ['failed exit with success fields',{...valid,exit_code:1}],
    ['wrong total',{...valid,response_bytes:body.length+1}],
    ['wrong offset',{...valid,offset:1}],
    ['wrong page length',{...valid,page_bytes:page.length-1}],
    ['oversized base64',{...valid,page_base64:Buffer.alloc(4097,'F').toString('base64')}],
    ['wrong page digest',{...valid,page_sha256:'0'.repeat(64)}],
    ['invalid response digest',{...valid,response_sha256:'not-a-digest'}],
    ['capture error with extra field',{capture_error:'RESULT_NOT_UTF8',unexpected:true}],
  ];
  for(const [label,frame] of cases) await t.test(label,async()=>{
    const outputs=[capturedStatus(status),completed(frame),capturedStatus(status)];
    const {facade,calls}=scriptedFacade(outputs);
    const result=unwrap(await facade.call('fabric_result_page',identity));
    assert.equal(result.error,'RESULT_TRANSFER_INVALID');
    const accepted=unwrap(await facade.call('fabric_accept',{
      ...identity,by:'deterministic',expected_response_sha256:digest(body),
      verification_summary:'artifact_digest_comparison',
    }));
    assert.equal(accepted.error,'RESULT_NOT_FULLY_DELIVERED');
    assert.equal(outputs.length,0);
    assert.ok(!calls.some(x=>x.arguments.command.includes("'accept' ")));
  });
});

test('out-of-order and duplicate pages do not fill a gap or survive a backend generation',async()=>{
  const body=Buffer.alloc(65_537,'G');
  const status=leafStatus(identity.run_id,body);
  const outputs=[];
  for(const offset of [4096,0,0,4096]) outputs.push(capturedStatus(status),capturedPage(body,offset));
  outputs.push(capturedStatus(status));
  const {facade,calls}=scriptedFacade(outputs);
  for(const [offset,prefix] of [[4096,0],[0,4096],[0,4096],[4096,8192]]) {
    const page=unwrap(await facade.call('fabric_result_page',{...identity,offset}));
    assert.equal(page.delivered_prefix_bytes,prefix);
    assert.equal(page.full_result_delivered,false);
  }
  const acceptance={...identity,by:'deterministic',expected_response_sha256:digest(body),
    verification_summary:'artifact_digest_comparison'};
  assert.equal(unwrap(await facade.call('fabric_accept',acceptance)).error,'RESULT_NOT_FULLY_DELIVERED');
  const fresh=scriptedFacade([capturedStatus(status)]);
  assert.equal(unwrap(await fresh.facade.call('fabric_accept',acceptance)).error,'RESULT_NOT_FULLY_DELIVERED');
  assert.equal(outputs.length,0);
  assert.ok(![...calls,...fresh.calls].some(x=>x.arguments.command.includes("'accept' ")));
});

test('fully delivered bytes are hashed again before oversized acceptance',async()=>{
  const body=Buffer.alloc(65_537,'H');
  const changed=Buffer.alloc(body.length,'J');
  const status=leafStatus(identity.run_id,body);
  const outputs=[];
  for(let offset=0;offset<body.length;offset+=4096) {
    outputs.push(capturedStatus(status),capturedPage(body,offset));
  }
  outputs.push(capturedStatus(status),capturedPage(changed,0,1));
  const {facade,calls}=scriptedFacade(outputs);
  let last;
  for(let offset=0;offset<body.length;offset+=4096) {
    last=unwrap(await facade.call('fabric_result_page',{...identity,offset}));
    assert.equal(last.error,undefined);
  }
  assert.equal(last.full_result_delivered,true);
  const accepted=unwrap(await facade.call('fabric_accept',{
    ...identity,by:'deterministic',expected_response_sha256:digest(body),
    verification_summary:'artifact_digest_comparison',
  }));
  assert.equal(accepted.error,'RESULT_CHANGED');
  assert.equal(accepted.current_response_sha256,digest(changed));
  assert.equal(outputs.length,0);
  assert.ok(!calls.some(x=>x.arguments.command.includes("'accept' ")));
});

test('paged origin reads its effective successor and accepts only that fully delivered leaf',async()=>{
  const body=Buffer.alloc(65_537,'S');
  const leaf='synthetic-successor-a';
  const status=leafStatus(leaf,body);
  const outputs=[];
  for(let offset=0;offset<body.length;offset+=4096) {
    outputs.push(capturedStatus(continuation(status)),capturedPage(body,offset));
  }
  outputs.push(capturedStatus(continuation(status)));
  outputs.push(capturedStatus(status),capturedPage(body,0,1),
    capturedStatus({accepted:true}),capturedStatus(leafStatus(leaf,body,true)));
  const {facade,calls}=scriptedFacade(outputs);
  const chunks=[];
  for(let offset=0;offset<body.length;offset+=4096) {
    const page=unwrap(await facade.call('fabric_result_page',{
      ...identity,offset,max_bytes:4096,expected_response_sha256:digest(body),
    }));
    assert.equal(page.error,undefined,JSON.stringify(page));
    assert.equal(page.run_id,identity.run_id);
    assert.equal(page.effective_run_id,leaf);
    assert.equal(page.accept_run_id,leaf);
    assert.equal(page.delivered_prefix_bytes,Math.min(offset+4096,body.length));
    assert.equal(page.full_result_delivered,offset+4096>=body.length);
    chunks.push(Buffer.from(page.page_base64,'base64'));
  }
  assert.deepEqual(Buffer.concat(chunks),body);
  const acceptance={...identity,by:'deterministic',
    expected_response_sha256:digest(body),verification_summary:'artifact_digest_comparison'};
  const origin=unwrap(await facade.call('fabric_accept',acceptance));
  assert.equal(origin.error,'ACCEPT_EXPLICIT_SUCCESSOR_REQUIRED');
  const accepted=unwrap(await facade.call('fabric_accept',{...acceptance,run_id:leaf}));
  assert.equal(accepted.accepted,true,JSON.stringify(accepted));
  assert.equal(accepted.run_id,leaf);
  assert.equal(outputs.length,0);
  const resultCommands=calls.filter(x=>x.arguments.command.includes("'result' "));
  assert.equal(resultCommands.length,Math.ceil(body.length/4096)+1);
  for(const request of resultCommands) {
    assert.ok(request.arguments.command.includes("'result' '"+leaf+"' '--max-bytes' '8388608'"));
    assert.ok(!request.arguments.command.includes("'result' '"+identity.run_id+"'"));
  }
  const acceptCommands=calls.filter(x=>x.arguments.command.includes("'accept' "));
  assert.equal(acceptCommands.length,1);
  assert.ok(acceptCommands[0].arguments.command.includes("'accept' '"+leaf+"' '--by' 'deterministic'"));
});

test('paging refuses an unconfirmed continuation controller before reading retained bytes',async()=>{
  const body=Buffer.alloc(65_537,'U');
  const outputs=[capturedStatus(continuation(
    leafStatus('synthetic-unconfirmed-successor',body),'UNCONFIRMED'))];
  const {facade,calls}=scriptedFacade(outputs);
  const result=unwrap(await facade.call('fabric_result_page',identity));
  assert.equal(result.error,'CONTROLLER_RETURN_UNCONFIRMED');
  assert.equal(result.effective_run_id,'synthetic-unconfirmed-successor');
  assert.equal(calls.length,1);
  assert.ok(calls[0].arguments.command.includes("'status' '"+identity.run_id+"'"));
});

test('a changed successor cannot inherit an identical result delivery prefix',async()=>{
  const body=Buffer.alloc(65_537,'I');
  const first=leafStatus('synthetic-successor-first',body);
  const second=leafStatus('synthetic-successor-second',body);
  const outputs=[
    capturedStatus(continuation(first)),capturedPage(body,0),
    capturedStatus(continuation(second)),capturedPage(body,4096),
    capturedStatus(second),
  ];
  const {facade,calls}=scriptedFacade(outputs);
  const firstPage=unwrap(await facade.call('fabric_result_page',{
    ...identity,offset:0,max_bytes:4096,
  }));
  assert.equal(firstPage.delivered_prefix_bytes,4096);
  const secondPage=unwrap(await facade.call('fabric_result_page',{
    ...identity,offset:4096,max_bytes:4096,expected_response_sha256:firstPage.response_sha256,
  }));
  assert.equal(secondPage.error,undefined,JSON.stringify(secondPage));
  assert.equal(secondPage.response_sha256,firstPage.response_sha256);
  assert.equal(secondPage.effective_run_id,second.run_id);
  assert.equal(secondPage.accept_run_id,second.run_id);
  assert.equal(secondPage.delivered_prefix_bytes,0);
  assert.equal(secondPage.full_result_delivered,false);
  const accepted=unwrap(await facade.call('fabric_accept',{
    ...identity,run_id:second.run_id,by:'deterministic',
    expected_response_sha256:firstPage.response_sha256,
    verification_summary:'artifact_digest_comparison',
  }));
  assert.equal(accepted.error,'RESULT_NOT_FULLY_DELIVERED');
  assert.equal(outputs.length,0);
  assert.ok(!calls.some(x=>x.arguments.command.includes("'accept' ")));
});
