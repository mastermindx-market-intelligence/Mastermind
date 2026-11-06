import { describe, expect, it } from 'vitest';
import {
  NATIVE_EXECUTIVE_REASON_VALUES,
  NATIVE_PROGRAMS_READ_PHASE_VALUES,
  NATIVE_EXECUTIVE_STATUS_SCHEMA,
  decodeNativeExecutiveObservation,
} from './native-executive-observation';
import type { NativeExecutiveObservation } from './native-executive-observation';

type V1Observation = Extract<NativeExecutiveObservation, { wire: 'v1' }>;

function v1Raw(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const raw: Record<string, unknown> = {
    schema: NATIVE_EXECUTIVE_STATUS_SCHEMA,
    generation: 12,
    available: true,
    configured: true,
    reason: 'AVAILABLE',
    programs_read: { phase: 'READY', http_status: 200 },
  };
  for (const key of Object.keys(overrides)) {
    if (overrides[key] === undefined) {
      delete raw[key];
    } else {
      raw[key] = overrides[key];
    }
  }
  return raw;
}

function expectRejected(raw: unknown): void {
  expect(decodeNativeExecutiveObservation(raw)).toBeNull();
}

describe('decodeNativeExecutiveObservation', () => {
  describe('legacy payloads', () => {
    it('decodes an available legacy payload at generation zero', () => {
      const observation = decodeNativeExecutiveObservation({ generation: 0, available: true });
      expect(observation).toEqual({
        wire: 'legacy',
        generation: 0,
        available: true,
        configured: null,
        reason: null,
        programsRead: null,
      });
      expect(observation?.wire).toBe('legacy');
    });

    it('decodes an unavailable legacy payload', () => {
      const observation = decodeNativeExecutiveObservation({ generation: 7, available: false });
      expect(observation).toEqual({
        wire: 'legacy',
        generation: 7,
        available: false,
        configured: null,
        reason: null,
        programsRead: null,
      });
    });

    it('normalizes legacy payloads with null configured, reason and programsRead', () => {
      const observation = decodeNativeExecutiveObservation({ generation: 3, available: true });
      expect(observation?.configured).toBeNull();
      expect(observation?.reason).toBeNull();
      expect(observation?.programsRead).toBeNull();
    });

    it('accepts null-prototype raw objects', () => {
      const raw = Object.create(null) as Record<string, unknown>;
      raw['generation'] = 4;
      raw['available'] = true;
      const observation = decodeNativeExecutiveObservation(raw);
      expect(observation?.wire).toBe('legacy');
      expect(observation?.generation).toBe(4);
    });

    it('accepts the maximum safe integer generation', () => {
      const observation = decodeNativeExecutiveObservation({
        generation: Number.MAX_SAFE_INTEGER,
        available: false,
      });
      expect(observation?.generation).toBe(Number.MAX_SAFE_INTEGER);
    });
  });

  describe('v1 payloads', () => {
    it('decodes an available observation with a READY programs read', () => {
      const observation = decodeNativeExecutiveObservation(v1Raw());
      expect(observation).toEqual({
        wire: 'v1',
        generation: 12,
        available: true,
        configured: true,
        reason: 'AVAILABLE',
        programsRead: { phase: 'READY', httpStatus: 200 },
      });
    });

    it('camelCases programs_read into programsRead and http_status into httpStatus', () => {
      const observation = decodeNativeExecutiveObservation(v1Raw()) as V1Observation;
      expect(Object.keys(observation.programsRead).sort()).toEqual(['httpStatus', 'phase']);
      expect(observation.programsRead.httpStatus).toBe(200);
    });

    it('decodes an expired observation with a pending programs read', () => {
      const observation = decodeNativeExecutiveObservation(
        v1Raw({
          available: false,
          reason: 'EXPIRED',
          programs_read: { phase: 'PENDING', http_status: null },
        }),
      );
      expect(observation?.available).toBe(false);
      expect(observation?.configured).toBe(true);
      expect(observation?.reason).toBe('EXPIRED');
      expect(observation?.programsRead).toEqual({ phase: 'PENDING', httpStatus: null });
    });

    it('decodes an unconfigured observation', () => {
      const observation = decodeNativeExecutiveObservation(
        v1Raw({
          available: false,
          configured: false,
          reason: 'UNCONFIGURED',
          programs_read: { phase: 'NOT_OBSERVED', http_status: null },
        }),
      );
      expect(observation?.configured).toBe(false);
      expect(observation?.reason).toBe('UNCONFIGURED');
      expect(observation?.programsRead).toEqual({ phase: 'NOT_OBSERVED', httpStatus: null });
    });

    it('decodes a generation-exhausted observation', () => {
      const observation = decodeNativeExecutiveObservation(
        v1Raw({
          available: false,
          configured: false,
          reason: 'GENERATION_EXHAUSTED',
          programs_read: { phase: 'TIMEOUT', http_status: null },
        }),
      );
      expect(observation?.available).toBe(false);
      expect(observation?.configured).toBe(false);
      expect(observation?.reason).toBe('GENERATION_EXHAUSTED');
    });

    it('decodes an HTTP_FAILURE programs read at 503', () => {
      const observation = decodeNativeExecutiveObservation(
        v1Raw({
          available: false,
          reason: 'NOT_ESTABLISHED',
          programs_read: { phase: 'HTTP_FAILURE', http_status: 503 },
        }),
      );
      expect(observation?.programsRead).toEqual({ phase: 'HTTP_FAILURE', httpStatus: 503 });
    });

    it('decodes NETWORK_FAILURE, TIMEOUT and AUTH_UNAVAILABLE programs reads with null status', () => {
      const phases = ['NETWORK_FAILURE', 'TIMEOUT', 'AUTH_UNAVAILABLE'] as const;
      for (const phase of phases) {
        const observation = decodeNativeExecutiveObservation(
          v1Raw({
            available: false,
            reason: 'EXPIRED',
            programs_read: { phase, http_status: null },
          }),
        );
        expect(observation?.programsRead).toEqual({ phase, httpStatus: null });
      }
    });

    it('accepts inclusive 2xx boundaries for READY, BODY_FAILURE and INVALID_RESPONSE', () => {
      const phases = ['READY', 'BODY_FAILURE', 'INVALID_RESPONSE'] as const;
      for (const phase of phases) {
        for (const status of [200, 250, 299]) {
          const observation = decodeNativeExecutiveObservation(
            v1Raw({ programs_read: { phase, http_status: status } }),
          );
          expect(observation?.programsRead).toEqual({ phase, httpStatus: status });
        }
      }
    });

    it('accepts 1xx and 5xx boundaries for HTTP_FAILURE', () => {
      for (const status of [100, 199, 300, 500, 599]) {
        const observation = decodeNativeExecutiveObservation(
          v1Raw({
            available: false,
            reason: 'EXPIRED',
            programs_read: { phase: 'HTTP_FAILURE', http_status: status },
          }),
        );
        expect(observation?.programsRead).toEqual({ phase: 'HTTP_FAILURE', httpStatus: status });
      }
    });

    it('accepts the minimum (0) and maximum safe integer generations', () => {
      const min = decodeNativeExecutiveObservation(v1Raw({ generation: 0 }));
      const max = decodeNativeExecutiveObservation(v1Raw({ generation: Number.MAX_SAFE_INTEGER }));
      expect(min?.generation).toBe(0);
      expect(max?.generation).toBe(Number.MAX_SAFE_INTEGER);
    });
  });

  describe('cross-field invariants', () => {
    it('rejects reason AVAILABLE with available false', () => {
      expectRejected(v1Raw({ available: false }));
    });

    it('rejects available true without reason AVAILABLE', () => {
      expectRejected(
        v1Raw({
          available: true,
          configured: true,
          reason: 'EXPIRED',
          programs_read: { phase: 'PENDING', http_status: null },
        }),
      );
      expectRejected(
        v1Raw({
          available: true,
          configured: true,
          reason: 'NOT_ESTABLISHED',
          programs_read: { phase: 'HTTP_FAILURE', http_status: 503 },
        }),
      );
    });

    it('rejects available true with configured false', () => {
      expectRejected(v1Raw({ available: true, configured: false, reason: 'AVAILABLE' }));
    });

    it('rejects configured false with reasons other than UNCONFIGURED or GENERATION_EXHAUSTED', () => {
      const programs = { phase: 'PENDING', http_status: null };
      const reasons = [
        'EXPIRED',
        'AUTHORIZING',
        'TOKEN_EXCHANGE_FAILED',
        'AUTH_BROWSER_UNAVAILABLE',
      ];
      for (const reason of reasons) {
        expectRejected(
          v1Raw({ available: false, configured: false, reason, programs_read: programs }),
        );
      }
    });

    it('rejects configured true with UNCONFIGURED or GENERATION_EXHAUSTED', () => {
      expectRejected(
        v1Raw({
          available: false,
          configured: true,
          reason: 'UNCONFIGURED',
          programs_read: { phase: 'NOT_OBSERVED', http_status: null },
        }),
      );
      expectRejected(
        v1Raw({
          available: false,
          configured: true,
          reason: 'GENERATION_EXHAUSTED',
          programs_read: { phase: 'NOT_OBSERVED', http_status: null },
        }),
      );
    });
  });

  describe('generation validation', () => {
    it('rejects non-safe-integer generations', () => {
      const generations = [
        Number.NaN,
        Number.POSITIVE_INFINITY,
        Number.NEGATIVE_INFINITY,
        -1,
        1.5,
        Number.MAX_SAFE_INTEGER + 1,
        2 ** 53,
      ];
      for (const generation of generations) {
        expectRejected(v1Raw({ generation }));
        expectRejected({ generation, available: true });
      }
    });

    it('rejects non-numeric generations', () => {
      const generations = ['3', null, undefined, true];
      for (const generation of generations) {
        expectRejected(v1Raw({ generation }));
        expectRejected({ generation, available: true });
      }
    });

    it('collapses negative zero generation to positive zero', () => {
      const observation = decodeNativeExecutiveObservation({ generation: -0, available: true });
      expect(observation).not.toBeNull();
      expect(observation?.generation).toBe(0);
      expect(Object.is(observation?.generation, -0)).toBe(false);
    });
  });

  describe('schema and enum validation', () => {
    it('rejects a wrong or missing schema discriminator', () => {
      expectRejected(v1Raw({ schema: 'mastermind.native_executive_status.v2' }));
      expectRejected(v1Raw({ schema: 'mastermind.native_executive_status.V1' }));
      expectRejected(v1Raw({ schema: 42 }));
      expectRejected(v1Raw({ schema: null }));
      expectRejected(v1Raw({ schema: undefined }));
    });

    it('rejects reasons outside the closed set', () => {
      const programs = { phase: 'READY', http_status: 200 };
      const reasons = ['available', 'AVAILABLE ', 'EXCHANGE', 'FOO', '', 42, null, undefined];
      for (const reason of reasons) {
        expectRejected(v1Raw({ reason, programs_read: programs }));
      }
    });

    it('exposes the full closed reason and phase sets', () => {
      expect([...NATIVE_EXECUTIVE_REASON_VALUES].sort()).toEqual([
        'AUTHORIZATION_REFUSED',
        'AUTHORIZING',
        'AUTH_BROWSER_UNAVAILABLE',
        'AUTH_TRANSACTION_EXPIRED',
        'AVAILABLE',
        'EXCHANGING',
        'EXPIRED',
        'GENERATION_EXHAUSTED',
        'NOT_ESTABLISHED',
        'TOKEN_EXCHANGE_FAILED',
        'TOKEN_RESPONSE_INVALID',
        'UNCONFIGURED',
      ]);
      expect([...NATIVE_PROGRAMS_READ_PHASE_VALUES].sort()).toEqual([
        'AUTH_UNAVAILABLE',
        'BODY_FAILURE',
        'HTTP_FAILURE',
        'INVALID_RESPONSE',
        'NETWORK_FAILURE',
        'NOT_OBSERVED',
        'PENDING',
        'READY',
        'TIMEOUT',
      ]);
    });
  });

  describe('programs_read validation', () => {
    it('rejects non-object programs_read values', () => {
      const values = [null, undefined, 'READY', 200, true, [], [{ phase: 'READY', http_status: 200 }]];
      for (const programs_read of values) {
        expectRejected(v1Raw({ programs_read }));
      }
    });

    it('rejects wrong, missing or extra programs_read keys', () => {
      expectRejected(v1Raw({ programs_read: { phase: 'READY', httpStatus: 200 } }));
      expectRejected(v1Raw({ programs_read: { phase: 'READY' } }));
      expectRejected(v1Raw({ programs_read: { http_status: 200 } }));
      expectRejected(v1Raw({ programs_read: { phase: 'READY', http_status: 200, extra: 1 } }));
      expectRejected(v1Raw({ programs_read: { phase: 'READY', http_status: undefined } }));
    });

    it('rejects phases outside the closed set', () => {
      const phases = ['ready', 'OBSERVED', '', 42, null, undefined];
      for (const phase of phases) {
        expectRejected(v1Raw({ programs_read: { phase, http_status: null } }));
      }
    });

    it('requires an integer 2xx status for READY, BODY_FAILURE and INVALID_RESPONSE', () => {
      const phases = ['READY', 'BODY_FAILURE', 'INVALID_RESPONSE'] as const;
      const statuses = [null, 199, 300, 503, 0, 2.5, Number.NaN, '200', undefined];
      for (const phase of phases) {
        for (const http_status of statuses) {
          expectRejected(v1Raw({ programs_read: { phase, http_status } }));
        }
      }
    });

    it('rejects null, 2xx and out-of-range statuses for HTTP_FAILURE', () => {
      const statuses = [null, 99, 200, 204, 299, 600, 1000, 2.5, Number.NaN, '503'];
      for (const http_status of statuses) {
        expectRejected(v1Raw({ programs_read: { phase: 'HTTP_FAILURE', http_status } }));
      }
    });

    it('requires null status for the status-free phases', () => {
      const phases = [
        'NOT_OBSERVED',
        'PENDING',
        'AUTH_UNAVAILABLE',
        'NETWORK_FAILURE',
        'TIMEOUT',
      ] as const;
      for (const phase of phases) {
        for (const http_status of [0, 200, 503, 599]) {
          expectRejected(v1Raw({ programs_read: { phase, http_status } }));
        }
      }
    });
  });

  describe('shape and accessor rejection', () => {
    it('rejects primitives, functions and other non-plain values', () => {
      const values = [
        null,
        undefined,
        0,
        -1,
        Number.NaN,
        '',
        'legacy',
        true,
        false,
        Symbol('x'),
        () => undefined,
      ];
      for (const value of values) {
        expectRejected(value);
      }
    });

    it('rejects arrays that mimic payloads', () => {
      expectRejected(['generation', 'available']);
      expectRejected([{ generation: 0, available: true }]);
      expectRejected([0, true]);
      expectRejected([]);
    });

    it('rejects non-plain objects with matching own keys', () => {
      class LegacyLike {
        generation = 0;
        available = true;
      }
      expectRejected(new LegacyLike());
      expectRejected(new Date());
      expectRejected(new Map());
      const functionProto = Object.create(() => undefined) as Record<string, unknown>;
      functionProto['generation'] = 0;
      functionProto['available'] = true;
      expectRejected(functionProto);
    });

    it('rejects symbol-keyed and unknown extra keys', () => {
      const withSymbol: Record<PropertyKey, unknown> = { generation: 0, available: true };
      withSymbol[Symbol('extra')] = 1;
      expectRejected(withSymbol);
      expectRejected({ generation: 0, available: true, credential: 'secret' });
      expectRejected({ generation: 0, available: false, tokens: {} });
      expectRejected({ generation: 0, availability: true });
      expectRejected({ generation: 0 });
      expectRejected({ available: true });
      expectRejected(v1Raw({ extra: true }));
    });

    it('rejects accessor properties without evaluating them', () => {
      let getterReads = 0;
      const raw: Record<string, unknown> = { generation: 0, available: true };
      Object.defineProperty(raw, 'generation', {
        enumerable: true,
        configurable: true,
        get() {
          getterReads += 1;
          return 0;
        },
      });
      expect(decodeNativeExecutiveObservation(raw)).toBeNull();
      expect(getterReads).toBe(0);
    });

    it('rejects nested accessor properties without evaluating them', () => {
      let phaseReads = 0;
      const programs: Record<string, unknown> = { phase: 'READY', http_status: 200 };
      Object.defineProperty(programs, 'phase', {
        enumerable: true,
        configurable: true,
        get() {
          phaseReads += 1;
          return 'READY';
        },
      });
      expect(decodeNativeExecutiveObservation(v1Raw({ programs_read: programs }))).toBeNull();
      expect(phaseReads).toBe(0);
    });

    it('rejects setter-only descriptors without invoking them', () => {
      let setterCalls = 0;
      const raw: Record<string, unknown> = { available: true };
      Object.defineProperty(raw, 'generation', {
        enumerable: true,
        configurable: true,
        set(_value: unknown) {
          setterCalls += 1;
        },
      });
      expect(decodeNativeExecutiveObservation(raw)).toBeNull();
      expect(setterCalls).toBe(0);
    });

    it('rejects throwing proxies without propagating the throw', () => {
      const throwingGet = new Proxy(
        { generation: 0, available: true },
        {
          get() {
            throw new Error('get trap refused');
          },
        },
      );
      expect(() => decodeNativeExecutiveObservation(throwingGet)).not.toThrow();
      expect(decodeNativeExecutiveObservation(throwingGet)).toBeNull();

      const throwingKeys = new Proxy(
        { generation: 0, available: true },
        {
          ownKeys() {
            throw new Error('ownKeys trap refused');
          },
        },
      );
      expect(() => decodeNativeExecutiveObservation(throwingKeys)).not.toThrow();
      expect(decodeNativeExecutiveObservation(throwingKeys)).toBeNull();
    });

    it('accepts an honest proxy over a plain payload', () => {
      const observation = decodeNativeExecutiveObservation(
        new Proxy({ generation: 2, available: true }, {}),
      );
      expect(observation?.wire).toBe('legacy');
      expect(observation?.generation).toBe(2);
    });
  });

  describe('immutability and detachment', () => {
    it('deeply freezes decoded observations', () => {
      const legacy = decodeNativeExecutiveObservation({ generation: 1, available: true });
      expect(Object.isFrozen(legacy)).toBe(true);

      const v1 = decodeNativeExecutiveObservation(v1Raw()) as V1Observation;
      expect(Object.isFrozen(v1)).toBe(true);
      expect(Object.isFrozen(v1.programsRead)).toBe(true);
    });

    it('keeps decoded output unchanged when the input is mutated afterwards', () => {
      const raw = v1Raw();
      const observation = decodeNativeExecutiveObservation(raw);
      expect(observation?.generation).toBe(12);
      raw['generation'] = 99;
      raw['reason'] = 'EXPIRED';
      const programs = raw['programs_read'] as Record<string, unknown>;
      programs['phase'] = 'NETWORK_FAILURE';
      programs['http_status'] = null;
      expect(observation?.generation).toBe(12);
      expect(observation?.reason).toBe('AVAILABLE');
      expect(observation?.programsRead).toEqual({ phase: 'READY', httpStatus: 200 });
    });

    it('keeps legacy output detached from later input mutation', () => {
      const raw: Record<string, unknown> = { generation: 5, available: true };
      const observation = decodeNativeExecutiveObservation(raw);
      raw['available'] = false;
      raw['generation'] = 0;
      expect(observation?.available).toBe(true);
      expect(observation?.generation).toBe(5);
    });

    it('ignores attempts to mutate the frozen decoded output', () => {
      const observation = decodeNativeExecutiveObservation(v1Raw());
      try {
        (observation as { generation: number }).generation = 99;
        (observation?.programsRead as { phase: string }).phase = 'TIMEOUT';
      } catch {
        // Strict-mode assignment to a frozen object throws; either way the
        // values below must be unchanged.
      }
      expect(observation?.generation).toBe(12);
      expect(observation?.programsRead?.phase).toBe('READY');
    });

    it('returns independent deep-equal results for repeated decodes', () => {
      const raw = v1Raw();
      const first = decodeNativeExecutiveObservation(raw) as V1Observation;
      const second = decodeNativeExecutiveObservation(raw) as V1Observation;
      expect(first).not.toBe(second);
      expect(first).toEqual(second);
      expect(first.programsRead).not.toBe(second.programsRead);
    });

    it('does not leak raw keys or values into the normalized output', () => {
      const observation = decodeNativeExecutiveObservation(v1Raw({ schema: 'x' }));
      expect(observation).toBeNull();
      const decoded = decodeNativeExecutiveObservation(v1Raw()) as V1Observation;
      expect(Object.keys(decoded).sort()).toEqual([
        'available',
        'configured',
        'generation',
        'programsRead',
        'reason',
        'wire',
      ]);
      expect(Object.keys(decoded.programsRead).sort()).toEqual(['httpStatus', 'phase']);
    });
  });
});
