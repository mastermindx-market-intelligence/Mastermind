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

function deps(execFile, extra = {}) {
  return {
    readFile: async () => BRIDGE,
    lstat: async () => ({ isFile: () => true, isSymbolicLink: () => false }),
    execFile,
    ...extra,
  };
}

test('paper tools expose three reads, one bounded prepare transition, and one explicit mutation', () => {
  assert.deepEqual(PAPER_DESIGN_TOOLS.map((x) => x.name), [
    'paper_inspect', 'paper_catalog', 'paper_read', 'paper_prepare', 'paper_edit',
  ]);
  assert.equal(PAPER_DESIGN_TOOLS[0].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[1].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[2].annotations.readOnlyHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.readOnlyHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.destructiveHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.idempotentHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[3].annotations.openWorldHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[4].annotations.readOnlyHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[4].annotations.idempotentHint, false);
  assert.equal(PAPER_DESIGN_TOOLS[4].annotations.destructiveHint, true);
  assert.equal(PAPER_DESIGN_TOOLS[4].annotations.openWorldHint, true);
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

test('prepare refuses arbitrary paths and URLs before any host open action', async () => {
  let opens = 0;
  const designer = createPaperDesigner(cfg(), deps(async () => ({ stdout: '{}' }), {
    paperAppPath: '/Users/test/Applications/Paper.app',
    openFile: async () => { opens += 1; },
    sleep: async () => {},
  }));
  for (const file_id of ['/tmp/file', 'https://app.paper.design/file/ABC', 'paper://file/ABC', 'abc']) {
    const result = await designer.call('paper_prepare', { file_id });
    assert.equal(result.isError, true);
    assert.equal(result.effectUnknown, false);
    assert.equal(result.value.state, 'PAPER_INVALID_FILE_ID');
  }
  assert.equal(opens, 0);
});

test('prepare is a no-op when the exact file is already active and write-admitted', async () => {
  const fileId = '01M2VWK62FA5S4VVF6G7SBPE5J';
  let opens = 0;
  const calls = [];
  const designer = createPaperDesigner(cfg(), deps(async (_cmd, argv) => {
    calls.push(argv);
    if (argv[1] === 'status') return { stdout: JSON.stringify({
      state: 'CONNECTED', server: { name: 'paper-desktop', version: '0.5.11' },
      document: {
        identity: { id: fileId },
        basic_info: { fileId, fileName: 'Refined vase', pageId: 'p-1-0', pageName: 'Page 1' },
        snapshot_sha256: 'a'.repeat(64),
        write_binding_ready: true,
      },
    }) };
    if (argv[1] === 'catalog') return { stdout: JSON.stringify({
      write_schema: { accepted_for_write: true, server_version: '0.5.11' },
    }) };
    throw new Error('unexpected call');
  }, {
    paperAppPath: '/Users/test/Applications/Paper.app',
    openFile: async () => { opens += 1; },
    sleep: async () => {},
  }));
  const result = await designer.call('paper_prepare', { file_id: fileId });
  assert.equal(result.isError, false);
  assert.equal(result.value.state, 'PAPER_READY');
  assert.equal(result.value.write_allowed, true);
  assert.equal(result.value.prepare_effect, 'already_active');
  assert.equal(result.value.document.file_id, fileId);
  assert.equal(opens, 0);
  assert.equal(calls.length, 2);
});

test('prepare opens only the host-pinned app and verifies the requested file before write readiness', async () => {
  const fileId = '01M2VWK62FA5S4VVF6G7SBPE5J';
  const other = '01M2WGNCX9475G79JRKJTCM08P';
  let statusCalls = 0;
  const opens = [];
  const designer = createPaperDesigner(cfg(), deps(async (_cmd, argv) => {
    if (argv[1] === 'status') {
      statusCalls += 1;
      const id = statusCalls === 1 ? other : fileId;
      return { stdout: JSON.stringify({
        state: 'CONNECTED', server: { name: 'paper-desktop', version: '0.5.11' },
        document: {
          identity: { id },
          basic_info: { fileId: id, fileName: id === fileId ? 'Target' : 'Other' },
          snapshot_sha256: 'b'.repeat(64),
          write_binding_ready: true,
        },
      }) };
    }
    if (argv[1] === 'catalog') return { stdout: JSON.stringify({
      write_schema: { accepted_for_write: true, server_version: '0.5.11' },
    }) };
    throw new Error('unexpected call');
  }, {
    paperAppPath: '/Users/test/Applications/Paper.app',
    openFile: async (appPath, observedFileId) => { opens.push([appPath, observedFileId]); },
    sleep: async () => {},
  }));
  const result = await designer.call('paper_prepare', { file_id: fileId });
  assert.equal(result.isError, false);
  assert.equal(result.value.state, 'PAPER_READY');
  assert.equal(result.value.prepare_effect, 'open_observed');
  assert.deepEqual(opens, [['/Users/test/Applications/Paper.app', fileId]]);
});

test('prepare preserves read access but refuses write readiness when the Paper version gate rejects', async () => {
  const fileId = '01M2WGNCX9475G79JRKJTCM08P';
  const designer = createPaperDesigner(cfg(), deps(async (_cmd, argv) => {
    if (argv[1] === 'status') return { stdout: JSON.stringify({
      state: 'CONNECTED', server: { name: 'paper-desktop', version: '0.5.9' },
      document: {
        identity: { id: fileId },
        basic_info: { fileId, fileName: 'MASTERMIND PAGES' },
        snapshot_sha256: 'c'.repeat(64),
        write_binding_ready: true,
      },
    }) };
    if (argv[1] === 'catalog') return { stdout: JSON.stringify({
      write_schema: {
        accepted_for_write: false,
        server_version: '0.5.9',
        expected_server: ['paper-desktop', '0.5.11'],
      },
    }) };
    throw new Error('unexpected call');
  }, {
    paperAppPath: '/Users/test/Applications/Paper.app',
    openFile: async () => { throw new Error('should not open'); },
    sleep: async () => {},
  }));
  const result = await designer.call('paper_prepare', { file_id: fileId });
  assert.equal(result.isError, false);
  assert.equal(result.value.state, 'PAPER_READY_READ_ONLY');
  assert.equal(result.value.write_allowed, false);
  assert.equal(result.value.write_reason, 'WRITE_ADMISSION_REFUSED');
});

test('prepare never blind-retries an unconfirmed document transition', async () => {
  const fileId = '01M2VWK62FA5S4VVF6G7SBPE5J';
  const other = '01M2WGNCX9475G79JRKJTCM08P';
  let opens = 0;
  let statusCalls = 0;
  const designer = createPaperDesigner(cfg(), deps(async (_cmd, argv) => {
    if (argv[1] === 'status') {
      statusCalls += 1;
      return { stdout: JSON.stringify({
        state: 'CONNECTED',
        document: {
          identity: { id: other },
          basic_info: { fileId: other },
          write_binding_ready: true,
        },
      }) };
    }
    throw new Error('catalog must not be called without the target file');
  }, {
    paperAppPath: '/Users/test/Applications/Paper.app',
    openFile: async () => { opens += 1; },
    sleep: async () => {},
  }));
  const result = await designer.call('paper_prepare', { file_id: fileId });
  assert.equal(result.isError, true);
  assert.equal(result.effectUnknown, false);
  assert.equal(result.value.state, 'PAPER_DOCUMENT_TRANSITION_UNCONFIRMED');
  assert.equal(result.value.retry_allowed, false);
  assert.equal(result.value.requires_inspect, true);
  assert.equal(result.value.observed_file_id, other);
  assert.equal(opens, 1);
  assert.equal(statusCalls, 4);
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

  let opens = 0;
  const guardedDesigner = createPaperDesigner(cfg(), {
    readFile: async () => Buffer.from('changed'),
    lstat: async () => ({ isFile: () => true, isSymbolicLink: () => false }),
    execFile: async () => { calls += 1; return { stdout: '{}' }; },
    paperAppPath: '/Users/test/Applications/Paper.app',
    openFile: async () => { opens += 1; },
    sleep: async () => {},
  });
  const prepare = await guardedDesigner.call('paper_prepare', {
    file_id: '01M2VWK62FA5S4VVF6G7SBPE5J',
  });
  assert.equal(prepare.value.state, 'PAPER_BRIDGE_IDENTITY_REFUSED');
  assert.equal(opens, 0);

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
