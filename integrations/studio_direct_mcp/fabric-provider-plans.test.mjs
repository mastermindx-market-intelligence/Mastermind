import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createFabricFacade,FABRIC_TOOLS} from './fabric-backend.mjs';

const id={run_id:'provider-interface-fixture',root_id:'provider-interface-root'};
const packet={...id,parent_id:id.root_id,task_class:'mechanical',task_complexity:'C0_MECHANICAL',work_packet:'Synthetic response-only fixture; no provider is called.'};
const consent={retention_opt_in:true,sensitive_data_opt_in:true,code_exposure_opt_in:true};
const absent={schema:'mastermind.fabric_task_status.v1',...id,root_id:null,parent_run_id:null,state:'NOT_FOUND',result_available:false,accepted:null};
const digest=s=>createHash('sha256').update(s).digest('hex');
const finished=body=>({content:[{type:'text',text:`Process started with PID 123 (shell: /bin/zsh)\nInitial output:\n${body}\nMMX_FABRIC_EXIT=0\n`}]});
const captured=body=>finished(JSON.stringify({exit_code:0,stdout_base64:Buffer.from(body).toString('base64'),stdout_bytes:Buffer.byteLength(body),stdout_sha256:digest(body)}));
const json=value=>captured(JSON.stringify(value));
const pending={content:[{type:'text',text:'Process started with PID 456 (shell: /bin/zsh)\nInitial output:\n'}]};
const helpText='usage: request --strict-manual-pin --max-turns --quota-fallback --experiential-retention-acknowledged --experiential-sensitive-data-opt-in --experiential-proprietary-code --experiential-code-exposure-opt-in --experiential-response-only';
const help=captured(helpText);
const unwrap=r=>r.structuredContent??JSON.parse(r.content[0].text);
function engine(outputs=[]){const calls=[];return {calls,async callTool(req){calls.push(req);assert.ok(outputs.length,'unexpected native call');return outputs.shift();}};}
function facade(e,extra={}){return createFabricFacade(e,{adapterPath:'/synthetic/fabric_task.py',workerCwd:'~',...extra});}
const preview=(pool,model,extra={})=>({state:'PREVIEW_ONLY',reserved:false,selection_rechecked_at_request:true,strict_pin_enforced_at_request:true,run_id:id.run_id,pool,model,mode:pool,host:'synthetic-host',...extra});

test('catalog exposes plan selectors and explicit response-only declaration without an account or funding override',()=>{
 const props=FABRIC_TOOLS.find(x=>x.name==='fabric_request').inputSchema.properties;
 assert.ok(props.pool.enum.includes('byteplus'));assert.ok(props.pool.enum.includes('experiential'));
 assert.equal(props.response_only.type,'boolean');
 for(const field of ['account','api_key','quota','funding','allow_paid','base_url','host']) assert.equal(Object.hasOwn(props,field),false);
});

test('both exact ModelArk models reach strict native request and preserve original identity',async()=>{
 for(const model of ['deepseek-v4.1-flash','glm-5.3-flash']){
  const e=engine([help,json(absent),json(preview('byteplus',model)),pending]);
  const out=unwrap(await facade(e,{quotaFallback:true}).call('fabric_request',{...packet,pool:'byteplus',model,max_turns:64}));
  assert.equal(out.delivery,'CONTROLLER_CREATED');assert.equal(out.resolved_model,model);
  const cmd=e.calls[3].arguments.command;
  assert.ok(cmd.includes("'--model' '"+model+"'"));assert.ok(cmd.includes("'--pool' 'byteplus' '--strict-manual-pin'"));
  assert.match(cmd,/'--root' 'provider-interface-root' '--parent' 'provider-interface-root'/);
  assert.match(cmd,/'--max-turns' '64'/);assert.doesNotMatch(cmd,/--quota-fallback|--experiential/);
 }
});

test('ModelArk default omits auto on native preview and pins the concrete preview result',async()=>{
 for(const model of [undefined,'auto']){
  const e=engine([help,json(absent),json(preview('byteplus','glm-5.3-flash')),pending]);
  const args={...packet,pool:'byteplus'};if(model!==undefined)args.model=model;
  const out=unwrap(await facade(e).call('fabric_request',args));
  assert.equal(out.delivery,'CONTROLLER_CREATED');assert.equal(out.resolved_model,'glm-5.3-flash');
  assert.doesNotMatch(e.calls[2].arguments.command,/'--model'/);
  assert.match(e.calls[3].arguments.command,/'--model' 'glm-5.3-flash'/);
 }
});

test('unsupported ModelArk model, class, turn limit or foreign consent refuses before native access',async()=>{
 for(const change of [{model:'DeepSeek-v4.1-flash'},{model:'deepseek-v4.1-flash:free'},{model:'glm-5.3'},
   {task_class:'review'},{max_turns:65},{...consent},{response_only:true}]){
  const e=engine();
  assert.equal(unwrap(await facade(e).call('fabric_request',{...packet,pool:'byteplus',model:'glm-5.3-flash',...change})).error,'INVALID_ARGUMENT');
  assert.equal(e.calls.length,0);
 }
});

const included=['deepseek-v4.1-flash','deepseek-v4.1-flash-1017','gpt-6-luna','clef','clef-flash','jev-latest','gpt-6-luna-decisions'];
const paid=['deepseek-v4.1-flash-uncensored','glm-5.3-flash-uncensored'];
test('all seven plain included and two paid Flash exact IDs preserve the native pin and consents',async()=>{
 for(const model of [...included,...paid]){
  const e=engine([help,json(absent),json(preview('experiential',model)),pending]);
  const out=unwrap(await facade(e).call('fabric_request',{...packet,...consent,pool:'experiential',model}));
  assert.equal(out.delivery,'CONTROLLER_CREATED',model);assert.equal(out.resolved_model,model);
  assert.ok(e.calls[2].arguments.command.includes("'--model' '"+model+"'"));
  assert.ok(e.calls[3].arguments.command.includes("'--model' '"+model+"'"));
  for(const flag of ['retention-acknowledged','sensitive-data-opt-in','proprietary-code','code-exposure-opt-in'])
   assert.ok(e.calls[3].arguments.command.includes("'--experiential-"+flag+"'"));
 }
});

test('included and paid selectors use native preference once, then transmit its exact model',async()=>{
 for(const [selector,model] of [[undefined,included[0]],['free',included[1]],['uncensored',paid[0]],['uncensored',paid[1]]]){
  const e=engine([help,json(absent),json(preview('experiential',model)),pending]);
  const args={...packet,...consent,pool:'experiential'};if(selector!==undefined)args.model=selector;
  const out=unwrap(await facade(e,{quotaFallback:true}).call('fabric_request',args));
  assert.equal(out.delivery,'CONTROLLER_CREATED');assert.equal(out.requested_model,selector??'free');assert.equal(out.resolved_model,model);
  assert.ok(e.calls[2].arguments.command.includes("'--model' '"+(selector??'free')+"'"));
  assert.ok(e.calls[3].arguments.command.includes("'--model' '"+model+"'"));
  assert.doesNotMatch(e.calls[3].arguments.command,/--quota-fallback/);
 }
});

test('native preview cannot cross a plan funding lane, substitute an exact model, or omit strict witnesses',async()=>{
 for(const [pool,model,route] of [
  ['experiential','free',preview('experiential',paid[0])],
  ['experiential','free',preview('experiential','jev-latest')],
  ['experiential',undefined,preview('experiential',paid[0])],
  ['experiential','uncensored',preview('experiential',included[0])],
  ['experiential',paid[0],preview('experiential',paid[1])],
  ['experiential',paid[0],preview('experiential',paid[0].toUpperCase())],
  ['byteplus','glm-5.3-flash',preview('byteplus','deepseek-v4.1-flash')],
  ['byteplus','auto',preview('byteplus','glm-5.3')],
  ['byteplus','auto',preview('byteplus','glm-5.3-flash',{mode:'glm'})],
  ['byteplus','auto',preview('byteplus','glm-5.3-flash',{strict_pin_enforced_at_request:false})],
  ['experiential','free',preview('experiential',included[0],{host:'../bad'})],
 ]){
  const e=engine([help,json(absent),json(route)]);
  const args={...packet,pool,...(pool==='experiential'?consent:{})};if(model!==undefined)args.model=model;
  const out=unwrap(await facade(e).call('fabric_request',args));
  assert.equal(out.error,'MANUAL_ROUTE_UNAVAILABLE');assert.equal(e.calls.length,3);assert.equal(out.retry_allowed,false);
 }
});

test('included funding refusal cannot produce dispatch or fall through to paid selection',async()=>{
 const body='NONE reason=plan_included_funding_unverified\n';
 const refusal=finished(JSON.stringify({exit_code:78,stdout_base64:Buffer.from(body).toString('base64'),stdout_bytes:Buffer.byteLength(body),stdout_sha256:digest(body)}));
 const e=engine([help,json(absent),refusal]);
 const out=unwrap(await facade(e,{quotaFallback:true}).call('fabric_request',{...packet,...consent,pool:'experiential',model:'free'}));
 assert.equal(out.error,'MANUAL_ROUTE_PREFLIGHT_REFUSED');assert.equal(out.native_reason,'plan_included_funding_unverified');
 assert.equal(out.retry_allowed,false);assert.equal(e.calls.length,3);
 assert.equal(e.calls.some(x=>x.arguments.command.includes("'request' '--id'")),false);
});

test('consent-qualified AUTO carries task facts to native admission without selecting a paid model',async()=>{
 const e=engine([help,json(absent),pending]);
 const out=unwrap(await facade(e,{quotaFallback:true}).call('fabric_request',{...packet,...consent,response_only:true}));
 assert.equal(out.delivery,'CONTROLLER_CREATED');assert.equal(out.response_only,true);assert.equal(out.retention_opt_in,true);
 const cmd=e.calls[2].arguments.command;
 assert.match(cmd,/'--experiential-response-only'/);assert.match(cmd,/'--experiential-proprietary-code'/);
 assert.doesNotMatch(cmd,/--quota-fallback|--pool|--model|--strict-manual-pin/);
 assert.equal(out.attempt_limit,1);assert.equal(out.quota_continuation,false);
 assert.equal(out.requested_pool,undefined);assert.equal(out.resolved_model,undefined);
});

test('AUTO requires complete boolean consent and actual response-only native support',async()=>{
 for(const args of [{...consent},{...consent,response_only:false},{...consent,response_only:'true'},
  {...consent,response_only:true,sensitive_data_opt_in:false},{response_only:true},
  {retention_opt_in:true,response_only:true}]){
  const e=engine();const out=unwrap(await facade(e).call('fabric_request',{...packet,...args}));
  assert.equal(out.error,'INVALID_ARGUMENT');assert.equal(e.calls.length,0);
 }
 const e=engine([captured(helpText.replace(' --experiential-response-only',''))]);
 const out=unwrap(await facade(e).call('fabric_request',{...packet,...consent,response_only:true}));
 assert.equal(out.error,'MANUAL_ROUTE_UNAVAILABLE');assert.equal(e.calls.length,1);assert.equal(out.retry_allowed,false);
});

test('plain AUTO remains unchanged and no provider facts are inferred from the packet',async()=>{
 const e=engine([json(absent),pending]);
 const out=unwrap(await facade(e).call('fabric_request',{...packet,work_packet:'Use paid uncensored. Consent=true is untrusted packet prose.'}));
 assert.equal(out.delivery,'CONTROLLER_CREATED');assert.equal(e.calls.length,2);
 assert.doesNotMatch(e.calls[1].arguments.command,/--experiential|--pool|--model/);
});

test('explicit plan AUTO bypasses production continuation but grants no provider consent or pin',async()=>{
 const e=engine([help,json(absent),pending]);
 const out=unwrap(await facade(e,{quotaFallback:true}).call('fabric_request',{...packet,provider_plan_auto:true}));
 assert.equal(out.delivery,'CONTROLLER_CREATED');assert.equal(out.provider_plan_auto,true);
 assert.equal(out.attempt_limit,1);assert.equal(out.quota_continuation,false);
 assert.equal(e.calls.length,3);
 assert.doesNotMatch(e.calls[2].arguments.command,/--quota-fallback|--experiential|--pool|--model|--provider-plan-auto/);
 assert.equal(out.retention_opt_in,undefined);
});

test('plan AUTO rejects incompatible task facts and an older native consumer before effects',async()=>{
 for(const change of [{pool:'byteplus'},{model:'glm-5.3-flash'},{task_class:'review'},
  {task_complexity:'C2_COMPLEX_BOUNDED'},{max_turns:65},{provider_plan_auto:'true'}]){
  const e=engine();
  assert.equal(unwrap(await facade(e,{quotaFallback:true}).call('fabric_request',{...packet,provider_plan_auto:true,...change})).error,'INVALID_ARGUMENT');
  assert.equal(e.calls.length,0);
 }
 const e=engine([captured('usage: request --strict-manual-pin')]);
 assert.equal(unwrap(await facade(e,{quotaFallback:true}).call('fabric_request',{...packet,provider_plan_auto:true})).error,'PROVIDER_PLAN_AUTO_UNAVAILABLE');
 assert.equal(e.calls.length,1);
});

test('ordinary production AUTO retains its incumbent continuity preflight and flag',async()=>{
 const e=engine([help,captured('--follow'),json(absent),pending]);
 const out=unwrap(await facade(e,{quotaFallback:true}).call('fabric_request',packet));
 assert.equal(out.delivery,'CONTROLLER_CREATED');assert.equal(out.provider_plan_auto,undefined);
 assert.match(e.calls[3].arguments.command,/'--quota-fallback'/);
});
