import { describe, expect, it } from 'vitest';
import { decodeNativeDraftContinuity } from './native-draft-continuity';
import type { NativeDraftContinuity } from './native-draft-continuity';

const CONTINUITY_SCHEMA = 'mastermind.native_draft_continuity.v1';
const OWNER_INSTANCE = '0123456789abcdef'.repeat(2);
const PRINCIPAL_SCOPE = '0f1e2d3c4b5a6978'.repeat(4);
const MAX_VALID_UNTIL_MS = 8640000000000000;
const FIELD_KEYS = [
  'schema', 'owner_instance', 'privacy_epoch', 'phase', 'cause', 'principal_scope', 'valid_until_ms',
];
const PHASES = ['UNQUALIFIED', 'QUALIFIED', 'EXPIRED', 'REAUTHENTICATING', 'WITHDRAWN'];
const CAUSES = [
  'OWNER_UNQUALIFIED', 'OWNER_QUALIFIED', 'TOKEN_EXPIRED',
  'REAUTHENTICATION', 'EXPLICIT_LOGOUT', 'PRINCIPAL_CHANGED', 'EPOCH_EXHAUSTED',
];
const QUALIFIED_CAUSES = ['OWNER_QUALIFIED', 'PRINCIPAL_CHANGED'];
const LIFECYCLE_CAUSES: Record<string, string[]> = {
  UNQUALIFIED: ['OWNER_UNQUALIFIED'],
  EXPIRED: ['TOKEN_EXPIRED'],
  REAUTHENTICATING: ['REAUTHENTICATION'],
  WITHDRAWN: ['EXPLICIT_LOGOUT', 'EPOCH_EXHAUSTED'],
};

type Row = Record<string, unknown>;

function continuityRecord(overrides: Row = {}): Row {
  return {
    schema: CONTINUITY_SCHEMA,
    owner_instance: OWNER_INSTANCE,
    privacy_epoch: 7,
    phase: 'QUALIFIED',
    cause: 'OWNER_QUALIFIED',
    principal_scope: PRINCIPAL_SCOPE,
    valid_until_ms: 1794000000000,
    ...overrides,
  };
}

function lifecycleRecord(phase: string, cause: string, overrides: Row = {}): Row {
  return continuityRecord({
    phase,
    cause,
    privacy_epoch: 0,
    principal_scope: null,
    valid_until_ms: null,
    ...overrides,
  });
}

/** Adds an own property to a fixture without touching the other fields. */
function defineField(raw: Row, key: string | symbol, descriptor: PropertyDescriptor): Row {
  Object.defineProperty(raw, key, descriptor);
  return raw;
}

function decodes(raw: unknown): NativeDraftContinuity {
  const decoded = decodeNativeDraftContinuity(raw);
  if (decoded === null) throw new Error('expected a decoded continuity record');
  return decoded;
}

function declines(raw: unknown): void {
  expect(decodeNativeDraftContinuity(raw)).toBeNull();
}

describe('decodeNativeDraftContinuity', () => {
  describe('accepted records', () => {
    it('decodes a QUALIFIED OWNER_QUALIFIED record with the exact field set', () => {
      const decoded = decodes(continuityRecord());
      expect(decoded).toStrictEqual({
        schema: CONTINUITY_SCHEMA,
        owner_instance: OWNER_INSTANCE,
        privacy_epoch: 7,
        phase: 'QUALIFIED',
        cause: 'OWNER_QUALIFIED',
        principal_scope: PRINCIPAL_SCOPE,
        valid_until_ms: 1794000000000,
      });
    });

    it('decodes a QUALIFIED PRINCIPAL_CHANGED record', () => {
      const decoded = decodes(continuityRecord({
        cause: 'PRINCIPAL_CHANGED',
        privacy_epoch: 1,
        valid_until_ms: MAX_VALID_UNTIL_MS,
      }));
      expect(decoded.cause).toBe('PRINCIPAL_CHANGED');
      expect(decoded.privacy_epoch).toBe(1);
      expect(decoded.valid_until_ms).toBe(MAX_VALID_UNTIL_MS);
    });

    it('decodes every lifecycle phase with null scope and null valid_until_ms', () => {
      for (const [phase, allowed] of Object.entries(LIFECYCLE_CAUSES)) {
        const decoded = decodes(lifecycleRecord(phase, allowed[0] as string));
        expect(decoded.phase).toBe(phase);
        expect(decoded.principal_scope).toBeNull();
        expect(decoded.valid_until_ms).toBeNull();
        expect(decoded.privacy_epoch).toBe(0);
      }
    });

    it('accepts the valid_until_ms boundaries 1 and 8640000000000000', () => {
      expect(decodes(continuityRecord({ valid_until_ms: 1 })).valid_until_ms).toBe(1);
      expect(decodes(continuityRecord({ valid_until_ms: MAX_VALID_UNTIL_MS })).valid_until_ms).toBe(MAX_VALID_UNTIL_MS);
    });

    it('accepts privacy_epoch boundaries for qualified and lifecycle phases', () => {
      expect(decodes(continuityRecord({ privacy_epoch: 1 })).privacy_epoch).toBe(1);
      expect(decodes(lifecycleRecord('UNQUALIFIED', 'OWNER_UNQUALIFIED')).privacy_epoch).toBe(0);
      expect(
        decodes(lifecycleRecord('UNQUALIFIED', 'OWNER_UNQUALIFIED', { privacy_epoch: 9007199254740991 })).privacy_epoch,
      ).toBe(9007199254740991);
    });

    it('accepts deep-frozen and sealed input records', () => {
      expect(decodes(Object.freeze(continuityRecord())).privacy_epoch).toBe(7);
      expect(decodes(Object.preventExtensions(continuityRecord({ privacy_epoch: 3 }))).privacy_epoch).toBe(3);
    });

    it('is pure: repeated decodes of one record are equal and the input stays untouched', () => {
      const raw = continuityRecord();
      const snapshot = { ...raw };
      const first = decodes(raw);
      const second = decodes(raw);
      expect(first).toStrictEqual(second);
      expect(raw).toStrictEqual(snapshot);
    });
  });

  describe('exact field closure', () => {
    it('refuses a record missing any required field', () => {
      for (const key of FIELD_KEYS) {
        const raw = continuityRecord();
        delete raw[key];
        declines(raw);
      }
    });

    it('refuses the empty object and unknown extra keys', () => {
      declines({});
      declines(continuityRecord({ draft_ref: 'abc' }));
      declines(continuityRecord({ extra: null }));
    });

    it('refuses symbol keys, including a symbol-keyed expected field name', () => {
      declines(defineField(continuityRecord(), Symbol('draft_ref'), {
        value: 'x', enumerable: true, writable: true, configurable: true,
      }));
      const symbolSchema = continuityRecord();
      delete symbolSchema.schema;
      declines(defineField(symbolSchema, Symbol('schema'), {
        value: CONTINUITY_SCHEMA, enumerable: true, writable: true, configurable: true,
      }));
    });

    it('refuses non-enumerable expected and extra properties', () => {
      const hiddenSchema = continuityRecord();
      Object.defineProperty(hiddenSchema, 'schema', {
        value: CONTINUITY_SCHEMA, enumerable: false, writable: true, configurable: true,
      });
      declines(hiddenSchema);
      declines(defineField(continuityRecord(), 'draft_ref', {
        value: 'abc', enumerable: false, writable: true, configurable: true,
      }));
    });

    it('refuses records whose expected fields are inherited rather than own', () => {
      declines(Object.create(continuityRecord()));
      const inheritedExtra = continuityRecord();
      Object.setPrototypeOf(inheritedExtra, { draft_ref: 'abc' });
      declines(inheritedExtra);
    });

    it('refuses foreign prototypes, null prototypes, arrays and collections', () => {
      class ContinuityRecord {}
      const instance = new ContinuityRecord();
      Object.assign(instance, continuityRecord());
      declines(instance);
      declines(Object.assign(Object.create(null), continuityRecord()));
      declines([continuityRecord()]);
      declines(new Map(Object.entries(continuityRecord())));
      declines(new Date(1794000000000));
    });

    it('refuses non-object input', () => {
      declines(null);
      declines(undefined);
      declines(7);
      declines(CONTINUITY_SCHEMA);
      declines(true);
      declines(() => undefined);
    });
  });

  describe('hostile getters and proxies', () => {
    it('refuses accessor fields without invoking the getter', () => {
      let reads = 0;
      const raw = continuityRecord();
      delete raw.schema;
      Object.defineProperty(raw, 'schema', {
        enumerable: true,
        configurable: true,
        get() {
          reads += 1;
          return CONTINUITY_SCHEMA;
        },
      });
      declines(raw);
      expect(reads).toBe(0);
    });

    it('refuses accessors on other fields without invoking the getter', () => {
      let reads = 0;
      const raw = continuityRecord();
      Object.defineProperty(raw, 'valid_until_ms', {
        enumerable: true,
        configurable: true,
        get() {
          reads += 1;
          return 1794000000000;
        },
      });
      declines(raw);
      expect(reads).toBe(0);
    });

    it('refuses a setter-only accessor', () => {
      let writes = 0;
      const raw = continuityRecord();
      Object.defineProperty(raw, 'privacy_epoch', {
        enumerable: true,
        configurable: true,
        set() {
          writes += 1;
        },
      });
      declines(raw);
      expect(writes).toBe(0);
    });

    it('refuses a toJSON property without invoking it', () => {
      let calls = 0;
      const raw = defineField(continuityRecord(), 'toJSON', {
        value() {
          calls += 1;
          return {};
        },
        enumerable: true, writable: true, configurable: true,
      });
      declines(raw);
      expect(calls).toBe(0);
    });

    it('refuses proxies whose traps throw, returning null safely', () => {
      const target = continuityRecord();
      declines(new Proxy(target, {
        get() {
          throw new Error('hostile get');
        },
      }));
      declines(new Proxy(target, {
        ownKeys() {
          throw new Error('hostile ownKeys');
        },
      }));
      declines(new Proxy(target, {
        getOwnPropertyDescriptor() {
          throw new Error('hostile descriptor');
        },
      }));
      declines(new Proxy(target, {
        getPrototypeOf() {
          throw new Error('hostile prototype');
        },
      }));
    });

    it('refuses proxies whose traps tamper with values or descriptors', () => {
      declines(new Proxy(continuityRecord(), {
        get(target, key) {
          return key === 'privacy_epoch' ? '7' : Reflect.get(target, key);
        },
      }));
      declines(new Proxy(continuityRecord(), {
        get(_target, key) {
          return key === 'cause' ? 'EPOCH_EXHAUSTED' : Reflect.get(_target, key);
        },
      }));
      declines(new Proxy(continuityRecord(), {
        getOwnPropertyDescriptor(target, key) {
          if (key === 'schema') {
            return {
              enumerable: true,
              configurable: true,
              get() {
                return CONTINUITY_SCHEMA;
              },
            };
          }
          return Reflect.getOwnPropertyDescriptor(target, key);
        },
      }));
    });

    it('decodes a transparent proxy over a valid record', () => {
      expect(decodes(new Proxy(continuityRecord(), {})).privacy_epoch).toBe(7);
    });

    it('refuses function and object values in closed fields', () => {
      declines(continuityRecord({ schema: () => CONTINUITY_SCHEMA }));
      declines(continuityRecord({ phase: ['QUALIFIED'] }));
      declines(continuityRecord({ phase: {} }));
      declines(continuityRecord({ principal_scope: { scope: PRINCIPAL_SCOPE } }));
      declines(continuityRecord({ cause: { cause: 'OWNER_QUALIFIED' } }));
      declines(continuityRecord({ owner_instance: ['5f3c9a1d7b2e8046c1d9a3f5e7b90214'] }));
    });
  });

  describe('cross-field closure', () => {
    it('restricts QUALIFIED to OWNER_QUALIFIED and PRINCIPAL_CHANGED', () => {
      for (const cause of CAUSES) {
        if (QUALIFIED_CAUSES.includes(cause)) {
          expect(decodes(continuityRecord({ cause })).cause).toBe(cause);
        } else {
          declines(continuityRecord({ cause }));
        }
      }
    });

    it('restricts each lifecycle phase to its closed cause set', () => {
      for (const [phase, allowed] of Object.entries(LIFECYCLE_CAUSES)) {
        for (const cause of CAUSES) {
          if (allowed.includes(cause)) {
            expect(decodes(lifecycleRecord(phase, cause)).cause).toBe(cause);
          } else {
            declines(lifecycleRecord(phase, cause));
          }
        }
      }
    });

    it('refuses unknown phase and cause strings', () => {
      declines(continuityRecord({ phase: 'MIGRATED' }));
      declines(continuityRecord({ phase: 'qualified' }));
      declines(continuityRecord({ phase: 'QUALIFIED ' }));
      declines(continuityRecord({ phase: 'QUALIFIED\n' }));
      declines(continuityRecord({ cause: 'OWNER_QUALIFIED_FUTURE' }));
      declines(continuityRecord({ cause: 'owner_qualified' }));
    });

    it('requires privacy_epoch >= 1 for QUALIFIED', () => {
      declines(continuityRecord({ privacy_epoch: 0 }));
      expect(decodes(continuityRecord({ privacy_epoch: 1 })).privacy_epoch).toBe(1);
    });

    it('requires a 64-lowercase-hex principal_scope for QUALIFIED', () => {
      for (const scope of [
        null, '', '0'.repeat(63), '0'.repeat(65), '0F1E2D3C4B5A6978'.repeat(4),
        'g'.repeat(64), `${'0'.repeat(64)}\n`, 12345, `${PRINCIPAL_SCOPE} `,
      ]) {
        declines(continuityRecord({ principal_scope: scope }));
      }
      expect(decodes(continuityRecord()).principal_scope).toBe(PRINCIPAL_SCOPE);
    });

    it('requires valid_until_ms within 1..8640000000000000 for QUALIFIED', () => {
      for (const until of [
        null, 0, -1, 8640000000000001, 9007199254740991, 1.5,
        Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, '1794000000000', true,
      ]) {
        declines(continuityRecord({ valid_until_ms: until }));
      }
      expect(decodes(continuityRecord({ valid_until_ms: MAX_VALID_UNTIL_MS })).valid_until_ms).toBe(MAX_VALID_UNTIL_MS);
    });

    it('requires null scope and valid_until_ms for every other phase', () => {
      for (const phase of PHASES) {
        if (phase === 'QUALIFIED') continue;
        const cause = LIFECYCLE_CAUSES[phase]![0] as string;
        declines(continuityRecord({ phase, cause, principal_scope: PRINCIPAL_SCOPE, valid_until_ms: null }));
        declines(continuityRecord({ phase, cause, principal_scope: null, valid_until_ms: 1794000000000 }));
        declines(continuityRecord({ phase, cause, principal_scope: PRINCIPAL_SCOPE, valid_until_ms: 1794000000000 }));
      }
    });
  });

  describe('closed field formats', () => {
    it('refuses schema values other than the exact schema constant', () => {
      declines(continuityRecord({ schema: 'mastermind.native_draft_continuity.v2' }));
      declines(continuityRecord({ schema: 'MASTERMIND.NATIVE_DRAFT_CONTINUITY.V1' }));
      declines(continuityRecord({ schema: `${CONTINUITY_SCHEMA}\n` }));
      declines(continuityRecord({ schema: 1 }));
      declines(continuityRecord({ schema: null }));
    });

    it('refuses owner_instance values that are not exactly 32 lowercase hex', () => {
      for (const owner of [
        '', 'a'.repeat(31), 'a'.repeat(33), 'A'.repeat(32), 'g'.repeat(32),
        `${'a'.repeat(32)}\n`, ` ${'a'.repeat(32)}`, `${'a'.repeat(31)}\n`, 12345, null,
      ]) {
        declines(continuityRecord({ owner_instance: owner }));
      }
      expect(decodes(continuityRecord()).owner_instance).toBe(OWNER_INSTANCE);
    });

    it('refuses unsafe or fractional privacy_epoch values on any phase', () => {
      for (const epoch of [
        -1, 0.5, 7.5, '7', true, false, Number.NaN, Number.POSITIVE_INFINITY,
        Number.NEGATIVE_INFINITY, 9007199254740992, null, [],
      ]) {
        declines(continuityRecord({ privacy_epoch: epoch }));
        declines(lifecycleRecord('EXPIRED', 'TOKEN_EXPIRED', { privacy_epoch: epoch }));
      }
    });

    it('refuses non-null or non-integer valid_until_ms and non-null scope on lifecycle phases', () => {
      declines(lifecycleRecord('UNQUALIFIED', 'OWNER_UNQUALIFIED', { valid_until_ms: 1794000000000 }));
      declines(lifecycleRecord('EXPIRED', 'TOKEN_EXPIRED', { valid_until_ms: 0 }));
      declines(lifecycleRecord('REAUTHENTICATING', 'REAUTHENTICATION', { valid_until_ms: '1794000000000' }));
      declines(lifecycleRecord('WITHDRAWN', 'EPOCH_EXHAUSTED', { valid_until_ms: Number.NaN }));
      declines(lifecycleRecord('WITHDRAWN', 'EPOCH_EXHAUSTED', { principal_scope: PRINCIPAL_SCOPE }));
      declines(lifecycleRecord('UNQUALIFIED', 'OWNER_UNQUALIFIED', { principal_scope: '' }));
    });
  });

  describe('frozen detached results', () => {
    it('returns a deeply frozen plain object with the exact field set', () => {
      const decoded = decodes(continuityRecord());
      expect(Object.isFrozen(decoded)).toBe(true);
      expect(Object.isExtensible(decoded)).toBe(false);
      expect(Object.getPrototypeOf(decoded)).toBe(Object.prototype);
      expect(Object.getOwnPropertySymbols(decoded).length).toBe(0);
      expect(Object.keys(decoded)).toStrictEqual(FIELD_KEYS);
      for (const value of Object.values(decoded)) {
        expect(typeof value === 'object' || typeof value === 'function').toBe(false);
      }
    });

    it('rejects mutation attempts and stays unchanged', () => {
      const decoded = decodes(continuityRecord());
      expect(() => {
        (decoded as unknown as Row).privacy_epoch = 8;
      }).toThrow(TypeError);
      expect(decoded.privacy_epoch).toBe(7);
      expect(() => {
        Object.defineProperty(decoded, 'extra', { value: 1 });
      }).toThrow(TypeError);
      expect(() => {
        delete (decoded as unknown as Row).schema;
      }).toThrow(TypeError);
    });

    it('does not mutate its input and returns an object detached from it', () => {
      const raw = continuityRecord();
      const snapshot = { ...raw };
      const decoded = decodes(raw);
      expect(raw).toStrictEqual(snapshot);
      expect(Object.isExtensible(raw)).toBe(true);
      raw.privacy_epoch = 99;
      raw.phase = 'EXPIRED';
      expect(decoded.privacy_epoch).toBe(7);
      expect(decoded.phase).toBe('QUALIFIED');
    });

    it('returns equal but non-identical results for equal inputs', () => {
      const decoded = decodes(continuityRecord());
      expect(decoded).not.toBe(continuityRecord());
      expect(decoded).toStrictEqual(continuityRecord());
    });
  });
});

it('rejects trailing line terminators on both closed hex identities', () => {
  for (const ending of ["\n", "\r", "\r\n", "\u2028", "\u2029"]) {
    expect(decodeNativeDraftContinuity({ schema: "mastermind.native_draft_continuity.v1", owner_instance: "1".repeat(32)+ending, privacy_epoch: 1, phase: "QUALIFIED", cause: "OWNER_QUALIFIED", principal_scope: "a".repeat(64), valid_until_ms: 5000 })).toBeNull();
    expect(decodeNativeDraftContinuity({ schema: "mastermind.native_draft_continuity.v1", owner_instance: "1".repeat(32), privacy_epoch: 1, phase: "QUALIFIED", cause: "OWNER_QUALIFIED", principal_scope: "a".repeat(64)+ending, valid_until_ms: 5000 })).toBeNull();
  }
});
