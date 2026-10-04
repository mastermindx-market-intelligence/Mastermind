import test from 'node:test';
import assert from 'node:assert/strict';

import {
  REQUIRED_HOST,
  RESERVED_FUNNEL_PORT,
  TAILNET_PROFILES,
  resolveTailnetGatewayConfig,
} from './tailnet-gateway.mjs';

function base(overrides = {}) {
  return {
    accountLabel: 'fabric-read',
    host: '127.0.0.1',
    port: 45117,
    testMode: false,
    publicUrl: 'https://mac-studio.example-tailnet.ts.net',
    command: process.execPath,
    args: ['fixture.mjs'],
    ...overrides,
  };
}

test('tailnet fabric gateway fixes channel, loopback bind, and shared backend', () => {
  const {config, auth} = resolveTailnetGatewayConfig(base());
  assert.deepEqual(Object.keys(TAILNET_PROFILES).sort(), ['fabric-design','fabric-read']);
  assert.equal(config.host, REQUIRED_HOST);
  assert.equal(config.port, 45117);
  assert.equal(config.publicUrl, 'https://mac-studio.example-tailnet.ts.net');
  assert.equal(config.backendMode, 'shared-account');
  assert.equal(config.reclaimIdleCatalogSessions, true);
  assert.equal(config.testMode, false);
  assert.equal(Object.hasOwn(config, 'accountLabel'), false);
  assert.deepEqual(config.toolAllowlist, [
    'studio_ping',
    'studio_fleet_status',
    'paper_inspect',
    'paper_catalog',
    'paper_read',
  ]);
  assert.equal(auth.accountLabel, 'fabric-read');
  assert.equal(auth.principal, 'tunnel:fabric-read');
});

test('tailnet origin is exact https ts.net root without credentials or query', () => {
  for (const publicUrl of [
    '',
    'http://mac-studio.example-tailnet.ts.net',
    'https://example.com',
    'https://mac-studio.example-tailnet.ts.net/not-root',
    'https://user:pass@mac-studio.example-tailnet.ts.net',
    'https://mac-studio.example-tailnet.ts.net?x=1',
    'https://mac-studio.example-tailnet.ts.net#frag',
    'https://ts.net',
  ]) {
    assert.throws(
      () => resolveTailnetGatewayConfig(base({publicUrl})),
      /publicUrl must be an https tailnet origin/,
      publicUrl,
    );
  }
  const {config} = resolveTailnetGatewayConfig(
    base({publicUrl:'https://mac-studio.example-tailnet.ts.net:10000/'}),
  );
  assert.equal(config.publicUrl, 'https://mac-studio.example-tailnet.ts.net:10000');
});

test('tailnet gateway refuses unknown account, bind, test mode, reserved port, and caller tool policy', () => {
  assert.throws(
    () => resolveTailnetGatewayConfig(base({accountLabel:'chatgpt1'})),
    /accountLabel must be fabric-read or fabric-design/,
  );
  assert.throws(
    () => resolveTailnetGatewayConfig(base({host:'0.0.0.0'})),
    /host is fixed to 127\.0\.0\.1/,
  );
  assert.throws(
    () => resolveTailnetGatewayConfig(base({testMode:true})),
    /testMode must be false or absent/,
  );
  assert.throws(
    () => resolveTailnetGatewayConfig(base({port:RESERVED_FUNNEL_PORT})),
    /must not be 45017/,
  );
  assert.throws(
    () => resolveTailnetGatewayConfig(base({backendMode:'per-session'})),
    /backendMode is fixed to shared-account/,
  );
  assert.throws(
    () => resolveTailnetGatewayConfig(base({toolAllowlist:['start_process']})),
    /toolAllowlist is profile-owned/,
  );
});

test('design route grants only the two Paper mutation tools beyond read', () => {
  const read = resolveTailnetGatewayConfig(base({accountLabel:'fabric-read'})).config.toolAllowlist;
  const design = resolveTailnetGatewayConfig(base({accountLabel:'fabric-design'})).config.toolAllowlist;
  assert.deepEqual(
    design.filter((name) => !read.includes(name)),
    ['paper_prepare','paper_edit'],
  );
  for (const forbidden of [
    'start_process',
    'interact_with_process',
    'write_file',
    'edit_block',
    'studio_git_commit_current_changes',
    'studio_git_push_current_branch',
  ]) {
    assert.equal(read.includes(forbidden), false);
    assert.equal(design.includes(forbidden), false);
  }
});

test('tailnet gateway source does not create a second authentication implementation', async () => {
  const {readFile} = await import('node:fs/promises');
  const source = await readFile(new URL('./tailnet-gateway.mjs', import.meta.url), 'utf8');
  assert.match(source, /createTunnelAuth/);
  assert.equal(source.includes("from './auth.mjs'"), false);
  assert.equal(source.includes('from "./auth.mjs"'), false);
  assert.doesNotMatch(source, /Authorization|Bearer|jwks|oauth/i);
  assert.doesNotMatch(source, /Tailscale-(User|Login|Name|Profile|App-Capabilities)/);
});
