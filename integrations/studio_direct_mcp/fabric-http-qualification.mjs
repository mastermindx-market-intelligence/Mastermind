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
 const identity={run_id:'http-fixture-001',root_id:'http-qualification-001'};
 const request=await call(first.client,'fabric_request',{...identity,parent_id:identity.root_id,
   task_class:'mechanical',task_complexity:'C0_MECHANICAL',work_packet:'OBJECTIVE: fixture transport qualification. No provider calls.'});
 assert.ok(request.controller_pid,JSON.stringify(request));assert.equal(request.worker_started,null);
 await first.transport.terminateSession();
 const second=await connect();
 const observed=await call(second.client,'fabric_status',identity);
 assert.equal(observed.status.state,'DONE');assert.equal(observed.root_verified,true);
 const output=await call(second.client,'fabric_controller_output',{...identity,controller_pid:request.controller_pid});
 assert.ok(output.process_output);
 const result=await call(second.client,'fabric_result',identity);
 assert.equal(result.adapter_response,'RETURN: VERIFIED\n\n');
 const accepted=await call(second.client,'fabric_accept',{...identity,by:'deterministic',
  expected_response_sha256:result.response_sha256,verification_summary:'artifact_digest_comparison'});
 assert.equal(accepted.accepted,true);
 assert.equal(gateway.stats().backend.spawns,1);
 assert.match(await readFile(join(directory,identity.run_id+'.packet'),'utf8'),/No provider calls/);
});
