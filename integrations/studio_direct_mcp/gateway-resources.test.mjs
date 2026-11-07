import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import {startPrivateGateway} from './private-tunnel-gateway.mjs';

test('advertised UI resources resolve through their own backend session', {timeout:15000}, async()=>{
  const gw=await startPrivateGateway({accountLabel:'resource-test',port:0,command:process.execPath,
    args:[fileURLToPath(new URL('./fixtures/resources-backend.mjs',import.meta.url))],
    backendMode:'per-session'});
  const clients=[];const transports=[];
  try {
    const pids=[];
    for(let i=0;i<2;i++) {
      const c=new Client({name:'native-discovery-fixture',version:'1'});
      const t=new StreamableHTTPClientTransport(new URL(gw.url));clients.push(c);transports.push(t);await c.connect(t);
      const catalog=await c.listTools();const uri=catalog.tools.find(x=>x.name==='preview')._meta['openai/outputTemplate'];
      const resources=await c.listResources();assert.equal(resources.resources[0].uri,uri);
      const result=await c.readResource({uri});
      assert.equal(result.contents[0].uri,uri);
      assert.match(result.contents[0].text,/<p>Resource fixture process \d+<\/p>/);
      pids.push(result.contents[0]._meta.fixturePid);
      assert.deepEqual((await c.listResourceTemplates()).resourceTemplates,[]);
      assert.deepEqual((await c.listPrompts()).prompts,[]);
      await assert.rejects(c.readResource({uri:'ui://studio-test/unknown'}));
    }
    assert.notEqual(pids[0],pids[1], 'resource reads use separate backend children');
  } finally {
    for(const t of transports) try {await t.terminateSession();} catch {}
    for(const c of clients) await c.close();
    await gw.close();
  }
});

test('shared-account bootstrap session survives capacity pressure through UI resource read', {timeout:15000}, async()=>{
  const gw=await startPrivateGateway({
    accountLabel:'resource-bootstrap-test',port:0,command:process.execPath,
    args:[fileURLToPath(new URL('./fixtures/resources-backend.mjs',import.meta.url))],
    backendMode:'shared-account',maxSessions:1,reclaimIdleGraceMs:1000,
    requestTimeoutMs:5000,idleTimeoutMs:60000,
  });
  const post=async(body,sid=null)=>{
    const headers={'content-type':'application/json',accept:'application/json, text/event-stream'};
    if(sid) headers['mcp-session-id']=sid;
    const res=await fetch(new URL('/mcp',gw.url),{method:'POST',headers,body:JSON.stringify(body)});
    return {status:res.status,sid:res.headers.get('mcp-session-id'),text:await res.text()};
  };
  const sleep=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
  try {
    const first=await post({jsonrpc:'2.0',id:'init-1',method:'initialize',params:{
      protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'bootstrap-fixture',version:'1'},
    }});
    assert.equal(first.status,200,first.text); assert.ok(first.sid);

    await sleep(400);
    const pressure1=await post({jsonrpc:'2.0',id:'init-pressure-1',method:'initialize',params:{
      protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'pressure',version:'1'},
    }});
    assert.equal(pressure1.status,503,'capacity pressure must not evict a recently initialized session');

    const initialized=await post({jsonrpc:'2.0',method:'notifications/initialized'},first.sid);
    assert.equal(initialized.status,202,initialized.text);
    await sleep(400);
    const pressure2=await post({jsonrpc:'2.0',id:'init-pressure-2',method:'initialize',params:{
      protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'pressure',version:'1'},
    }});
    assert.equal(pressure2.status,503,'initialized activity must refresh the reclaim grace');

    const resource=await post({jsonrpc:'2.0',id:'resource-read',method:'resources/read',params:{
      uri:'ui://studio-test/preview',
    }},first.sid);
    assert.equal(resource.status,200,resource.text);
    assert.match(resource.text,/Resource fixture process/);

    await sleep(1100);
    const afterGrace=await post({jsonrpc:'2.0',id:'init-after-grace',method:'initialize',params:{
      protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'after-grace',version:'1'},
    }});
    assert.equal(afterGrace.status,200,afterGrace.text);
    assert.notEqual(afterGrace.sid,first.sid);

    const old=await post({jsonrpc:'2.0',id:'old-session-probe',method:'resources/read',params:{
      uri:'ui://studio-test/preview',
    }},first.sid);
    assert.equal(old.status,404,'the old shell becomes reclaimable only after its idle grace');
  } finally { await gw.close(); }
});
