/**
 * Explicit host-only synthetic composition qualification.
 * Does not invoke any real Fabric run, provider, production ledger or credentials.
 * The caller must select exact reviewed source backend and disposable fixture.
 * This is opt-in and deliberately excluded from normal *.test.mjs CI.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { startPrivateGateway } from './private-tunnel-gateway.mjs';

const backend = process.env.MMX_SYNTHETIC_PAGING_BACKEND;
const adapter = process.env.MMX_SYNTHETIC_PAGING_ADAPTER;
const engineEntry = process.env.MMX_FABRIC_ENGINE_ENTRY;
if (process.env.MMX_SYNTHETIC_PAGING_TEST !== '1' ||
    [backend,adapter,engineEntry].some(x=>!x || !isAbsolute(x))) {
  throw new Error('SYNTHETIC_PAGING_QUALIFICATION_REQUIRES_EXPLICIT_LOCAL_SOURCE_AND_ENGINE');
}
const [backendText,adapterText] = await Promise.all([readFile(backend,'utf8'),readFile(adapter,'utf8')]);
if (!backendText.includes("tool('fabric_result_page'") ||
    !adapterText.includes('FABRIC_FIXTURE_RESULT_BYTES') ||
    !adapterText.includes('Isolated CLI fixture for facade tests')) {
  throw new Error('SYNTHETIC_PAGING_QUALIFICATION_SOURCE_NOT_VERIFIED');
}
const digest = bytes=>createHash('sha256').update(bytes).digest('hex');
const unwrap = result=>result.structuredContent ?? JSON.parse(result.content.find(c=>c.type==='text').text);
const dir = await mkdtemp(join(tmpdir(),'mmx-modern-fabric-paging-'));
const identity={run_id:'synthetic-modern-paging-001',root_id:'synthetic-modern-paging-root'};
const packet={...identity,parent_id:identity.root_id,task_class:'mechanical',
  task_complexity:'C0_MECHANICAL',work_packet:'SYNTHETIC: read-only qualification; no provider, production ledger or real run.'};
const expectedBytes=196317;
const expected=Buffer.from('SYNTHETIC RESULT\n'+'R'.repeat(expectedBytes-Buffer.byteLength('SYNTHETIC RESULT\n')));
const clients=[];
let gateway;
async function connect(){
  const client=new Client({name:'synthetic-modern-fabric-paging',version:'0.0.1'},
    {versionNegotiation:{mode:{pin:'2026-07-28'},probe:{timeoutMs:3000,maxRetries:0}}});
  clients.push(client);
  await client.connect(new StreamableHTTPClientTransport(new URL(gateway.url)));
  return client;
}
async function call(c,name,args){return unwrap(await c.callTool({name,arguments:args},undefined,{timeout:30000}));}
try {
  gateway=await startPrivateGateway({host:'127.0.0.1',port:0,accountLabel:'synthetic-modern-paging',
    modernFabricProtocol:true,fabricOnly:true,backendMode:'shared-account',
    command:process.execPath,args:[backend],cwd:homedir(),requestTimeoutMs:30000,
    childEnv:{NODE_OPTIONS:'',MMX_FABRIC_ENGINE_ENTRY:engineEntry,
      MMX_FABRIC_SDK_PACKAGE:fileURLToPath(new URL('./package.json',import.meta.url)),
      MMX_FABRIC_ADAPTER_PATH:adapter,FABRIC_FIXTURE_STATE:dir,
      FABRIC_FIXTURE_RESULT_BYTES:String(expectedBytes)}});
  const first=await connect();
  const catalog=(await first.listTools()).tools.map(x=>x.name);
  assert.equal(catalog.length,10);
  assert.ok(catalog.includes('fabric_result_page'));
  assert.ok(!catalog.includes('start_process'));
  const submitted=await call(first,'fabric_request',packet);
  assert.equal(submitted.action,'fabric_request',JSON.stringify(submitted));
  const generation=gateway.stats().backend.owners[0].generation;
  await first.close();
  const second=await connect();
  const status=await call(second,'fabric_status',identity);
  assert.equal(status.status.result_available,true);
  assert.equal(status.status.result_bytes,expectedBytes);
  assert.equal(status.root_verified,true);
  const tooLarge=await call(second,'fabric_result',{...identity,max_bytes:65536});
  assert.equal(tooLarge.error,'RESULT_TOO_LARGE');
  let offset=0,expectedHash=null,pages=0;const chunks=[];
  while(offset<expectedBytes) {
    const page=await call(second,'fabric_result_page',{...identity,offset,max_bytes:4096,
      ...(expectedHash?{expected_response_sha256:expectedHash}:{})});
    assert.equal(page.error,undefined,JSON.stringify({error:page.error,status:page.status}));
    assert.equal(page.response_bytes,expectedBytes);
    assert.equal(page.offset,offset);
    assert.equal(page.page_bytes,Math.min(4096,expectedBytes-offset));
    const bytes=Buffer.from(page.page_base64,'base64');
    assert.equal(digest(bytes),page.page_sha256);
    assert.equal(bytes.length,page.page_bytes);
    if(expectedHash)assert.equal(page.response_sha256,expectedHash);
    expectedHash=page.response_sha256;
    chunks.push(bytes);
    offset=page.next_offset;
    pages++;
    if(pages===1) {
      const premature=await call(second,'fabric_accept',{...identity,by:'deterministic',
        expected_response_sha256:expectedHash,verification_summary:'Synthetic partial result must never be accepted.'});
      assert.equal(premature.error,'RESULT_NOT_FULLY_DELIVERED');
    }
  }
  assert.ok(pages>1);
  assert.deepEqual(Buffer.concat(chunks),expected);
  assert.equal(digest(expected),expectedHash);
  assert.equal(gateway.stats().backend.spawns,1);
  assert.equal(gateway.stats().backend.owners[0].generation,generation);
  const accepted=await call(second,'fabric_accept',{...identity,by:'deterministic',
    expected_response_sha256:expectedHash,
    verification_summary:'Verified exact synthetic 196317 bytes and complete SHA256 through modern HTTP.'});
  assert.equal(accepted.accepted,true,JSON.stringify(accepted));
  const finalStatus=await call(second,'fabric_status',identity);
  assert.equal(finalStatus.status.accepted,true);
  console.log(JSON.stringify({qualification:'synthetic-modern-paging',result:'PASS',
    page_count:pages,bytes:expectedBytes,sha256:expectedHash,root_verified:true,
    backend_spawns:gateway.stats().backend.spawns,accepted_fixture_only:true}));
} finally {
  for(const c of clients) await c.close().catch(()=>{});
  await gateway?.close();
  await rm(dir,{recursive:true,force:true});
}
