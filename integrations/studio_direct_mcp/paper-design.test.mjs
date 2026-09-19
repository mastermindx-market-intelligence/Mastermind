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
    commandTimeoutMs: 5000,
    ...extra,
  };
}

function deps(execFile) {
  return {
    readFile: async () => BRIDGE,
    lstat: async () => ({ isFile: () => true, isSymbolicLink: () => false }),
    execFile,
  };
}

test('paper tools expose three reads plus one explicit mutation', () => {
  assert.deepEqual(PAPER_DESIGN_TOOLS.map((x) => x.name), [
    'paper_inspect', 'paper_catalog', 'paper_read', 'paper_edit',
  ]);
  assert.equal(PAPER_DESIGN_TOOLS[0].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[1].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[2].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.readOnlyHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.idempotentHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.destructiveHint, true);
});

test('paper config is closed, absolute and digest pinned', () => {
  assert.equal(resolvePaperDesignConfig(false), null);
  assert.throws(() => resolvePaperDesignConfig({ ...cfg(), extra: true }), /not supported/);
  assert.throws(() => resolvePaperDesignConfig({ ...cfg(), pythonPath: 'python' }), /absolute/);
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

test('bridge hash drift refuses before process dispatch', async () => {
  let calls = 0;
  const designer = createPaperDesigner(cfg(), {
    readFile: async () => Buffer.from('changed'),
    lstat: async () => ({ isFile: () => true, isSymbolicLink: () => false }),
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
