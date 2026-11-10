import {expect, it, vi} from 'vitest';
import {bindNativeWorkAuthorization, decodeWorkAuthorization} from './native-work-authorization';
import type {RawClient} from './host';
import fixture from './fixtures/native-work-authorization-source.json';

it('admits only the two read-only status tuples', () => {
  for (const value of [fixture.active, fixture.refused]) {
    expect(decodeWorkAuthorization(value)).toEqual(value);
    expect(Object.isFrozen(decodeWorkAuthorization(value))).toBe(true);
  }
});

it('rejects earlier ELIGIBLE metadata, unsafe generations and open shapes', () => {
  const available = fixture.active;
  const getter = Object.defineProperty({...available}, 'generation', {get() { throw Error('PRIVATE_GETTER'); }});
  for (const value of [fixture.initial, {...available, token:'no'}, {...available, state:'ADMIN_ACTION_REQUIRED'},
    {...available, generation:NaN}, {...available, generation:2**53}, {...available, generation:-1},
    getter, Object.create(available), null]) {
    expect(() => decodeWorkAuthorization(value)).toThrow('WORK_AUTHORIZATION_UNAVAILABLE');
  }
});

function setup() {
  let rawEpoch = 1;
  let hostEpoch = 2;
  let finish!: (value: unknown) => void;
  const pending = new Promise(resolve => { finish = resolve; });
  const raw = {
    getState: () => ({status:'signed_in', reason:null, acquisition:true, content:true}),
    invalidationGeneration: () => rawEpoch,
    readWorkAuthorization: vi.fn(() => pending),
  } as unknown as RawClient;
  const owner = bindNativeWorkAuthorization(raw, () => hostEpoch)!;
  return {raw, owner, finish, bumpRaw: () => {rawEpoch++;}, bumpHost: () => {hostEpoch++;}};
}

it('exposes only the incumbent read operation', async () => {
  const {owner, finish} = setup();
  expect(Object.keys(owner)).toEqual(['read']);
  const result = owner.read({signal:new AbortController().signal});
  finish(fixture.refused);
  await expect(result).resolves.toEqual(fixture.refused);
});

it.each(['raw', 'host', 'abort'] as const)('rejects late metadata after %s withdrawal', async kind => {
  const {owner, finish, bumpRaw, bumpHost} = setup();
  const controller = new AbortController();
  const result = owner.read({signal:controller.signal});
  if (kind === 'raw') bumpRaw();
  if (kind === 'host') bumpHost();
  if (kind === 'abort') controller.abort();
  finish(fixture.refused);
  await expect(result).rejects.toThrow('WORK_AUTHORIZATION_UNAVAILABLE');
});
