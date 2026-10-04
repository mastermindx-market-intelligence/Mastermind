import test from 'node:test';
import assert from 'node:assert/strict';

import {
  REQUIRED_HOST,
  RESERVED_FUNNEL_PORT,
  TAILNET_ACCOUNT_LABEL,
  resolveTailnetGatewayConfig,
} from './tailnet-gateway.mjs';

function base(overrides = {}) {
  return {
    accountLabel: 'fabric',
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
  assert.equal(TAILNET_ACCOUNT_LABEL, 'fabric');
  assert.equal(config.host, REQUIRED_HOST);
  assert.equal(config.port, 45117);
  assert.equal(config.publicUrl, 'https://mac-studio.example-tailnet.ts.net');
  assert.equal(config.backendMode, 'shared-account');
  assert.equal(config.reclaimIdleCatalogSessions, true);
  assert.equal(config.testMode, false);
  assert.equal(Object.hasOwn(config, 'accountLabel'), false);
  assert.equal(auth.accountLabel, 'fabric');
  assert.equal(auth.principal, 'tunnel:fabric');
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

test('tailnet gateway refuses alternate account, bind, test mode, and reserved port', () => {
  assert.throws(
    () => resolveTailnetGatewayConfig(base({accountLabel:'chatgpt1'})),
    /accountLabel is fixed to fabric/,
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
});

test('tailnet gateway source does not create a second authentication implementation', async () => {
  const {readFile} = await import('node:fs/promises');
  const source = await readFile(new URL('./tailnet-gateway.mjs', import.meta.url), 'utf8');
  assert.match(source, /createTunnelAuth/);
  assert.doesNotMatch(source, /auth\.mjs/);
  assert.doesNotMatch(source, /Authorization|Bearer|jwks|oauth/i);
  assert.doesNotMatch(source, /Tailscale-(User|Login|Name|Profile|App-Capabilities)/);
});
