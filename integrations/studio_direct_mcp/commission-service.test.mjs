import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer, request } from 'node:http';
import test from 'node:test';
import { createCommissionService, COMMISSION_ROUTE } from './commission-service.mjs';
import { canonicalJson, commissionBytes, operationKeyForCommission } from './commission-prepare.mjs';

const sha = (value) => createHash('sha256').update(value).digest('hex');
const principal = '1'.repeat(64);
const policy = { resource: 'https://mcp.mastermind-x.com/os/executive' };
const template = { workstream: 'WS:OS-Test', department: 'engineering', priority: 5, execution_profile: 'research_only' };
const args = { ...template, objective: 'Read the contract.' };
args.operation_key = operationKeyForCommission(args, principal);
const body = JSON.stringify({ arguments: args });
const bearer = 'original.signed.bearer';
const config = { release_sha: 'a'.repeat(40), base_sha: 'b'.repeat(40), policy,
  grants: [{ principal_scope: principal, template }] };

async function setup(options = {}) {
  const events = [];
  let closed = false;
  let checks = 0;
  const workspace = {
    inspect: async () => { events.push('inspect'); return { status: 'PRESENT' }; },
    acquire: async () => assert.fail('reopen must not acquire'),
    commitCommission: async () => assert.fail('reopen must not commit'),
    push: async () => assert.fail('reopen must not push'),
    commissionStatus: async () => {
      events.push('read');
      return { operation_id: args.operation_key, branch: 'sol/web-' + args.operation_key,
        local_head_sha: 'c'.repeat(40), remote_head_sha: 'c'.repeat(40), clean: true,
        commission_content_sha256: sha(commissionBytes(args, principal)) };
    },
  };
  const service = await createCommissionService({
    configurationDigest: 'd'.repeat(64), accountLabel: 'test', port: 45025,
  }, {
    readConfiguration: async () => {
      checks++;
      if (closed) throw Error('configuration drift');
      return config;
    },
    verifyFiles: async () => {},
    workspace,
    runHelper: async (_filename, input) => {
      events.push(input);
      if (options.gate) await options.gate(input);
      if (options.deny || input.bearer !== bearer) throw Error('auth refused');
      const identity = { principal_scope: principal, policy_digest: sha(canonicalJson(policy)), expires_at: 9999999999 };
      if (!input.request_body) return { ok: true, identity };
      // Canonical signed-token/parser tests exercise the actual helper separately.
      // This seam records exact raw forwarding and dispatch ordering.
      if (input.request_body === '{"arguments":{},"arguments":{}}') throw Error('duplicate member');
      return { ok: true, identity, arguments_digest: sha(canonicalJson(JSON.parse(input.request_body).arguments)) };
    },
  });
  let fallthrough = 0;
  const server = createServer((req, res) => service.middleware(req, res, () => {
    fallthrough++; res.statusCode = 418; res.end('generic');
  }));
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  async function send({ route = COMMISSION_ROUTE, method = 'POST', headers, content = body, end = true } = {}) {
    return new Promise((resolve, reject) => {
      const req = request({ host: '127.0.0.1', port: server.address().port, path: route, method,
        headers: headers ?? { authorization: 'Bearer ' + bearer, 'content-type': 'application/json' },
      }, (res) => {
        let result = '';
        res.on('data', (chunk) => { result += chunk; });
        res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: result }));
      });
      req.on('error', reject);
      if (end) req.end(content);
      else req.flushHeaders();
    });
  }
  return { events, send, service, configDrift: () => { closed = true; },
    fallthrough: () => fallthrough, checks: () => checks,
    close: async () => { await service.close(); server.closeAllConnections(); await new Promise((r) => server.close(r)); } };
}

test('fixed authenticated route forwards original bearer/raw body and only reads a published same-key commission', async () => {
  const f = await setup();
  try {
    const out = await f.send();
    assert.equal(out.status, 200);
    assert.equal(JSON.parse(out.body).status, 'prepared');
    assert.equal(out.headers['cache-control'], 'no-store');
    assert.deepEqual(f.events[0], { bearer });
    assert.deepEqual(f.events[1], { bearer, request_body: body });
    assert.equal(f.events.filter((e) => e === 'read').length, 1);
    assert.equal(f.fallthrough(), 0);
    assert.ok(f.checks() >= 4);
    assert.equal(out.body.includes(bearer), false);
  } finally { await f.close(); }
});

for (const route of [COMMISSION_ROUTE + '?x=1', COMMISSION_ROUTE + '/', '/os-internal/commission/submit']) {
  test('foreign commission route refuses before auth: ' + route, async () => {
    const f = await setup();
    try { assert.equal((await f.send({ route })).status, 404); assert.deepEqual(f.events, []); assert.equal(f.fallthrough(), 0); }
    finally { await f.close(); }
  });
}
test('generic MCP stays with its incumbent dispatcher and cannot be selected by a prepare argument', async () => {
  const f = await setup();
  try { assert.equal((await f.send({ route: '/mcp' })).status, 418); assert.deepEqual(f.events, []); }
  finally { await f.close(); }
});
for (const headers of [{}, { authorization: 'Bearer malformed' }, ['Host', '127.0.0.1', 'Authorization', 'Bearer ' + bearer, 'Authorization', 'Bearer ' + bearer]]) {
  test('missing malformed or duplicate bearer refuses without reading a body', async () => {
    const f = await setup();
    try {
      assert.equal((await f.send({ headers, end: false })).status, 401);
      assert.deepEqual(f.events, []);
    } finally { await f.close(); }
  });
}
test('denied signed bearer refuses before waiting for an unfinished body', async () => {
  const f = await setup({ deny: true });
  try { assert.equal((await f.send({ end: false })).status, 503); assert.deepEqual(f.events, [{ bearer }]); }
  finally { await f.close(); }
});
for (const content of [Buffer.from([0xff]), '{"arguments":{},"arguments":{}}', 'x'.repeat(65537)]) {
  test('invalid body never reaches workspace owner', async () => {
    const f = await setup();
    try {
      const out = await f.send({ content });
      assert.equal(out.status, 503);
      assert.equal(f.events.includes('inspect'), false);
    } finally { await f.close(); }
  });
}
test('one active operation refuses a second rather than queuing; shutdown drains first and then refuses', async () => {
  let entered, release;
  const started = new Promise((r) => { entered = r; });
  const wait = new Promise((r) => { release = r; });
  const f = await setup({ gate: async () => { entered(); await wait; } });
  try {
    const first = f.send();
    await started;
    assert.equal((await f.send()).status, 503);
    const draining = f.service.close();
    release();
    assert.equal((await first).status, 503);
    await draining;
    assert.equal((await f.send()).status, 503);
    assert.equal(f.events.includes('inspect'), false);
  } finally { release(); await f.close(); }
});
test('configuration drift refuses before any subsequent owner call', async () => {
  const f = await setup();
  try { f.configDrift(); assert.equal((await f.send()).status, 503); assert.deepEqual(f.events, []); }
  finally { await f.close(); }
});
