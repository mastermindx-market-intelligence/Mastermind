import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';

import {
  PAPER_DESIGN_TOOLS,
  createPaperDesigner,
  paperToolResult,
  resolvePaperDesignConfig,
} from './paper-design.mjs';

const BRIDGE = Buffer.from('paper bridge exact bytes');
const BRIDGE_SHA = createHash('sha256').update(BRIDGE).digest('hex');

function cfg(extra = {}) {
  return {
    enabled: true,
    pythonPath: '/opt/paper/python',
    bridgePath: '/opt/paper/bridge.py',
    bridgeSha256: BRIDGE_SHA,
    appPath: '/Applications/Paper.app',
    commandTimeoutMs: 5000,
    ...extra,
  };
}

function deps(execFile) {
  return {
    readFile: async () => BRIDGE,
    lstat: async () => ({ isFile: () => true, isDirectory: () => true, isSymbolicLink: () => false }),
    execFile,
  };
}

test('paper tools expose discovery, bounded prepare, reads and one explicit content mutation', () => {
  assert.deepEqual(PAPER_DESIGN_TOOLS.map((x) => x.name), [
    'paper_inspect', 'paper_catalog', 'paper_read', 'paper_prepare', 'paper_edit',
  ]);
  assert.equal(PAPER_DESIGN_TOOLS[0].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[1].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[2].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.readOnlyHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.destructiveHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.idempotentHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[4].annotations.readOnlyHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[4].annotations.idempotentHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[4].annotations.destructiveHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[4].annotations.openWorldHint, true);
});

test('paper config is closed, absolute and digest pinned', () => {
  assert.equal(resolvePaperDesignConfig(false), null);
  assert.throws(() => resolvePaperDesignConfig({ ...cfg(), extra: true }), /not supported/);
  assert.throws(() => resolvePaperDesignConfig({ ...cfg(), pythonPath: 'python' }), /absolute/);
  assert.throws(() => resolvePaperDesignConfig({ ...cfg(), appPath: 'Paper.app' }), /absolute/);
  assert.throws(() => resolvePaperDesignConfig({ ...cfg(), bridgeSha256: 'bad' }), /SHA-256/);
  assert.equal(resolvePaperDesignConfig(cfg()).bridgeSha256, BRIDGE_SHA);
});

test('inspect dispatches exact bridge status without shell or caller path', async () => {
  const calls = [];
  const designer = createPaperDesigner(cfg(), deps(async (...args) => {
    calls.push(args);
    return { stdout: JSON.stringify({ state: 'CONNECTED', document: { snapshot_sha256: 'a'.repeat(64) } }) };
  }));
  const result = await designer.call('paper_inspect', {});
  assert.equal(result.isError, false);
  assert.equal(result.effectUnknown, false);
  assert.deepEqual(calls[0][0], '/opt/paper/python');
  assert.deepEqual(calls[0][1], ['/opt/paper/bridge.py', 'status']);
  assert.equal(calls[0][2].shell, undefined);
});

test('read sends only normalized tool arguments and optional snapshot', async () => {
  const calls = [];
  const designer = createPaperDesigner(cfg(), deps(async (...args) => {
    calls.push(args);
    return { stdout: JSON.stringify({ state: 'OBSERVED', result: { content: [] } }) };
  }));
  const snap = 'b'.repeat(64);
  const result = await designer.call('paper_read', {
    tool: 'get_jsx',
    arguments: { fileId: 'FILE', nodeId: '1-0' },
    expected_snapshot: snap,
  });
  assert.equal(result.isError, false);
  assert.deepEqual(calls[0][1], [
    '/opt/paper/bridge.py', 'read', '--tool', 'get_jsx',
    '--arguments', '{"fileId":"FILE","nodeId":"1-0"}',
    '--expected-snapshot', snap,
  ]);
});

test('prepare skips desktop launch when exact file is already active and returns write readiness', async () => {
  const fileId = '01M2WGNCX9475G79JRKJTCM08P';
  const snap = '1'.repeat(64);
  const calls = [];
  let opens = 0;
  const designer = createPaperDesigner(cfg(), {
    ...deps(async (...args) => {
      calls.push(args[1][1]);
      if (args[1][1] === 'status') {
        return { stdout: JSON.stringify({
          state: 'CONNECTED', server: { name: 'paper-desktop', version: '0.5.11' },
          document: { identity: { kind: 'file-id', id: fileId }, snapshot_sha256: snap },
        }) };
      }
      return { stdout: JSON.stringify({
        server: { name: 'paper-desktop', version: '0.5.11' },
        write_schema: { accepted_for_write: true },
      }) };
    }),
    openFile: async () => { opens += 1; },
    sleep: async () => {},
  });
  const result = await designer.call('paper_prepare', { file_id: fileId });
  assert.equal(result.isError, false);
  assert.equal(result.effectUnknown, false);
  assert.equal(result.value.state, 'PAPER_READY');
  assert.equal(result.value.snapshot_sha256, snap);
  assert.equal(result.value.write_qualified, true);
  assert.equal(result.value.already_active, true);
  assert.equal(result.value.app_open_attempted, false);
  assert.equal(opens, 0);
  assert.deepEqual(calls, ['status', 'catalog']);
});

test('prepare opens only the host-pinned app and returns read-only when write schema is not admitted', async () => {
  const oldFile = '01M2VWK62FA5S4VVF6G7SBPE5J';
  const fileId = '01M2WGNCX9475G79JRKJTCM08P';
  const snap = '2'.repeat(64);
  let statusCount = 0;
  const opens = [];
  const designer = createPaperDesigner(cfg(), {
    ...deps(async (...args) => {
      const action = args[1][1];
      if (action === 'status') {
        statusCount += 1;
        const current = statusCount === 1 ? oldFile : fileId;
        return { stdout: JSON.stringify({
          state: 'CONNECTED', server: { name: 'paper-desktop', version: '0.5.11' },
          document: { identity: { kind: 'file-id', id: current }, snapshot_sha256: snap },
        }) };
      }
      return { stdout: JSON.stringify({
        server: { name: 'paper-desktop', version: '0.5.11' },
        write_schema: { accepted_for_write: false, expected_server: ['paper-desktop', '0.5.11'] },
      }) };
    }),
    openFile: async (...args) => { opens.push(args); },
    sleep: async () => {},
  });
  const result = await designer.call('paper_prepare', { file_id: fileId });
  assert.equal(result.isError, false);
  assert.equal(result.value.state, 'PAPER_READY_READ_ONLY');
  assert.equal(result.value.write_qualified, false);
  assert.equal(result.value.already_active, false);
  assert.equal(result.value.app_open_attempted, true);
  assert.equal(result.value.concurrency_rule, 'ONE_WRITER_PER_FILE_ACROSS_HOSTS');
  assert.deepEqual(opens, [['/Applications/Paper.app', fileId]]);
});

test('prepare refuses untrusted app identity and non-openable bridge failures before desktop effect', async () => {
  const fileId = '01M2WGNCX9475G79JRKJTCM08P';
  let opens = 0;
  let lstatCalls = 0;
  const badApp = createPaperDesigner(cfg(), {
    readFile: async () => BRIDGE,
    lstat: async (target) => {
      lstatCalls += 1;
      if (target === '/Applications/Paper.app') {
        return { isFile: () => false, isDirectory: () => false, isSymbolicLink: () => true };
      }
      return { isFile: () => true, isDirectory: () => false, isSymbolicLink: () => false };
    },
    execFile: async () => ({ stdout: JSON.stringify({ state: 'UPSTREAM_UNAVAILABLE', retry_allowed: false }) }),
    openFile: async () => { opens += 1; },
    sleep: async () => {},
  });
  const appResult = await badApp.call('paper_prepare', { file_id: fileId });
  assert.equal(appResult.value.state, 'PAPER_APP_IDENTITY_REFUSED');
  assert.equal(appResult.effectUnknown, false);
  assert.equal(opens, 0);
  assert.equal(lstatCalls, 2);

  opens = 0;
  const badBridge = createPaperDesigner(cfg(), {
    readFile: async () => Buffer.from('wrong bridge'),
    lstat: async () => ({ isFile: () => true, isDirectory: () => true, isSymbolicLink: () => false }),
    execFile: async () => { throw new Error('must not dispatch'); },
    openFile: async () => { opens += 1; },
    sleep: async () => {},
  });
  const bridgeResult = await badBridge.call('paper_prepare', { file_id: fileId });
  assert.equal(bridgeResult.value.state, 'PAPER_BRIDGE_IDENTITY_REFUSED');
  assert.equal(bridgeResult.effectUnknown, false);
  assert.equal(opens, 0);
});

test('prepare rejects malformed or widened targets before desktop or bridge activity', async () => {
  let bridgeCalls = 0;
  let opens = 0;
  const designer = createPaperDesigner(cfg(), {
    ...deps(async () => { bridgeCalls += 1; return { stdout: '{}' }; }),
    openFile: async () => { opens += 1; },
    sleep: async () => {},
  });
  for (const input of [
    { file_id: '../../Paper.app' },
    { file_id: '01M2WGNCX9475G79JRKJTCM08P', appPath: '/tmp/evil.app' },
    {},
  ]) {
    const result = await designer.call('paper_prepare', input);
    assert.equal(result.value.state, 'PAPER_INVALID_ARGUMENTS');
    assert.equal(result.effectUnknown, false);
  }
  assert.equal(bridgeCalls, 0);
  assert.equal(opens, 0);
});

test('prepare reconciles a lost open reply but fails closed when the exact target never appears', async () => {
  const fileId = '01M2WGNCX9475G79JRKJTCM08P';
  const other = '01M2VWK62FA5S4VVF6G7SBPE5J';
  let opens = 0;
  let bridgeCalls = 0;
  const designer = createPaperDesigner(cfg(), {
    ...deps(async (...args) => {
      bridgeCalls += 1;
      assert.equal(args[1][1], 'status');
      return { stdout: JSON.stringify({
        state: 'CONNECTED',
        document: { identity: { kind: 'file-id', id: other }, snapshot_sha256: '3'.repeat(64) },
      }) };
    }),
    openFile: async () => { opens += 1; throw new Error('lost open reply'); },
    sleep: async () => {},
  });
  const result = await designer.call('paper_prepare', { file_id: fileId });
  assert.equal(result.isError, true);
  assert.equal(result.effectUnknown, true);
  assert.equal(result.value.state, 'PAPER_DOCUMENT_TRANSITION_UNCONFIRMED');
  assert.equal(result.value.retry_allowed, false);
  assert.equal(opens, 1);
  assert.equal(bridgeCalls, 13);
});

test('edit requires snapshot and operation identity before any child process', async () => {
  let calls = 0;
  const designer = createPaperDesigner(cfg(), deps(async () => {
    calls += 1;
    return { stdout: '{}' };
  }));
  const bad = await designer.call('paper_edit', { tool: 'write_html', arguments: {} });
  assert.equal(bad.isError, true);
  assert.equal(bad.effectUnknown, false);
  assert.equal(bad.value.state, 'PAPER_INVALID_ARGUMENTS');
  assert.equal(calls, 0);
});

test('edit dispatches once and preserves adapter effect unknown', async () => {
  let calls = 0;
  const designer = createPaperDesigner(cfg(), deps(async () => {
    calls += 1;
    const err = new Error('bridge exit 2');
    err.stdout = JSON.stringify({
      state: 'EFFECT_UNKNOWN',
      operation_id: 'paper-op-1',
      retry_allowed: false,
    });
    throw err;
  }));
  const result = await designer.call('paper_edit', {
    tool: 'write_html',
    arguments: { fileId: 'FILE', html: '<div />' },
    expected_snapshot: 'c'.repeat(64),
    operation_id: 'paper-op-1',
  });
  assert.equal(calls, 1);
  assert.equal(result.isError, true);
  assert.equal(result.effectUnknown, true);
  assert.equal(result.value.retry_allowed, false);
});

test('lost edit subprocess result becomes effect unknown while lost read stays definite local failure', async () => {
  const failed = async () => {
    const err = new Error('lost');
    err.killed = true;
    throw err;
  };
  const designer = createPaperDesigner(cfg(), deps(failed));
  const edit = await designer.call('paper_edit', {
    tool: 'write_html',
    arguments: { fileId: 'FILE' },
    expected_snapshot: 'd'.repeat(64),
    operation_id: 'paper-op-2',
  });
  assert.equal(edit.effectUnknown, true);
  assert.equal(edit.value.state, 'EFFECT_UNKNOWN');

  const read = await designer.call('paper_read', { tool: 'get_jsx', arguments: {} });
  assert.equal(read.effectUnknown, false);
  assert.equal(read.value.state, 'PAPER_LOCAL_TIMEOUT');
});

test('edit spawn refusal before child execution is definite no effect', async () => {
  let calls = 0;
  const designer = createPaperDesigner(cfg(), deps(async () => {
    calls += 1;
    const err = new Error('spawn ENOENT');
    err.code = 'ENOENT';
    throw err;
  }));
  const edit = await designer.call('paper_edit', {
    tool: 'write_html',
    arguments: { fileId: 'FILE', html: '<div />' },
    expected_snapshot: 'e'.repeat(64),
    operation_id: 'paper-spawn-refusal',
  });
  assert.equal(calls, 1);
  assert.equal(edit.isError, true);
  assert.equal(edit.effectUnknown, false);
  assert.equal(edit.value.state, 'PAPER_LOCAL_SPAWN_REFUSED');
  assert.equal(edit.value.retry_allowed, false);
});

test('bridge hash drift refuses before process dispatch', async () => {
  let calls = 0;
  const designer = createPaperDesigner(cfg(), {
    readFile: async () => Buffer.from('changed'),
    lstat: async () => ({ isFile: () => true, isDirectory: () => true, isSymbolicLink: () => false }),
    execFile: async () => {
      calls += 1;
      return { stdout: '{}' };
    },
  });
  const result = await designer.call('paper_inspect', {});
  assert.equal(result.value.state, 'PAPER_BRIDGE_IDENTITY_REFUSED');
  assert.equal(result.effectUnknown, false);
  assert.equal(calls, 0);

  const edit = await designer.call('paper_edit', {
    tool: 'write_html',
    arguments: { fileId: 'FILE', html: '<div />' },
    expected_snapshot: 'e'.repeat(64),
    operation_id: 'paper-hash-drift-edit',
  });
  assert.equal(edit.value.state, 'PAPER_BRIDGE_IDENTITY_REFUSED');
  assert.equal(edit.effectUnknown, false);
  assert.equal(calls, 0);
});

test('oversized arguments refuse before process dispatch without effect ambiguity', async () => {
  let calls = 0;
  const designer = createPaperDesigner(cfg(), deps(async () => {
    calls += 1;
    return { stdout: '{}' };
  }));
  const huge = { fileId: 'FILE', html: 'x'.repeat((1 << 19) + 32) };
  const edit = await designer.call('paper_edit', {
    tool: 'write_html',
    arguments: huge,
    expected_snapshot: 'f'.repeat(64),
    operation_id: 'paper-oversized-edit',
  });
  assert.equal(edit.value.state, 'PAPER_INVALID_ARGUMENTS');
  assert.equal(edit.effectUnknown, false);
  assert.equal(calls, 0);
});

test('image payloads stay native MCP images and are removed from text receipt', () => {
  const result = paperToolResult({
    state: 'OBSERVED',
    result: {
      content: [
        { type: 'text', text: 'ok' },
        { type: 'image', mimeType: 'image/jpeg', data: 'aGVsbG8=' },
      ],
    },
  });
  assert.equal(result.isError, false);
  assert.equal(result.content.length, 2);
  assert.equal(result.content[1].type, 'image');
  assert.equal(result.content[1].data, 'aGVsbG8=');
  const receipt = JSON.parse(result.content[0].text);
  assert.equal(receipt.result.content[1].data, undefined);
  assert.equal(receipt.result.content[1].rendered_as_mcp_image, true);
});
