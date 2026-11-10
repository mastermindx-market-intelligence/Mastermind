import { EventEmitter } from 'node:events';
import test from 'node:test';
import assert from 'node:assert/strict';
import { makeControllerInvoker, operatorAuth, createOperatorHandler, FABRIC_OPERATOR_TOOLS, CAPABILITY_HEADER } from './fabric-operator.mjs';
import { principalKeyOf, startGateway } from './gateway.mjs';

const TOKEN = 'a'.repeat(64), OTHER = 'b'.repeat(64);
const base = { middleware(req,res,next) { req.auth={principal:'tunnel:fabric-read',scopes:['studio.control']}; next(); } };
const invoke = async (action,token,args) => token===TOKEN ? {root:'root',operator_run:'operator',child_budget_remaining:2,action} : {state:'OPERATOR_REQUEST_REFUSED'};
function authorize(token) {
  const req={headers:token===undefined ? {} : {[CAPABILITY_HEADER]:token}};
  return new Promise(resolve=>{
    const res={status(code){this.code=code;return this;},setHeader(){},json(body){resolve({req,code:this.code,body});}};
    operatorAuth(base,invoke).middleware(req,res,()=>resolve({req,code:200}));
  });
}
test('ordinary read clients retain exact principal and no operator grant',async()=>{
  const {req,code}=await authorize();assert.equal(code,200);assert.equal(principalKeyOf(req.auth),'p:tunnel:fabric-read');assert.equal(req.auth.fabricOperator,undefined);
});
test('capability is validated and bound into session identity without plaintext',async()=>{
  const {req,code}=await authorize(TOKEN);assert.equal(code,200);
  assert.equal(req.auth.fabricOperator.operatorRun,'operator');assert.equal(Object.isFrozen(req.auth.fabricOperator),true);
  assert(!principalKeyOf(req.auth).includes(TOKEN));assert.notEqual(principalKeyOf(req.auth),'p:tunnel:fabric-read');
});
test('unknown malformed and multi-header tokens refuse',async()=>{
  for(const token of [OTHER,'invalid',[TOKEN,OTHER]])assert.equal((await authorize(token)).code,403);
});
test('missing capability cannot invoke effect',async()=>{
  let calls=0;const handler=createOperatorHandler(async()=>{calls++;return {};});
  assert.equal((await handler('fabric_child_request',{},{})).isError,true);assert.equal(calls,0);
});
test('tool receives request-local credential, never a mutable global binding',async()=>{
  const {req}=await authorize(TOKEN);let seen;
  const handler=createOperatorHandler(async(a,t,args)=>{seen={a,t,args};return {state:'SUBMITTED_TO_EXISTING_ADAPTER'};});
  const result=await handler('fabric_child_request',{run_id:'child'},req.auth);
  assert.equal(result.isError,false);assert.deepEqual(seen,{a:'request',t:TOKEN,args:{run_id:'child'}});
  assert(!JSON.stringify(result).includes(TOKEN));
});
test('typed schema admits no caller host model account lease or capability override',()=>{
  const request=FABRIC_OPERATOR_TOOLS.find(x=>x.name==='fabric_child_request');assert.equal(request.inputSchema.additionalProperties,false);
  for(const k of ['token','pool','model','host','account','lease','env'])assert.equal(request.inputSchema.properties[k],undefined);
});
test('real MCP request carries authInfo and rejects substituted session capability',async()=>{
  const calls=[];
  const fake=async(action,token,args)=>{calls.push({action,token,args});return token===OTHER ? {root:'root-2',operator_run:'operator-2',child_budget_remaining:2,action} : invoke(action,token,args);};
  const auth=operatorAuth(base,fake);
  const gateway=await startGateway({testMode:true,port:0,host:'127.0.0.1',command:process.execPath,args:['-e','process.exit(90)'],
    toolAllowlist:['studio_ping',...FABRIC_OPERATOR_TOOLS.map(t=>t.name)],fabricOperatorInvoke:fake},auth);
  try{
    const post=async(body,token=TOKEN,sid)=>{
      const headers={'content-type':'application/json',accept:'application/json, text/event-stream',[CAPABILITY_HEADER]:token};
      if(token===null)delete headers[CAPABILITY_HEADER];
      if(sid)headers['mcp-session-id']=sid;
      const r=await fetch(gateway.url,{method:'POST',headers,body:JSON.stringify(body)});const text=await r.text();
      const data=text.startsWith('event:')||text.startsWith('data:') ? JSON.parse(text.split('\n').find(l=>l.startsWith('data:')).slice(5)) : JSON.parse(text);
      return {status:r.status,sid:r.headers.get('mcp-session-id'),data};
    };
    const ordinary=await post({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'ordinary-read',version:'1'}}},null);
    const forbidden=await post({jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'fabric_child_request',arguments:{}}},null,ordinary.sid);
    assert.equal(forbidden.data.error.code,-32601);assert.equal(calls.filter(x=>x.action==='request').length,0);
    const init=await post({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'synthetic-operator',version:'1'}}});
    assert.equal(init.status,200);assert(init.sid);
    const result=await post({jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'fabric_operator_scope',arguments:{}}},TOKEN,init.sid);
    assert.equal(result.status,200);assert.equal(JSON.parse(result.data.result.content[0].text).operator_run,'operator');
    const denied=await post({jsonrpc:'2.0',id:3,method:'tools/call',params:{name:'fabric_child_request',arguments:{}}},OTHER,init.sid);
    assert.equal(denied.status,403);assert.equal(calls.filter(x=>x.action==='request').length,0);
  }finally{await gateway.close();}
});

test('helper admission is bounded before spawning even for forged capabilities',async()=>{
  const children=[];
  const spawnImpl=()=>{const c=new EventEmitter();c.stdout=new EventEmitter();c.stderr=new EventEmitter();c.stdin=new EventEmitter();c.stdin.end=()=>{};children.push(c);return c;};
  const call=makeControllerInvoker({python:'/python',ownerPath:'/owner.py',spawnImpl,maxConcurrent:2});
  const a=call('describe',TOKEN,{}), b=call('describe',OTHER,{});
  await assert.rejects(call('describe','c'.repeat(64),{}),/busy/);assert.equal(children.length,2);
  for(const c of children){c.stdout.emit('data',Buffer.from('{"state":"OPERATOR_REQUEST_REFUSED"}'));c.emit('close',75);}
  await Promise.all([a,b]);
  const next=call('describe',TOKEN,{});assert.equal(children.length,3);
  children[2].stdout.emit('data',Buffer.from('{"state":"OPERATOR_REQUEST_REFUSED"}'));children[2].emit('close',75);await next;
});
