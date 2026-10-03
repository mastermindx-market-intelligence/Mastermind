'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const EXT = path.resolve(__dirname,'../integrations/chairman_surfaces/web_sol_extension');
const source = name => fs.readFileSync(path.join(EXT, name), 'utf8');
const PAYLOAD = JSON.parse(process.env.COGNITION_PAYLOAD);
const DIGEST = process.env.CAPABILITY_DIGEST;
assert.match(DIGEST, /^[0-9a-f]{64}$/);
const INSTANCE = 'a'.repeat(64);
const B = 'b'.repeat(64);
const tick = () => new Promise(resolve => setImmediate(resolve));
const plain = value => JSON.parse(JSON.stringify(value));
const fingerprint = pathname => createHash('sha256').update('https://chatgpt.com'+pathname).digest('hex');

// Only browser IO is simulated. Every validator, hash, renderer and listener is real.
function contentHarness(options = {}) {
  const state = {active:!!options.active, error:!!options.error, clicks:0, writes:0, clears:0,
    hashHook:null, inputHook:null, focusHook:null, node:null, fetches:0, fetchHook:null};
  const location = {origin:'https://chatgpt.com', pathname:options.path || '/c/session-alpha'};
  let value = options.nonEmpty ? 'USER TEXT' : '';
  const composer = {
    disabled:false, getAttribute:()=>null,
    get value(){return value;},
    set value(text){
      if (!text) { state.clears++; if(options.cleanupThrows) throw Error('cleanup'); }
      else { state.writes++; if(options.partialWrite) {value=text.slice(0,7);throw Error('partial write');} }
      value=text;
    },
    focus(){state.focusHook?.();},
    dispatchEvent(){state.inputHook?.();if(options.inputThrows && value) throw Error('input');return true;},
  };
  if(options.editable){
    delete composer.value;composer.isContentEditable=true;composer.childNodes=[];
    composer.replaceChildren=(...nodes)=>{if(nodes.length)state.writes++;else state.clears++;composer.childNodes=nodes;};
  }
  state.node=composer;
  const document = {readyState:'complete', visibilityState:'visible',
    querySelector(selector){
      if(selector==="#prompt-textarea") return state.node;
      if(selector==="[data-testid='stop-button']") return state.active ? {} : null;
      if(selector==="[data-testid='conversation-turn-error']") return state.error ? {} : null;
      if(selector==="button[data-testid='send-button']") return {
        disabled:!!options.busy, getAttribute:()=>null,
        click(){state.clicks++;if(options.clickThrows)throw Error('click');state.active=!options.neverStarts;},
      };
      return null;
    },
    createTextNode(text){return {nodeType:3,data:text};},
  };
  let listener;
  const crypto = {
    getRandomValues:bytes=>webcrypto.getRandomValues(bytes),
    subtle:{async digest(algorithm,bytes){
      const result=await webcrypto.subtle.digest(algorithm,bytes);
      state.hashHook?.(new TextDecoder().decode(bytes));
      return result;
    }},
  };
  const context=vm.createContext({crypto,TextEncoder,TextDecoder,Uint8Array,URL,location,document,
    fetch:async (url,init)=>{
      state.fetches++;
      assert.equal(url,'https://chatgpt.com/backend-api/conversation/session-alpha');
      assert.deepEqual(plain(init),{method:'GET',credentials:'include',cache:'no-store',redirect:'error',headers:{Accept:'application/json'}});
      const snapshot=await providerSnapshot(context,options.snapshot);
      state.fetchHook?.();
      const bytes=options.invalidUtf8 ? new Uint8Array([255]) : new TextEncoder().encode(JSON.stringify(snapshot));let done=false;
      if(options.fetchThrows) throw Error('network or redirect');
      const status=options.httpStatus || 200;
      return {ok:status>=200&&status<300,status,headers:{get:name=>name==='content-type'?'application/json':name==='content-length'?String(options.oversized ? 9*1024*1024 : bytes.length):null},
        body:{getReader:()=>({read:async()=>{if(done)return {done:true};done=true;return {done:false,value:bytes};},cancel:async()=>{}})}};
    },
    InputEvent:function(){},Event:function(){},
    chrome:{runtime:{onMessage:{addListener(callback){listener=callback;}},sendMessage:async()=>{}}},
  });
  for(const name of ['cognition_result_core.js','cognition_transport_core.js','content.js'])
    vm.runInContext(source(name),context,{filename:name});
  const epoch=vm.runInContext('DOCUMENT_EPOCH',context);
  return {context,state,composer,location,epoch,
    fp:()=>fingerprint(location.pathname),
    setUserText(text){if(options.editable)composer.childNodes=[{nodeType:3,data:text}];else value=text;},
    async send(message){
      return new Promise(resolve=>{
        if(listener(message,{},response=>resolve(plain(response)))!==true)resolve(null);
      });
    },
    async probe(){return this.send({kind:'MMX_WEB_SOL_REPROBE',expected_conversation_fingerprint:this.fp()});},
  };
}

function request(fp,overrides={}){
  const now=Date.now();
  return {schema:'mastermind.web_sol_surface_action.v1',
    binding_id:'11111111-1111-4111-8111-111111111111',conversation_fingerprint:fp,
    binding_fingerprint:B,action:'SUBMIT_COGNITION_ASSIGNMENT',
    operation_key:'web-sol-cognition-extension-test',
    issued_at:new Date(now).toISOString(),expires_at:new Date(now+30000).toISOString(),
    nonce:'cognition-extension-nonce-0001',session_alias:'EXECUTIVE-CEO-A',
    runtime_binding_id:PAYLOAD.runtime_binding_id,runtime_binding_generation:PAYLOAD.runtime_binding_generation,
    runtime_binding_fingerprint:PAYLOAD.runtime_binding_fingerprint,cognition_payload:plain(PAYLOAD),
    ...overrides};
}
function contentRequest(content,overrides={}){
  return {kind:'MMX_WEB_SOL_SUBMIT_COGNITION_ASSIGNMENT',
    expected_conversation_fingerprint:content.fp(),expected_document_epoch:content.epoch,
    session_alias:'EXECUTIVE-CEO-A',cognition_payload:plain(PAYLOAD),...overrides};
}
async function backgroundHarness(options={}){
  const target=contentHarness(options.content);
  const tabs=new Map([[7,{id:7,windowId:10,content:target}]]);
  if(options.unrelated)tabs.set(3,{id:3,windowId:11,content:contentHarness({path:'/c/unrelated-chat'})});
  if(options.duplicate)tabs.set(8,{id:8,windowId:12,content:contentHarness()});
  let runtimeListener,portListener,disconnectListener;
  const messages=[],sent=[],pending=new Map();
  let afterProbeHook=null,afterSendHook=null;
  const event=capture=>({addListener(callback){capture?.(callback);}});
  const port={onDisconnect:event(cb=>{disconnectListener=cb;}),onMessage:event(cb=>{portListener=cb;}),
    postMessage(value){messages.push(plain(value));if(pending.has(value.nonce))pending.get(value.nonce)(plain(value));},
    disconnect(){},
  };
  const config={schema:'mastermind.web_sol_instance_config.v1',instanceId:INSTANCE,
    nativeHost:'com.mastermind.web_sol_surface.'+INSTANCE.slice(0,24),
    protocolMajor:1,clientPackageVersion:'0.6.0',nativePackageVersion:'0.6.0',
    extensionPackageVersion:'0.6.0',capabilityDigest:DIGEST};
  const chrome={runtime:{id:'kmpbpccecbofdnhpcmjogofgmdodpnko',
    onMessage:event(cb=>{runtimeListener=cb;}),connectNative:()=>port},
    tabs:{query:async()=>[],get:async id=>({id,windowId:tabs.get(id).windowId,active:true}),
      onUpdated:event(),onRemoved:event(),onMoved:event(),onAttached:event(),onDetached:event(),onReplaced:event(),
      async sendMessage(id,message,frame){
        const tab=tabs.get(id);
        if(message.kind==='MMX_WEB_SOL_REPROBE'){
          const probe=await tab.content.send(message);afterProbeHook?.(id,probe);return probe;
        }
        assert.equal(frame.frameId,0);sent.push({id,message:plain(message)});
        let result=await tab.content.send(message);
        if(options.responseMutation)result=options.responseMutation(result);
        afterSendHook?.(id,result);
        if(options.loss)throw Error('lost response');
        return result;
      }},
    alarms:{create(){},clear:async()=>true,getAll:async()=>[],onAlarm:event()},
  };
  let clockOffset=0;
  class BrowserDate extends Date {
    constructor(...args){super(...(args.length?args:[Date.now()+clockOffset]));}
    static now(){return Date.now()+clockOffset;}
  }
  const context=vm.createContext({chrome,Date:BrowserDate,crypto:webcrypto,TextEncoder,TextDecoder,Uint8Array,
    performance,structuredClone,setTimeout:callback=>setImmediate(callback),clearTimeout});
  context.importScripts=name=>{
    if(name==='instance_config.js')context.MMX_WEB_SOL_INSTANCE=config;
    else vm.runInContext(source(name),context,{filename:name});
  };
  vm.runInContext(source('background.js'),context,{filename:'background.js'});
  await tick();
  assert.equal(typeof portListener,'function');
  const ack=()=>portListener({...messages.at(-1),schema:'mastermind.web_sol_transport_hello_ack.v1',
    boot_nonce:'boot-nonce-0000000000000001'});
  ack();ack();
  assert.equal(vm.runInContext('transportHandshakeReady',context),true);
  for(const tab of tabs.values()){
    runtimeListener(await tab.content.probe(),{id:chrome.runtime.id,frameId:0,tab:{id:tab.id,windowId:tab.windowId}});
  }
  return {context,target,tabs,sent,messages,
    disconnect(){disconnectListener();},
    advanceClock(milliseconds){clockOffset+=milliseconds;},
    afterProbe(fn){afterProbeHook=fn;},afterSend(fn){afterSendHook=fn;},
    async send(value){
      return new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(Error('no bounded receipt')),3000);
        pending.set(value.nonce,result=>{clearTimeout(timer);pending.delete(value.nonce);resolve(result);});
        portListener(plain(value));
      });
    },
    async direct(value){return context.handleNativeRequest(value,port);},
  };
}


const RESULT=JSON.parse(process.env.COGNITION_RESULT);
function canonical(v){
  if(v===null || typeof v!=='object')return JSON.stringify(v);
  if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';
  return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
}
function observeRequest(fp,edit={}){
  const r=request(fp);r.action='OBSERVE_COGNITION_RESULT';
  r.cognition_observe_payload=plain(PAYLOAD);delete r.cognition_observe_payload.assignment;
  r.cognition_observe_payload.schema='mastermind.web_sol_cognition_result_observe_payload/v1';
  delete r.cognition_payload;return {...r,...edit};
}
async function providerSnapshot(context,edit){
  const prompt=await context.MMXWebSolCognitionTransport.renderAssignmentPrompt(PAYLOAD);
  assert.equal(typeof prompt,'string');
  const message=(role,id,text,end_turn)=>({id,author:{role},status:'finished_successfully',end_turn,content:{content_type:'text',parts:[text]}});
  const s={conversation_id:'session-alpha',current_node:'assistant-result-001',mapping:{
    'user-assignment-001':{id:'user-assignment-001',parent:null,children:['assistant-result-001'],message:message('user','user-assignment-001',prompt,false)},
    'assistant-result-001':{id:'assistant-result-001',parent:'user-assignment-001',children:[],message:message('assistant','assistant-result-001',canonical(RESULT),true)},
  }};
  if(edit==='later-user'){
    s.mapping['assistant-result-001'].children=['later-user-001'];s.current_node='later-user-001';
    s.mapping['later-user-001']={id:'later-user-001',parent:'assistant-result-001',children:[],message:message('user','later-user-001','A later request',false)};
  }
  if(edit==='tool-after'){
    s.mapping['assistant-result-001'].children=['tool-later-001'];s.current_node='tool-later-001';
    s.mapping['tool-later-001']={id:'tool-later-001',parent:'assistant-result-001',children:[],message:message('tool','tool-later-001','tool result',false)};
  }
  if(edit==='no-terminal'){
    s.mapping['assistant-result-001'].message.end_turn=false;
  }
  if(edit==='malformed-result')s.mapping['assistant-result-001'].message.content.parts=['not JSON'];
  if(edit==='wrong-result'){
    const result=plain(RESULT);result.job_id='JOB-FOREIGN';
    s.mapping['assistant-result-001'].message.content.parts=[canonical(result)];
  }
  if(edit==='private-result'){
    const result=plain(RESULT);result.summary='api_key=sk-secret-fixture';
    s.mapping['assistant-result-001'].message.content.parts=[canonical(result)];
  }
  return s;
}
test('provider fixture passes actual canonical cores before integration',async()=>{
  const c=contentHarness();const s=await providerSnapshot(c.context);
  const o=await c.context.MMXWebSolCognitionTransport.reduceConversation(s,observeRequest(c.fp()).cognition_observe_payload,c.epoch);
  assert.equal(o.status,'COGNITION_RESULT_READY');assert.deepEqual(plain(o.result),RESULT);
});
test('two explicit result observations read once each with zero submission effects',async()=>{
  const h=await backgroundHarness({unrelated:true});
  for(let i=0;i<2;i++){
    const result=await h.send(observeRequest(h.target.fp(),{nonce:'observe-unique-nonce-000'+i}));
    assert.equal(result.status,'COGNITION_RESULT_READY');assert.deepEqual(result.cognition_observation.result,RESULT);
    assert.equal(result.cognition_observation.document_epoch,h.target.epoch);
    process.stdout.write('OBSERVATION_PROOF:'+JSON.stringify(result)+'\n');
  }
  assert.equal(h.target.state.fetches,2);assert.equal(h.sent.length,2);
  assert.equal(h.target.state.clicks,0);assert.equal(h.target.state.writes,0);assert.equal(h.target.state.clears,0);
  assert(h.sent.every(x=>x.id===7 && x.message.kind==='MMX_WEB_SOL_OBSERVE_COGNITION_RESULT'));
});
test('active DOM cannot bless an old terminal snapshot as READY',async()=>{
  const h=await backgroundHarness({content:{active:true}});
  const r=await h.send(observeRequest(h.target.fp()));assert.notEqual(r.status,'COGNITION_RESULT_READY');
});
for(const edit of ['later-user','tool-after'])test(edit+' never returns READY',async()=>{
  const h=await backgroundHarness({content:{snapshot:edit}});
  const r=await h.send(observeRequest(h.target.fp()));assert.notEqual(r.status,'COGNITION_RESULT_READY');
});
test('ambiguous target refuses before provider fetch',async()=>{
  const h=await backgroundHarness({duplicate:true});const r=await h.send(observeRequest(h.target.fp()));
  assert.equal(r.status,'AMBIGUOUS_TARGET');assert.equal(r.cognition_observation,null);assert.equal(h.target.state.fetches,0);
});
test('navigation during fetch cannot release the old result',async()=>{
  const h=await backgroundHarness();h.target.state.fetchHook=()=>{h.target.location.pathname='/c/changed';};
  const r=await h.send(observeRequest(h.target.fp()));assert.notEqual(r.status,'COGNITION_RESULT_READY');
});
test('native disconnect during fetch delivers no old receipt',async()=>{
  const h=await backgroundHarness();h.target.state.fetchHook=()=>h.disconnect();
  const n=h.messages.length;await h.direct(observeRequest(h.target.fp()));assert.equal(h.messages.length,n);
});
test('window movement after result cannot release READY',async()=>{
  const h=await backgroundHarness();h.afterSend(()=>{h.tabs.get(7).windowId=99;});
  const r=await h.send(observeRequest(h.target.fp()));assert.notEqual(r.status,'COGNITION_RESULT_READY');
});
test('expiry during provider acquisition yields no result',async()=>{
  const h=await backgroundHarness();h.target.state.fetchHook=()=>h.advanceClock(120000);
  const r=await h.send(observeRequest(h.target.fp()));assert.notEqual(r.status,'COGNITION_RESULT_READY');assert.equal(r.cognition_observation,null);
});
test('self-consistent foreign observation cannot cross the original request join',async()=>{
  const h=await backgroundHarness({responseMutation:r=>{
    const o=r.cognition_observation;o.job_id='JOB-FOREIGN';o.result.job_id='JOB-FOREIGN';
    const b=canonical(o.result);o.result_digest=createHash('sha256').update(b).digest('hex');o.result_byte_length=Buffer.byteLength(b);return r;
  }});
  const r=await h.send(observeRequest(h.target.fp()));assert.notEqual(r.status,'COGNITION_RESULT_READY');
});

function proof(receipt){process.stdout.write('OBSERVATION_PROOF:'+JSON.stringify(receipt)+'\n');}
for(const [name,options,status] of [
  ['active',{active:true},'COGNITION_RESULT_PENDING'],
  ['no-terminal',{snapshot:'no-terminal'},'COGNITION_RESULT_PENDING'],
  ['later-user',{snapshot:'later-user'},'COGNITION_RESULT_REFUSED'],
  ['tool-after',{snapshot:'tool-after'},'COGNITION_RESULT_REFUSED'],
  ['malformed-result',{snapshot:'malformed-result'},'COGNITION_RESULT_REFUSED'],
  ['wrong-result',{snapshot:'wrong-result'},'COGNITION_RESULT_REFUSED'],
  ['private-result',{snapshot:'private-result'},'COGNITION_RESULT_REFUSED'],
  ['auth',{httpStatus:403},'COGNITION_RESULT_REFUSED'],
  ['provider-error',{httpStatus:500},'COGNITION_RESULT_PENDING'],
  ['network-or-redirect',{fetchThrows:true},'COGNITION_RESULT_PENDING'],
  ['invalid-utf8',{invalidUtf8:true},'COGNITION_RESULT_REFUSED'],
  ['oversized-snapshot',{oversized:true},'COGNITION_RESULT_REFUSED'],
]) test(name+' yields a real typed result-free receipt',async()=>{
  const h=await backgroundHarness({content:options});const r=await h.send(observeRequest(h.target.fp()));
  assert.equal(r.status,status);assert.equal(r.cognition_observation.result,null);
  assert.equal(r.cognition_observation.provider_native_turn_id,null);
  assert.equal(h.target.state.fetches,1);assert.equal(h.target.state.clicks,0);
  proof(r);
});
const identityMutations={turn_id:'ohf-turn-foreign',assignment_digest:'1'.repeat(64),
  result_schema_digest:'2'.repeat(64),runtime_binding_id:'bind-wsx-'+'c'.repeat(48),
  runtime_binding_generation:3,runtime_binding_fingerprint:'d'.repeat(64),
  job_id:'JOB-FOREIGN',attempt_id:'ATT-FOREIGN',worker_id:'web-sol-other',root_job_id:'JOB-OTHER',role:'review'};
for(const [field,value] of Object.entries(identityMutations))test('valid foreign PENDING '+field+' cannot cross original identity join',async()=>{
  const h=await backgroundHarness({content:{snapshot:'no-terminal'},responseMutation:r=>{
    r.cognition_observation[field]=value;return r;
  }});
  const r=await h.send(observeRequest(h.target.fp()));assert.equal(r.status,'UNKNOWN');
  assert.equal(r.cognition_observation,null);assert.equal(h.target.state.fetches,1);proof(r);
});
for(const [name,edit] of [
  ['result-digest',r=>{r.cognition_observation.result_digest='0'.repeat(64);}],
  ['result-bytes',r=>{r.cognition_observation.result_byte_length++;}],
  ['result-role',r=>{r.cognition_observation.result.role='review';}],
  ['outer-epoch',r=>{r.document_epoch='0'.repeat(32);}],
  ['inner-epoch',r=>{r.cognition_observation.document_epoch='0'.repeat(32);}],
  ['extra-field',r=>{r.extra=true;}],
  ['outer-alias',r=>{r.session_alias='EXECUTIVE-OTHER';}],
  ['status-result-contradiction',r=>{r.cognition_observation.status='COGNITION_RESULT_PENDING';}],
])test('malformed content '+name+' cannot publish result',async()=>{
  const h=await backgroundHarness({responseMutation:r=>{edit(r);return r;}});
  const r=await h.send(observeRequest(h.target.fp()));assert.equal(r.status,'UNKNOWN');
  assert.equal(r.cognition_observation,null);proof(r);
});
test('request expiry refuses before any read',async()=>{
  const h=await backgroundHarness();const r=await h.send(observeRequest(h.target.fp(),{
    issued_at:new Date(Date.now()-60000).toISOString(),expires_at:new Date(Date.now()-30000).toISOString()}));
  assert.equal(r.status,'REQUEST_EXPIRED');assert.equal(h.target.state.fetches,0);proof(r);
});
test('native disconnect during actual result hashing suppresses receipt',async()=>{
  const h=await backgroundHarness();h.target.state.hashHook=text=>{if(text===canonical(RESULT))h.disconnect();};
  const count=h.messages.length;await h.direct(observeRequest(h.target.fp()));
  assert.equal(h.messages.length,count);assert.equal(h.target.state.fetches,1);
});
test('navigation during actual result hashing cannot publish result',async()=>{
  const h=await backgroundHarness();h.target.state.hashHook=text=>{if(text===canonical(RESULT))h.target.location.pathname='/c/changed';};
  const r=await h.send(observeRequest(h.target.fp()));assert.notEqual(r.status,'COGNITION_RESULT_READY');
  assert.equal(r.cognition_observation,null);assert.equal(h.target.state.fetches,1);proof(r);
});
