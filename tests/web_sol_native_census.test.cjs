'use strict';
// Real worker/collector code; only Chrome APIs, event delivery and clock are fixtures.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const EXT = path.resolve(__dirname, '../integrations/chairman_surfaces/web_sol_extension');
const ID = 'kmpbpccecbofdnhpcmjogofgmdodpnko';
const INSTANCE = 'a'.repeat(64);
// Controlled, in-memory gate removals. Checkout bytes are never modified.
const mutations={
 outer:['background.js','chrome.tabs, INSTANCE_CONFIG.instanceId, deadline);','chrome.tabs, INSTANCE_CONFIG.instanceId);'],
 slots:['census_core.js','const CONCURRENCY = 8;','const CONCURRENCY = 16;'],
 sender:['background.js','!Object.prototype.hasOwnProperty.call(sender, "tab")','true'],
 late:['background.js','nativePort !== port || nativePortToken !== token || transportBootNonce !== boot ||\n      !transportHandshakeReady || performance.now() >= deadline','performance.now() >= deadline'],
 unknown:['census_core.js','initial_tab_count: null, final_tab_count: null','initial_tab_count: 0, final_tab_count: null'],
 columns:['background.js','"status", "generation_cue", "selected_in_window"','"generation_cue", "status", "selected_in_window"'],
};
function source(name) {
 let text=fs.readFileSync(path.join(EXT,name),'utf8');const key=process.env.C2_TEST_MUTATION;
 if(key){assert.ok(mutations[key],'known controlled mutation');const [file,from,to]=mutations[key];
  if(file===name){assert.equal(text.split(from).length,2,'one exact mutation anchor');text=text.replace(from,to);}}
 return text;
}
const cap = {schema:'mastermind.web_sol_transport_capabilities.v1',protocol_major:1,
 package_version:'0.2.0',roles:['client','extension'],actions:['FOREGROUND','INSPECT'],
 schemas:['mastermind.web_sol_surface_action.v1','mastermind.web_sol_transport_hello_ack.v1',
 'mastermind.web_sol_transport_hello.v1','mastermind.web_sol_instance_config.v1',
 'mastermind.web_sol_surface_probe.v1','mastermind.web_sol_surface_receipt.v1',
 'mastermind.web_sol_census_request.v1','mastermind.web_sol_census_receipt.v1',
 'mastermind.web_sol_census_table.v1'].sort()};
const DIGEST = createHash('sha256').update(JSON.stringify(cap,Object.keys(cap).sort())).digest('hex');
const tick = () => new Promise(r=>setImmediate(r));
const plain = x => JSON.parse(JSON.stringify(x));
function request(changes={}) {const now=Date.now();return {schema:'mastermind.web_sol_census_request.v1',
 adapter_instance_id:INSTANCE,operation_key:'c2-fixture',nonce:'census-fixture-nonce-0001',
 issued_at:new Date(now).toISOString(),expires_at:new Date(now+10000).toISOString(),...changes};}
function emitter() {const listeners=[];return {addListener:f=>listeners.push(f),listeners,
 fire(...args){return listeners.map(f=>f(...args));}};}
function harness({count=1, queryFailure=false, pending=false, instance=INSTANCE, clock, postNative, mode, configPatch}={}) {
 const events=emitter(), ports=[];let queries=0, reads=0;const resolvers=[];
 const rows=Array.from({length:count},(_,i)=>({id:i+1,windowId:1,url:'https://chatgpt.com/c/c2-'+i,
 status:'complete',discarded:!pending&&!mode,frozen:false,incognito:false,active:false}));
 if(mode==='mixed') {rows[1].url=rows[0].url;rows[1].discarded=true;rows[3].frozen=true;rows[4].status='loading';}
 const tabs={query:async()=>{queries++;if(queryFailure)throw Error('PRIVATE');
 return mode==='mixed'&&queries>2?rows.slice(0,4):rows;},
 get:id=>{reads++;if(pending)return new Promise(r=>resolvers.push(()=>r(rows[id-1])));return Promise.resolve(rows[id-1]);},
 sendMessage:async(id,req,target)=>{if(!mode||mode==='mixed'&&id===3)throw Error('unavailable');
  assert.equal(target.frameId,0);assert.equal(req.expected_conversation_fingerprint,
   createHash('sha256').update(rows[id-1].url).digest('hex'));
  return {...validObservation(),conversation_fingerprint:req.expected_conversation_fingerprint};
 },onUpdated:emitter(),onRemoved:emitter()};
 const config={schema:'mastermind.web_sol_instance_config.v1',instanceId:instance,
 nativeHost:'com.mastermind.web_sol_surface.'+instance.slice(0,24),protocolMajor:1,
 clientPackageVersion:'0.2.0',nativePackageVersion:'0.2.0',extensionPackageVersion:'0.2.0',capabilityDigest:DIGEST,...configPatch};
 const runtime={id:ID,getURL:p=>'chrome-extension://'+ID+'/'+p,onMessage:events,
 connectNative(){const port={messages:[],onMessage:emitter(),onDisconnect:emitter(),
 postMessage:x=>{port.messages.push(plain(x));if(postNative)postNative(x);},disconnect:()=>port.onDisconnect.fire()};ports.push(port);return port;}};
 const alarms={scheduled:[],create(name){alarms.scheduled.push(name);},clear:async()=>true,getAll:async()=>[],onAlarm:emitter()};
 const context=vm.createContext({console,crypto:webcrypto,TextEncoder,TextDecoder,URL,setTimeout,clearTimeout,
 performance:clock||performance,Date,MMX_WEB_SOL_INSTANCE:config,chrome:{runtime,tabs,
 alarms,
 windows:{update:async()=>{throw Error('NO_FOREGROUND');}}}});
 context.importScripts=(...names)=>{for(const name of names)if(name!=='instance_config.js')
 vm.runInContext(source(name),context,{filename:name});};
 vm.runInContext(source('background.js'),context,{filename:'background.js'});
 const sender={id:ID,url:runtime.getURL('census.html'),origin:'chrome-extension://'+ID};
 async function ready() {await tick();assert.equal(ports.length,1,'new capability package must connect');
  const p=ports[0];for(let i=0;i<2;i++){const hello=p.messages.at(-1);assert.equal(hello.schema,'mastermind.web_sol_transport_hello.v1');
  p.onMessage.fire({...hello,schema:'mastermind.web_sol_transport_hello_ack.v1',boot_nonce:'boot-fixture-000000000001'});}return p;}
 async function popup(s=sender,event={kind:'MMX_WEB_SOL_CENSUS_REFRESH'}) {
  let response;const returns=events.fire(event,s,x=>{response=plain(x);});
  for(let i=0;i<100&&response===undefined;i++)await tick();return {response,returns};}
 return {context,ports,events,tabs,sender,ready,popup,resolvers,alarms,get reads(){return reads;},get queries(){return queries;}};
}
async function nativeResult(h, req=request()) {
 const p=await h.ready();return new Promise((resolve,reject)=>{
 const timer=setTimeout(()=>reject(Error('real native CENSUS produced no receipt')),10000);
 const post=p.postMessage;p.postMessage=x=>{post(x);if(x.schema==='mastermind.web_sol_census_receipt.v1'){
 clearTimeout(timer);resolve(plain(x));}};p.onMessage.fire(req);
 });
}

function collectorClock(tabs) {
 let now=0, serial=0;const timers=new Map();
 const context=vm.createContext({crypto:webcrypto,TextEncoder,URL,Date,performance:{now:()=>now},
  setTimeout(fn,ms){const id=++serial;timers.set(id,{fn,at:now+ms});return id;},
  clearTimeout:id=>timers.delete(id)});
 vm.runInContext(source('census_core.js'),context);
 return {collect:deadline=>context.MMXWebSolCensus.collect(tabs,INSTANCE,deadline),
  advance(value){now=value;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}},
  get now(){return now;},get waits(){return [...timers.values()].map(t=>t.at-now);}};
}
const awake={id:1,windowId:1,url:'https://chatgpt.com/c/deadline',status:'complete'};
function validObservation() {return {kind:'MMX_WEB_SOL_PROBE',
 conversation_fingerprint:createHash('sha256').update(awake.url).digest('hex'),observation:{
 schema:'mastermind.web_sol_surface_probe.v1',target_present:true,exact_conversation_loaded:true,
 page_responsive:true,document_ready_state:'complete',visibility:'visible',composer_available:true,
 generation_state:'idle',auth_required:false,provider_error_present:false}};}

if(process.argv.includes('--native-pipe')) {
 const options=JSON.parse(process.argv[process.argv.indexOf('--native-pipe')+1]);
 const h=harness({...options,postNative(value){const data=Buffer.from(JSON.stringify(value));
 const header=Buffer.alloc(4);header.writeUInt32LE(data.length);process.stdout.write(Buffer.concat([header,data]));}});
 let buffer=Buffer.alloc(0);process.stdin.on('data',chunk=>{buffer=Buffer.concat([buffer,chunk]);
 while(buffer.length>=4){const n=buffer.readUInt32LE();if(n>65536)throw Error('frame too large');
 if(buffer.length<4+n)break;const message=JSON.parse(buffer.subarray(4,4+n));buffer=buffer.subarray(4+n);
 h.ports[0].onMessage.fire(message);}});process.stdin.on('end',()=>process.exit(0));
} else if(process.argv.includes('--validate-requests')) {
 const inputs=JSON.parse(fs.readFileSync(0,'utf8')),h=harness();
 h.context.correlationInputs=inputs;
 process.stdout.write(JSON.stringify(vm.runInContext('correlationInputs.map(validCensusRequest)',h.context)));
} else if(process.argv.includes('--fixture')) {
 const input=JSON.parse(fs.readFileSync(0,'utf8'));
 nativeResult(harness({count:input.count||0,mode:input.mode,queryFailure:input.queryFailure,instance:input.request.adapter_instance_id}),input.request)
 .then(x=>process.stdout.write(JSON.stringify(x))).catch(e=>{console.error(e.message);process.exitCode=1;});
} else {
 test('local digest timeout is not an acquired Chrome slot or retirement',async()=>{
  for(const count of [1,9]) {
   let now=0,serial=0,queries=0,gets=0,sends=0,digests=0;const timers=new Map();
   const rows=Array.from({length:count},(_,i)=>({...awake,id:i+1,active:false,discarded:false,frozen:false}));
   const context=vm.createContext({TextEncoder,URL,Date,performance:{now:()=>now},
    crypto:{subtle:{digest(...args){digests++;return digests<=Math.min(count,8)
     ?new Promise(()=>{}):webcrypto.subtle.digest(...args);}}},
    setTimeout(fn,ms){const id=++serial;timers.set(id,{fn,at:now+ms});return id;},
    clearTimeout:id=>timers.delete(id)});
   vm.runInContext(source('census_core.js'),context);
   const result=context.MMXWebSolCensus.collect({query:async()=>{queries++;return rows;},
    get:async id=>{gets++;return rows[id-1];},sendMessage:async()=>{sends++;return validObservation();}},INSTANCE);
   for(let i=0;i<100&&digests<Math.min(count,8);i++)await tick();
   assert.equal(digests,Math.min(count,8));now=800;
   for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}
   const snapshot=await result;
   const proof={count,statuses:plain(snapshot.rows.map(r=>r.status)),queries,gets,sends,pending_timer_count:timers.size};
   console.log(JSON.stringify({local_digest_timeout:proof}));
   assert.deepEqual(proof.statuses.slice(0,Math.min(count,8)),Array(Math.min(count,8)).fill('SWEEP_DEADLINE'),
    'local digest timeout must not invent Chrome slot exhaustion');
   assert.equal(queries,2);assert.equal(timers.size,0);
   if(count===1){assert.equal(gets,0);assert.equal(sends,0);}
   else {assert.equal(snapshot.rows[8].status,'OBSERVED','local computation cannot retire an unacquired Chrome slot');
    assert.equal(gets,2);assert.equal(sends,1);}
  }
 });
 test('invalid, exhausted and both deferred dispatch boundaries acquire zero reads',async()=>{
  let reads=0;const tabs={query:async()=>{reads++;return [];},get:async()=>{reads++;},sendMessage:async()=>{reads++;}};
  for(const deadline of [0,-1,NaN,Infinity,-Infinity,null,'100',{}]) {
   const c=collectorClock(tabs),r=await c.collect(deadline);assert.equal(r.initial_tab_count,null);
  }
  assert.equal(reads,0);
  for(const defer of [false,true]) {
   const c=collectorClock(tabs),p=c.collect(100);
   if(defer)queueMicrotask(()=>c.advance(100));else c.advance(100);
   assert.equal((await p).initial_tab_count,null);assert.equal(reads,0);
  }
 });
 test('default and larger caller budgets retain the five second popup maximum',async()=>{
  for(const deadline of [undefined,100000]) {
   let reads=0;const c=collectorClock({query:()=>{reads++;return new Promise(()=>{});},get(){},sendMessage(){}});
   const p=c.collect(deadline);await tick();assert.deepEqual(c.waits,[800]);
   c.advance(800);const r=await p;assert.equal(reads,1);assert.equal(r.initial_tab_count,null);
  }
 });
 test('short timely collection remains measured, while delayed probe and final are unknown',async()=>{
  for(const stage of ['timely','probe','final']) {
   let queries=0,release;const calls=[];let c;
   const tabs={query:()=>{calls.push(['query',c.now]);queries++;
    return stage==='final'&&queries===2?new Promise(r=>{release=r;}):Promise.resolve([awake]);},
    get:async()=>{calls.push(['get',c.now]);return awake;},
    sendMessage:()=>{calls.push(['probe',c.now]);return stage==='probe'
     ?new Promise(r=>{release=r;}):Promise.resolve(validObservation());}};
   c=collectorClock(tabs);const p=c.collect(100);
   if(stage!=='timely') {
    for(let i=0;i<50&&!release;i++)await tick();assert.ok(release,'actual '+stage+' acquisition');
    c.advance(100);release(stage==='probe'?validObservation():[awake]);
   }
   const r=await p;
   if(stage==='timely'){assert.equal(r.probed_tab_count,1);assert.equal(r.final_tab_count,1);}
   else {assert.equal(r.final_tab_count,null);assert.equal(r.consistency,'UNKNOWN');}
   assert.deepEqual(calls.filter(([,at])=>at>=100),[]);
  }
 });
 test('eight unresolved reads remain charged after expiry and only settlement frees capacity',async()=>{
  for(const reject of [false,true]) {
  let c,queries=0,gets=0;const releases=[];const calls=[];
  const rows=Array.from({length:8},(_,i)=>({...awake,id:i+1}));
  const tabs={query:async()=>{queries++;calls.push(c.now);return rows;},
   get:id=>{gets++;calls.push(c.now);return new Promise((resolve,fail)=>releases.push(()=>
    reject?fail(Error('actual Chrome rejection')):resolve(rows[id-1])));},
   sendMessage:async()=>{calls.push(c.now);return validObservation();}};
  c=collectorClock(tabs);const first=c.collect(100);
  for(let i=0;i<50&&gets<8;i++)await tick();assert.equal(gets,8);
  c.advance(100);await first;const count=calls.length;
  const blocked=await c.collect(200);assert.equal(blocked.initial_tab_count,null);
  assert.equal(calls.length,count,'timeouts never free actual promises');
  c.advance(150);releases.forEach(r=>r());await tick();await tick();
  assert.equal(calls.length,count,'settlement cannot revive expired sweep');
  tabs.query=async()=>{queries++;calls.push(c.now);return [];};
  const fresh=await c.collect(250);assert.equal(fresh.initial_tab_count,0);
  assert.equal(queries,3,'new caller obtains real freed slots for both inventory reads');
  }
 });
 test('one unresolved Chrome read is not eight exhausted slots',async()=>{
  let now=0,serial=0,queries=0,gets=0,digests=0,release;const timers=new Map();
  const rows=Array.from({length:9},(_,i)=>({...awake,id:i+1}));
  const context=vm.createContext({TextEncoder,URL,Date,performance:{now:()=>now},
   crypto:{subtle:{digest(...args){digests++;return digests===1||digests>8
    ?webcrypto.subtle.digest(...args):new Promise(()=>{});}}},
   setTimeout(fn,ms){const id=++serial;timers.set(id,{fn,at:now+ms});return id;},
   clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source('census_core.js'),context);
  const snapshot=context.MMXWebSolCensus.collect({query:async()=>{queries++;return rows;},
   get:id=>{gets++;return id===1?new Promise(r=>{release=()=>r(rows[0]);}):Promise.resolve(rows[id-1]);},
   sendMessage:async()=>validObservation()},INSTANCE);
  for(let i=0;i<100&&!release;i++)await tick();assert.ok(release);assert.equal(digests,8);
  now=800;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}
  const result=await snapshot;
  assert.deepEqual(plain(result.rows.slice(0,8).map(r=>r.status)),Array(8).fill('SWEEP_DEADLINE'),
   'one real pending read cannot relabel local deadline rows as full capacity');
  assert.equal(result.rows[8].status,'OBSERVED');assert.equal(gets,3);assert.equal(queries,2);
  release();await tick();assert.equal(timers.size,0);
 });
 test('outer expiry forbids Chrome acquisitions after a delayed initial query',async()=>{
  let now=0, release;const calls=[];
  const h=harness({clock:{now:()=>now}});const p=await h.ready();
  const row={id:1,windowId:1,url:'https://chatgpt.com/c/deadline',status:'complete'};
  h.tabs.query=()=>{calls.push(['query',now]);return calls.length===1
   ?new Promise(r=>{release=r;}):Promise.resolve([row]);};
  h.tabs.get=async()=>{calls.push(['get',now]);return row;};
  h.tabs.sendMessage=async()=>{calls.push(['probe',now]);throw Error('unavailable');};
  const wall=Date.now();p.onMessage.fire(request({issued_at:new Date(wall).toISOString(),
   expires_at:new Date(wall+100).toISOString()}));
  for(let i=0;i<20&&!release;i++)await tick();assert.ok(release,'initial query actually acquired');
  now=150;release([row]);for(let i=0;i<20;i++)await tick();
  assert.deepEqual(calls.filter(([,at])=>at>=100),[], 'no actual Chrome acquisition after outer expiry');
  assert.equal(p.messages.length,2,'expired attempt cannot post a browser receipt');
 });
 test('native CENSUS admits a sibling schema and returns actual collector rows',async()=>{
  const h=harness({count:129});const r=await nativeResult(h);
  assert.equal(r.status,'COLLECTED');assert.equal(r.snapshot.rows.length,128);
  assert.equal(r.snapshot.header[12],1);assert.equal(r.adapter_instance_id,INSTANCE);
  assert.ok(Buffer.byteLength(JSON.stringify(r))<=61440);
 });
 test('worker fixed columns preserve literal status and cue slots',async()=>{
  const r=await nativeResult(harness({mode:'observed'}));assert.equal(r.status,'COLLECTED');
  assert.equal(r.snapshot.header[0],'mastermind.web_sol_local_census.v1');
  assert.equal(r.snapshot.header.length,20);assert.equal(r.snapshot.rows[0].length,19);
  assert.equal(r.snapshot.rows[0][4],'OBSERVED','literal status slot');
  assert.equal(r.snapshot.rows[0][5],'NOT_OBSERVED');
  assert.equal(r.snapshot.rows[0][3],'UNVERIFIED');
  assert.match(r.snapshot.rows[0][14],/^\d{4}-/);
  assert.deepEqual(r.snapshot.rows[0].slice(15),[null,null,null,'UNVERIFIED']);
 });
 test('popup uses the same worker collector and accepts toolbar sender without frameId',async()=>{
  const h=harness();const {response}=await h.popup();assert.ok(response,'popup broker must answer');
  assert.equal(response.rows.length,1);assert.equal(response.initial_tab_count,1);
 });
 test('real broker null on collector rejection clears actual popup truth',async()=>{
  const h=harness({clock:{now(){throw Error('PRIVATE_CLOCK_FAILURE');}}});await h.ready();
  assert.equal((await h.popup()).response,null,'real collector rejection becomes broker null');
  class Element {
   constructor(){this.children=[];this.textContent='';this.events={};this.disabled=false;}
   replaceChildren(...rows){this.children=rows;}
   append(...rows){this.children.push(...rows);}
   addEventListener(name,fn){this.events[name]=fn;}
  }
  const nodes=Object.fromEntries(['refresh','summary','status','scope','timestamp','rows'].map(k=>[k,new Element()]));
  const top={};const context={self:top,top,document:{getElementById:id=>nodes[id],createElement:()=>new Element()},
   chrome:{runtime:{sendMessage:async message=>(await h.popup(h.sender,message)).response}}};
  vm.runInNewContext(source('census.js'),context);
  for(let i=0;i<50&&nodes.refresh.disabled;i++)await tick();
  assert.equal(nodes.refresh.disabled,false);assert.equal(nodes.summary.children.length,0);
  assert.equal(nodes.rows.children.length,0);assert.equal(nodes.scope.textContent,'');
  assert.match(nodes.status.textContent,/Snapshot unavailable/);
  assert.doesNotMatch(nodes.status.textContent,/PRIVATE_CLOCK_FAILURE/);
 });
 test('content script, foreign page, origin, extension and unknown keys cannot collect',async()=>{
  const h=harness();await tick();const start=h.queries;
  for(const sender of [{...h.sender,tab:{id:1}},{...h.sender,url:'chrome-extension://'+ID+'/other.html'},
   {...h.sender,origin:'https://chatgpt.com'},{...h.sender,id:'foreign'}]) {
   const r=await h.popup(sender);assert.equal(r.response,undefined);
  }
  assert.equal((await h.popup(h.sender,{kind:'MMX_WEB_SOL_CENSUS_REFRESH',extra:1})).response,undefined);
  assert.equal(h.queries,start);
 });
 test('configured failed query is unknown COLLECTED, never measured empty',async()=>{
  const r=await nativeResult(harness({queryFailure:true}));assert.equal(r.status,'COLLECTED');
  assert.equal(r.snapshot.header[9],null);assert.equal(r.snapshot.header[8],'QUERY_UNAVAILABLE');
 });
 test('wrong adapter/extra fields do not invoke collector',async()=>{
  const h=harness();const p=await h.ready();await tick();const before=h.queries;
  p.onMessage.fire(request({adapter_instance_id:'b'.repeat(64)}));p.onMessage.fire(request({extra:true}));
  await tick();assert.equal(h.queries,before);assert.equal(p.messages.length,2);
 });
 test('mixed package or digest refuses native registration and popup acquisition',async()=>{
  for(const configPatch of [{clientPackageVersion:'0.1.0'},{capabilityDigest:'0'.repeat(64)}]) {
   const h=harness({configPatch});await tick();assert.equal(h.ports.length,0);
   const startupQueries=h.queries;assert.equal((await h.popup()).response,undefined);
   assert.equal(h.queries,startupQueries,'no census read beyond inherited startup hydration');
  }
 });
 test('reconnect boot and old port callbacks cannot deliver a stale census',async()=>{
  const h=harness({count:8,pending:true});const old=await h.ready();const req=request();
  old.onMessage.fire(req);for(let i=0;i<50&&h.reads<8;i++)await tick();assert.equal(h.reads,8);
  old.onDisconnect.fire();const alarm=h.alarms.scheduled.at(-1);
  assert.match(alarm,/reconnect/);h.alarms.onAlarm.fire({name:alarm});await tick();
  assert.equal(h.ports.length,2);const fresh=h.ports[1];
  for(let i=0;i<2;i++){const hello=fresh.messages.at(-1);fresh.onMessage.fire({...hello,
   schema:'mastermind.web_sol_transport_hello_ack.v1',boot_nonce:'boot-new-generation-0001'});}
  old.onMessage.fire(request());h.resolvers.forEach(r=>r());await tick();await tick();
  assert.equal(old.messages.length,2);assert.equal(fresh.messages.length,2);
  h.tabs.query=async()=>[];const next=request({nonce:'new-request-correlation-0001'});
  fresh.onMessage.fire(next);next.nonce='mutated-after-admission-0001';
  for(let i=0;i<50&&fresh.messages.length<3;i++)await tick();
  assert.equal(fresh.messages[2].nonce,'new-request-correlation-0001');
  assert.equal(fresh.messages[2].status,'COLLECTED');
 });
 test('port disconnect during real collection prevents late posts to old port',async()=>{
  const h=harness({count:8,pending:true});const p=await h.ready();p.onMessage.fire(request());
  for(let i=0;i<30&&h.reads<8;i++)await tick();assert.equal(h.reads,8,'real collection reached read boundary');
  p.onDisconnect.fire();h.resolvers.forEach(r=>r());await tick();await tick();
  assert.equal(p.messages.length,2,'disconnected port must not receive completion');
 });
 test('popup and native share eight unresolved Chrome slots without wrappers',async()=>{
  const h=harness({count:8,pending:true});const p=await h.ready();p.onMessage.fire(request());
  for(let i=0;i<30&&h.reads<8;i++)await tick();assert.equal(h.reads,8);
  const result=await h.popup();assert.equal(h.reads,8,"shared actual reads stay bounded");assert.ok(result.response);
  assert.equal(result.response.initial_tab_count,null);
  h.resolvers.forEach(r=>r());await tick();
 });
}
module.exports={harness,request,nativeResult,DIGEST};
