import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {tmpdir,homedir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import {startGateway} from './gateway.mjs';
import {createTunnelAuth} from './private-tunnel-auth.mjs';
import {FABRIC_TOOLS} from './fabric-backend.mjs';

// Opt-in host qualification, not a green skipped provider test in normal CI.
// The normal portable suite is fabric-backend.test.mjs. This requires the installed
// maintained Desktop Commander engine and never invokes the production Fabric.
const hostEngine=process.env.MMX_FABRIC_ENGINE_ENTRY;
assert.ok(hostEngine,'MMX_FABRIC_ENGINE_ENTRY must name the installed maintained engine');
test('real HTTP + SDK + maintained process owner: cross-session retained result and acceptance',async t=>{
 const directory=await mkdtemp(join(tmpdir(),'mmx-fabric-http-'));
 const clients=[];
 const gateway=await startGateway({host:'127.0.0.1',port:0,backendMode:'shared-account',
  command:process.execPath,args:[fileURLToPath(new URL('./fabric-backend.mjs',import.meta.url))],cwd:homedir(),
  stateDir:join(directory,'gateway'),requestTimeoutMs:30000,fabricOnly:true,gitPublish:false,paperDesign:false,
  childEnv:{NODE_OPTIONS:'',MMX_FABRIC_ENGINE_ENTRY:hostEngine,
    MMX_FABRIC_SDK_PACKAGE:fileURLToPath(new URL('./package.json',import.meta.url)),
    MMX_FABRIC_ADAPTER_PATH:fileURLToPath(new URL('./fixtures/fabric-adapter.py',import.meta.url)),
    FABRIC_FIXTURE_STATE:directory},
 },createTunnelAuth({accountLabel:'fabric-qualification'}));
 t.after(async()=>{for(const c of clients) await c.close();await gateway.close();await rm(directory,{recursive:true,force:true});});
 const connect=async()=>{
  const client=new Client({name:'fabric-http-qualification',version:'0.1.0'});
  clients.push(client);
  const transport=new StreamableHTTPClientTransport(new URL(gateway.url));
  await client.connect(transport);
  return {client,transport};
 };
 const value=result=>result.structuredContent??JSON.parse(result.content[0].text);
 const call=async(client,name,args)=>value(await client.callTool({name,arguments:args},undefined,{timeout:30000}));
 const first=await connect();
 const names=(await first.client.listTools()).tools.map(t=>t.name);
 for(const tool of FABRIC_TOOLS) assert.ok(names.includes(tool.name));
 assert.ok(names.every(n=>n.startsWith('fabric_')||n==='studio_ping'||n==='studio_output_page'));
 // This source tree also contains Context/Browser/Computer implementations.
 // A Fabric-only account must not silently inherit any of those tools.
 for(const forbidden of ['resolve_context','atlas_search','browser_click','execute_shell','computer_click'])
   assert.ok(!names.includes(forbidden));
 const capability=await call(first.client,'fabric_capabilities',{});
 assert.equal(capability.worker_admission,'UNPROBED');
 assert.equal(capability.worker_start,'UNPROBED');
 assert.equal(capability.root_metadata_is_authentication,false);
 const injected={run_id:'http-unauthorized-host-000',root_id:'http-qualification-001',
   parent_id:'http-qualification-001',task_class:'mechanical',
   task_complexity:'C0_MECHANICAL',work_packet:'Fixture only',host:'ubuntu1'};
 let refused=false;
 try { const answer=await first.client.callTool({name:'fabric_request',arguments:injected});
   refused=answer.isError===true;
 } catch { refused=true; } // MCP SDK schema may deny before the backend runs.
 assert.equal(refused,true);
 await assert.rejects(readFile(join(directory,injected.run_id+'.packet'),'utf8'),{code:'ENOENT'});
 const identity={run_id:'http-fixture-001',root_id:'http-qualification-001'};
 const request=await call(first.client,'fabric_request',{...identity,parent_id:identity.root_id,
   task_class:'mechanical',task_complexity:'C0_MECHANICAL',work_packet:'OBJECTIVE: fixture transport qualification. No provider calls.'});
 assert.ok(request.controller_pid);assert.equal(request.worker_started,null);
 await first.transport.terminateSession();
 const second=await connect();
 const observed=await call(second.client,'fabric_status',identity);
 assert.equal(observed.status.state,'DONE');assert.equal(observed.root_verified,true);
 const output=await call(second.client,'fabric_controller_output',{...identity,controller_pid:request.controller_pid});
 assert.ok(output.process_output);
 const result=await call(second.client,'fabric_result',identity);
 assert.equal(result.adapter_response,'RETURN: VERIFIED\n\n');
 const accepted=await call(second.client,'fabric_accept',{...identity,by:'deterministic',
  expected_response_sha256:result.response_sha256,verification_summary:'Compared exact isolated fixture bytes across HTTP session replacement.'});
 assert.equal(accepted.accepted,true);
 assert.equal(gateway.stats().backend.spawns,1);
 assert.match(await readFile(join(directory,identity.run_id+'.packet'),'utf8'),/No provider calls/);
 // A maximally useful bounded packet is still a LITERAL stdin payload when
 // the actual maintained M2 engine, HTTPS-like MCP client, gateway and native
 // controller all participate. Small synthetic packets alone miss the native
 // shell's platform-dependent here-doc/pipe backpressure failure modes.
 const largePacket='OBJECTIVE: Verify that a full bounded Fabric work packet is transmitted byte-for-byte.\n'
   + 'context-evidence-'.repeat(850)
   + '\nLITERAL ONLY: $HOME $(echo forbidden) `echo forbidden` \'quoted\' 🧩 /tmp/not-a-command';
 assert.ok(largePacket.length<16000);
 assert.ok(Buffer.byteLength(largePacket,'utf8')<32768);
 const largeId={run_id:'http-fixture-large-002',root_id:identity.root_id};
 const largeRequest=await call(second.client,'fabric_request',{
   ...largeId,parent_id:largeId.root_id,task_class:'mechanical',
   task_complexity:'C0_MECHANICAL',work_packet:largePacket});
 assert.ok(largeRequest.controller_pid);
 assert.equal(largeRequest.worker_started,null);
 const largeOutput=await call(second.client,'fabric_controller_output',{
   ...largeId,controller_pid:largeRequest.controller_pid});
 assert.ok(largeOutput.process_output);
 const largeStatus=await call(second.client,'fabric_status',largeId);
 assert.equal(largeStatus.status.state,'DONE');
 assert.equal(largeStatus.root_verified,true);
 assert.equal(await readFile(join(directory,largeId.run_id+'.packet'),'utf8'),largePacket+'\n');
 const largeResult=await call(second.client,'fabric_result',largeId);
 assert.equal(largeResult.adapter_response,'RETURN: VERIFIED\n\n');
 const largeAccepted=await call(second.client,'fabric_accept',{
   ...largeId,by:'deterministic',expected_response_sha256:largeResult.response_sha256,
   verification_summary:'Verified the full 12KiB literal packet and complete retained fixture result across the same engine process.'});
 assert.equal(largeAccepted.accepted,true);
 assert.equal(gateway.stats().backend.spawns,1);
});
