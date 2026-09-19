import test from 'node:test';
import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import { mkdtemp, writeFile, chmod, rm } from 'node:fs/promises';
import {
  MOSYLE_TOOL_NAMES,
  createMosyleClient,
  resolveMosyleConfig,
} from './mosyle.mjs';

async function fixture() {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'mosyle-test-'));
  const credentialPath = path.join(dir, 'mosyle.json');
  await writeFile(credentialPath, JSON.stringify({ accessToken: 'api-key', email: 'bot@example.com', password: 'secret' }));
  await chmod(credentialPath, 0o600);
  return { dir, credentialPath };
}

function fakeFetch(calls) {
  return async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith('/login')) {
      return { ok: true, status: 200, headers: { get: (name) => name.toLowerCase() === 'authorization' ? 'Bearer bearer-123' : null } };
    }
    return new Response(JSON.stringify({
      status: 'OK',
      response: [{ serial_number: 'SER123', device_name: 'Studio', date_last_beat: '123', secret_field: 'drop-me' }],
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
}

test('config is opt-in and pinned to absolute credential file', () => {
  assert.equal(resolveMosyleConfig(undefined), null);
  assert.throws(() => resolveMosyleConfig({ enabled: true, credentialPath: 'relative.json' }), /absolute path/);
});

test('fleet status logs in, uses bearer, bounds fields, and strips unknown response keys', async () => {
  const fx = await fixture();
  const calls = [];
  try {
    const client = createMosyleClient({ enabled: true, credentialPath: fx.credentialPath, timeoutMs: 5000 }, { fetch: fakeFetch(calls) });
    const result = await client.call('mosyle_fleet_status', { os: 'mac', page: 2, page_size: 20 });
    assert.equal(result.isError, false);
    assert.equal(result.value.state, 'OBSERVED');
    assert.deepEqual(result.value.devices, [{ serial_number: 'SER123', device_name: 'Studio', date_last_beat: '123' }]);
    assert.equal(calls.length, 2);
    const loginBody = JSON.parse(calls[0].init.body);
    assert.equal(loginBody.accessToken, 'api-key');
    const listBody = JSON.parse(calls[1].init.body);
    assert.equal(listBody.options.os, 'mac');
    assert.equal(listBody.options.page, 2);
    assert.equal(listBody.options.page_size, 20);
    assert.equal(calls[1].init.headers.Authorization, 'Bearer bearer-123');
  } finally { await rm(fx.dir, { recursive: true, force: true }); }
});

test('device status filters by exact serial and reuses cached bearer token', async () => {
  const fx = await fixture();
  const calls = [];
  try {
    const client = createMosyleClient({ enabled: true, credentialPath: fx.credentialPath }, { fetch: fakeFetch(calls) });
    const first = await client.call('mosyle_device_status', { serial_number: 'SER123', os: 'mac' });
    const second = await client.call('mosyle_device_status', { serial_number: 'SER123', os: 'mac' });
    assert.equal(first.value.device.serial_number, 'SER123');
    assert.equal(second.value.device.serial_number, 'SER123');
    assert.equal(calls.filter((c) => c.url.endsWith('/login')).length, 1);
    const body = JSON.parse(calls[1].init.body);
    assert.deepEqual(body.options.serial_numbers, ['SER123']);
  } finally { await rm(fx.dir, { recursive: true, force: true }); }
});

test('credential permissions fail closed', async () => {
  const fx = await fixture();
  try {
    await chmod(fx.credentialPath, 0o644);
    const client = createMosyleClient({ enabled: true, credentialPath: fx.credentialPath }, { fetch: fakeFetch([]) });
    const result = await client.call('mosyle_fleet_status', {});
    assert.equal(result.isError, true);
    assert.equal(result.value.state, 'MOSYLE_READ_FAILED');
    assert.equal(result.value.reason, 'MOSYLE_CREDENTIAL_MODE_REFUSED');
  } finally { await rm(fx.dir, { recursive: true, force: true }); }
});

test('only two read-only tool names are exported', () => {
  assert.deepEqual([...MOSYLE_TOOL_NAMES].sort(), ['mosyle_device_status', 'mosyle_fleet_status']);
});
