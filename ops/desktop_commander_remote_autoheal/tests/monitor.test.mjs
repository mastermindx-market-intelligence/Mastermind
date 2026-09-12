import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { probeInner, Watchdog, restartPolicy, atomicJson, eventLogger } from '../monitor.mjs';
const ok = { content: [{ type: 'text', text: 'prefix\nDC_LOCAL_HEALTH_V1\n' }] };
const wait = ms => new Promise(r => setTimeout(r, ms));

test('probe uses read_file on the supplied EXISTING client, never ping or a shell', async () => {
  const requests = [];
  const client = {callTool: async request => {requests.push(request); return ok;}};
  await probeInner(client, '/fixture/sentinel', 'DC_LOCAL_HEALTH_V1', 30);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].name, 'read_file');
  assert.equal(requests[0].arguments.path, '/fixture/sentinel');
});
test('pong without a sentinel is not execution health', async () => {
  await assert.rejects(probeInner({callTool: async () => ({content:[{type:'text',text:'pong'}]})}, '/x', 'DC_LOCAL_HEALTH_V1', 30), /probe_invalid/);
});
test('isError result is not healthy even when text contains the sentinel', async () => {
  await assert.rejects(probeInner({callTool: async () => ({...ok,isError:true})}, '/x', 'DC_LOCAL_HEALTH_V1', 30), /probe_invalid/);
});
test('Not connected transport rejection is detected and the command is not replayed', async () => {
  let calls = 0;
  await assert.rejects(probeInner({callTool: async () => {calls++;throw Error('Not connected');}}, '/x','DC_LOCAL_HEALTH_V1',30), /Not connected/);
  assert.equal(calls, 1);
});
test('a wedged read has a real deadline even when dependency ignores timeout', async () => {
  const started=Date.now();
  await assert.rejects(probeInner({callTool:()=>new Promise(()=>{})},'/x','DC_LOCAL_HEALTH_V1',25),/probe_timeout/);
  assert.ok(Date.now()-started < 500);
});
test('probes never overlap and failures have one recovery edge', async () => {
  let calls=0; const trips=[];
  const w=new Watchdog({probe:async()=>{calls++;await wait(10);throw Error('bad');},trip:code=>trips.push(code),maxFailures:2});
  await Promise.all([w.tick(),w.tick(),w.tick()]);
  assert.equal(calls,1); assert.equal(trips.length,0);
  await w.tick(); await w.tick(); w.closed();
  assert.deepEqual(trips,['inner_probe_failed']); assert.equal(calls,2);
});
test('successful probe resets consecutive failures', async () => {
  let failing=true; const trips=[];
  const w=new Watchdog({probe:async()=>{if(failing)throw Error('bad');},trip:c=>trips.push(c),maxFailures:2});
  await w.tick(); failing=false; await w.tick(); failing=true; await w.tick();
  assert.equal(trips.length,0);
});
test('child close trips immediately and deliberate stop suppresses recovery', () => {
  const trips=[];const w=new Watchdog({probe:async()=>{},trip:c=>trips.push(c)});
  w.closed();w.closed();assert.deepEqual(trips,['inner_transport_closed']);
  const x=new Watchdog({probe:async()=>{},trip:c=>trips.push(c)});x.stop();x.closed();
  assert.equal(trips.length,1);
});
test('restart backoff is capped but never permanently exhausts', () => {
  const now=1000000;
  assert.equal(restartPolicy([],now).delayMs,0);
  assert.equal(restartPolicy([now-20000],now).delayMs,10000);
  const repeated=restartPolicy(Array(20).fill(now-1000),now);
  assert.equal(repeated.allowed,true);
  assert.equal(repeated.delayMs,300000);
  assert.equal(repeated.starts.length,6);
  assert.equal(restartPolicy([now-700000],now).delayMs,0);
});
test('state is atomically replaced and private', () => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dc-state-'));
  try {const p=path.join(root,'state.json');atomicJson(p,{n:1});atomicJson(p,{n:2});
    assert.deepEqual(JSON.parse(fs.readFileSync(p)),{n:2});assert.equal(fs.statSync(p).mode&0o777,0o600);
    assert.deepEqual(fs.readdirSync(root),['state.json']);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
test('new diagnostics drop arbitrary secrets and rotate within a fixed bound', () => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dc-log-'));
  try {const log=eventLogger(root,'generation-test',{maxBytes:400,backups:2});
    for(let i=0;i<30;i++)log('probe_pass',{mcpPid:123,token:'TOP_SECRET',message:'RAW_ARGS'});
    const files=fs.readdirSync(root);assert.ok(files.length<=3);
    const body=files.map(f=>fs.readFileSync(path.join(root,f),'utf8')).join('');
    assert.ok(!body.includes('TOP_SECRET'));assert.ok(!body.includes('RAW_ARGS'));
    assert.ok(body.includes('probe_pass'));
    for(const f of files)assert.equal(fs.statSync(path.join(root,f)).mode&0o777,0o600);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
