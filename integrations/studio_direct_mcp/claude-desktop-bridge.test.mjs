import assert from 'node:assert/strict';
import test from 'node:test';

import { assertCatalog, routeUrl, ROUTES } from './claude-desktop-bridge.mjs';

const ORIGIN = 'https://bridge.fixture.ts.net';

test('routeUrl accepts only exact HTTPS tailnet origins and fixed routes', () => {
  assert.equal(routeUrl(ORIGIN, 'read'), ORIGIN + '/studio-fabric');
  assert.equal(routeUrl(ORIGIN + '/', 'design'), ORIGIN + '/studio-design');
  for (const value of [
    'http://bridge.fixture.ts.net',
    'https://bridge.fixture.ts.net:8443',
    'https://user@bridge.fixture.ts.net',
    'https://bridge.fixture.ts.net/path',
    'https://bridge.fixture.example',
  ]) {
    assert.throws(() => routeUrl(value, 'design'), /STUDIO_ORIGIN_REFUSED/);
  }
  assert.throws(() => routeUrl(ORIGIN, 'admin'), /STUDIO_ROUTE_REFUSED/);
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
