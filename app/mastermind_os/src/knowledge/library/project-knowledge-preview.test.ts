import { describe, expect, it } from 'vitest';
import {
  type ProjectFileAddRequest,
  type ProjectPreferenceSetRequest,
} from './project-knowledge-requests';
import {
  PROJECT_KNOWLEDGE_ORIGINAL_INPUT_SCHEMA,
  PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE,
  PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD,
  PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES,
  PROJECT_KNOWLEDGE_PREFERENCE_VALUE_MAX_UTF8_BYTES,
  PROJECT_KNOWLEDGE_PREVIEW_SCHEMA,
  PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA,
  decodeProjectKnowledgePreview,
  projectKnowledgePreviewCanonicalUtf8Bytes,
  type ProjectKnowledgePreparedPreview,
} from './project-knowledge-preview';

const FILE_REQUEST_SCHEMA='mastermind.project_file_add_request.v1';
const PREFERENCE_REQUEST_SCHEMA='mastermind.project_preference_set_request.v1';
const WORK_REF = 'WS:PROPHET-US';
const WORK_REF_KEY = 'PROPHET-US';
const REQUEST_ID = 'mmos-project-file-add-'+'a'.repeat(40);
const PREF_REQUEST_ID='mmos-project-preference-set-'+'b'.repeat(40);
const SOURCE_COMMIT = 'dd9671026f0547c69f3fb30e5d897538272912a7';
const BASE_REVISION = '9089d60a0e9b3ce0a59b2c60f77c4a3f77a5f9101808e3cb8d5e6fe6d8392f13';
const PREFERENCE_REVISION = '55d0c1e49a2b8f07b6c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1';
const PRINCIPAL_SCOPE = 'ef'.repeat(32);
const PUBLIC_REQUEST_SHA256 = 'ab'.repeat(32);
const OTHER_SHA256 = '90'.repeat(32);
const RECIPE_FINGERPRINT_SHA256 = 'cd'.repeat(32);
const INPUT_REF_SHA256 = '19'.repeat(32);
const ARTIFACT_SHA256 = '22'.repeat(32);
const PAYLOAD_SHA256 = '33'.repeat(32);
const WORKSTREAM_SHA256 = '726c6e67a0cb30b222a769d16c6fc9f875dca7482a4fd55f2a5611299c932346';
const PROJECT_FILE_SHA256 = 'e3379aa112115365ec88766d2a004546049c9bdf257d8b8dbc2445aa2e51c105';
const DECISION_SHA256 = '44'.repeat(32);
const DISPLAY_NAME = 'notes.md';
const CONTENT_UTF8 = '# notes\n\n中文 body line.\r\n第二段。\n';
const PREF_VALUE = '以后请用中文写周报。\r\n以下周报默认中文。';
const WORKSTREAM_PATH = `agentos/workstreams/WS-${WORK_REF_KEY}.md`;
const PROJECT_FILE_PATH = `agentos/project-files/WS-${WORK_REF_KEY}/${PROJECT_FILE_SHA256}.md`;
const DECISION_PATH = `agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-${WORK_REF_KEY}.md`;

/** TextEncoder UTF-8 byte length, mirroring the owner's size_bytes math. */
function utf8Length(text: string): number {
  return new TextEncoder().encode(text).length;
}

const CONTENT_BYTES = utf8Length(CONTENT_UTF8);

type FileOverrides = {
  display_name?: string;
  media_type?: 'text/markdown' | 'text/plain';
  content_utf8?: string;
};

function fileRequest(overrides: FileOverrides = {}): ProjectFileAddRequest {
  return {
    schema: FILE_REQUEST_SCHEMA,
    request_id: REQUEST_ID,
    work_ref: WORK_REF,
    source_commit: SOURCE_COMMIT,
    base_revision: BASE_REVISION,
    file: {
      display_name: DISPLAY_NAME,
      media_type: 'text/markdown',
      content_utf8: CONTENT_UTF8,
      ...overrides,
    },
  };
}

function prefRequest(
  overrides: { value?: string; expected_preference_revision?: string | null } = {},
): ProjectPreferenceSetRequest {
  return {
    schema: PREFERENCE_REQUEST_SCHEMA,
    request_id: PREF_REQUEST_ID,
    work_ref: WORK_REF,
    source_commit: SOURCE_COMMIT,
    base_revision: BASE_REVISION,
    expected_preference_revision: PREFERENCE_REVISION,
    value: PREF_VALUE,
    ...overrides,
  };
}

function witness(): Record<string, unknown> {
  return {
    original_input: {
      schema: PROJECT_KNOWLEDGE_ORIGINAL_INPUT_SCHEMA,
      input_ref: `terminal-input:${INPUT_REF_SHA256}`,
      artifact_sha256: ARTIFACT_SHA256,
      payload_sha256: PAYLOAD_SHA256,
    },
    recipe_fingerprint_sha256: RECIPE_FINGERPRINT_SHA256,
  };
}

function fileRaw(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema: PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA,
    selection: {
      action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD,
      request_id: REQUEST_ID,
      work_ref: WORK_REF,
    },
    owner_context: { principal_scope: PRINCIPAL_SCOPE },
    request_sha256: PUBLIC_REQUEST_SHA256,
    recipe_fingerprint_sha256: RECIPE_FINGERPRINT_SHA256,
    preview_witness: witness(),
    preview: {
      schema: PROJECT_KNOWLEDGE_PREVIEW_SCHEMA,
      state: 'DRAFT_ONLY',
      action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD,
      work_ref: WORK_REF,
      source_commit: SOURCE_COMMIT,
      change: { kind: 'FILE_ADD', display_name: DISPLAY_NAME, size_bytes: CONTENT_BYTES },
      postimages: [
        {
          path: WORKSTREAM_PATH,
          content_sha256: WORKSTREAM_SHA256,
          expected_preimage_sha256: BASE_REVISION,
        },
        {
          path: PROJECT_FILE_PATH,
          content_sha256: PROJECT_FILE_SHA256,
          expected_preimage_sha256: null,
        },
      ],
    },
    ...overrides,
  };
}

function prefRaw(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema: PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA,
    selection: {
      action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE,
      request_id: PREF_REQUEST_ID,
      work_ref: WORK_REF,
    },
    owner_context: { principal_scope: PRINCIPAL_SCOPE },
    request_sha256: PUBLIC_REQUEST_SHA256,
    recipe_fingerprint_sha256: RECIPE_FINGERPRINT_SHA256,
    preview_witness: witness(),
    preview: {
      schema: PROJECT_KNOWLEDGE_PREVIEW_SCHEMA,
      state: 'DRAFT_ONLY',
      action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE,
      work_ref: WORK_REF,
      source_commit: SOURCE_COMMIT,
      change: { kind: 'COMMUNICATION_PREFERENCE', value: PREF_VALUE },
      postimages: [
        {
          path: WORKSTREAM_PATH,
          content_sha256: WORKSTREAM_SHA256,
          expected_preimage_sha256: BASE_REVISION,
        },
        {
          path: DECISION_PATH,
          content_sha256: DECISION_SHA256,
          expected_preimage_sha256: PREFERENCE_REVISION,
        },
      ],
    },
    ...overrides,
  };
}

/** Overwrites one nested field of a mutable fixture. */
function setField(target: object, path: readonly (string | number)[], value: unknown): void {
  let node = target as Record<string, unknown>;
  const walk = path.slice(0, -1);
  for (const key of walk) {
    node = node[String(key)] as Record<string, unknown>;
  }
  node[String(path[walk.length])] = value;
}

/** Removes one nested key of a mutable fixture. */
function dropIn(target: object, path: readonly (string | number)[]): void {
  let node = target as Record<string, unknown>;
  const walk = path.slice(0, -1);
  for (const key of walk) {
    node = node[String(key)] as Record<string, unknown>;
  }
  delete node[String(path[walk.length])];
}

/** Reads one nested field of a mutable fixture. */
function readIn(root: unknown, path: readonly (string | number)[]): unknown {
  let node: unknown = root;
  for (const key of path) {
    if (node === null || typeof node !== 'object') {
      return undefined;
    }
    node = (node as Record<string, unknown>)[String(key)];
  }
  return node;
}

const decode = decodeProjectKnowledgePreview;

function expectedFilePreview(): ProjectKnowledgePreparedPreview {
  return {
    schema: PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA,
    selection: {
      action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD,
      request_id: REQUEST_ID,
      work_ref: WORK_REF,
    },
    owner_context: { principal_scope: PRINCIPAL_SCOPE },
    request_sha256: PUBLIC_REQUEST_SHA256,
    recipe_fingerprint_sha256: RECIPE_FINGERPRINT_SHA256,
    preview_witness: {
      original_input: {
        schema: PROJECT_KNOWLEDGE_ORIGINAL_INPUT_SCHEMA,
        input_ref: `terminal-input:${INPUT_REF_SHA256}`,
        artifact_sha256: ARTIFACT_SHA256,
        payload_sha256: PAYLOAD_SHA256,
      },
      recipe_fingerprint_sha256: RECIPE_FINGERPRINT_SHA256,
    },
    preview: {
      schema: PROJECT_KNOWLEDGE_PREVIEW_SCHEMA,
      state: 'DRAFT_ONLY',
      action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD,
      work_ref: WORK_REF,
      source_commit: SOURCE_COMMIT,
      change: { kind: 'FILE_ADD', display_name: DISPLAY_NAME, size_bytes: CONTENT_BYTES },
      postimages: [
        {
          path: WORKSTREAM_PATH,
          content_sha256: WORKSTREAM_SHA256,
          expected_preimage_sha256: BASE_REVISION,
        },
        {
          path: PROJECT_FILE_PATH,
          content_sha256: PROJECT_FILE_SHA256,
          expected_preimage_sha256: null,
        },
      ],
    },
  };
}

function expectedPrefPreview(value: string, revision: string | null): ProjectKnowledgePreparedPreview {
  return {
    schema: PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA,
    selection: {
      action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE,
      request_id: PREF_REQUEST_ID,
      work_ref: WORK_REF,
    },
    owner_context: { principal_scope: PRINCIPAL_SCOPE },
    request_sha256: PUBLIC_REQUEST_SHA256,
    recipe_fingerprint_sha256: RECIPE_FINGERPRINT_SHA256,
    preview_witness: {
      original_input: {
        schema: PROJECT_KNOWLEDGE_ORIGINAL_INPUT_SCHEMA,
        input_ref: `terminal-input:${INPUT_REF_SHA256}`,
        artifact_sha256: ARTIFACT_SHA256,
        payload_sha256: PAYLOAD_SHA256,
      },
      recipe_fingerprint_sha256: RECIPE_FINGERPRINT_SHA256,
    },
    preview: {
      schema: PROJECT_KNOWLEDGE_PREVIEW_SCHEMA,
      state: 'DRAFT_ONLY',
      action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE,
      work_ref: WORK_REF,
      source_commit: SOURCE_COMMIT,
      change: { kind: 'COMMUNICATION_PREFERENCE', value },
      postimages: [
        {
          path: WORKSTREAM_PATH,
          content_sha256: WORKSTREAM_SHA256,
          expected_preimage_sha256: BASE_REVISION,
        },
        {
          path: DECISION_PATH,
          content_sha256: DECISION_SHA256,
          expected_preimage_sha256: revision,
        },
      ],
    },
  };
}

describe('project file add previews', () => {
  it('decodes the exact FILE_ADD wrapper into the detached frozen DTO', () => {
    const decoded = decode(fileRaw(), fileRequest(), PUBLIC_REQUEST_SHA256);
    expect(decoded).toStrictEqual(expectedFilePreview());
    expect(projectKnowledgePreviewCanonicalUtf8Bytes(decoded)).not.toBeNull();
    const bytes = projectKnowledgePreviewCanonicalUtf8Bytes(decoded) as number;
    expect(bytes <= PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES).toBe(true);
  });

  it('keeps every level deeply frozen', () => {
    const decoded = decode(fileRaw(), fileRequest(), PUBLIC_REQUEST_SHA256) as ProjectKnowledgePreparedPreview;
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded.selection)).toBe(true);
    expect(Object.isFrozen(decoded.owner_context)).toBe(true);
    expect(Object.isFrozen(decoded.preview_witness)).toBe(true);
    expect(Object.isFrozen(decoded.preview_witness.original_input)).toBe(true);
    expect(Object.isFrozen(decoded.preview)).toBe(true);
    expect(Object.isFrozen(decoded.preview.change)).toBe(true);
    expect(Object.isFrozen(decoded.preview.postimages)).toBe(true);
    expect(Object.isFrozen(decoded.preview.postimages[0] ?? null)).toBe(true);
    expect(Object.isFrozen(decoded.preview.postimages[1] ?? null)).toBe(true);
  });

  it('pairs the text/plain media type with the .txt project file extension', () => {
    const request = fileRequest({ media_type: 'text/plain', content_utf8: 'plain body' });
    const raw = fileRaw();
    setField(raw, ['preview', 'change', 'size_bytes'], utf8Length('plain body'));
    setField(raw, ['preview', 'postimages', 1, 'path'], PROJECT_FILE_PATH.slice(0, -3) + '.txt');
    const decoded = decode(raw, request, PUBLIC_REQUEST_SHA256);
    expect(decoded).not.toBeNull();
    const postimages = (decoded as ProjectKnowledgePreparedPreview).preview.postimages;
    expect(postimages[1]?.path).toBe(
      `agentos/project-files/WS-${WORK_REF_KEY}/${PROJECT_FILE_SHA256}.txt`,
    );
  });

  it('preserves CJK display names verbatim', () => {
    const cjkName = '记录-中文.md';
    const request = fileRequest({ display_name: cjkName });
    const raw = fileRaw();
    setField(raw, ['preview', 'change', 'display_name'], cjkName);
    const decoded = decode(raw, request, PUBLIC_REQUEST_SHA256) as ProjectKnowledgePreparedPreview;
    const change = decoded.preview.change;
    expect(change.kind === 'FILE_ADD' ? change.display_name : null).toBe(cjkName);
  });

  it('accepts content exactly at the 32768 byte boundary', () => {
    const boundaryContent = 'a'.repeat(PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES);
    const request = fileRequest({ content_utf8: boundaryContent });
    const raw = fileRaw();
    setField(raw, ['preview', 'change', 'size_bytes'], PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES);
    const decoded = decode(raw, request, PUBLIC_REQUEST_SHA256) as ProjectKnowledgePreparedPreview;
    const change = decoded.preview.change;
    expect(change.kind === 'FILE_ADD' ? change.size_bytes : null).toBe(
      PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES,
    );
  });
});

describe('communication preference previews', () => {
  it('decodes the exact COMMUNICATION_PREFERENCE wrapper with the bound preimage', () => {
    const decoded = decode(prefRaw(), prefRequest(), PUBLIC_REQUEST_SHA256);
    expect(decoded).toStrictEqual(expectedPrefPreview(PREF_VALUE, PREFERENCE_REVISION));
  });

  it('keeps CJK text and CRLF line breaks verbatim in the value', () => {
    const decoded = decode(prefRaw(), prefRequest(), PUBLIC_REQUEST_SHA256) as ProjectKnowledgePreparedPreview;
    const change = decoded.preview.change;
    expect(change.kind).toBe('COMMUNICATION_PREFERENCE');
    expect(change.kind === 'COMMUNICATION_PREFERENCE' ? change.value : null).toBe(PREF_VALUE);
    expect(PREF_VALUE.includes('\r\n')).toBe(true);
  });

  it('binds a null request revision to a null decision preimage', () => {
    const raw = prefRaw();
    setField(raw, ['preview', 'postimages', 1, 'expected_preimage_sha256'], null);
    const decoded = decode(raw, prefRequest({ expected_preference_revision: null }), PUBLIC_REQUEST_SHA256);
    expect(decoded).toStrictEqual(expectedPrefPreview(PREF_VALUE, null));
  });

  it('accepts a value exactly at the 2000 UTF-8 byte boundary', () => {
    const boundaryValue = `${'a'.repeat(1997)}以`;
    expect(utf8Length(boundaryValue)).toBe(PROJECT_KNOWLEDGE_PREFERENCE_VALUE_MAX_UTF8_BYTES);
    const raw = prefRaw();
    setField(raw, ['preview', 'change', 'value'], boundaryValue);
    const decoded = decode(raw, prefRequest({ value: boundaryValue }), PUBLIC_REQUEST_SHA256);
    expect(decoded).not.toBeNull();
    const change = (decoded as ProjectKnowledgePreparedPreview).preview.change;
    expect(change.kind === 'COMMUNICATION_PREFERENCE' ? change.value : null).toBe(boundaryValue);
  });
});

describe('expected tuple, public hash and witness fingerprint mismatches', () => {
  it('rejects selection fields that do not pair with the request', () => {
    const mismatchedId = fileRaw();
    setField(mismatchedId, ['selection', 'request_id'], 'req-other');
    expect(decode(mismatchedId, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const mismatchedWorkRef = fileRaw();
    setField(mismatchedWorkRef, ['selection', 'work_ref'], 'WS:ATLAS-CORE');
    expect(decode(mismatchedWorkRef, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const mismatchedAction = fileRaw();
    setField(mismatchedAction, ['selection', 'action'], 'COMMUNICATION_PREFERENCE');
    expect(decode(mismatchedAction, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects a request whose schema selects a different action', () => {
    expect(decode(fileRaw(), prefRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(decode(prefRaw(), fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects preview action, work_ref and source_commit mismatches', () => {
    const actionMismatch = fileRaw();
    setField(actionMismatch, ['preview', 'action'], 'COMMUNICATION_PREFERENCE');
    expect(decode(actionMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const workRefMismatch = fileRaw();
    setField(workRefMismatch, ['preview', 'work_ref'], 'WS:ATLAS-CORE');
    expect(decode(workRefMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const commitMismatch = fileRaw();
    setField(commitMismatch, ['preview', 'source_commit'], OTHER_SHA256.slice(0, 40));
    expect(decode(commitMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects public request hash mismatches and malformed hashes', () => {
    expect(decode(fileRaw(), fileRequest(), OTHER_SHA256)).toBeNull();
    expect(decode(fileRaw(), fileRequest(), 'ab'.repeat(31))).toBeNull();
    expect(decode(fileRaw(), fileRequest(), 'AB'.repeat(32))).toBeNull();
    expect(decode(fileRaw(), fileRequest(), 'not-a-hash')).toBeNull();

    const raw = fileRaw();
    setField(raw, ['request_sha256'], OTHER_SHA256);
    expect(decode(raw, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects witness fingerprint and original input mismatches', () => {
    const fingerprintMismatch = fileRaw();
    setField(fingerprintMismatch, ['preview_witness', 'recipe_fingerprint_sha256'], OTHER_SHA256);
    expect(decode(fingerprintMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const schemaMismatch = fileRaw();
    setField(
      schemaMismatch,
      ['preview_witness', 'original_input', 'schema'],
      'mastermind.other_reference.v1',
    );
    expect(decode(schemaMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const prefixMismatch = fileRaw();
    setField(
      prefixMismatch,
      ['preview_witness', 'original_input', 'input_ref'],
      `terminal-other:${INPUT_REF_SHA256}`,
    );
    expect(decode(prefixMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const shortInputRef = fileRaw();
    setField(
      shortInputRef,
      ['preview_witness', 'original_input', 'input_ref'],
      `terminal-input:${'19'.repeat(31)}`,
    );
    expect(decode(shortInputRef, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const artifactMismatch = fileRaw();
    setField(
      artifactMismatch,
      ['preview_witness', 'original_input', 'artifact_sha256'],
      'ZZ'.repeat(32),
    );
    expect(decode(artifactMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects foreign wrapper and preview schemas and foreign states', () => {
    const wrapper = fileRaw();
    setField(wrapper, ['schema'], 'mastermind.workspace_source_operation_preview.v2');
    expect(decode(wrapper, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const preview = fileRaw();
    setField(preview, ['preview', 'schema'], 'mastermind.project_knowledge_preview.v2');
    expect(decode(preview, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const state = fileRaw();
    setField(state, ['preview', 'state'], 'DRAFT');
    expect(decode(state, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const scope = fileRaw();
    setField(scope, ['owner_context', 'principal_scope'], 'not-hex');
    expect(decode(scope, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });
});

describe('namespace, path, preimage and media pairing', () => {
  it('requires the exact workstream postimage path and preimage', () => {
    const otherKey = fileRaw();
    setField(otherKey, ['preview', 'postimages', 0, 'path'], 'agentos/workstreams/WS-ATLAS-CORE.md');
    expect(decode(otherKey, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const foreignNamespace = fileRaw();
    setField(
      foreignNamespace,
      ['preview', 'postimages', 0, 'path'],
      `agentosx/workstreams/WS-${WORK_REF_KEY}.md`,
    );
    expect(decode(foreignNamespace, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const missingExtension = fileRaw();
    setField(missingExtension, ['preview', 'postimages', 0, 'path'], `agentos/workstreams/WS-${WORK_REF_KEY}`);
    expect(decode(missingExtension, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const preimageMismatch = fileRaw();
    setField(
      preimageMismatch,
      ['preview', 'postimages', 0, 'expected_preimage_sha256'],
      OTHER_SHA256,
    );
    expect(decode(preimageMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('pairs the project file path with the media type and a null preimage', () => {
    const wrongExtension = fileRaw();
    setField(wrongExtension, ['preview', 'postimages', 1, 'path'], PROJECT_FILE_PATH.slice(0, -3) + '.txt');
    expect(decode(wrongExtension, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const wrongDirectory = fileRaw();
    setField(
      wrongDirectory,
      ['preview', 'postimages', 1, 'path'],
      `agentos/project-files/WS-ATLAS-CORE/${PROJECT_FILE_SHA256}.md`,
    );
    expect(decode(wrongDirectory, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const shortHex = fileRaw();
    setField(
      shortHex,
      ['preview', 'postimages', 1, 'path'],
      `agentos/project-files/WS-${WORK_REF_KEY}/${'e3'.repeat(31)}.md`,
    );
    expect(decode(shortHex, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const nonHexName = fileRaw();
    setField(
      nonHexName,
      ['preview', 'postimages', 1, 'path'],
      `agentos/project-files/WS-${WORK_REF_KEY}/${'z'.repeat(64)}.md`,
    );
    expect(decode(nonHexName, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const boundPreimage = fileRaw();
    setField(
      boundPreimage,
      ['preview', 'postimages', 1, 'expected_preimage_sha256'],
      BASE_REVISION,
    );
    expect(decode(boundPreimage, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const foreignSecondPath = fileRaw();
    setField(
      foreignSecondPath,
      ['preview', 'postimages', 1, 'path'],
      `agentos/notes/${PROJECT_FILE_SHA256}.md`,
    );
    expect(decode(foreignSecondPath, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('requires the exact decision postimage path and bound preimage', () => {
    const otherKey = prefRaw();
    setField(
      otherKey,
      ['preview', 'postimages', 1, 'path'],
      `agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-ATLAS-CORE.md`,
    );
    expect(decode(otherKey, prefRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const extraSuffix = prefRaw();
    setField(extraSuffix, ['preview', 'postimages', 1, 'path'], `${DECISION_PATH}x`);
    expect(decode(extraSuffix, prefRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const preimageMismatch = prefRaw();
    setField(
      preimageMismatch,
      ['preview', 'postimages', 1, 'expected_preimage_sha256'],
      OTHER_SHA256,
    );
    expect(decode(preimageMismatch, prefRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const nullPreimage = prefRaw();
    setField(nullPreimage, ['preview', 'postimages', 1, 'expected_preimage_sha256'], null);
    expect(decode(nullPreimage, prefRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const staleRevision = prefRaw();
    const staleRequest = prefRequest({ expected_preference_revision: null });
    expect(decode(staleRevision, staleRequest, PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('accepts exactly two unique postimages only', () => {
    const single = fileRaw();
    setField(single, ['preview', 'postimages'], [readIn(fileRaw(), ['preview', 'postimages', 0])]);
    expect(decode(single, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const triple = fileRaw();
    const extra = {
      path: `agentos/project-files/WS-${WORK_REF_KEY}/${'57'.repeat(32)}.md`,
      content_sha256: '57'.repeat(32),
      expected_preimage_sha256: null,
    };
    setField(triple, ['preview', 'postimages'], [
      readIn(triple, ['preview', 'postimages', 0]),
      readIn(triple, ['preview', 'postimages', 1]),
      extra,
    ]);
    expect(decode(triple, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const duplicated = fileRaw();
    setField(duplicated, ['preview', 'postimages'], [
      readIn(duplicated, ['preview', 'postimages', 0]),
      readIn(duplicated, ['preview', 'postimages', 0]),
    ]);
    expect(decode(duplicated, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('validates postimage field shapes', () => {
    const upperDigest = fileRaw();
    setField(upperDigest, ['preview', 'postimages', 0, 'content_sha256'], 'AB'.repeat(32));
    expect(decode(upperDigest, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const badDigest = fileRaw();
    setField(badDigest, ['preview', 'postimages', 0, 'content_sha256'], 'topf');
    expect(decode(badDigest, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const badPreimage = fileRaw();
    setField(badPreimage, ['preview', 'postimages', 0, 'expected_preimage_sha256'], 7);
    expect(decode(badPreimage, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const extraKey = fileRaw();
    setField(extraKey, ['preview', 'postimages', 0, 'media_type'], 'text/markdown');
    expect(decode(extraKey, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });
});

describe('closed inert plain data only', () => {
  it('rejects extra keys at every level', () => {
    const wrapper = fileRaw();
    wrapper['extra'] = 1;
    expect(decode(wrapper, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const owner = fileRaw();
    setField(owner, ['owner_context', 'extra'], 1);
    expect(decode(owner, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const preview = fileRaw();
    setField(preview, ['preview', 'extra'], 1);
    expect(decode(preview, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const change = fileRaw();
    setField(change, ['preview', 'change', 'note'], 'extra');
    expect(decode(change, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const toJSON = fileRaw();
    setField(toJSON, ['preview', 'toJSON'], () => 'x');
    expect(decode(toJSON, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects own symbol keys, enumerable or hidden', () => {
    const visibleSymbol = fileRaw();
    (visibleSymbol.selection as Record<PropertyKey, unknown>)[Symbol('extra')] = 1;
    expect(decode(visibleSymbol, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const hiddenSymbol = fileRaw();
    Object.defineProperty(hiddenSymbol, Symbol('hidden'), { value: 1, enumerable: false });
    expect(decode(hiddenSymbol, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects hidden non-enumerable fields and non-enumerable expected keys', () => {
    const hidden = fileRaw();
    Object.defineProperty(hidden.preview, 'hidden', { value: 1, enumerable: false });
    expect(decode(hidden, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const shadowed = fileRaw();
    const preview = shadowed.preview as Record<string, unknown>;
    const workRef = preview['work_ref'];
    delete preview['work_ref'];
    Object.defineProperty(preview, 'work_ref', { value: workRef, enumerable: false });
    expect(decode(shadowed, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects accessor properties', () => {
    const raw = fileRaw();
    const change = (raw.preview as Record<string, unknown>).change as Record<string, unknown>;
    delete change['display_name'];
    Object.defineProperty(change, 'display_name', {
      enumerable: true,
      get() {
        return DISPLAY_NAME;
      },
    });
    expect(decode(raw, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects custom prototypes at any level', () => {
    const forged = Object.assign(Object.create({ inherited: true }), fileRaw());
    expect(decode(forged, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    class FakeChange {
      kind = 'FILE_ADD';
      display_name = DISPLAY_NAME;
      size_bytes = CONTENT_BYTES;
    }
    const instance = fileRaw();
    (instance.preview as Record<string, unknown>).change = new FakeChange();
    expect(decode(instance, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    class FakeArray extends Array {}
    const exoticList = fileRaw();
    setField(
      exoticList,
      ['preview', 'postimages'],
      FakeArray.from((exoticList.preview as Record<string, unknown>).postimages as unknown[]),
    );
    expect(decode(exoticList, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const sparseNamed = fileRaw();
    const widened: unknown[] = [
      readIn(sparseNamed, ['preview', 'postimages', 0]),
      readIn(sparseNamed, ['preview', 'postimages', 1]),
    ];
    setField(widened, ['extra'], 1);
    setField(sparseNamed, ['preview', 'postimages'], widened);
    expect(decode(sparseNamed, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects non-object and structurally wrong raws', () => {
    expect(decode(null, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(decode(42, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(decode('x', fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(decode(true, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(decode([], fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(decode(undefined, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects change field mismatches', () => {
    const sizeMismatch = fileRaw();
    setField(sizeMismatch, ['preview', 'change', 'size_bytes'], CONTENT_BYTES + 1);
    expect(decode(sizeMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const floatSize = fileRaw();
    setField(floatSize, ['preview', 'change', 'size_bytes'], CONTENT_BYTES + 0.5);
    expect(decode(floatSize, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const booleanSize = fileRaw();
    setField(booleanSize, ['preview', 'change', 'size_bytes'], true);
    expect(decode(booleanSize, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const nameMismatch = fileRaw();
    setField(nameMismatch, ['preview', 'change', 'display_name'], 'other.md');
    expect(decode(nameMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const kindMismatch = fileRaw();
    setField(kindMismatch, ['preview', 'change', 'kind'], 'COMMUNICATION_PREFERENCE');
    expect(decode(kindMismatch, fileRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();

    const valueMismatch = prefRaw();
    setField(valueMismatch, ['preview', 'change', 'value'], 'other value');
    expect(decode(valueMismatch, prefRequest(), PUBLIC_REQUEST_SHA256)).toBeNull();
  });
});

describe('budgets', () => {
  it('rejects a wrapper over the canonical UTF-8 budget', () => {
    const longName = `${'a'.repeat(PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES + 1)}.md`;
    const request = fileRequest({ display_name: longName });
    const raw = fileRaw();
    setField(raw, ['preview', 'change', 'display_name'], longName);
    expect(decode(raw, request, PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects content over the 32768 byte budget', () => {
    const request = fileRequest({ content_utf8: 'a'.repeat(32769) });
    expect(decode(fileRaw(), request, PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects empty and over-long preference values', () => {
    expect(decode(prefRaw(), prefRequest({ value: '' }), PUBLIC_REQUEST_SHA256)).toBeNull();

    const longValue = `${'a'.repeat(1997)}以以`;
    expect(utf8Length(longValue)).toBe(2003);
    expect(
      decode(prefRaw(), prefRequest({ value: longValue }), PUBLIC_REQUEST_SHA256),
    ).toBeNull();
  });
});

describe('invalid direct calls fail closed', () => {
  it('rejects malformed file requests', () => {
    const missing = fileRequest();
    dropIn(missing, ['source_commit']);
    expect(decode(fileRaw(), missing, PUBLIC_REQUEST_SHA256)).toBeNull();

    const extra = fileRequest();
    setField(extra, ['extra'], 1);
    expect(decode(fileRaw(), extra, PUBLIC_REQUEST_SHA256)).toBeNull();

    const foreignSchema = fileRequest();
    setField(foreignSchema, ['schema'], 'mastermind.other_request.v1');
    expect(decode(fileRaw(), foreignSchema, PUBLIC_REQUEST_SHA256)).toBeNull();

    const shortCommit = fileRequest();
    setField(shortCommit, ['source_commit'], 'd'.repeat(39));
    expect(decode(fileRaw(), shortCommit, PUBLIC_REQUEST_SHA256)).toBeNull();

    const upperBase = fileRequest();
    setField(upperBase, ['base_revision'], 'FF'.repeat(32));
    expect(decode(fileRaw(), upperBase, PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('enforces the workstream work_ref grammar on requests', () => {
    for (const badWorkRef of [
      'ws:PROPHET-US',
      'WS:p',
      'WS:P',
      'WS:PRO--PHET',
      'WS:PROPHET_US',
      'PROPHET-US',
      'WS:',
    ]) {
      const request = fileRequest();
      setField(request, ['work_ref'], badWorkRef);
      expect(decode(fileRaw(), request, PUBLIC_REQUEST_SHA256)).toBeNull();
    }
  });

  it('rejects path-like or control display names and unknown media types', () => {
    const pathName = fileRequest();
    setField(pathName, ['file', 'display_name'], 'a/b.md');
    expect(decode(fileRaw(), pathName, PUBLIC_REQUEST_SHA256)).toBeNull();

    const parentName = fileRequest();
    setField(parentName, ['file', 'display_name'], '..');
    expect(decode(fileRaw(), parentName, PUBLIC_REQUEST_SHA256)).toBeNull();

    const controlName = fileRequest();
    setField(controlName, ['file', 'display_name'], 'a\nb.md');
    expect(decode(fileRaw(), controlName, PUBLIC_REQUEST_SHA256)).toBeNull();

    const unknownMedia = fileRequest();
    setField(unknownMedia, ['file', 'media_type'], 'application/pdf');
    expect(decode(fileRaw(), unknownMedia, PUBLIC_REQUEST_SHA256)).toBeNull();

    const nonStringContent = fileRequest();
    setField(nonStringContent, ['file', 'content_utf8'], 42);
    expect(decode(fileRaw(), nonStringContent, PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects malformed preference requests', () => {
    const emptyValue = prefRequest({ value: '' });
    expect(decode(prefRaw(), emptyValue, PUBLIC_REQUEST_SHA256)).toBeNull();

    const shortRevision = prefRequest({ expected_preference_revision: 'ab'.repeat(31) });
    expect(decode(prefRaw(), shortRevision, PUBLIC_REQUEST_SHA256)).toBeNull();

    const nonHexRevision = prefRequest({ expected_preference_revision: 'up' });
    expect(decode(prefRaw(), nonHexRevision, PUBLIC_REQUEST_SHA256)).toBeNull();
  });

  it('rejects non-object requests', () => {
    expect(decode(fileRaw(), null as unknown as ProjectFileAddRequest, PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(
      decode(fileRaw(), undefined as unknown as ProjectFileAddRequest, PUBLIC_REQUEST_SHA256),
    ).toBeNull();
    expect(decode(fileRaw(), 42 as unknown as ProjectFileAddRequest, PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(decode(fileRaw(), 'x' as unknown as ProjectFileAddRequest, PUBLIC_REQUEST_SHA256)).toBeNull();
    expect(
      decode(fileRaw(), [] as unknown as ProjectFileAddRequest, PUBLIC_REQUEST_SHA256),
    ).toBeNull();
  });
});

describe('detached, deeply frozen returns', () => {
  it('a later change to raw cannot mutate a returned preview', () => {
    const raw = fileRaw();
    const decoded = decode(raw, fileRequest(), PUBLIC_REQUEST_SHA256) as ProjectKnowledgePreparedPreview;
    setField(raw, ['preview', 'change', 'display_name'], 'tampered.md');
    setField(raw, ['selection', 'request_id'], 'req-tampered');
    setField(raw, ['request_sha256'], OTHER_SHA256);
    setField(raw, ['preview', 'change', 'size_bytes'], 1);
    const change = decoded.preview.change;
    expect(change.kind === 'FILE_ADD' ? change.display_name : null).toBe(DISPLAY_NAME);
    expect(decoded.selection.request_id).toBe(REQUEST_ID);
    expect(decoded.request_sha256).toBe(PUBLIC_REQUEST_SHA256);
    expect(change.kind === 'FILE_ADD' ? change.size_bytes : null).toBe(CONTENT_BYTES);
    expect(decoded.preview.postimages.length).toBe(2);
  });

  it('a later change to the request cannot mutate a returned preview', () => {
    const request = fileRequest();
    const decoded = decode(fileRaw(), request, PUBLIC_REQUEST_SHA256) as ProjectKnowledgePreparedPreview;
    setField(request, ['file', 'content_utf8'], 'mutated');
    setField(request, ['request_id'], 'req-mutated');
    expect(decoded.preview.change.kind === 'FILE_ADD' ? decoded.preview.change.size_bytes : null).toBe(
      CONTENT_BYTES,
    );
    expect(decoded.selection.request_id).toBe(REQUEST_ID);
  });

  it('a later change to raw cannot mutate a returned preference preview', () => {
    const raw = prefRaw();
    const decoded = decode(raw, prefRequest(), PUBLIC_REQUEST_SHA256) as ProjectKnowledgePreparedPreview;
    setField(raw, ['preview', 'change', 'value'], ' mutated ');
    const change = decoded.preview.change;
    expect(change.kind === 'COMMUNICATION_PREFERENCE' ? change.value : null).toBe(PREF_VALUE);
  });
});
