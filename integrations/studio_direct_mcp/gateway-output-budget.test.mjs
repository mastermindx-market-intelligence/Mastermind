import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import {startGateway} from './gateway.mjs';
const fixture=new URL('./fixtures/shared-state-backend.mjs',import.meta.url).pathname;
const auth={middleware(req,_res,next){const principal=req.headers.authorization;
  if(!['alice','bob'].includes(principal))throw Object.assign(new Error('unauthorized'),{statusCode:401});
  req.auth={principal,clientId:principal,scopes:['studio.control']};next();}};
const call=(c,name,args={})=>c.callTool({name,arguments:args});
const body=r=>JSON.parse(r.content[0].text);
const size=r=>Buffer.byteLength(JSON.stringify(r));
async function setup(t,extra={}){
  const gateway=await startGateway({host:'127.0.0.1',port:0,command:process.execPath,args:[fixture],
    backendMode:'shared-account',requestTimeoutMs:3000,childEnv:{NODE_OPTIONS:''},...extra},auth);
  const clients=[];
  t.after(async()=>{for(const c of clients)await c.close();await gateway.close();});
  async function connect(principal='alice'){
    const client=new Client({name:'output-budget-test',version:'1'});clients.push(client);
    const transport=new StreamableHTTPClientTransport(new URL(gateway.url),{requestInit:{headers:{authorization:principal}}});
    await client.connect(transport);await client.listTools();return {client,transport};
  }return {gateway,connect};
}
async function reconstruct(client,receipt){let offset=0;const chunks=[];
  for(let n=0;n<200;n++){
    const out=await call(client,'studio_output_page',{receipt_id:receipt.receipt_id,offset});assert.ok(size(out)<=16384);
    const page=body(out);assert.equal(page.status,'OUTPUT_PAGE');assert.equal(page.offset,offset);chunks.push(page.text);
    if(page.done){const raw=chunks.join('');assert.equal(Buffer.byteLength(raw),receipt.source_bytes);
      assert.equal(createHash('sha256').update(raw).digest('hex'),receipt.sha256);return JSON.parse(raw);}
    assert.ok(page.next_offset>offset);offset=page.next_offset;
  }assert.fail('result did not finish paging');
}
async function reconstructCompat(client,receipt,gateway){let offset=0;const chunks=[];
  const backendOpsBefore=gateway.stats().requests.backendOps;
  for(let n=0;n<200;n++){
    const out=await call(client,'read_file',{path:receipt.compat_read_path,offset,length:1,origin:'llm'});
    assert.ok(size(out)<=16384);const page=body(out);assert.equal(page.status,'OUTPUT_PAGE');
    assert.equal(page.offset,offset);chunks.push(page.text);
    if(page.done){const raw=chunks.join('');assert.equal(Buffer.byteLength(raw),receipt.source_bytes);
      assert.equal(createHash('sha256').update(raw).digest('hex'),receipt.sha256);
      assert.equal(gateway.stats().requests.backendOps,backendOpsBefore);return JSON.parse(raw);}
    assert.ok(page.next_offset>offset);offset=page.next_offset;
  }assert.fail('compat result did not finish paging');
}
test('catalog exposes exactly one narrow read-only paging tool',async t=>{
  const {connect}=await setup(t),a=await connect();const tools=(await a.client.listTools()).tools;
  const pages=tools.filter(x=>x.name==='studio_output_page');assert.equal(pages.length,1);
  assert.equal(pages[0].annotations.readOnlyHint,true);assert.equal(pages[0].inputSchema.additionalProperties,false);
});
test('real MCP large result is bounded, exact, and executed only once',async t=>{
  const {gateway,connect}=await setup(t),a=await connect();
  const cmd='BEGIN '+('🧠\\\"\n').repeat(10000)+' END';
  const first=await call(a.client,'start_process',{cmd});assert.ok(size(first)<=16384);
  const receipt=body(first);assert.equal(receipt.status,'OUTPUT_PAGED');
  t.diagnostic(JSON.stringify({proof:'text-result-ingestion',sourceBytes:receipt.source_bytes,initialResponseBytes:size(first),reductionFraction:1-size(first)/receipt.source_bytes}));
  const exact=body(await reconstruct(a.client,receipt));assert.equal(exact.cmd,cmd);assert.equal(exact.pid,10001);
  const next=body(await call(a.client,'start_process',{cmd:'next'}));assert.equal(next.pid,10002);
  assert.equal(gateway.stats().backend.spawns,1);
});
test('shared-owner result survives creator frontend DELETE',async t=>{
  const {gateway,connect}=await setup(t),a=await connect(),b=await connect();const cmd='retain-'+('x'.repeat(50000));
  const receipt=body(await call(a.client,'start_process',{cmd}));assert.equal(receipt.status,'OUTPUT_PAGED');
  await a.transport.terminateSession();const exact=body(await reconstruct(b.client,receipt));assert.equal(exact.cmd,cmd);
  assert.equal(gateway.stats().backend.spawns,1);
});
test('foreign principal cannot retrieve another owner result',async t=>{
  const {connect}=await setup(t),a=await connect('alice'),b=await connect('bob');
  const receipt=body(await call(a.client,'start_process',{cmd:'private-'+('x'.repeat(50000))}));assert.equal(receipt.status,'OUTPUT_PAGED');
  const out=await call(b.client,'studio_output_page',{receipt_id:receipt.receipt_id,offset:0});assert.equal(out.isError,true);
  assert.equal(body(out).status,'OUTPUT_NOT_AVAILABLE');assert.doesNotMatch(JSON.stringify(out),/private-/);
});
test('per-session mode does not share receipt with same principal sibling',async t=>{
  const {connect}=await setup(t,{backendMode:'per-session'}),a=await connect(),b=await connect();
  const receipt=body(await call(a.client,'start_process',{cmd:'x'.repeat(50000)}));assert.equal(receipt.status,'OUTPUT_PAGED');
  const out=await call(b.client,'studio_output_page',{receipt_id:receipt.receipt_id,offset:0});assert.equal(out.isError,true);
  assert.equal(body(out).status,'OUTPUT_NOT_AVAILABLE');
});
test('unknown receipt is a local read and makes no tool call to backend',async t=>{
  const {gateway,connect}=await setup(t),a=await connect();const before=gateway.stats().backend.spawns;
  const out=await call(a.client,'studio_output_page',{receipt_id:'00000000-0000-0000-0000-000000000000',offset:0});
  assert.equal(out.isError,true);assert.equal(body(out).status,'OUTPUT_NOT_AVAILABLE');
  assert.equal(gateway.stats().backend.spawns,before);
});

test('projection failure never becomes a backend failure or repeats an effect',async t=>{
  const {TextOutputPager}=await import('./output-budget.mjs');
  const {gateway,connect}=await setup(t),a=await connect();
  const saved=TextOutputPager.prototype.project;
  TextOutputPager.prototype.project=function(){throw new Error('private projection internals');};
  let failed;
  try{failed=await call(a.client,'start_process',{cmd:'one-effect'});}
  finally{TextOutputPager.prototype.project=saved;}
  const receipt=body(failed);
  assert.equal(receipt.status,'OUTPUT_PROJECTION_FAILED');
  assert.equal(receipt.backend_result_received,true);
  assert.doesNotMatch(JSON.stringify(failed),/private projection internals|EFFECT_UNKNOWN|NOT_APPLIED/);
  assert.equal(body(await call(a.client,'start_process',{cmd:'next-effect'})).pid,10002);
  assert.equal(gateway.stats().backend.spawns,1);
});

test('frozen app snapshot can page through existing read_file without backend replay',async t=>{
  const {gateway,connect}=await setup(t),a=await connect();
  const cmd='compat-'+('z'.repeat(50000));
  const first=await call(a.client,'start_process',{cmd});const receipt=body(first);
  assert.equal(receipt.status,'OUTPUT_PAGED');
  assert.equal(receipt.compat_read_tool,'read_file');
  assert.equal(receipt.compat_offset_argument,'offset');
  assert.equal(receipt.compat_read_path,`studio-output://receipt/${receipt.receipt_id}`);
  const exact=body(await reconstructCompat(a.client,receipt,gateway));
  assert.equal(exact.cmd,cmd);assert.equal(exact.pid,10001);
  const next=body(await call(a.client,'start_process',{cmd:'next'}));assert.equal(next.pid,10002);
});

test('frozen compat receipt survives creator frontend deletion for same owner',async t=>{
  const {gateway,connect}=await setup(t),a=await connect(),b=await connect();
  const cmd='compat-reconnect-'+('r'.repeat(50000));
  const receipt=body(await call(a.client,'start_process',{cmd}));
  assert.equal(receipt.status,'OUTPUT_PAGED');
  const before=gateway.stats().requests.backendOps;
  await a.transport.terminateSession();
  const exact=body(await reconstructCompat(b.client,receipt,gateway));
  assert.equal(exact.cmd,cmd);
  assert.equal(gateway.stats().requests.backendOps,before);
  assert.equal(gateway.stats().backend.spawns,1);
});

test('frozen compat read remains owner-bound and never reaches foreign backend',async t=>{
  const {gateway,connect}=await setup(t),a=await connect('alice'),b=await connect('bob');
  const receipt=body(await call(a.client,'start_process',{cmd:'private-'+('x'.repeat(50000))}));
  const before=gateway.stats().requests.backendOps;
  const out=await call(b.client,'read_file',{path:receipt.compat_read_path,offset:0,length:1,origin:'llm'});
  assert.equal(out.isError,true);assert.equal(body(out).status,'OUTPUT_NOT_AVAILABLE');
  assert.equal(gateway.stats().requests.backendOps,before);
  assert.doesNotMatch(JSON.stringify(out),/private-/);
});

test('reserved frozen compat path refuses malformed receipt locally',async t=>{
  const {gateway,connect}=await setup(t),a=await connect();
  const before=gateway.stats().requests.backendOps;
  const out=await call(a.client,'read_file',{
    path:'studio-output://receipt/not-a-receipt',offset:0,length:1,origin:'llm'});
  assert.equal(out.isError,true);assert.equal(body(out).status,'OUTPUT_PAGE_ARGUMENT_INVALID');
  assert.equal(gateway.stats().requests.backendOps,before);
});

