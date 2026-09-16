import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import {startPrivateGateway, resolvePrivateTunnelConfig} from './private-tunnel-gateway.mjs';

const fixture = new URL('./fixtures/backend.mjs', import.meta.url).pathname;

async function setup(t, options = {}, env = {}) {
  const dir = await mkdtemp(resolve(tmpdir(), 'studio-owner-review-'));
  const marker = resolve(dir, 'marker');
  const effects = resolve(dir, 'effects.jsonl');
  const gateway = await startPrivateGateway({accountLabel:'review', port:0,
    command:process.execPath, args:[fixture], requestTimeoutMs:3000,
    childEnv:{NODE_OPTIONS:'', FIXTURE_MARKER_PATH:marker, FIXTURE_EFFECT_LOG:effects, ...env},
    ...options});
  const connections = [];
  t.after(async () => {
    for (const {client, transport} of connections) {
      try { await transport.terminateSession(); } catch {}
      await client.close();
    }
    await gateway.close();
    await rm(dir, {recursive:true, force:true});
  });
  async function connect() {
    const client = new Client({name:'independent-owner-review', version:'1'});
    const transport = new StreamableHTTPClientTransport(new URL(gateway.url));
    connections.push({client, transport});
    await client.connect(transport);
    return {client, transport};
  }
  async function paths(client) {
    const result = await client.callTool({name:'fixture_paths', arguments:{}});
    return JSON.parse(result.content[0].text);
  }
  return {gateway, connect, paths, marker, effects};
}

test('private default preserves child across completed effects, DELETE and twelve new sessions', async t => {
  assert.equal(resolvePrivateTunnelConfig({accountLabel:'review',port:0}).config.backendMode, 'shared-account');
  const {gateway,connect,paths} = await setup(t);
  const first = await connect();
  const original = await paths(first.client);
  await first.client.callTool({name:'delayed_effect',arguments:{marker:'initial',delayMs:0}});
  await first.transport.terminateSession();
  for (let i=0; i<12; i++) {
    const next = await connect();
    assert.equal((await paths(next.client)).pid, original.pid);
    await next.client.callTool({name:'delayed_effect',arguments:{marker:`churn-${i}`,delayMs:0}});
    await sleep(80);
  }
  assert.equal(gateway.stats().backend.spawns, 1);
  assert.ok(gateway.stats().sessions.active <= 8);
  assert.ok(gateway.stats().sessions.reclaimed >= 4);
});

test('a real ambiguous timeout preserves the healthy account child and never replays', async t => {
  const {gateway,connect,paths,marker} = await setup(t, {backendMode:'shared-account',requestTimeoutMs:700}, {FIXTURE_NEVER:'1'});
  const origin = await connect();
  const healthy = await connect();
  const original = await paths(healthy.client);
  await assert.rejects(origin.client.callTool({name:'delayed_effect',arguments:{marker:'once',delayMs:0}}), /EFFECT_UNKNOWN/);
  assert.equal((await paths(healthy.client)).pid, original.pid);
  await assert.rejects(paths(origin.client), /tainted/i);
  assert.equal(gateway.stats().backend.spawns, 1);
  assert.equal(gateway.stats().backend.lost, 0);
  assert.equal(gateway.stats().requests.timeouts, 1);
  assert.equal((await readFile(marker,'utf8')).split('\n').filter(x=>x==='once').length,1);
});

test('backend loss also rejects old sessions which had not yet opened the child', async t => {
  const {gateway,connect,paths,marker} = await setup(t, {backendMode:'shared-account'});
  const origin = await connect();
  const oldLazy = await connect();
  const original = await paths(origin.client);
  await oldLazy.client.callTool({name:'studio_ping', arguments:{}});
  await assert.rejects(origin.client.callTool({name:'drop_after_effect',arguments:{marker:'drop-once'}}), /EFFECT_UNKNOWN/);
  const fresh = await connect();
  assert.notEqual((await paths(fresh.client)).pid, original.pid);
  await assert.rejects(paths(oldLazy.client), /tainted|generation|backend.*lost/i);
  await assert.rejects(paths(origin.client), /tainted/i);
  assert.equal(gateway.stats().backend.spawns, 2);
  assert.equal(gateway.stats().backend.lost, 1);
  assert.equal((await readFile(marker,'utf8')).trim(),'drop-once');
});

test('one aggregate execution and queue bound applies across frontend sessions', async t => {
  const {gateway,connect,paths,effects} = await setup(t, {backendMode:'shared-account',maxSessions:12});
  const clients = [];
  for(let i=0;i<10;i++) clients.push((await connect()).client);
  await paths(clients[0]);
  const results = await Promise.allSettled(clients.map((c,i) => c.callTool({name:'delayed_effect',arguments:{marker:`load-${i}`,delayMs:350}})));
  assert.equal(results.filter(r=>r.status==='fulfilled').length,8);
  assert.equal(results.filter(r=>r.status==='rejected').length,2);
  let active=0,peak=0;
  for (const entry of (await readFile(effects,'utf8')).trim().split('\n').map(JSON.parse)) {
    if(entry.phase==='start') peak=Math.max(peak,++active);
    if(entry.phase==='resolved') active--;
  }
  assert.equal(peak,4);
  assert.equal(active,0);
  assert.equal(gateway.stats().requests.busy,2);
  assert.equal(gateway.stats().backend.spawns,1);
});
