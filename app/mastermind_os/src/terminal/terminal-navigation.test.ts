import { describe, expect, it } from 'vitest';
import { createTerminalBriefsNavigationPort, decodeTerminalBriefsLandingReceipt } from './terminal-navigation';
import type { TerminalBriefsLandingReceipt } from './terminal-navigation';

const FIXED_ERROR = 'TERMINAL_HANDOFF_UNAVAILABLE';
const SCHEMA = 'mastermind.terminal_navigation.v1';
const DESTINATION = 'TERMINAL_BRIEFS';
const OUTCOME = 'HANDOFF_REQUESTED';

const GOOD_RECEIPT: TerminalBriefsLandingReceipt = {
  schema: SCHEMA,
  destination: DESTINATION,
  outcome: OUTCOME,
};

function goodRecord(): Record<string, unknown> {
  return { schema: SCHEMA, destination: DESTINATION, outcome: OUTCOME };
}

/** Test double for the host bridge seam; records every argument vector it receives. */
type InvokeSpy = { calls: unknown[][]; invoke: (command: 'open_terminal_briefs') => Promise<unknown> };

function spyInvoke(behavior: () => unknown): InvokeSpy {
  const calls: unknown[][] = [];
  return {
    calls,
    invoke: (...args: unknown[]) => {
      calls.push(args);
      return Promise.resolve(behavior());
    },
  };
}

async function failureOf(run: Promise<unknown>): Promise<unknown> {
  return run.then(
    () => 'unexpected success',
    (error: unknown) => error,
  );
}

describe('decodeTerminalBriefsLandingReceipt', () => {
  it('accepts the exact receipt and returns a fresh object each call', () => {
    const input = goodRecord();
    const decoded = decodeTerminalBriefsLandingReceipt(input);
    expect(decoded).not.toBe(input);
    expect(decoded).toEqual(GOOD_RECEIPT);
    expect(decodeTerminalBriefsLandingReceipt(input)).not.toBe(decoded);
  });

  it('accepts any key order and a null-prototype detached record', () => {
    const reordered = { outcome: OUTCOME, schema: SCHEMA, destination: DESTINATION };
    expect(decodeTerminalBriefsLandingReceipt(reordered)).toEqual(GOOD_RECEIPT);
    const detached = Object.assign(Object.create(null), goodRecord());
    expect(decodeTerminalBriefsLandingReceipt(detached)).toEqual(GOOD_RECEIPT);
  });

  it('rejects every non-plain-object value', () => {
    const values = [null, undefined, 0, '', 'TERMINAL_BRIEFS', true, [], [GOOD_RECEIPT], new Date(0), new Map(), () => GOOD_RECEIPT];
    for (const value of values) {
      expect(() => decodeTerminalBriefsLandingReceipt(value)).toThrow(FIXED_ERROR);
    }
  });

  it('rejects missing, extra and incorrect receipt fields', () => {
    const missing = [{}, { schema: SCHEMA }, { schema: SCHEMA, destination: DESTINATION }, { destination: DESTINATION, outcome: OUTCOME }];
    const incorrect = [
      { ...goodRecord(), schema: 'mastermind.terminal_navigation.v2' },
      { ...goodRecord(), destination: 'TERMINAL_ALERTS' },
      { ...goodRecord(), outcome: 'NAVIGATED' },
      { ...goodRecord(), schema: 1 },
      { ...goodRecord(), destination: null },
      { ...goodRecord(), outcome: undefined },
    ];
    for (const value of [...missing, ...incorrect, { ...goodRecord(), extra: 'no' }]) {
      expect(() => decodeTerminalBriefsLandingReceipt(value)).toThrow(FIXED_ERROR);
    }
  });

  it('rejects array-shaped, inherited, instance and symbol-extra shapes', () => {
    expect(() => decodeTerminalBriefsLandingReceipt([SCHEMA, DESTINATION, OUTCOME])).toThrow(FIXED_ERROR);
    expect(() => decodeTerminalBriefsLandingReceipt(Object.assign(Object.create({ inherited: true }), goodRecord()))).toThrow(FIXED_ERROR);
    class BorrowedShape {}
    expect(() => decodeTerminalBriefsLandingReceipt(Object.assign(new BorrowedShape(), goodRecord()))).toThrow(FIXED_ERROR);
    expect(() => decodeTerminalBriefsLandingReceipt(Object.assign(goodRecord(), { [Symbol('extra')]: true }))).toThrow(FIXED_ERROR);
  });

  it('rejects prototype-pollution key shapes without polluting Object.prototype', () => {
    const lead = JSON.parse('{"__proto__":{"polluted":true},"schema":"' + SCHEMA + '","destination":"' + DESTINATION + '","outcome":"' + OUTCOME + '"}');
    const tail = JSON.parse('{"schema":"' + SCHEMA + '","destination":"' + DESTINATION + '","__proto__":{"polluted":true},"outcome":"' + OUTCOME + '"}');
    for (const value of [lead, tail]) {
      expect(() => decodeTerminalBriefsLandingReceipt(value)).toThrow(FIXED_ERROR);
    }
    expect(({} as { polluted?: boolean }).polluted).toBeUndefined();
  });

  it('exposes only the fixed message with no input echo', () => {
    const secret = 'secret-input-echo';
    let message = '';
    try {
      decodeTerminalBriefsLandingReceipt({ schema: secret, destination: secret, outcome: secret });
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(FIXED_ERROR);
    expect(message).not.toContain(secret);
  });
});

describe('createTerminalBriefsNavigationPort', () => {
  it('calls invoke exactly once with only the literal command and no other argument', async () => {
    const spy = spyInvoke(() => ({ ...GOOD_RECEIPT }));
    const port = createTerminalBriefsNavigationPort(spy.invoke);
    expect(port.length).toBe(0); // zero-input port: no abort signal, no URL, no options
    await expect(port()).resolves.toEqual(GOOD_RECEIPT);
    expect(spy.calls).toEqual([['open_terminal_briefs']]);
  });

  it('resolves a detached good result to the fixed HANDOFF_REQUESTED receipt only', async () => {
    const spy = spyInvoke(() => Promise.resolve(goodRecord()));
    const receipt = await createTerminalBriefsNavigationPort(spy.invoke)();
    expect(spy.calls).toEqual([['open_terminal_briefs']]);
    expect(receipt.outcome).toBe(OUTCOME);
    expect(receipt).toEqual(GOOD_RECEIPT);
  });

  it('never replays a rejected invocation and never leaks its canary', async () => {
    const canary = 'native-bridge-canary';
    const spy = spyInvoke(() => Promise.reject(new Error(canary)));
    const failure = await failureOf(createTerminalBriefsNavigationPort(spy.invoke)());
    expect(spy.calls).toEqual([['open_terminal_briefs']]);
    expect(failure).toBeInstanceOf(Error);
    expect((failure as Error).message).toBe(FIXED_ERROR);
    expect((failure as Error).message).not.toContain(canary);
    expect((failure as { cause?: unknown }).cause).toBeUndefined();
  });

  it('reports a malformed receipt once with no success and no repeat', async () => {
    const spy = spyInvoke(() => Promise.resolve({ ...GOOD_RECEIPT, outcome: 'NAVIGATED' }));
    const failure = await failureOf(createTerminalBriefsNavigationPort(spy.invoke)());
    expect(spy.calls).toEqual([['open_terminal_briefs']]);
    expect(failure).toBeInstanceOf(Error);
    expect((failure as Error).message).toBe(FIXED_ERROR);
  });

  it('converts a synchronous invoke failure into the fixed safe error without retry', async () => {
    const spy = spyInvoke(() => {
      throw new Error('sync-failure-canary');
    });
    const failure = await failureOf(createTerminalBriefsNavigationPort(spy.invoke)());
    expect(spy.calls).toEqual([['open_terminal_briefs']]);
    expect(failure).toBeInstanceOf(Error);
    expect((failure as Error).message).toBe(FIXED_ERROR);
  });
});
