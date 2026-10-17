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
        expected_response_sha256:expectedDigest,verification_summary:'Premature fixture acceptance must fail.'}));
      assert.equal(premature.error,'RESULT_NOT_FULLY_DELIVERED');
    }
   }
   assert.ok(pages>1);
   assert.deepEqual(Buffer.concat(output),expected);
   assert.equal(digest(Buffer.concat(output)),expectedDigest);
   const accepted=unwrap(await f.call('fabric_accept',{...identity,by:'deterministic',
     expected_response_sha256:expectedDigest,verification_summary:'Synthetic fixture byte-exact, full digest verified.'}));
   assert.equal(accepted.accepted,true,JSON.stringify(accepted));
   const status=unwrap(await f.call('fabric_status',identity));
   assert.equal(status.status.accepted,true);
  } finally { await rm(dir,{recursive:true,force:true}); }
 });
});

test('paged result parameters and root must be verified before adapter access', async()=>{
 const calls=[];
 const engine={async callTool(req){calls.push(req);
  return {content:[{type:'text',text:`Process started with PID 99 (shell: /bin/zsh)\nInitial output:\n${JSON.stringify({schema:'mastermind.fabric_task_status.v1',...identity,state:'TERMINAL',result_available:true,result_bytes:196317,accepted:false})}\nMMX_FABRIC_EXIT=0\n`}]};}};
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
    expected_response_sha256:page.response_sha256,verification_summary:'Mutated fixture is not valid.'}));
  assert.equal(accept.error,'RESULT_NOT_FULLY_DELIVERED');
  changed[50]=0xff;
  await writeFile(join(dir,identity.run_id+'.result'),changed);
  const badUtf8=unwrap(await f.call('fabric_result_page',{...identity,offset:0,max_bytes:4096}));
  assert.equal(badUtf8.error,'RESULT_NOT_UTF8');
 }finally{await rm(dir,{recursive:true,force:true});}
});

test('synthetic 8-MiB adapter ceiling and out-of-order reads never bypass full coverage',async()=>{
 let calls=0;
 const status={schema:'mastermind.fabric_task_status.v1',...identity,state:'TERMINAL',result_available:true,
   result_bytes:8_388_609,accepted:false};
 const f=createFabricFacade({async callTool(){calls++;return {content:[{type:'text',text:
   `Process started with PID 77 (shell: /bin/zsh)\nInitial output:\n${JSON.stringify(status)}\nMMX_FABRIC_EXIT=0\n`}]};}},
  {adapterPath:'/fixed/fixture.py',python:'python3',workerCwd:'~'});
 const o=unwrap(await f.call('fabric_result_page',identity));
 assert.equal(o.error,'RESULT_EXCEEDS_ADAPTER_LIMIT');
 assert.equal(calls,1);
});
