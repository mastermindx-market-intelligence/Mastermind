// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  KnowledgeInputError,
  MAX_FILE_BYTES,
  MAX_PREFERENCE_BYTES,
  buildProjectFileRequest,
  buildProjectPreferenceRequest,
  canonicalPublicRequest,
  publicRequestSha256,
  type KnowledgeInputErrorCode,
  type ProjectFileAddRequest,
  type ProjectKnowledgeSourceContext,
  type ProjectPreferenceSetRequest,
  type ProjectSourceCurrentFn,
} from './project-knowledge-requests';

const WORK_REF = 'WS:MMOS-K42';
const SOURCE_COMMIT = '0123456789abcdef0123456789abcdef01234567';
const BASE_REVISION = 'ab'.repeat(32);
const FILE_REQUEST_ID = 'mmos-project-file-add-' + 'ab'.repeat(20);
const PREF_REQUEST_ID = 'mmos-project-preference-set-' + 'cd'.repeat(20);
const PREF_REVISION = 'cd'.repeat(32);
const FILE_REQUEST_SCHEMA = 'mastermind.project_file_add_request.v1';
const PREFERENCE_REQUEST_SCHEMA = 'mastermind.project_preference_set_request.v1';

/** True when this jsdom build lacks File.prototype.arrayBuffer and tests stub it locally. */
let ARRAY_BUFFER_STUBBED = false;

function context(): ProjectKnowledgeSourceContext {
  return { workRef: WORK_REF, sourceCommit: SOURCE_COMMIT, baseRevision: BASE_REVISION };
}

function makeFile(content: Uint8Array | string, name = 'a.txt', type = ''): File {
  const bytes = typeof content === 'string' ? new TextEncoder().encode(content) : content;
  const owned = bytes.slice(); // exact-length buffer
  const file = new File([owned as BlobPart], name, type === '' ? {} : { type });
  if (typeof (file as unknown as Record<string, unknown>).arrayBuffer !== 'function') {
    ARRAY_BUFFER_STUBBED = true;
    Object.defineProperty(file, 'arrayBuffer', {
      configurable: true,
      value: () => Promise.resolve(owned.buffer as ArrayBuffer),
    });
  }
  return file;
}

/** Overrides the File read with a manually settled promise (deferred read). */
function deferRead(file: File, content: Uint8Array | string): { readSpy: ReturnType<typeof vi.fn>; settle: () => void } {
  const bytes = typeof content === 'string' ? new TextEncoder().encode(content) : content;
  const owned = bytes.slice();
  let deliver: (buffer: ArrayBuffer) => void = () => undefined;
  const pending = new Promise<ArrayBuffer>((resolve) => {
    deliver = (buffer) => resolve(buffer);
  });
  const readSpy = vi.fn(() => pending);
  Object.defineProperty(file, 'arrayBuffer', { configurable: true, value: readSpy });
  return { readSpy, settle: () => deliver(owned.buffer as ArrayBuffer) };
}

function currentOk(): ProjectSourceCurrentFn {
  return (snapshot) => ({ ...snapshot });
}

async function expectCode(
  action: () => unknown,
  code: KnowledgeInputErrorCode,
): Promise<KnowledgeInputError> {
  let caught: unknown;
  try {
    await action();
  } catch (error: unknown) {
    caught = error;
  }
  expect(caught, `expected KnowledgeInputError ${code}`).toBeInstanceOf(KnowledgeInputError);
  const error = caught as KnowledgeInputError;
  expect(error.code).toBe(code);
  return error;
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('constants', () => {
  it('exposes the fixed wire limits', () => {
    expect(MAX_FILE_BYTES).toBe(32768);
    expect(MAX_PREFERENCE_BYTES).toBe(2000);
  });
});

describe('buildProjectFileRequest', () => {
  it('builds the exact closed md request preserving BOM, CRLF, TAB and Unicode bytes', async () => {
    const text = '\ufeff# 标题\r\n正文行一\r\n正文行二\t结尾\n';
    const request = await buildProjectFileRequest(
      context(),
      FILE_REQUEST_ID,
      makeFile(text, 'meeting-notes.md', 'text/markdown'),
      null,
      currentOk(),
    );
    expect(request).toEqual({
      schema: FILE_REQUEST_SCHEMA,
      request_id: FILE_REQUEST_ID,
      work_ref: WORK_REF,
      source_commit: SOURCE_COMMIT,
      base_revision: BASE_REVISION,
      file: { display_name: 'meeting-notes.md', media_type: 'text/markdown', content_utf8: text },
    });
    expect(Object.keys(request).sort()).toEqual([
      'base_revision',
      'file',
      'request_id',
      'schema',
      'source_commit',
      'work_ref',
    ]);
    expect(request.file.content_utf8).toBe(text); // no trimming, no newline normalization
    expect(request.file.content_utf8.charCodeAt(0)).toBe(0xfeff); // BOM scalar preserved
    expect(request.file.content_utf8.includes('标题')).toBe(true);
  });

  it('builds the exact txt request with LF preserved and empty browser-omitted MIME', async () => {
    const text = 'plain line\nsecond line';
    const request = await buildProjectFileRequest(
      context(),
      FILE_REQUEST_ID,
      makeFile(text, 'read me.txt'),
      undefined,
      currentOk(),
    );
    expect(request.file).toEqual({
      display_name: 'read me.txt',
      media_type: 'text/plain',
      content_utf8: text,
    });
  });

  it('maps extensions case-insensitively to the exact trusted lowercase media type', async () => {
    const request = await buildProjectFileRequest(
      context(),
      FILE_REQUEST_ID,
      makeFile('body', 'Notes.TXT', 'text/plain'),
      null,
      currentOk(),
    );
    expect(request.file.media_type).toBe('text/plain');
    expect(request.file.display_name).toBe('Notes.TXT');
  });

  it('rejects path-bearing File names before reading bytes', async () => {
    for (const name of ['folder/notes.md', 'folder\\notes.txt', '../notes.md']) {
      const file=makeFile('body', name, name.endsWith('.txt')?'text/plain':'text/markdown');
      const read=vi.spyOn(file,'arrayBuffer');
      await expectCode(()=>buildProjectFileRequest(context(),FILE_REQUEST_ID,file,null,currentOk()),'INVALID_FILE');
      expect(read).not.toHaveBeenCalled();
    }
  });

  it('rejects mismatched, uppercase and non-exact MIME types', async () => {
    const current = currentOk();
    // Browsers (and jsdom) normalize the constructor type, so hostile MIME
    // values are set directly on the fixture to exercise the exact-match rule.
    const hostileType = (mimeType: string): File => {
      const file = makeFile('x', 'a.md', 'text/markdown');
      Object.defineProperty(file, 'type', { configurable: true, value: mimeType });
      return file;
    };
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, hostileType('text/plain'), null, current),
      'UNSUPPORTED_FILE_TYPE',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, hostileType('TEXT/PLAIN'), null, current),
      'UNSUPPORTED_FILE_TYPE',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, hostileType('text/markdown;charset=utf-8'), null, current),
      'UNSUPPORTED_FILE_TYPE',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, hostileType('application/json'), null, current),
      'UNSUPPORTED_FILE_TYPE',
    );
    // The empty browser-omitted type is accepted.
    const omitted = makeFile('x', 'a.md', 'text/markdown');
    Object.defineProperty(omitted, 'type', { configurable: true, value: '' });
    const request = await buildProjectFileRequest(context(), FILE_REQUEST_ID, omitted, null, current);
    expect(request.file.media_type).toBe('text/markdown');
  });

  it('rejects unsupported and missing extensions', async () => {
    const current = currentOk();
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('x', 'notes.rst', ''), null, current),
      'UNSUPPORTED_FILE_TYPE',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('x', 'README', 'text/plain'), null, current),
      'UNSUPPORTED_FILE_TYPE',
    );
  });

  it('rejects empty basenames, directory selection and non-File inputs', async () => {
    const current = currentOk();
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('x', 'folder/'), null, current),
      'INVALID_FILE',
    );
    const directoryFile = makeFile('x', 'notes.md', 'text/markdown');
    Object.defineProperty(directoryFile, 'webkitRelativePath', { configurable: true, value: 'pkg/notes.md' });
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, directoryFile, null, current),
      'INVALID_FILE',
    );
    await expectCode(() => buildProjectFileRequest(context(), FILE_REQUEST_ID, 'notes.md' as unknown as File, null, current), 'INVALID_FILE');
    await expectCode(() => buildProjectFileRequest(context(), FILE_REQUEST_ID, null as unknown as File, null, current), 'INVALID_FILE');
    await expectCode(
      () =>
        buildProjectFileRequest(
          context(),
          FILE_REQUEST_ID,
          { name: 'a.md', size: 1, type: 'text/markdown' } as unknown as File,
          null,
          current,
        ),
      'INVALID_FILE',
    );
    await expectCode(
      () =>
        buildProjectFileRequest(
          context(),
          FILE_REQUEST_ID,
          new Blob(['x']) as unknown as File,
          null,
          current,
        ),
      'INVALID_FILE',
    );
  });

  it('enforces display name rules: 128 byte edge, dots, space-only, control characters', async () => {
    const current = currentOk();
    const edgeName = 'é'.repeat(61) + '.md'; // exactly 125 UTF-8 bytes, under the limit
    const ok = await buildProjectFileRequest(
      context(),
      FILE_REQUEST_ID,
      makeFile('x', edgeName, 'text/markdown'),
      null,
      current,
    );
    expect(ok.file.display_name).toBe(edgeName);
    const longName = 'é'.repeat(64) + 'a.md'; // 129 UTF-8 bytes
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('x', longName, 'text/markdown'), null, current),
      'INVALID_FILE',
    );
    for (const bad of ['.', '..', ' ', 'a\u0001b.md']) {
      await expectCode(
        () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('x', bad, 'text/markdown'), null, current),
        'INVALID_FILE',
      );
    }
  });

  it('enforces size edges and rejects declared/actual size disagreement', async () => {
    const current = currentOk();
    const atLimit = await buildProjectFileRequest(
      context(),
      FILE_REQUEST_ID,
      makeFile('a'.repeat(MAX_FILE_BYTES), 'big.txt', 'text/plain'),
      null,
      current,
    );
    expect(atLimit.file.content_utf8.length).toBe(MAX_FILE_BYTES);

    const over = makeFile('a'.repeat(MAX_FILE_BYTES + 1), 'big.txt', 'text/plain');
    const overRead = vi.fn(() => Promise.resolve(new ArrayBuffer(0)));
    Object.defineProperty(over, 'arrayBuffer', { configurable: true, value: overRead });
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, over, null, current),
      'FILE_TOO_LARGE',
    );
    expect(overRead).not.toHaveBeenCalled(); // never read

    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('', 'empty.txt', 'text/plain'), null, current),
      'INVALID_FILE',
    );

    const mismatch = makeFile('abcde', 'm.txt', 'text/plain');
    Object.defineProperty(mismatch, 'arrayBuffer', {
      configurable: true,
      value: () => Promise.resolve(new TextEncoder().encode('abcd').buffer as ArrayBuffer),
    });
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, mismatch, null, current),
      'READ_FAILED',
    );
  });

  it('rejects invalid UTF-8, C0, C1, DEL and lone surrogates', async () => {
    const current = currentOk();
    const raw = (bytes: number[]): Uint8Array => new Uint8Array(bytes);
    const rawFile = (bytes: number[], name = 'a.txt'): File => {
      const file = makeFile(raw(bytes), name);
      // makeFile may pass the raw bytes through the jsdom Blob decoder; force exact bytes.
      Object.defineProperty(file, 'arrayBuffer', {
        configurable: true,
        value: () => Promise.resolve(raw(bytes).slice().buffer as ArrayBuffer),
      });
      return file;
    };
    await expectCode(() => buildProjectFileRequest(context(), FILE_REQUEST_ID, rawFile([0xc3, 0x28]), null, current), 'INVALID_TEXT');
    await expectCode(() => buildProjectFileRequest(context(), FILE_REQUEST_ID, rawFile([0xed, 0xa0, 0x80]), null, current), 'INVALID_TEXT');
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('a\u0000b'), null, current),
      'INVALID_TEXT',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('a\u0007b'), null, current),
      'INVALID_TEXT',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('a\u0081b'), null, current),
      'INVALID_TEXT',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('a\u007fb'), null, current),
      'INVALID_TEXT',
    );
    // A well-formed File can never decode to a lone surrogate (byte-level
    // surrogates are rejected by the fatal decoder above), so caller-supplied
    // request strings carrying one are rejected by canonical revalidation.
    await expectCode(
      () =>
        buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, 'a' + String.fromCharCode(0xd800) + 'b'),
      'INVALID_PREFERENCE',
    );
  });

  it('rejects stale source before the read with no bytes read', async () => {
    const file = makeFile('x', 'a.md', 'text/markdown');
    const { readSpy } = deferRead(file, 'x');
    const stale: ProjectSourceCurrentFn = () => {
      throw new Error('private stale detail');
    };
    const error = await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, file, null, stale),
      'SOURCE_CHANGED',
    );
    expect(error.message).not.toContain('private stale detail'); // no exception text retained
    expect(readSpy).not.toHaveBeenCalled();
  });

  it('rejects source changed after a deferred arrayBuffer read', async () => {
    const file = makeFile('x', 'a.md', 'text/markdown');
    const { readSpy, settle } = deferRead(file, 'x');
    const current = vi.fn<ProjectSourceCurrentFn>()
      .mockImplementationOnce((snapshot) => ({ ...snapshot }))
      .mockImplementationOnce((snapshot) => ({ ...snapshot, baseRevision: 'ff'.repeat(32) }));
    const pending = buildProjectFileRequest(context(), FILE_REQUEST_ID, file, null, current);
    settle();
    await expectCode(() => pending, 'SOURCE_CHANGED');
    expect(readSpy).toHaveBeenCalledTimes(1);
  });

  it('rejects a currency callback returning an unexpected shape', async () => {
    const current = vi.fn<ProjectSourceCurrentFn>().mockImplementation(() => null as unknown as ProjectKnowledgeSourceContext);
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, makeFile('x', 'a.md', 'text/markdown'), null, current),
      'SOURCE_CHANGED',
    );
  });

  it('rejects abort before the read without reading', async () => {
    const controller = new AbortController();
    controller.abort();
    const file = makeFile('x', 'a.md', 'text/markdown');
    const { readSpy } = deferRead(file, 'x');
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID, file, controller.signal, currentOk()),
      'CANCELLED',
    );
    expect(readSpy).not.toHaveBeenCalled();
  });

  it('rejects a late abort while the read is pending and produces no request', async () => {
    const controller = new AbortController();
    const file = makeFile('x', 'a.md', 'text/markdown');
    const { settle } = deferRead(file, 'x');
    const pending = buildProjectFileRequest(context(), FILE_REQUEST_ID, file, controller.signal, currentOk());
    controller.abort();
    settle();
    await expectCode(() => pending, 'CANCELLED');
  });

  it('requires a function currency callback', async () => {
    await expectCode(
      () =>
        buildProjectFileRequest(
          context(),
          FILE_REQUEST_ID,
          makeFile('x', 'a.md', 'text/markdown'),
          null,
          undefined as unknown as ProjectSourceCurrentFn,
        ),
      'INVALID_CONTEXT',
    );
  });

  it('rejects invalid request ids including trailing newlines', async () => {
    const current = currentOk();
    const file = () => makeFile('x', 'a.md', 'text/markdown');
    await expectCode(
      () => buildProjectFileRequest(context(), FILE_REQUEST_ID + '\n', file(), null, current),
      'INVALID_REQUEST_ID',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), 'mmos-project-preference-set-' + 'ab'.repeat(20), file(), null, current),
      'INVALID_REQUEST_ID',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), 'mmos-project-file-add-' + 'AB'.repeat(20), file(), null, current),
      'INVALID_REQUEST_ID',
    );
    await expectCode(
      () => buildProjectFileRequest(context(), 'mmos-project-file-add-' + 'ab'.repeat(21), file(), null, current),
      'INVALID_REQUEST_ID',
    );
    await expectCode(() => buildProjectFileRequest(context(), 42 as unknown as string, file(), null, current), 'INVALID_REQUEST_ID');
  });

  it('rejects invalid source contexts including trailing newlines', async () => {
    const current = currentOk();
    const file = () => makeFile('x', 'a.md', 'text/markdown');
    const cases: Array<Record<string, unknown>> = [
      { workRef: 'WS:MMOS-K42\n', sourceCommit: SOURCE_COMMIT, baseRevision: BASE_REVISION },
      { workRef: 'WS:A', sourceCommit: SOURCE_COMMIT, baseRevision: BASE_REVISION },
      { workRef: 'ws:mmos-k42', sourceCommit: SOURCE_COMMIT, baseRevision: BASE_REVISION },
      { workRef: WORK_REF, sourceCommit: SOURCE_COMMIT + '\n', baseRevision: BASE_REVISION },
      { workRef: WORK_REF, sourceCommit: '0123456789ABCDEF0123456789ABCDEF01234567', baseRevision: BASE_REVISION },
      { workRef: WORK_REF, sourceCommit: SOURCE_COMMIT, baseRevision: BASE_REVISION.slice(0, 63) },
      { workRef: WORK_REF, sourceCommit: SOURCE_COMMIT, baseRevision: BASE_REVISION + '\n' },
      { workRef: WORK_REF, sourceCommit: SOURCE_COMMIT, baseRevision: BASE_REVISION, extra: 1 },
    ];
    for (const bad of cases) {
      await expectCode(
        () => buildProjectFileRequest(bad as unknown as ProjectKnowledgeSourceContext, FILE_REQUEST_ID, file(), null, current),
        'INVALID_CONTEXT',
      );
    }
    await expectCode(
      () => buildProjectFileRequest([context()] as unknown as ProjectKnowledgeSourceContext, FILE_REQUEST_ID, file(), null, current),
      'INVALID_CONTEXT',
    );
    await expectCode(
      () => buildProjectFileRequest(null as unknown as ProjectKnowledgeSourceContext, FILE_REQUEST_ID, file(), null, current),
      'INVALID_CONTEXT',
    );
  });

  it('accepts a null-prototype context snapshot', async () => {
    const nullProto = Object.assign(Object.create(null), context());
    const request = await buildProjectFileRequest(
      nullProto,
      FILE_REQUEST_ID,
      makeFile('x', 'a.md', 'text/markdown'),
      null,
      currentOk(),
    );
    expect(request.work_ref).toBe(WORK_REF);
  });

  it('leaves inputs untouched and detaches the request from the File', async () => {
    const callerContext = context();
    const file = makeFile('x', 'a.md', 'text/markdown');
    const request = await buildProjectFileRequest(callerContext, FILE_REQUEST_ID, file, null, currentOk());
    callerContext.workRef = 'WS:OTHER-1'; // later caller mutation cannot affect the built request
    expect(file.name).toBe('a.md'); // original input untouched
    expect(file.size).toBe(1);
    expect(file.type).toBe('text/markdown');
    expect(request.work_ref).toBe(WORK_REF);
    expect(request.file.display_name).toBe('a.md');
    expect(request.file).toEqual({
      display_name: 'a.md',
      media_type: 'text/markdown',
      content_utf8: 'x',
    });
    expect(JSON.parse(JSON.stringify(request))).toEqual(request); // pure detached plain data
  });

  it('returns a deep-frozen request that refuses mutation', async () => {
    const request = (await buildProjectFileRequest(
      context(),
      FILE_REQUEST_ID,
      makeFile('x', 'a.md', 'text/markdown'),
      null,
      currentOk(),
    )) as ProjectFileAddRequest;
    expect(Object.isFrozen(request)).toBe(true);
    expect(Object.isFrozen(request.file)).toBe(true);
    expect(() => {
      (request as { work_ref: string }).work_ref = 'WS:EVIL-1';
    }).toThrow(TypeError);
    expect(() => {
      (request.file as { display_name: string }).display_name = 'evil.md';
    }).toThrow(TypeError);
  });

  it('never uploads, fetches, persists or reads via File.text', async () => {
    const holder = globalThis as { fetch?: unknown };
    const originalFetch = holder.fetch;
    const fetchSpy = vi.fn();
    holder.fetch = fetchSpy;
    const file = makeFile('x', 'a.md', 'text/markdown');
    const textSpy = vi.fn();
    Object.defineProperty(file, 'text', { configurable: true, value: textSpy });
    const sendBeaconSpy = vi.fn();
    const navigatorHolder = globalThis as { navigator?: { sendBeacon?: unknown } };
    const originalBeacon = navigatorHolder.navigator?.sendBeacon;
    if (navigatorHolder.navigator) navigatorHolder.navigator.sendBeacon = sendBeaconSpy;
    try {
      const request = await buildProjectFileRequest(context(), FILE_REQUEST_ID, file, null, currentOk());
      const preference = buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, 'ok');
      await publicRequestSha256(request);
      await publicRequestSha256(preference);
    } finally {
      holder.fetch = originalFetch;
      if (navigatorHolder.navigator) navigatorHolder.navigator.sendBeacon = originalBeacon;
    }
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(textSpy).not.toHaveBeenCalled();
    expect(sendBeaconSpy).not.toHaveBeenCalled();
  });
});

describe('buildProjectPreferenceRequest', () => {
  const PREFERENCE_VALUE = '沟通偏好：\n- 中文优先\n\t- 保留制表符\r\n第二段';

  it('builds the exact closed preference request with the literal ZH multiline value preserved', () => {
    const request = buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, PREFERENCE_VALUE);
    expect(request).toEqual({
      schema: PREFERENCE_REQUEST_SCHEMA,
      request_id: PREF_REQUEST_ID,
      work_ref: WORK_REF,
      source_commit: SOURCE_COMMIT,
      base_revision: BASE_REVISION,
      expected_preference_revision: null,
      value: PREFERENCE_VALUE,
    });
    expect(Object.keys(request).sort()).toEqual([
      'base_revision',
      'expected_preference_revision',
      'request_id',
      'schema',
      'source_commit',
      'value',
      'work_ref',
    ]);
    expect(Object.isFrozen(request)).toBe(true);
    expect(request.value).toBe(PREFERENCE_VALUE); // no trimming or newline normalization
  });

  it('accepts an explicit 64 lowercase hex expected preference revision', () => {
    const request = buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, PREF_REVISION, 'ok');
    expect(request.expected_preference_revision).toBe(PREF_REVISION);
  });

  it('enforces the exact 2000-byte limit on the literal value', () => {
    expect(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, '文'.repeat(666))).not.toThrow(); // 1998 bytes
    expect(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, '文'.repeat(667))).toThrow(KnowledgeInputError); // 2001 bytes
    const atLimit = buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, 'a'.repeat(MAX_PREFERENCE_BYTES));
    expect(atLimit.value.length).toBe(2000);
    expectCode(
      () => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, 'a'.repeat(MAX_PREFERENCE_BYTES + 1)),
      'INVALID_PREFERENCE',
    );
  });

  it('rejects empty, blank, control, DEL and lone surrogate values', async () => {
    await expectCode(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, ''), 'INVALID_PREFERENCE');
    await expectCode(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, '   \n\t '), 'INVALID_PREFERENCE');
    await expectCode(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, 'a\u0007b'), 'INVALID_PREFERENCE');
    await expectCode(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, 'a\u007fb'), 'INVALID_PREFERENCE');
    await expectCode(
      () => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, 'a' + String.fromCharCode(0xdfff) + 'b'),
      'INVALID_PREFERENCE',
    );
    await expectCode(
      () => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, 5 as unknown as string),
      'INVALID_PREFERENCE',
    );
  });

  it('rejects malformed expected preference revision shapes', async () => {
    await expectCode(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, 'ZZ'.repeat(32), 'ok'), 'INVALID_PREFERENCE');
    await expectCode(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, 'c'.repeat(63), 'ok'), 'INVALID_PREFERENCE');
    await expectCode(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, 'c'.repeat(65), 'ok'), 'INVALID_PREFERENCE');
    await expectCode(
      () => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, undefined as unknown as string | null, 'ok'),
      'INVALID_PREFERENCE',
    );
    await expectCode(() => buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, PREF_REVISION + '\n', 'ok'), 'INVALID_PREFERENCE');
  });
});

describe('canonicalPublicRequest and publicRequestSha256', () => {
  const PREFERENCE_VALUE = '偏好一\n偏好二';

  function preferenceRequest(): ProjectPreferenceSetRequest {
    return buildProjectPreferenceRequest(context(), PREF_REQUEST_ID, null, PREFERENCE_VALUE);
  }

  async function fileRequest(): Promise<ProjectFileAddRequest> {
    return buildProjectFileRequest(
      context(),
      FILE_REQUEST_ID,
      makeFile('\ufeff行一\r\n行二', 'notes.md', 'text/markdown'),
      null,
      currentOk(),
    );
  }

  it('emits canonical sorted-key JSON with default separators and Unicode unchanged', async () => {
    const expected = JSON.stringify({
      base_revision: BASE_REVISION,
      expected_preference_revision: null,
      request_id: PREF_REQUEST_ID,
      schema: PREFERENCE_REQUEST_SCHEMA,
      source_commit: SOURCE_COMMIT,
      value: PREFERENCE_VALUE,
      work_ref: WORK_REF,
    });
    expect(canonicalPublicRequest(preferenceRequest())).toBe(expected);
    expect(canonicalPublicRequest(preferenceRequest())).not.toContain(' '); // no spaces
    expect(canonicalPublicRequest(preferenceRequest())).toContain('偏好一');
  });

  it('matches an independently computed SHA-256 using actual WebCrypto', async () => {
    const request = await fileRequest();
    const expectedCanonical = JSON.stringify({
      base_revision: BASE_REVISION,
      file: { content_utf8: request.file.content_utf8, display_name: 'notes.md', media_type: 'text/markdown' },
      request_id: FILE_REQUEST_ID,
      schema: FILE_REQUEST_SCHEMA,
      source_commit: SOURCE_COMMIT,
      work_ref: WORK_REF,
    });
    expect(canonicalPublicRequest(request)).toBe(expectedCanonical);
    expect(await publicRequestSha256(request)).toBe(await sha256Hex(expectedCanonical));
    // Stable and detached: hashing again needs no source currency fence and matches.
    expect(await publicRequestSha256(await fileRequest())).toBe(await publicRequestSha256(request));
  });

  it('rejects hostile request inputs without invoking getters', async () => {
    const request = preferenceRequest();
    let getterHits = 0;
    const withGetter: Record<string, unknown> = { ...request };
    Object.defineProperty(withGetter, 'value', {
      enumerable: true,
      get() {
        getterHits += 1;
        return 'SERIALIZED-LEAK';
      },
    });
    await expectCode(() => canonicalPublicRequest(withGetter as unknown as ProjectPreferenceSetRequest), 'INVALID_REQUEST_ID');
    expect(getterHits).toBe(0);

    const throwingGetter: Record<string, unknown> = { ...request };
    Object.defineProperty(throwingGetter, 'value', {
      enumerable: true,
      get() {
        throw new Error('getter explosion');
      },
    });
    const error = await expectCode(
      () => canonicalPublicRequest(throwingGetter as unknown as ProjectPreferenceSetRequest),
      'INVALID_REQUEST_ID',
    );
    expect(error.message).not.toContain('getter explosion');

    class Hostile {}
    await expectCode(
      () =>
        canonicalPublicRequest(
          Object.assign(new Hostile(), request) as unknown as ProjectPreferenceSetRequest,
        ),
      'INVALID_REQUEST_ID',
    );
    await expectCode(() => canonicalPublicRequest([request] as unknown as ProjectPreferenceSetRequest), 'INVALID_REQUEST_ID');
    await expectCode(() => canonicalPublicRequest(null as unknown as ProjectPreferenceSetRequest), 'INVALID_REQUEST_ID');
    await expectCode(
      () => canonicalPublicRequest({ ...request, extra: 1 } as unknown as ProjectPreferenceSetRequest),
      'INVALID_REQUEST_ID',
    );
    await expectCode(() => canonicalPublicRequest({ ...request, schema: 'other.schema' } as unknown as ProjectPreferenceSetRequest), 'INVALID_REQUEST_ID');
    await expectCode(
      () =>
        canonicalPublicRequest({
          schema: FILE_REQUEST_SCHEMA,
          request_id: PREF_REQUEST_ID, // wrong action pairing
          work_ref: WORK_REF,
          source_commit: SOURCE_COMMIT,
          base_revision: BASE_REVISION,
          file: { display_name: 'a.md', media_type: 'text/markdown', content_utf8: 'x' },
        } as unknown as ProjectPreferenceSetRequest),
      'INVALID_REQUEST_ID',
    );
  });

  it('revalidates the closed file part: added fields, slash display names and size limits', async () => {
    const request = await fileRequest();
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          file: { ...request.file, extra: 1 },
        } as unknown as ProjectFileAddRequest),
      'INVALID_FILE',
    );
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          file: { ...request.file, display_name: 'evil/notes.md' },
        } as unknown as ProjectFileAddRequest),
      'INVALID_FILE',
    );
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          file: { ...request.file, media_type: 'application/json' },
        } as unknown as ProjectFileAddRequest),
      'UNSUPPORTED_FILE_TYPE',
    );
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          file: { ...request.file, content_utf8: 'a'.repeat(MAX_FILE_BYTES + 1) },
        } as unknown as ProjectFileAddRequest),
      'FILE_TOO_LARGE',
    );
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          file: { ...request.file, content_utf8: 'a' + String.fromCharCode(0xd800) + 'b' },
        } as unknown as ProjectFileAddRequest),
      'INVALID_TEXT',
    );
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          work_ref: 'WS:MMOS-K42\n',
        } as unknown as ProjectFileAddRequest),
      'INVALID_CONTEXT',
    );
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          source_commit: SOURCE_COMMIT.toUpperCase(),
        } as unknown as ProjectFileAddRequest),
      'INVALID_CONTEXT',
    );
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          base_revision: BASE_REVISION.slice(1),
        } as unknown as ProjectFileAddRequest),
      'INVALID_CONTEXT',
    );
    await expectCode(
      () =>
        canonicalPublicRequest({
          ...request,
          request_id: FILE_REQUEST_ID.slice(0, -1), // 39 hex
        } as unknown as ProjectFileAddRequest),
      'INVALID_REQUEST_ID',
    );
    // The module-built frozen request itself always passes revalidation.
    expect(canonicalPublicRequest(request)).toBeTypeOf('string');
  });

  it('hashes only the canonical validated request and never trusts caller strings', async () => {
    const request = preferenceRequest();
    const tampered = { ...request, value: PREFERENCE_VALUE + 'x' } as ProjectPreferenceSetRequest;
    expect(await publicRequestSha256(request)).not.toBe(await publicRequestSha256(tampered));
    expect(await publicRequestSha256(request)).toMatch(/^[0-9a-f]{64}$/);
  });
});


describe('parent native File boundary',()=>{
  it('rejects a forged File tag without reading metadata or content',async()=>{
    const read=vi.fn(async()=>new ArrayBuffer(1));let calls=0;
    const forged={name:'a.txt',size:1,type:'text/plain',arrayBuffer:read,
      get [Symbol.toStringTag](){calls++;return 'File';}};
    await expectCode(()=>buildProjectFileRequest(context(),FILE_REQUEST_ID,forged as never,null,currentOk()),'INVALID_FILE');
    expect(read).not.toHaveBeenCalled();expect(calls).toBe(0);
  });
  it('rejects a forged ArrayBuffer tag without invoking caller getters',async()=>{
    const file=makeFile('x','a.txt','text/plain');let calls=0;
    Object.defineProperty(file,'arrayBuffer',{value:async()=>({
      get [Symbol.toStringTag](){calls++;return 'ArrayBuffer';},byteLength:1,slice:()=>new ArrayBuffer(1)})});
    await expectCode(()=>buildProjectFileRequest(context(),FILE_REQUEST_ID,file,null,currentOk()),'READ_FAILED');
    expect(calls).toBe(0);
  });
});


describe('fixed input error text',()=>{
  it('does not forward a callback error message even for a typed input error',async()=>{
    const file=makeFile('x','a.txt','text/plain');
    const error=await expectCode(()=>buildProjectFileRequest(context(),FILE_REQUEST_ID,file,null,()=>{
      throw new KnowledgeInputError('SOURCE_CHANGED','private marker');
    }),'SOURCE_CHANGED');
    expect(error.message).toBe('SOURCE_CHANGED');expect(error.message).not.toContain('private marker');
    expect(new KnowledgeInputError('private marker' as never,'private marker').code).toBe('READ_FAILED');
  });
});
