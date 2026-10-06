import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import {startGateway, resolveConfig} from './gateway.mjs';

const fixture = new URL('./fixtures/shared-state-backend.mjs', import.meta.url).pathname;
const auth = {middleware(req, _res, next) {
  const principal = req.headers.authorization;
  if (!['alice','bob'].includes(principal)) throw Object.assign(new Error('unauthorized'),{statusCode:401});
  req.auth = {principal,clientId:principal,scopes:['studio.control']};
  next();
}};
async function setup(t, extra = {}) {
  const gateway = await startGateway({host:'127.0.0.1',port:0,command:process.execPath,args:[fixture],
    backendMode:'shared-account',requestTimeoutMs:3000,childEnv:{NODE_OPTIONS:''},...extra},auth);
  const clients=[];
  t.after(async()=>{for(const c of clients) await c.close(); await gateway.close();});
  async function connect(principal='alice') {
    const client = new Client({name:'shared-state-test',version:'1'});
    clients.push(client);
    const transport = new StreamableHTTPClientTransport(new URL(gateway.url),{requestInit:{headers:{authorization:principal}}});
    await client.connect(transport);
    return {client,transport};
  }
  return {gateway,connect};
}
const call=(client,name,args={})=>client.callTool({name,arguments:args});
const value=result=>JSON.parse(result.content[0].text);

test('process state is shared across sessions and remains after creator DELETE', async t=>{
  const {gateway,connect}=await setup(t);
  const a=await connect(), b=await connect();
  const {pid}=value(await call(a.client,'start_process',{cmd:'marker-a'}));
  assert.notEqual((await call(b.client,'interact_with_process',{pid,input:'continued'})).isError,true);
  await a.transport.terminateSession();
  const result=await call(b.client,'read_process_output',{pid});
  assert.notEqual(result.isError,true);
  assert.deepEqual(value(result).output,['[continued]']);
  assert.equal(gateway.stats().backend.spawns,1);
});

test('different principals on one gateway cannot access one another process handles',async t=>{
  const {gateway,connect}=await setup(t);
  const a=await connect('alice'),b=await connect('bob');
  const {pid}=value(await call(a.client,'start_process',{cmd:'alice-private'}));
  assert.equal((await call(b.client,'read_process_output',{pid})).isError,true);
  await call(b.client,'start_process',{cmd:'bob-private'});
  assert.equal(value(await call(a.client,'read_process_output',{pid})).cmd,'alice-private');
  assert.equal(value(await call(b.client,'read_process_output',{pid})).cmd,'bob-private');
  assert.equal(gateway.stats().backend.spawns,2);
  assert.equal(new Set(gateway.stats().backend.owners.map(o=>o.generation)).size,2);
});

test('separate gateways for the same principal retain separate backend state',async t=>{
  const one=await setup(t),two=await setup(t);
  const a=await one.connect(),b=await two.connect();
  const {pid}=value(await call(a.client,'start_process',{cmd:'gateway-one'}));
  assert.equal((await call(b.client,'read_process_output',{pid})).isError,true);
  assert.notEqual(one.gateway.stats().backend.owners[0].generation,two.gateway.stats().backend.owners[0].generation);
});

test('the generic gateway default keeps per-session isolation',async t=>{
  assert.equal(resolveConfig({}).backendMode,'per-session');
  const {gateway,connect}=await setup(t,{backendMode:'per-session'});
  const a=await connect(),b=await connect();
  const {pid}=value(await call(a.client,'start_process'));
  assert.equal((await call(b.client,'read_process_output',{pid})).isError,true);
  assert.equal(gateway.stats().backend.spawns,2);
});

test('backend mode configuration rejects unsupported values',()=>{
  assert.throws(()=>resolveConfig({backendMode:'invalid'}),/backendMode/);
  assert.equal(resolveConfig({backendMode:'shared-account'}).reclaimIdleCatalogSessions,true);
  assert.equal(resolveConfig({backendMode:'per-session'}).reclaimIdleCatalogSessions,false);
});
