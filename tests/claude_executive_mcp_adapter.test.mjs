import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { createAdapter } from '../integrations/claude_executive_mcp/adapter.mjs';

const READ = 'mastermind.executive.read';
const COO = 'mastermind.executive.coo.act';
const CEO = 'mastermind.executive.intent.submit';
const LOCAL = 'http://127.0.0.1:8444/mcp';
const RESOURCE = 'https://executive.example.test/mcp';
const METADATA = '/.well-known/oauth-protected-resource';
const policy = { resource: RESOURCE, issuer: 'https://issuer.example.test/',
  resource_metadata_url: 'https://executive.example.test/custom-resource-metadata' };
function configuration() {
  return { policies: { read: { ...policy, required_scopes: [READ] },
    submit: { ...policy, required_scopes: [CEO, READ].sort() } },
    coo: { policy: { ...policy, required_scopes: [COO, READ].sort() } } };
}
async function listen(server) {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return server.address().port;
}
function close(server) {
  server.closeAllConnections();
  return new Promise(resolve => server.close(resolve));
}
async function fixture(t, respond) {
  const seen = [], oauth = [];
  const upstream = http.createServer((req, res) => {
    seen.push({ path: req.url, method: req.method, authorization: req.headers.authorization });
    if (respond) return respond(req, res);
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify(req.url.includes('metadata') || req.url === METADATA
      ? { resource: RESOURCE, authorization_servers: [policy.issuer], scopes_supported: [READ, CEO, COO] }
      : { upstream_path: req.url }));
  });
  const port = await listen(upstream);
  const server = createAdapter(configuration(), {
    requestExecutive(options, done) {
      assert.equal(options.host, '127.0.0.1'); assert.equal(options.port, 8443);
      return http.request({ ...options, port }, done);
    },
    async fetchOAuth(url, options) {
      oauth.push({ url: String(url), options });
      return new Response(JSON.stringify({ issuer: policy.issuer, scopes_supported: [READ, COO, CEO, 'offline_access'],
        authorization_endpoint: policy.issuer + 'authorize', token_endpoint: policy.issuer + 'oauth/token' }));
    },
  });
  await listen(server);
  t.after(async () => { await close(server); await close(upstream); });
  return { server, seen, oauth };
}
function exchange(server, path, { method = 'POST', headers = {}, body = '{}' } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port: server.address().port, path, method,
      headers: { host: '127.0.0.1:8444', 'content-type': 'application/json', ...headers } }, res => {
      const chunks = []; res.on('data', b => chunks.push(b));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, text: Buffer.concat(chunks).toString() }));
      res.on('error', reject);
    });
    req.on('error', reject); req.end(body);
  });
}

test('native MCP targets only the static COO route and forwards the unchanged bearer', async t => {
  const f = await fixture(t);
  const result = await exchange(f.server, '/mcp', { headers: { authorization: 'Bearer fixture-only' } });
  assert.equal(result.status, 200);
  assert.equal(JSON.parse(result.text).upstream_path, '/mcp/coo');
  assert.deepEqual(f.seen, [{ path: '/mcp/coo', method: 'POST', authorization: 'Bearer fixture-only' }]);
});

test('local metadata follows the installed metadata path and exposes only COO scopes', async t => {
  const f = await fixture(t);
  const result = await exchange(f.server, METADATA, { method: 'GET', body: '' });
  assert.equal(result.status, 200);
  assert.equal(f.seen[0].path, '/custom-resource-metadata');
  assert.equal(JSON.parse(result.text).resource, LOCAL);
  assert.deepEqual(JSON.parse(result.text).scopes_supported.sort(), [COO, READ].sort());
});
for (const mutation of [c => delete c.coo, c => c.coo.policy.required_scopes.push(CEO),
  c => c.coo.policy.resource = 'https://other.example.test/mcp',
  c => c.coo.policy.issuer = 'http://issuer.example.test/',
  c => c.coo.policy.resource_metadata_url = 'https://executive.example.test/mcp/coo']) {
  test('absent or incompatible role policy refuses before any listener', () => {
    const config = configuration(); mutation(config);
    assert.throws(() => createAdapter(config));
  });
}
for (const [path, method] of [['/mcp', 'GET'], ['/mcp?x=1', 'POST'], ['/x/../mcp', 'POST'],
  ['/mcp/', 'POST'], ['/mcp/coo', 'POST'], [METADATA, 'POST']]) {
  test(`literal route refuses ${method} ${path} before forwarding`, async t => {
    const f = await fixture(t); const result = await exchange(f.server, path, { method });
    assert.equal(result.status, 404); assert.equal(f.seen.length, 0);
  });
}
for (const headers of [{ host: 'attacker.example.test' }, { origin: 'https://attacker.example.test' },
  { authorization: ['Bearer one', 'Bearer two'] }]) {
  test('host, origin and duplicate bearer ambiguity refuse before forwarding', async t => {
    const f = await fixture(t); const result = await exchange(f.server, '/mcp', { headers });
    assert.ok([400, 401, 403].includes(result.status)); assert.equal(f.seen.length, 0);
  });
}
test('a missing COO upstream never falls back to the CEO endpoint', async t => {
  const f = await fixture(t, (req, res) => { res.writeHead(404); res.end('missing'); });
  const result = await exchange(f.server, '/mcp');
  assert.equal(result.status, 404); assert.deepEqual(f.seen.map(x => x.path), ['/mcp/coo']);
});
for (const scopes of [CEO, `${COO} ${READ} ${CEO}`]) {
  test('authorization request cannot request CEO authority', async t => {
    const f = await fixture(t);
    const q = new URLSearchParams({ resource: LOCAL, scope: scopes });
    const result = await exchange(f.server, '/authorize?' + q, { method: 'GET', body: '' });
    assert.equal(result.status, 400); assert.equal(result.headers.location, undefined);
    assert.equal(f.oauth.length, 0);
  });
}
test('role-correct PKCE request retains challenge, state and callback', async t => {
  const f = await fixture(t);
  const q = new URLSearchParams({ resource: LOCAL, scope: `${READ} ${COO} offline_access`,
    client_id: 'public-fixture-client', redirect_uri: 'http://localhost:8774/callback',
    state: 'fixture-state', code_challenge: 'fixture-challenge', code_challenge_method: 'S256' });
  const result = await exchange(f.server, '/authorize?' + q, { method: 'GET', body: '' });
  assert.equal(result.status, 302); const target = new URL(result.headers.location);
  assert.equal(target.origin, 'https://issuer.example.test');
  assert.equal(target.searchParams.get('resource'), RESOURCE);
  for (const key of ['client_id', 'redirect_uri', 'state', 'code_challenge', 'code_challenge_method', 'scope'])
    assert.equal(target.searchParams.get(key), q.get(key));
});
test('challenge metadata is local and a foreign role challenge is not forwarded', async t => {
  const f = await fixture(t, (_req, res) => {
    res.writeHead(401, { 'www-authenticate': `Bearer resource_metadata="${policy.resource_metadata_url}", scope="${CEO}"` });
    res.end('{"error":"unauthorized"}');
  });
  const result = await exchange(f.server, '/mcp');
  assert.equal(result.status, 502);
  assert.equal(result.headers['www-authenticate'], undefined);
  assert.ok(!result.text.includes(CEO)); assert.equal(f.seen.length, 1);
});
test('correct COO challenge retains status and translates its metadata URL', async t => {
  const f = await fixture(t, (_req, res) => {
    res.writeHead(401, { 'www-authenticate': `Bearer resource_metadata="${policy.resource_metadata_url}", scope="${COO} ${READ}"` });
    res.end('{"error":"unauthorized"}');
  });
  const result = await exchange(f.server, '/mcp');
  assert.equal(result.status, 401);
  assert.ok(result.headers['www-authenticate'].includes('http://127.0.0.1:8444' + METADATA));
  assert.ok(result.headers['www-authenticate'].includes(COO));
});
test('authorization without scope requests the installed COO set, not an IdP default', async t => {
  const f = await fixture(t);
  const result = await exchange(f.server, '/authorize?resource=' + encodeURIComponent(LOCAL), { method: 'GET', body: '' });
  assert.equal(result.status, 302);
  assert.equal(new URL(result.headers.location).searchParams.get('scope'), `${COO} ${READ}`);
});
test('refresh preserves the client-owned token and uses exactly one upstream exchange', async t => {
  const f = await fixture(t);
  const params = new URLSearchParams({ resource: LOCAL, grant_type: 'refresh_token',
    refresh_token: 'nonsecret-test-fixture', client_id: 'public-fixture-client' });
  const result = await exchange(f.server, '/oauth/token', { body: params.toString(),
    headers: { 'content-type': 'application/x-www-form-urlencoded' } });
  assert.equal(result.status, 200); assert.equal(f.oauth.length, 1);
  assert.equal(f.oauth[0].url, policy.issuer + 'oauth/token');
  const sent = new URLSearchParams(f.oauth[0].options.body);
  assert.equal(sent.get('resource'), RESOURCE);
  assert.equal(sent.get('refresh_token'), 'nonsecret-test-fixture');
  assert.equal(sent.get('client_id'), 'public-fixture-client');
  assert.equal(sent.has('scope'), false);
});
for (const body of [{ resource: 'https://foreign.example.test/mcp', scopes_supported: [COO, READ] },
  { resource: RESOURCE, scopes_supported: [READ, CEO] }]) {
  test('wrong upstream resource or absent COO scope never becomes valid metadata', async t => {
    const f = await fixture(t, (_req, res) => { res.end(JSON.stringify(body)); });
    const result = await exchange(f.server, METADATA, { method: 'GET', body: '' });
    assert.equal(result.status, 502); assert.ok(result.text.includes('invalid_upstream_metadata'));
  });
}
test('oversized metadata is refused rather than buffered without a bound', async t => {
  const f = await fixture(t, (_req, res) => { res.end(JSON.stringify({ resource: RESOURCE,
    scopes_supported: [COO, READ], padding: 'x'.repeat(150000) })); });
  const result = await exchange(f.server, METADATA, { method: 'GET', body: '' });
  assert.equal(result.status, 502);
});
test('lost upstream response makes no second send and preserves uncertainty', async t => {
  const f = await fixture(t, (req, _res) => { req.socket.destroy(); });
  const result = await exchange(f.server, '/mcp');
  assert.equal(result.status, 502);
  assert.equal(JSON.parse(result.text).effect, 'UNKNOWN');
  assert.deepEqual(f.seen.map(x => x.path), ['/mcp/coo']);
  assert.equal(f.oauth.length, 0);
});
