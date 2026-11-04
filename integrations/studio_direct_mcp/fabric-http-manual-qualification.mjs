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

// Opt-in test: real authenticated HTTP/MCP + Desktop Commander engine transport,
// synthetic native preview/request fixture ONLY. Never calls a provider.
const entry=process.env.MMX_FABRIC_ENGINE_ENTRY;
assert.ok(entry,'MMX_FABRIC_ENGINE_ENTRY must name the qualified installed engine');

test('authenticated Web MCP exact GLM pin -> native preview -> strict request -> result -> accept',async t=>{
 const state=await mkdtemp(join(tmpdir(),'mmx-fabric-manual-http-'));
 const clients=[];
 const gateway=await startGateway({host:'127.0.0.1',port:0,backendMode:'shared-account',
   command:process.execPath,args:[fileURLToPath(new URL('./fabric-backend.mjs',import.meta.url))],
   cwd:homedir(),stateDir:join(state,'gateway'),requestTimeoutMs:30000,
   fabricOnly:true,gitPublish:false,paperDesign:false,
   childEnv:{NODE_OPTIONS:'',MMX_FABRIC_ENGINE_ENTRY:entry,
     MMX_FABRIC_SDK_PACKAGE:fileURLToPath(new URL('./package.json',import.meta.url)),
     MMX_FABRIC_ADAPTER_PATH:fileURLToPath(new URL('./fixtures/fabric-adapter-manual.py',import.meta.url)),
     FABRIC_FIXTURE_STATE:state},
 },createTunnelAuth({accountLabel:'fabric-manual-qualification'}));
 t.after(async()=>{for(const c of clients) await c.close();await gateway.close();await rm(state,{recursive:true,force:true});});
 const connect=async()=>{
   const client=new Client({name:'manual-qualification',version:'0.1.0'});
   clients.push(client);
   const transport=new StreamableHTTPClientTransport(new URL(gateway.url));
   await client.connect(transport);
   return {client,transport};
 };
 const decode=r=>r.structuredContent??JSON.parse(r.content[0].text);
 const call=(client,name,args)=>client.callTool({name,arguments:args},undefined,{timeout:30000}).then(decode);
 const first=await connect();
 const spec=(await first.client.listTools()).tools.find(x=>x.name==='fabric_request')?.inputSchema;
 assert.ok(spec);
 assert.deepEqual(spec.properties.pool.enum,['grok','glm','minimax','bailian','cursor','ocfree','go']);
 assert.equal(spec.properties.model.type,'string');
 const cap=await call(first.client,'fabric_capabilities',{});
 assert.equal(cap.manual_routing.available,true);
 assert.equal(cap.manual_routing.cross_provider_fallback,false);
 const id={run_id:'http-manual-glm-001',root_id:'http-manual-original-001'};
 const request=await call(first.client,'fabric_request',{...id,parent_id:id.root_id,
   task_class:'review',task_complexity:'C2_COMPLEX_BOUNDED',pool:'glm',model:'glm-5.3',
   subject_pool:'openai',max_turns:12,
   work_packet:'READ-ONLY SYNTHETIC MODEL PIN ACCEPTANCE. Never contact a provider.'});
 assert.equal(request.delivery,'CONTROLLER_CREATED',JSON.stringify(request));
 assert.equal(request.worker_started,null);
 assert.equal(request.requested_model,'glm-5.3');
 assert.equal(request.strict_manual_pin,true);
 const route=JSON.parse(await readFile(join(state,id.run_id+'.route'),'utf8'));
 assert.deepEqual(route,{pool:'glm',model:'glm-5.3',strict:true,quota_fallback:false,
   max_turns:12,subject_pool:'openai',root:id.root_id,parent:id.root_id});
 assert.match(await readFile(join(state,id.run_id+'.packet'),'utf8'),/Never contact a provider/);
 await first.transport.terminateSession();
 const second=await connect();
 const status=await call(second.client,'fabric_status',id);
 assert.equal(status.status.state,'DONE');assert.equal(status.root_verified,true);
 const result=await call(second.client,'fabric_result',id);
 assert.equal(result.adapter_response,'RETURN: VERIFIED\n\n');
 assert.equal(result.accept_run_id,id.run_id);
 const accepted=await call(second.client,'fabric_accept',{...id,by:'deterministic',
   expected_response_sha256:result.response_sha256,verification_summary:'artifact_digest_comparison'});
 assert.equal(accepted.accepted,true);
 assert.equal(gateway.stats().backend.spawns,1);
});
