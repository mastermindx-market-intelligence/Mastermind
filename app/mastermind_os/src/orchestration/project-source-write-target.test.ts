import { describe, expect, it } from 'vitest';
import {
  parseProjectSourceWriteTarget,
  projectSourceWriteKeyMatches,
  serializeProjectSourceWriteTarget,
  type ProjectSourceWriteTarget,
} from './project-source-write-target';

const TARGET_PREFIX = 'project-source-write.v1:';
const WORK_REF_ADD = 'WS:ALPHA-KEY-2';
const WORK_REF_PREFERENCE = 'WS:BETA-9';

function lowerHex(seed: string, length: number): string {
  return seed.replace(/[^0-9a-f]/g, '').padEnd(length, '0').slice(0, length);
}

const SOURCE_COMMIT = lowerHex('abc123def', 40);
const BASE_REVISION = lowerHex('7f3e9a1b', 64);
const REQUEST_SHA256 = lowerHex('c0ffee', 64);
const PREFERENCE_REVISION = lowerHex('ba5eba11', 64);
const UNRELATED_KEY_HEX = lowerHex('a9b8c7d6e5', 40);

const ADD_OPERATION_KEY = `mmos-project-file-add-${UNRELATED_KEY_HEX}`;
const PREFERENCE_OPERATION_KEY = `mmos-project-preference-set-${UNRELATED_KEY_HEX}`;

function addProjectFileTarget(): ProjectSourceWriteTarget {
  return {
    action: 'add_project_file',
    work_ref: WORK_REF_ADD,
    source_commit: SOURCE_COMMIT,
    base_revision: BASE_REVISION,
    request_sha256: REQUEST_SHA256,
    expected_preference_revision: null,
  };
}

function preferenceTarget(): ProjectSourceWriteTarget {
  return {
    action: 'set_project_communication_preference',
    work_ref: WORK_REF_PREFERENCE,
    source_commit: SOURCE_COMMIT,
    base_revision: BASE_REVISION,
    request_sha256: REQUEST_SHA256,
    expected_preference_revision: PREFERENCE_REVISION,
  };
}

function recordOf(target: ProjectSourceWriteTarget): Record<string, unknown> {
  return { ...target };
}

function canonicalBody(record: Record<string, unknown>): string {
  const names = Object.keys(record).sort();
  return `{${names
    .map((name) => `${JSON.stringify(name)}:${JSON.stringify(record[name])}`)
    .join(',')}}`;
}

function targetString(record: Record<string, unknown>): string {
  return `${TARGET_PREFIX}${canonicalBody(record)}`;
}

/** Hand-written canonical forms, pinned byte for byte. */
const ADD_TARGET_STRING =
  `${TARGET_PREFIX}{"action":"add_project_file","base_revision":"${BASE_REVISION}",` +
  `"expected_preference_revision":null,"request_sha256":"${REQUEST_SHA256}",` +
  `"source_commit":"${SOURCE_COMMIT}","work_ref":"${WORK_REF_ADD}"}`;

const PREFERENCE_TARGET_STRING =
  `${TARGET_PREFIX}{"action":"set_project_communication_preference",` +
  `"base_revision":"${BASE_REVISION}","expected_preference_revision":"${PREFERENCE_REVISION}",` +
  `"request_sha256":"${REQUEST_SHA256}","source_commit":"${SOURCE_COMMIT}",` +
  `"work_ref":"${WORK_REF_PREFERENCE}"}`;

const PREFERENCE_TARGET_NULL_REVISION_STRING =
  `${TARGET_PREFIX}{"action":"set_project_communication_preference",` +
  `"base_revision":"${BASE_REVISION}","expected_preference_revision":null,` +
  `"request_sha256":"${REQUEST_SHA256}","source_commit":"${SOURCE_COMMIT}",` +
  `"work_ref":"${WORK_REF_PREFERENCE}"}`;

describe('fixtures', () => {
  it('uses correctly shaped hex and key fixtures', () => {
    expect(SOURCE_COMMIT).toMatch(/^[0-9a-f]{40}$/);
    expect(BASE_REVISION).toMatch(/^[0-9a-f]{64}$/);
    expect(REQUEST_SHA256).toMatch(/^[0-9a-f]{64}$/);
    expect(PREFERENCE_REVISION).toMatch(/^[0-9a-f]{64}$/);
    expect(UNRELATED_KEY_HEX).toMatch(/^[0-9a-f]{40}$/);
    expect(ADD_OPERATION_KEY).toMatch(/^mmos-project-file-add-[0-9a-f]{40}$/);
    expect(PREFERENCE_OPERATION_KEY).toMatch(
      /^mmos-project-preference-set-[0-9a-f]{40}$/,
    );
    expect(ADD_TARGET_STRING.length).toBeLessThan(2048);
    expect(PREFERENCE_TARGET_STRING.length).toBeLessThan(2048);
  });
});

describe('serializeProjectSourceWriteTarget', () => {
  it('emits the exact canonical byte string for an add_project_file target', () => {
    expect(serializeProjectSourceWriteTarget(addProjectFileTarget())).toBe(
      ADD_TARGET_STRING,
    );
  });

  it('emits the exact canonical byte string for a preference target with a revision', () => {
    expect(serializeProjectSourceWriteTarget(preferenceTarget())).toBe(
      PREFERENCE_TARGET_STRING,
    );
  });

  it('emits a null expected_preference_revision when the preference target has none', () => {
    const target = { ...preferenceTarget(), expected_preference_revision: null };
    expect(serializeProjectSourceWriteTarget(target)).toBe(
      PREFERENCE_TARGET_NULL_REVISION_STRING,
    );
  });

  it('is independent of the input key insertion order', () => {
    const reordered: Record<string, unknown> = {};
    for (const [name, value] of Object.entries(recordOf(preferenceTarget())).reverse()) {
      reordered[name] = value;
    }
    expect(serializeProjectSourceWriteTarget(reordered)).toBe(
      PREFERENCE_TARGET_STRING,
    );
  });

  it('accepts a frozen input record', () => {
    expect(serializeProjectSourceWriteTarget(Object.freeze(addProjectFileTarget()))).toBe(
      ADD_TARGET_STRING,
    );
  });

  it('round trips through parse', () => {
    const serialized = serializeProjectSourceWriteTarget(preferenceTarget());
    expect(serialized).not.toBeNull();
    expect(parseProjectSourceWriteTarget(serialized)).toEqual(preferenceTarget());
  });
});

describe('parseProjectSourceWriteTarget', () => {
  it('parses the exact canonical add_project_file string', () => {
    expect(parseProjectSourceWriteTarget(ADD_TARGET_STRING)).toEqual(
      addProjectFileTarget(),
    );
  });

  it('parses the exact canonical preference string', () => {
    expect(parseProjectSourceWriteTarget(PREFERENCE_TARGET_STRING)).toEqual(
      preferenceTarget(),
    );
  });

  it('parses a strictly shaped plain object input', () => {
    expect(parseProjectSourceWriteTarget(addProjectFileTarget())).toEqual(
      addProjectFileTarget(),
    );
    expect(parseProjectSourceWriteTarget(recordOf(preferenceTarget()))).toEqual(
      preferenceTarget(),
    );
  });

  it('round trips without rewriting the accepted stored target', () => {
    for (const target of [addProjectFileTarget(), preferenceTarget()]) {
      const serialized = serializeProjectSourceWriteTarget(target);
      expect(serialized).not.toBeNull();
      expect(parseProjectSourceWriteTarget(serialized)).toEqual(target);
      expect(
        serializeProjectSourceWriteTarget(parseProjectSourceWriteTarget(serialized)),
      ).toBe(serialized);
    }
  });

  it('accepts boundary shaped work_ref keys', () => {
    const shortest = targetString({ ...recordOf(addProjectFileTarget()), work_ref: 'WS:AB' });
    expect(parseProjectSourceWriteTarget(shortest)).toEqual({
      ...addProjectFileTarget(),
      work_ref: 'WS:AB',
    });
    const longest = targetString({
      ...recordOf(addProjectFileTarget()),
      work_ref: `WS:${'A1'.padEnd(64, '0')}`,
    });
    expect(parseProjectSourceWriteTarget(longest)).not.toBeNull();
    const singleSegment = targetString({
      ...recordOf(addProjectFileTarget()),
      work_ref: 'WS:ALPHAKEY2',
    });
    expect(parseProjectSourceWriteTarget(singleSegment)).not.toBeNull();
    const digitsOnly = targetString({
      ...recordOf(addProjectFileTarget()),
      work_ref: 'WS:1234-5678',
    });
    expect(parseProjectSourceWriteTarget(digitsOnly)).not.toBeNull();
  });
});

describe('stored string canonicality', () => {
  const body = ADD_TARGET_STRING.slice(TARGET_PREFIX.length);

  it('rejects whitespace anywhere in the stored body', () => {
    expect(parseProjectSourceWriteTarget(ADD_TARGET_STRING)).not.toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX} ${body}`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}  ${body}`)).toBeNull();
    const spaced = `{"action": "add_project_file", "base_revision": "${BASE_REVISION}", "expected_preference_revision": null, "request_sha256": "${REQUEST_SHA256}", "source_commit": "${SOURCE_COMMIT}", "work_ref": "${WORK_REF_ADD}"}`;
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}${spaced}`)).toBeNull();
    expect(
      parseProjectSourceWriteTarget(
        `${TARGET_PREFIX}${JSON.stringify(recordOf(addProjectFileTarget()), null, 2)}`,
      ),
    ).toBeNull();
  });

  it('rejects noncanonical key order', () => {
    const swapped = `{"work_ref":"${WORK_REF_ADD}","source_commit":"${SOURCE_COMMIT}",` +
      `"request_sha256":"${REQUEST_SHA256}","expected_preference_revision":null,` +
      `"base_revision":"${BASE_REVISION}","action":"add_project_file"}`;
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}${swapped}`)).toBeNull();
  });

  it('rejects duplicate keys', () => {
    const duplicate = `{"action":"set_project_communication_preference","action":"add_project_file",` +
      `"base_revision":"${BASE_REVISION}","expected_preference_revision":null,` +
      `"request_sha256":"${REQUEST_SHA256}","source_commit":"${SOURCE_COMMIT}",` +
      `"work_ref":"${WORK_REF_ADD}"}`;
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}${duplicate}`)).toBeNull();
  });

  it('rejects trailing and leading noise on the stored string', () => {
    expect(parseProjectSourceWriteTarget(`${ADD_TARGET_STRING}\n`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${ADD_TARGET_STRING}\r\n`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${ADD_TARGET_STRING} `)).toBeNull();
    expect(parseProjectSourceWriteTarget(` ${ADD_TARGET_STRING}`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`\n${ADD_TARGET_STRING}`)).toBeNull();
  });

  it('rejects missing or altered prefixes', () => {
    expect(parseProjectSourceWriteTarget(body)).toBeNull();
    expect(parseProjectSourceWriteTarget(`project-source-write.v2:${body}`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`Project-Source-Write.V1:${body}`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`project-source-write.v1;${body}`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}${ADD_TARGET_STRING}`)).toBeNull();
  });

  it('rejects multiple, empty and non-object JSON bodies', () => {
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}${body}${body}`)).toBeNull();
    expect(parseProjectSourceWriteTarget(TARGET_PREFIX)).toBeNull();
    expect(parseProjectSourceWriteTarget('')).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}null`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}[]`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}123`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}"add_project_file"`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}true`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}{`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}{"action":}`)).toBeNull();
  });

  it('rejects noncanonical JSON escaping in the stored body', () => {
    const escaped = `{"action":"add_project_file","base_revision":"${BASE_REVISION}",` +
      `"expected_preference_revision":null,"request_sha256":"${REQUEST_SHA256}",` +
      `"source_commit":"${SOURCE_COMMIT}","work_ref":"WS:ALPHA\\u002DKEY\\u002D2"}`;
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}${escaped}`)).toBeNull();
  });
});

describe('field validation', () => {
  const addRecord = recordOf(addProjectFileTarget());

  it('rejects invalid action values', () => {
    const invalid: unknown[] = [
      '',
      'ADD_PROJECT_FILE',
      'Add_Project_File',
      'add_project_files',
      'add-project-file',
      'set-project-communication-preference',
      ' ',
      'add_project_file\n',
      'add_project_file ',
      1,
      0,
      -1,
      true,
      false,
      null,
      {},
      [],
    ];
    for (const action of invalid) {
      expect(parseProjectSourceWriteTarget(targetString({ ...addRecord, action }))).toBeNull();
      expect(serializeProjectSourceWriteTarget({ ...addProjectFileTarget(), action })).toBeNull();
    }
  });

  it('rejects malformed work_ref values', () => {
    const invalid = [
      '',
      'WS:',
      'WS:A',
      'ws:ALPHA-KEY-2',
      'WS:alpha-key-2',
      'ALPHA-KEY-2',
      'WS:ALPHA KEY',
      'WS:ALPHA--KEY',
      'WS:-ALPHA-KEY',
      'WS:ALPHA-KEY-',
      'WS:ALPHA_KEY',
      'WS:ALPHA.KEY',
      `WS:${'A'.repeat(65)}`,
      'WS:ALPHA-KEY-2\n',
      'WS:ALPHA-KEY-2 ',
      'WS:ALPHA-KEY-2  X',
      'WS',
      'WSALPHA',
      null,
      true,
      7,
    ];
    for (const work_ref of invalid) {
      expect(
        parseProjectSourceWriteTarget(targetString({ ...addRecord, work_ref })),
      ).toBeNull();
      expect(
        serializeProjectSourceWriteTarget({ ...addProjectFileTarget(), work_ref }),
      ).toBeNull();
    }
  });

  it('rejects malformed source_commit values', () => {
    const invalid = [
      '',
      'abc',
      SOURCE_COMMIT.slice(1),
      `${SOURCE_COMMIT}0`,
      SOURCE_COMMIT.toUpperCase(),
      `${SOURCE_COMMIT.slice(0, 39)}g`,
      `${SOURCE_COMMIT.slice(0, 39)}G`,
      ` ${SOURCE_COMMIT}`,
      `${SOURCE_COMMIT} `,
      12345,
      null,
      true,
    ];
    for (const source_commit of invalid) {
      expect(
        parseProjectSourceWriteTarget(targetString({ ...addRecord, source_commit })),
      ).toBeNull();
      expect(
        serializeProjectSourceWriteTarget({ ...addProjectFileTarget(), source_commit }),
      ).toBeNull();
    }
  });

  it('rejects malformed base_revision and request_sha256 values', () => {
    const invalid = [
      '',
      BASE_REVISION.slice(1),
      `${BASE_REVISION}0`,
      BASE_REVISION.toUpperCase(),
      `${BASE_REVISION.slice(0, 63)}g`,
      `${BASE_REVISION.slice(0, 63)}Z`,
      ` ${BASE_REVISION}`,
      0,
      null,
      true,
    ];
    for (const key of ['base_revision', 'request_sha256'] as const) {
      for (const value of invalid) {
        expect(
          parseProjectSourceWriteTarget(targetString({ ...addRecord, [key]: value })),
        ).toBeNull();
        expect(
          serializeProjectSourceWriteTarget({ ...addProjectFileTarget(), [key]: value }),
        ).toBeNull();
      }
    }
  });

  it('rejects malformed expected_preference_revision values', () => {
    const invalid = [
      '',
      PREFERENCE_REVISION.slice(0, 40),
      PREFERENCE_REVISION.slice(1),
      `${PREFERENCE_REVISION}0`,
      PREFERENCE_REVISION.toUpperCase(),
      `${PREFERENCE_REVISION.slice(0, 63)}g`,
      'null',
      'NULL',
      7,
      true,
      {},
      [],
    ];
    for (const expected_preference_revision of invalid) {
      expect(
        parseProjectSourceWriteTarget(
          targetString({ ...recordOf(preferenceTarget()), expected_preference_revision }),
        ),
      ).toBeNull();
      expect(
        serializeProjectSourceWriteTarget({
          ...preferenceTarget(),
          expected_preference_revision,
        }),
      ).toBeNull();
    }
  });

  it('requires a null expected_preference_revision for add_project_file', () => {
    const withRevision = {
      ...addProjectFileTarget(),
      expected_preference_revision: PREFERENCE_REVISION,
    };
    expect(parseProjectSourceWriteTarget(targetString(recordOf(withRevision)))).toBeNull();
    expect(serializeProjectSourceWriteTarget(withRevision)).toBeNull();
  });

  it('accepts null or a full revision for set_project_communication_preference', () => {
    const withoutRevision = { ...preferenceTarget(), expected_preference_revision: null };
    expect(
      parseProjectSourceWriteTarget(targetString(recordOf(withoutRevision))),
    ).toEqual(withoutRevision);
    expect(serializeProjectSourceWriteTarget(withoutRevision)).toBe(
      PREFERENCE_TARGET_NULL_REVISION_STRING,
    );
  });

  it('rejects missing, extra and misspelled fields', () => {
    for (const name of Object.keys(addRecord)) {
      const partial = { ...addRecord };
      delete partial[name];
      expect(parseProjectSourceWriteTarget(targetString(partial))).toBeNull();
      expect(serializeProjectSourceWriteTarget(partial)).toBeNull();
    }
    expect(
      parseProjectSourceWriteTarget(
        targetString({ ...addRecord, operation_digest: UNRELATED_KEY_HEX }),
      ),
    ).toBeNull();
    expect(
      serializeProjectSourceWriteTarget({ ...addProjectFileTarget(), operation_digest: 'x' }),
    ).toBeNull();
    expect(
      parseProjectSourceWriteTarget(targetString({ ...addRecord, sourceCommits: SOURCE_COMMIT })),
    ).toBeNull();
  });
});

describe('projectSourceWriteKeyMatches', () => {
  it('matches the exact fixed key shape for each action', () => {
    expect(projectSourceWriteKeyMatches(ADD_OPERATION_KEY, addProjectFileTarget())).toBe(
      true,
    );
    expect(
      projectSourceWriteKeyMatches(PREFERENCE_OPERATION_KEY, preferenceTarget()),
    ).toBe(true);
  });

  it('matches the fixed pattern alone: the key digest is a lookup fact, not an identity check', () => {
    expect(ADD_OPERATION_KEY.endsWith(SOURCE_COMMIT)).toBe(false);
    expect(projectSourceWriteKeyMatches(ADD_OPERATION_KEY, addProjectFileTarget())).toBe(
      true,
    );
    expect(
      projectSourceWriteKeyMatches(`mmos-project-preference-set-${SOURCE_COMMIT}`, {
        ...preferenceTarget(),
        source_commit: UNRELATED_KEY_HEX,
      }),
    ).toBe(true);
  });

  it('rejects an action prefix mismatch', () => {
    expect(
      projectSourceWriteKeyMatches(PREFERENCE_OPERATION_KEY, addProjectFileTarget()),
    ).toBe(false);
    expect(projectSourceWriteKeyMatches(ADD_OPERATION_KEY, preferenceTarget())).toBe(
      false,
    );
  });

  it('rejects malformed operation keys', () => {
    const nearMisses = [
      '',
      'mmos-project-file-add',
      `mmos-project-file-add-${UNRELATED_KEY_HEX}0`,
      `mmos-project-file-add-${UNRELATED_KEY_HEX.slice(1)}`,
      `mmos-project-file-add-${UNRELATED_KEY_HEX.toUpperCase()}`,
      `mmos-project-file-add-${UNRELATED_KEY_HEX.slice(0, 39)}g`,
      `mmos-project-file-addx-${UNRELATED_KEY_HEX}`,
      `mmos-project-file-${UNRELATED_KEY_HEX}`,
      `MMOS-PROJECT-FILE-ADD-${UNRELATED_KEY_HEX}`,
      `mmos-project-file-add-${UNRELATED_KEY_HEX}\n`,
      `mmos-project-file-add-${UNRELATED_KEY_HEX} `,
      ` ${ADD_OPERATION_KEY}`,
      `${ADD_OPERATION_KEY}-extra`,
      'mmos-project-file-add-null',
      'mmos-project-preference-set',
      `mmos-project-preference-set-${UNRELATED_KEY_HEX.slice(0, 39)}`,
      `mmos-project-preference-set-${UNRELATED_KEY_HEX} `,
      'mmos-project-preference-setx',
    ];
    for (const key of nearMisses) {
      expect(projectSourceWriteKeyMatches(key, addProjectFileTarget())).toBe(false);
      expect(projectSourceWriteKeyMatches(key, preferenceTarget())).toBe(false);
    }
  });

  it('rejects non-string operation keys', () => {
    for (const key of [null, undefined, 0, 1, -1, true, false, {}, [], Symbol('k')]) {
      expect(projectSourceWriteKeyMatches(key, addProjectFileTarget())).toBe(false);
      expect(projectSourceWriteKeyMatches(key, preferenceTarget())).toBe(false);
    }
  });

  it('rejects a target that no longer satisfies the target shape', () => {
    const mutated = {
      ...addProjectFileTarget(),
      action: 'not-an-action',
    } as unknown as ProjectSourceWriteTarget;
    expect(projectSourceWriteKeyMatches(ADD_OPERATION_KEY, mutated)).toBe(false);
    const stripped = recordOf(addProjectFileTarget());
    delete stripped.request_sha256;
    expect(
      projectSourceWriteKeyMatches(
        ADD_OPERATION_KEY,
        stripped as unknown as ProjectSourceWriteTarget,
      ),
    ).toBe(false);
    expect(
      projectSourceWriteKeyMatches(
        ADD_OPERATION_KEY,
        null as unknown as ProjectSourceWriteTarget,
      ),
    ).toBe(false);
    expect(
      projectSourceWriteKeyMatches(
        ADD_OPERATION_KEY,
        'project-source-write.v1:{}' as unknown as ProjectSourceWriteTarget,
      ),
    ).toBe(false);
  });

  it('matches keys for targets produced by parse', () => {
    const parsed = parseProjectSourceWriteTarget(PREFERENCE_TARGET_STRING);
    expect(parsed).not.toBeNull();
    expect(
      projectSourceWriteKeyMatches(PREFERENCE_OPERATION_KEY, parsed as ProjectSourceWriteTarget),
    ).toBe(true);
    expect(
      projectSourceWriteKeyMatches(ADD_OPERATION_KEY, parsed as ProjectSourceWriteTarget),
    ).toBe(false);
  });
});

describe('hostile and non-plain inputs', () => {
  it('rejects non-plain and non-object inputs', () => {
    class Wrapper {}
    const nonPlain: unknown[] = [
      null,
      undefined,
      0,
      -1,
      1.5,
      Number.NaN,
      Number.POSITIVE_INFINITY,
      true,
      false,
      '',
      'x',
      TARGET_PREFIX,
      'project-source-write.v1:{}',
      BigInt(1),
      Symbol('s'),
      () => undefined,
      [],
      [addProjectFileTarget()],
      new Date(),
      new Map(),
      new Set(),
      /regex/,
      new Error('e'),
      new Wrapper(),
      Object.create({ inherited: true }),
    ];
    for (const value of nonPlain) {
      expect(parseProjectSourceWriteTarget(value)).toBeNull();
      expect(serializeProjectSourceWriteTarget(value)).toBeNull();
    }
  });

  it('never invokes accessors, getters or toJSON', () => {
    let actionGetterInvoked = false;
    const withGetter: Record<string, unknown> = {};
    Object.defineProperty(withGetter, 'action', {
      enumerable: true,
      get() {
        actionGetterInvoked = true;
        return 'add_project_file';
      },
    });
    Object.assign(withGetter, {
      work_ref: WORK_REF_ADD,
      source_commit: SOURCE_COMMIT,
      base_revision: BASE_REVISION,
      request_sha256: REQUEST_SHA256,
      expected_preference_revision: null,
    });
    expect(Object.getOwnPropertyNames(withGetter).length).toBe(6);
    expect(serializeProjectSourceWriteTarget(withGetter)).toBeNull();
    expect(parseProjectSourceWriteTarget(withGetter)).toBeNull();
    expect(
      projectSourceWriteKeyMatches(
        ADD_OPERATION_KEY,
        withGetter as unknown as ProjectSourceWriteTarget,
      ),
    ).toBe(false);
    expect(actionGetterInvoked).toBe(false);

    let toJSONInvoked = false;
    const withToJSON = {
      ...addProjectFileTarget(),
      toJSON: () => {
        toJSONInvoked = true;
        return {};
      },
    };
    expect(serializeProjectSourceWriteTarget(withToJSON)).toBeNull();
    expect(parseProjectSourceWriteTarget(withToJSON)).toBeNull();
    expect(toJSONInvoked).toBe(false);

    let setterInvoked = false;
    const withSetter: Record<string, unknown> = recordOf(addProjectFileTarget());
    Object.defineProperty(withSetter, 'source_commit', {
      enumerable: true,
      get() {
        return SOURCE_COMMIT;
      },
      set() {
        setterInvoked = true;
      },
    });
    expect(serializeProjectSourceWriteTarget(withSetter)).toBeNull();
    expect(parseProjectSourceWriteTarget(withSetter)).toBeNull();
    expect(setterInvoked).toBe(false);
  });

  it('rejects hidden and symbol-keyed own fields', () => {
    const hidden = recordOf(addProjectFileTarget());
    Object.defineProperty(hidden, 'smuggled', {
      enumerable: false,
      value: true,
      writable: true,
      configurable: true,
    });
    expect(serializeProjectSourceWriteTarget(hidden)).toBeNull();
    expect(parseProjectSourceWriteTarget(hidden)).toBeNull();

    const symbolic = { ...recordOf(addProjectFileTarget()), [Symbol('extra')]: true };
    expect(serializeProjectSourceWriteTarget(symbolic)).toBeNull();
    expect(parseProjectSourceWriteTarget(symbolic)).toBeNull();

    const nonEnumerableAction: Record<string, unknown> = {};
    Object.defineProperty(nonEnumerableAction, 'action', {
      enumerable: false,
      value: 'add_project_file',
    });
    Object.assign(nonEnumerableAction, {
      work_ref: WORK_REF_ADD,
      source_commit: SOURCE_COMMIT,
      base_revision: BASE_REVISION,
      request_sha256: REQUEST_SHA256,
      expected_preference_revision: null,
    });
    expect(Object.getOwnPropertyNames(nonEnumerableAction).length).toBe(6);
    expect(serializeProjectSourceWriteTarget(nonEnumerableAction)).toBeNull();
    expect(parseProjectSourceWriteTarget(nonEnumerableAction)).toBeNull();
  });

  it('rejects prototype pollution and inherited field carriers', () => {
    const prototypeBridge = Object.prototype as unknown as Record<string, unknown>;
    const pollutedString = `${TARGET_PREFIX}{"action":"add_project_file",` +
      `"base_revision":"${BASE_REVISION}","expected_preference_revision":null,` +
      `"request_sha256":"${REQUEST_SHA256}","source_commit":"${SOURCE_COMMIT}",` +
      `"work_ref":"${WORK_REF_ADD}","__proto__":{"admin":true}}`;
    expect(parseProjectSourceWriteTarget(pollutedString)).toBeNull();
    expect(prototypeBridge.admin).toBeUndefined();

    const pollutedObject = JSON.parse(
      '{"__proto__":{"admin":true},"action":"add_project_file"}',
    ) as Record<string, unknown>;
    expect(Object.keys(pollutedObject)).toContain('__proto__');
    expect(prototypeBridge.admin).toBeUndefined();
    expect(
      serializeProjectSourceWriteTarget({
        ...recordOf(addProjectFileTarget()),
        ...pollutedObject,
      }),
    ).toBeNull();

    const inheritedCarrier = Object.assign(
      Object.create({ extra: 1 }),
      recordOf(addProjectFileTarget()),
    );
    expect(serializeProjectSourceWriteTarget(inheritedCarrier)).toBeNull();
    expect(parseProjectSourceWriteTarget(inheritedCarrier)).toBeNull();
    expect(prototypeBridge.admin).toBeUndefined();
    expect(prototypeBridge.extra).toBeUndefined();
  });

  it('fails closed without throwing on hostile proxies and cyclic records', () => {
    const hostile = new Proxy(
      {},
      {
        getPrototypeOf() {
          throw new Error('boom');
        },
        getOwnPropertyDescriptor() {
          throw new Error('boom');
        },
        ownKeys() {
          throw new Error('boom');
        },
      },
    );
    expect(() => serializeProjectSourceWriteTarget(hostile)).not.toThrow();
    expect(serializeProjectSourceWriteTarget(hostile)).toBeNull();
    expect(() => parseProjectSourceWriteTarget(hostile)).not.toThrow();
    expect(parseProjectSourceWriteTarget(hostile)).toBeNull();
    expect(() =>
      projectSourceWriteKeyMatches(
        ADD_OPERATION_KEY,
        hostile as unknown as ProjectSourceWriteTarget,
      ),
    ).not.toThrow();
    expect(
      projectSourceWriteKeyMatches(
        ADD_OPERATION_KEY,
        hostile as unknown as ProjectSourceWriteTarget,
      ),
    ).toBe(false);

    const cyclic: Record<string, unknown> = recordOf(addProjectFileTarget());
    cyclic.self = cyclic;
    expect(() => serializeProjectSourceWriteTarget(cyclic)).not.toThrow();
    expect(serializeProjectSourceWriteTarget(cyclic)).toBeNull();
    expect(() =>
      parseProjectSourceWriteTarget(`${TARGET_PREFIX}{"action":"add_project_file",`),
    ).not.toThrow();
    expect(
      parseProjectSourceWriteTarget(`${TARGET_PREFIX}{"action":"add_project_file",`),
    ).toBeNull();
  });
});

describe('bounds and detachment', () => {
  it('rejects targets above the maximum length', () => {
    expect(ADD_TARGET_STRING.length).toBeLessThan(2048);
    expect(parseProjectSourceWriteTarget(`${TARGET_PREFIX}${'x'.repeat(4096)}`)).toBeNull();
    expect(parseProjectSourceWriteTarget(`${ADD_TARGET_STRING}${' '.repeat(2000)}`)).toBeNull();
    expect(
      serializeProjectSourceWriteTarget({
        ...addProjectFileTarget(),
        work_ref: `WS:${'A'.repeat(64)}`,
      }),
    ).not.toBeNull();
  });

  it('returns a detached plain object that aliases neither the input nor prior results', () => {
    const input = addProjectFileTarget();
    const parsed = parseProjectSourceWriteTarget(ADD_TARGET_STRING) as ProjectSourceWriteTarget;
    expect(parsed).toEqual(input);
    expect(parsed).not.toBe(input);
    expect(Object.getPrototypeOf(parsed)).toBe(Object.prototype);
    (parsed as { work_ref: string }).work_ref = 'MUTATED';
    expect(parseProjectSourceWriteTarget(ADD_TARGET_STRING)).toEqual(input);

    const serialized = serializeProjectSourceWriteTarget(input) as string;
    const reparsed = parseProjectSourceWriteTarget(serialized) as ProjectSourceWriteTarget;
    expect(reparsed).not.toBe(input);
    (reparsed as { source_commit: string }).source_commit = 'deadbeef';
    expect(serializeProjectSourceWriteTarget(input)).toBe(serialized);
  });
});

describe('full-string identity boundaries',()=>{
 const target={action:'add_project_file' as const,work_ref:'WS:PROJECT-ONE',source_commit:'a'.repeat(40),base_revision:'b'.repeat(64),request_sha256:'c'.repeat(64),expected_preference_revision:null};
 it.each(['work_ref','source_commit','base_revision','request_sha256'])('rejects a final-newline %s inside otherwise canonical JSON',(field)=>{
  const value={...target,[field]:String(target[field as keyof typeof target])+'\n'};
  expect(serializeProjectSourceWriteTarget(value)).toBeNull();expect(parseProjectSourceWriteTarget(value)).toBeNull();
 });
 it('rejects final-newline original IDs and expected preference revisions',()=>{
  expect(projectSourceWriteKeyMatches('mmos-project-file-add-'+'a'.repeat(40)+'\n',target)).toBe(false);
  expect(serializeProjectSourceWriteTarget({...target,action:'set_project_communication_preference',expected_preference_revision:'b'.repeat(64)+'\n'})).toBeNull();
 });
});
