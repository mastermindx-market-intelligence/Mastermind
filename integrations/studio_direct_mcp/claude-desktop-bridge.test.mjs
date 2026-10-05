import assert from 'node:assert/strict';
import test from 'node:test';

import { assertCatalog, routeUrl, ROUTES } from './claude-desktop-bridge.mjs';

test('routeUrl derives loopback endpoint from exact installed route manifest', async () => {
  const seen = [];
  const result = await routeUrl('design', {
    home: '/fixture-home',
    readManifest: async (path) => {
      seen.push(path);
      return { account: 'fabric-design', port: 45118 };
    },
  });
  assert.equal(result.route, 'design');
  assert.equal(result.account, 'fabric-design');
  assert.equal(result.url, 'http://127.0.0.1:45118/mcp');
  assert.equal(
    seen[0],
    '/fixture-home/.local/share/studio-direct-mcp/private/fabric-design/manifest.json',
  );
});

test('routeUrl refuses missing, wrong-account, and invalid-port runtime state', async () => {
  await assert.rejects(
    () => routeUrl('read', { readManifest: async () => { throw new Error('missing'); } }),
    /STUDIO_RUNTIME_UNAVAILABLE/,
  );
  await assert.rejects(
    () => routeUrl('read', { readManifest: async () => ({ account: 'fabric-design', port: 1 }) }),
    /STUDIO_RUNTIME_REFUSED/,
  );
  for (const port of [0, 65536, 1.5, '45117']) {
    await assert.rejects(
      () => routeUrl('read', { readManifest: async () => ({ account: 'fabric-read', port }) }),
      /STUDIO_RUNTIME_REFUSED/,
    );
  }
  await assert.rejects(() => routeUrl('admin'), /STUDIO_ROUTE_REFUSED/);
});

test('catalog fence accepts exact read/design ceilings', () => {
  for (const route of ['read', 'design']) {
    const rows = ROUTES[route].tools.map((name) => ({ name }));
    assert.equal(assertCatalog(route, rows), true);
  }
});

test('catalog fence refuses missing, extra, duplicate, malformed tools', () => {
  const exact = ROUTES.design.tools.map((name) => ({ name }));
  assert.throws(() => assertCatalog('design', exact.slice(1)), /STUDIO_CATALOG_REFUSED/);
  assert.throws(
    () => assertCatalog('design', [...exact, { name: 'start_process' }]),
    /STUDIO_CATALOG_REFUSED/,
  );
  assert.throws(
    () => assertCatalog('design', [...exact, { name: exact[0].name }]),
    /STUDIO_CATALOG_REFUSED/,
  );
  assert.throws(() => assertCatalog('design', [{ nope: true }]), /STUDIO_CATALOG_REFUSED/);
});
