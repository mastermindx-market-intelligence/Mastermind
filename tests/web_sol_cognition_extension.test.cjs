'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const EXT = path.resolve(__dirname, '../integrations/chairman_surfaces/web_sol_extension');
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
  const state = {active:!!options.active, error:false, clicks:0, writes:0, clears:0,
    hashHook:null, inputHook:null, focusHook:null, node:null};
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
  const context=vm.createContext({crypto,TextEncoder,TextDecoder,Uint8Array,location,document,
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

test('actual background and content listeners submit once to exact B with A also present',async()=>{
  const h=await backgroundHarness({unrelated:true}),r=request(h.target.fp());
  const result=await h.send(r);
  assert.equal(result.status,'COGNITION_STARTED');
  assert.deepEqual(h.sent.map(x=>x.id),[7]);assert.equal(h.target.state.clicks,1);assert.equal(h.target.state.writes,1);
  assert.equal(h.sent[0].message.expected_document_epoch,h.target.epoch);
  assert.deepEqual(Object.keys(h.sent[0].message).sort(),
    ['kind','expected_conversation_fingerprint','expected_document_epoch','session_alias','cognition_payload'].sort());
  assert.equal(JSON.stringify(result).includes(PAYLOAD.assignment.job.objective),false);
});
test('duplicate exact target refuses with no message or write',async()=>{
  const h=await backgroundHarness({duplicate:true});
  assert.equal((await h.send(request(h.target.fp()))).status,'AMBIGUOUS_TARGET');
  assert.equal(h.sent.length,0);assert.equal(h.target.state.writes,0);
});
test('wrong schema and malformed timestamps are rejected by the actual request gate',async()=>{
  const h=await backgroundHarness();
  for(const edit of [{schema:'wrong'},{issued_at:[]},{expires_at:{}}])
    assert.equal(await h.direct(request(h.target.fp(),edit)),undefined);
  assert.equal(h.sent.length,0);
});
test('actual content rejects all epoch/fingerprint and closed payload mismatches',async()=>{
  for(const edit of [{expected_document_epoch:'f'.repeat(32)},{expected_conversation_fingerprint:'f'.repeat(64)}]){
    const c=contentHarness();const result=await c.send(contentRequest(c,edit));
    assert.equal(result.effect,'NOT_SUBMITTED');assert.equal(c.state.writes,0);
  }
  const c=contentHarness();
  assert.equal(await c.send({...contentRequest(c),extra:true}),null);
});
test('wrong assignment digest never causes a content effect',async()=>{
  const h=await backgroundHarness();const r=request(h.target.fp());
  r.cognition_payload.assignment_digest='f'.repeat(64);
  assert.equal((await h.send(r)).status,'COGNITION_NOT_SUBMITTED');assert.equal(h.target.state.writes,0);
});
test('every reply identity mismatch becomes unknown after one possible dispatch',async()=>{
  for(const key of ['turn_id','assignment_digest','result_schema_digest','job_id','attempt_id','worker_id','root_job_id','role',
    'runtime_binding_id','runtime_binding_generation','runtime_binding_fingerprint','session_alias','document_epoch','conversation_fingerprint']){
    const h=await backgroundHarness({responseMutation:row=>{
      if(Object.hasOwn(row.cognition_identity,key))row.cognition_identity[key]='wrong';
      else row[key]=key==='runtime_binding_generation'?99:'wrong';return row;
    }});
    const r=request(h.target.fp());
    assert.equal((await h.send(r)).status,'COGNITION_SUBMIT_EFFECT_UNKNOWN',key);
    assert.equal(h.sent.length,1);assert.equal(h.target.state.clicks,1);
    assert.equal((await h.send({...r,nonce:'retry-nonce-after-unknown'})).status,'COGNITION_NOT_SUBMITTED');
    assert.equal(h.sent.length,1);
  }
});
for(const [name,options] of [['nonempty',{nonEmpty:true}],['active',{active:true}],['busy',{busy:true}]]){
  test(name+' never clicks or destroys user text',async()=>{
    const c=contentHarness(options);const result=await c.send(contentRequest(c));
    assert.equal(result.effect,'NOT_SUBMITTED');assert.equal(c.state.clicks,0);
    assert.equal(c.composer.value,options.nonEmpty?'USER TEXT':'');
  });
}
for(const change of ['user','node','active','error','navigation']){
  test('real hashing await rechecks '+change+' before writing',async()=>{
    const c=contentHarness();let fired=false;
    c.state.hashHook=text=>{
      if(fired||!text.startsWith('{'))return;fired=true;
      if(change==='user')c.setUserText('USER TEXT');
      if(change==='node')c.state.node={value:'USER TEXT'};
      if(change==='active')c.state.active=true;
      if(change==='error')c.state.error=true;
      if(change==='navigation')c.location.pathname='/c/changed-chat';
    };
    const result=await c.send(contentRequest(c));
    assert.equal(fired,true);assert.equal(result.effect,'NOT_SUBMITTED');
    assert.equal(c.state.writes,0);assert.equal(c.state.clicks,0);
    if(change==='user')assert.equal(c.composer.value,'USER TEXT');
  });
}
test('URL change inside fingerprint hashing refuses before rendering',async()=>{
  const c=contentHarness();const r=contentRequest(c);
  c.state.hashHook=text=>{if(text.startsWith('https://'))c.location.pathname='/c/changed-chat';};
  const result=await c.send(r);assert.equal(result.effect,'NOT_SUBMITTED');assert.equal(c.state.writes,0);
});
test('focus callback user text is rechecked before write',async()=>{
  const c=contentHarness();c.state.focusHook=()=>c.setUserText('USER TEXT');
  const result=await c.send(contentRequest(c));
  assert.equal(result.effect,'NOT_SUBMITTED');assert.equal(c.composer.value,'USER TEXT');assert.equal(c.state.writes,0);
});
for(const change of ['user','node','navigation','active','error']){
  test('post-write '+change+' never clicks and clears only its own text',async()=>{
    const c=contentHarness();c.state.inputHook=()=>{
      if(!c.composer.value)return;
      if(change==='user')c.setUserText('USER TEXT');
      if(change==='node')c.state.node={value:'USER TEXT'};
      if(change==='navigation')c.location.pathname='/c/changed-chat';
      if(change==='active')c.state.active=true;
      if(change==='error')c.state.error=true;
    };
    const result=await c.send(contentRequest(c));
    assert.equal(result.effect,['user','node'].includes(change)?'SUBMIT_EFFECT_UNKNOWN':'NOT_SUBMITTED');
    assert.equal(c.state.clicks,0);
    if(change==='user')assert.equal(c.composer.value,'USER TEXT');
    if(change==='node')assert.equal(c.state.node.value,'USER TEXT');
  });
}
for(const [name,options,effect] of [
  ['partial write',{partialWrite:true},'SUBMIT_EFFECT_UNKNOWN'],
  ['input throws',{inputThrows:true},'NOT_SUBMITTED'],
  ['cleanup throws',{inputThrows:true,cleanupThrows:true},'SUBMIT_EFFECT_UNKNOWN'],
  ['click throws',{clickThrows:true},'SUBMIT_EFFECT_UNKNOWN'],
]){
  test(name+' retains honest effect classification',async()=>{
    const c=contentHarness(options);const result=await c.send(contentRequest(c));
    assert.equal(result.effect,effect);assert.equal(c.state.clicks,options.clickThrows?1:0);
  });
}
test('lost response is unknown and never resubmitted',async()=>{
  const h=await backgroundHarness({loss:true}),r=request(h.target.fp());
  assert.equal((await h.send(r)).status,'COGNITION_SUBMIT_EFFECT_UNKNOWN');
  assert.equal((await h.send({...r,nonce:'another-retry-nonce-001'})).status,'COGNITION_NOT_SUBMITTED');
  assert.equal(h.sent.length,1);
});
for(const refused of [false,true]){
  test('window change after '+(refused?'NOT_SUBMITTED':'click')+' reply is never success',async()=>{
    const h=await backgroundHarness({content:{nonEmpty:refused}});
    h.afterSend(()=>{h.tabs.get(7).windowId=99;});
    assert.equal((await h.send(request(h.target.fp()))).status,'COGNITION_SUBMIT_EFFECT_UNKNOWN');
    assert.equal(h.sent.length,1);
  });
}
test('post-probe target movement is checked before an active observation is accepted',async()=>{
  const h=await backgroundHarness();
  h.afterProbe((_id,probe)=>{if(probe.observation.generation_state==='active')h.tabs.get(7).windowId=99;});
  assert.equal((await h.send(request(h.target.fp()))).status,'COGNITION_SUBMIT_EFFECT_UNKNOWN');
});
test('shared atomic effect owner fences nonce, turn, capacity and both action families',async()=>{
  for(const field of ['nonce','turn']){
    const h=await backgroundHarness(),r=request(h.target.fp());
    h.context.MMXWebSolContinuation.reserveEffect(field==='nonce'?r.nonce:'previous-nonce',field==='turn'?PAYLOAD.turn_id:'previous-turn');
    assert.equal((await h.send(r)).status,'COGNITION_NOT_SUBMITTED');assert.equal(h.sent.length,0);
  }
  const full=await backgroundHarness();
  for(let i=0;i<256;i++)assert.equal(full.context.MMXWebSolContinuation.reserveEffect('capacity-nonce-'+i,'capacity-turn-'+i),true);
  assert.equal((await full.send(request(full.target.fp()))).status,'COGNITION_NOT_SUBMITTED');assert.equal(full.sent.length,0);
  const h=await backgroundHarness(),r=request(h.target.fp());
  const results=await Promise.all([h.send(r),h.send({...r,nonce:'concurrent-other-nonce-01'})]);
  assert.deepEqual(results.map(x=>x.status).sort(),['COGNITION_NOT_SUBMITTED','COGNITION_STARTED']);
  assert.equal(h.sent.length,1);
  assert.equal(h.context.MMXWebSolContinuation.reserveEffect('later-other-nonce',PAYLOAD.turn_id),false);
  assert.equal(h.context.MMXWebSolContinuation.reserveEffect(r.nonce,'later-other-turn'),false);
});

for(const replace of [false,true]){
  test('contenteditable owns only its inserted text node; user replacement '+replace,async()=>{
    const c=contentHarness({editable:true});
    if(replace)c.state.inputHook=()=>c.setUserText('USER TEXT');
    const r=await c.send(contentRequest(c));
    assert.equal(r.effect,replace?'SUBMIT_EFFECT_UNKNOWN':'SUBMIT_TRIGGERED');
    assert.equal(c.state.clicks,replace?0:1);
    if(replace)assert.equal(c.composer.childNodes[0].data,'USER TEXT');
  });
}
function continuationRequest(fp,nonce,turn){
  const {cognition_payload,...base}=request(fp,{nonce});
  return {...base,action:'SUBMIT_CONTINUATION',turn_id:turn,
    directive_digest:'55cca851529f53f89ade6a2abb43880513fcd189dfcda50237ec1369640a06c5',
    wake_obligation_ids:['WAKE-'+'a'.repeat(32)],wake_obligation_digest:'f'.repeat(64)};
}
test('actual continuation and cognition listeners share cross-action replay fences',async()=>{
  for(const first of ['cognition','continuation']){
    const h=await backgroundHarness(),r=request(h.target.fp());
    const c=continuationRequest(h.target.fp(),'continuation-cross-nonce-01',PAYLOAD.turn_id);
    assert.equal((await h.send(first==='cognition'?r:c)).status,first==='cognition'?'COGNITION_STARTED':'CONTINUATION_STARTED');
    h.target.state.active=false;h.target.setUserText('');
    const second=await h.send(first==='cognition'?c:r);
    assert.equal(second.status,first==='cognition'?'CONTINUATION_NOT_SUBMITTED':'COGNITION_NOT_SUBMITTED');
    assert.equal(h.sent.length,1);
  }
});

test('expired during preeffect probe never reserves or dispatches',async()=>{
  const h=await backgroundHarness(),r=request(h.target.fp());
  h.afterProbe(()=>h.advanceClock(61000));
  assert.equal((await h.send(r)).status,'REQUEST_EXPIRED');assert.equal(h.sent.length,0);
  assert.equal(h.context.MMXWebSolContinuation.effectCapacity(),256);
});
test('expired after dispatch is unknown even with an active probe',async()=>{
  const h=await backgroundHarness();h.afterSend(()=>h.advanceClock(61000));
  assert.equal((await h.send(request(h.target.fp()))).status,'COGNITION_SUBMIT_EFFECT_UNKNOWN');
  assert.equal(h.sent.length,1);
});
test('new document epoch after dispatch cannot be accepted as the old target',async()=>{
  const h=await backgroundHarness();h.afterSend(()=>{h.tabs.get(7).content=contentHarness({active:true});});
  assert.equal((await h.send(request(h.target.fp()))).status,'COGNITION_SUBMIT_EFFECT_UNKNOWN');
});
test('accepted payload is detached before the first real asynchronous hash',async()=>{
  const h=await backgroundHarness(),r=request(h.target.fp());const result=h.direct(r);
  r.cognition_payload.assignment.job.objective='a caller changed this after acceptance';
  assert.equal((await result).status,'COGNITION_STARTED');assert.equal(h.sent.length,1);
});
test('no observed generation never becomes a false started claim',async()=>{
  const h=await backgroundHarness({content:{neverStarts:true}});
  assert.equal((await h.send(request(h.target.fp()))).status,'COGNITION_SUBMIT_EFFECT_UNKNOWN');
  assert.equal(h.sent.length,1);assert.equal(h.target.state.clicks,1);
});

for (const stage of ['render', 'probe', 'sent', 'afterProbe']) {
  test('native disconnect at '+stage+' cannot dispatch late or publish an old receipt',async()=>{
    const h=await backgroundHarness();let probeCount=0;
    if(stage==='render') h.context.crypto={...webcrypto,subtle:{async digest(...args){
      const value=await webcrypto.subtle.digest(...args);h.disconnect();return value;
    }}};
    if(stage==='probe'||stage==='afterProbe') h.afterProbe(()=>{
      probeCount++;if(probeCount===(stage==='probe'?1:2))h.disconnect();
    });
    if(stage==='sent') h.afterSend(()=>h.disconnect());
    const initial=h.messages.length;
    const result=await h.direct(request(h.target.fp()));
    assert.equal(result,undefined);
    assert.equal(h.sent.length,stage==='sent'||stage==='afterProbe'?1:0);
    assert.equal(h.target.state.clicks,stage==='sent'||stage==='afterProbe'?1:0);
    assert.equal(h.messages.length,initial,'old connection receives no positive/negative receipt');
  });
}
for (const property of ['nativePortToken','nativePortEpoch','transportBootNonce']) {
  test('native generation identity '+property+' changing during probe fences submit',async()=>{
    const h=await backgroundHarness();
    h.afterProbe(()=>vm.runInContext(property+" = 'changed-generation'",h.context));
    const initial=h.messages.length;
    await h.direct(request(h.target.fp()));
    assert.equal(h.sent.length,0);assert.equal(h.target.state.clicks,0);
    assert.equal(h.messages.length,initial);
  });
}

test('delayed generation shares bounded observation ticks without another submission',async()=>{
  const h=await backgroundHarness({content:{neverStarts:true}});let probes=0;
  h.afterProbe(()=>{probes++;if(probes===3)h.target.state.active=true;});
  const r=await h.send(request(h.target.fp()));
  assert.equal(r.status,'COGNITION_STARTED');assert.equal(probes,4);
  assert.equal(h.sent.length,1);assert.equal(h.target.state.clicks,1);
});
test('shared observation schedule is fixed and never reserves an effect',async()=>{
  const h=await backgroundHarness();const K=h.context.MMXWebSolContinuation;
  const capacity=K.effectCapacity(),ticks=[];
  for await(const attempt of K.startObservationTicks(true))ticks.push(attempt);
  assert.deepEqual(ticks,[0,1,2,3,4,5,6,7,8,9]);
  assert.equal(K.effectCapacity(),capacity);assert.equal(h.sent.length,0);
  assert.equal(h.target.state.writes,0);assert.equal(h.target.state.clicks,0);
});
