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

test('authenticated Web MCP exact GLM and Experiential synthetic pins -> strict request -> result -> accept',async t=>{
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
 assert.deepEqual(spec.properties.pool.enum,['grok','glm','minimax','bailian','cursor','ocfree','go','byteplus','experiential']);
 assert.equal(spec.properties.model.type,'string');
 for(const consent of ['retention_opt_in','sensitive_data_opt_in','code_exposure_opt_in'])
   assert.equal(spec.properties[consent].type,'boolean');
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

 // Actual authenticated MCP/Studio process path, but ONLY a synthetic adapter:
 // no provider, credential, installed Experiential picker, or billable call.
 const exp={run_id:'http-manual-exp-001',root_id:'http-manual-original-exp-001'};
 const expRequest=await call(second.client,'fabric_request',{...exp,parent_id:exp.root_id,
   task_class:'mechanical',task_complexity:'C0_MECHANICAL',
   pool:'experiential',model:'glm-5.3-uncensored',retention_opt_in:true,
   sensitive_data_opt_in:true,code_exposure_opt_in:true,
   work_packet:'PUBLIC SYNTHETIC manual model selection; never contact a provider.'});
 assert.equal(expRequest.delivery,'CONTROLLER_CREATED',JSON.stringify(expRequest));
 assert.equal(expRequest.worker_started,null);
 assert.equal(expRequest.requested_pool,'experiential');
 assert.equal(expRequest.requested_model,'glm-5.3-uncensored');
 assert.equal(expRequest.retention_opt_in,true);
 assert.equal(expRequest.sensitive_data_opt_in,true);
 assert.equal(expRequest.code_exposure_opt_in,true);
 assert.equal(expRequest.strict_manual_pin,true);
 const expRoute=JSON.parse(await readFile(join(state,exp.run_id+'.route'),'utf8'));
 assert.deepEqual(expRoute,{pool:'experiential',model:'glm-5.3-uncensored',
   strict:true,quota_fallback:false,max_turns:null,subject_pool:null,
   root:exp.root_id,parent:exp.root_id,
   experiential_retention_acknowledged:true,
   experiential_sensitive_data_opt_in:true,
   experiential_proprietary_code:true,
   experiential_code_exposure_opt_in:true});
 assert.match(await readFile(join(state,exp.run_id+'.packet'),'utf8'),/PUBLIC SYNTHETIC/);
 const expStatus=await call(second.client,'fabric_status',exp);
 assert.equal(expStatus.status.state,'DONE');
 assert.equal(expStatus.root_verified,true);
 const expResult=await call(second.client,'fabric_result',exp);
 assert.equal(expResult.adapter_response,'RETURN: VERIFIED\n\n');
 const expAccepted=await call(second.client,'fabric_accept',{...exp,by:'deterministic',
   expected_response_sha256:expResult.response_sha256,verification_summary:'artifact_digest_comparison'});
 assert.equal(expAccepted.accepted,true);

 // Exercise the complete HTTP/schema -> native-argument -> result -> acceptance
 // path for plan selectors, using only the isolated synthetic adapter.
 for(const [suffix,pool,requested,resolved] of [
  ['byteplus-ds','byteplus','deepseek-v4.1-flash','deepseek-v4.1-flash'],
  ['byteplus-default','byteplus','auto','glm-5.3-flash'],
  ['exp-included','experiential','free','deepseek-v4.1-flash'],
  ['exp-paid','experiential','uncensored','deepseek-v4.1-flash-uncensored'],
  ['exp-glm','experiential','glm-5.3-flash-uncensored','glm-5.3-flash-uncensored'],
  ['exp-auto',undefined,undefined,undefined],
 ]){
  const plan={run_id:'http-plan-'+suffix,root_id:'http-plan-original'};
  const consents={retention_opt_in:true,sensitive_data_opt_in:true,code_exposure_opt_in:true};
  const args={...plan,parent_id:plan.root_id,task_class:'mechanical',task_complexity:'C0_MECHANICAL',
    work_packet:'PUBLIC SYNTHETIC plan selection; never contact a provider.',
    ...(pool?{pool,model:requested}:{}),
    ...(pool==='experiential'||!pool?consents:{}),...(!pool?{response_only:true}:{})};
  const submitted=await call(second.client,'fabric_request',args);
  assert.equal(submitted.delivery,'CONTROLLER_CREATED',JSON.stringify(submitted));
  assert.equal(submitted.resolved_model,resolved);assert.equal(submitted.worker_start_proven,false);
  const native=JSON.parse(await readFile(join(state,plan.run_id+'.route'),'utf8'));
  assert.equal(native.pool,pool??null);assert.equal(native.model,resolved??null);
  assert.equal(native.strict,Boolean(pool));assert.equal(native.quota_fallback,false);
  assert.equal(native.root,plan.root_id);assert.equal(native.parent,plan.root_id);
  if(!pool)assert.equal(native.response_only,true);
  if(pool==='experiential'||!pool){
   for(const key of ['experiential_retention_acknowledged','experiential_sensitive_data_opt_in',
    'experiential_proprietary_code','experiential_code_exposure_opt_in'])assert.equal(native[key],true);
  }
  const retained=await call(second.client,'fabric_result',plan);
  assert.equal(retained.adapter_response,'RETURN: VERIFIED\n\n');
  const acceptedPlan=await call(second.client,'fabric_accept',{...plan,by:'deterministic',
   expected_response_sha256:retained.response_sha256,verification_summary:'artifact_digest_comparison'});
  assert.equal(acceptedPlan.accepted,true);
 }
 assert.equal(gateway.stats().backend.spawns,1);
});
