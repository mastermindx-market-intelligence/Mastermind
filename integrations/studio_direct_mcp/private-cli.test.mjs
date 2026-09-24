import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';

test('actual private CLI starts a listener and gracefully exits on SIGTERM', {timeout:30000}, async () => {
  const dir = await mkdtemp(join(tmpdir(), 'studio-private-cli-'));
  const cfg = join(dir, 'config.json');
  await writeFile(cfg, JSON.stringify({accountLabel:'cli-check',host:'127.0.0.1',port:0,
    command:process.execPath,args:[fileURLToPath(new URL('./fixtures/backend.mjs',import.meta.url))],
    cwd:dir,stateDir:join(dir,'state'),testMode:false}));
  const child = spawn(process.execPath,[fileURLToPath(new URL('./private-tunnel-gateway.mjs',import.meta.url)),cfg],
    {stdio:['ignore','pipe','pipe'],env:{...process.env,NODE_OPTIONS:''}});
  let logs = '';
  child.stderr.on('data',c=>{logs+=c.toString();});
  child.stdout.on('data',c=>{logs+=c.toString();});
  const exited = once(child,'exit');
  try {
    const until = Date.now()+20000;
    while(!/listening on http:\/\/127\.0\.0\.1:(\d+)\/mcp/.test(logs) && child.exitCode === null && Date.now()<until)
      await delay(25);
    const match = logs.match(/listening on (http:\/\/127\.0\.0\.1:\d+)\/mcp/);
    assert.ok(match, `CLI must stay running and announce the private listener; exit=${child.exitCode}; logs=${logs}`);
    const response = await fetch(match[1]+'/.well-known/oauth-protected-resource',{signal:AbortSignal.timeout(3000)});
    assert.equal(response.status,404);
    child.kill('SIGTERM');
    assert.deepEqual(await exited,[0,null]);
    assert.match(logs,/gateway_stopped/);
  } finally {
    if(child.exitCode === null && child.signalCode === null) {child.kill('SIGTERM');await exited;}
    await rm(dir,{recursive:true,force:true});
  }
});
