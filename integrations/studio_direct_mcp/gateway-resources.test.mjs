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
