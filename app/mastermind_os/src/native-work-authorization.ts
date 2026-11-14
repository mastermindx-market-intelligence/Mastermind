import type {RawClient} from './host';

export type WorkAuthorization = Readonly<{
  schema: 'mastermind.native_work_authorization.v1';
  generation: number;
} & (
  | {state: 'INELIGIBLE'; reason: 'NOT_ELIGIBLE'}
  | {state: 'ADMIN_ACTION_REQUIRED'; reason: 'AUTHORIZATION_REFUSED'}
)>;

export interface NativeWorkAuthorizationOwner {
  read(request: {signal: AbortSignal}): Promise<WorkAuthorization>;
}

export function decodeWorkAuthorization(raw: unknown): WorkAuthorization {
  const unavailable = (): never => { throw Error('WORK_AUTHORIZATION_UNAVAILABLE'); };
  if (!raw || typeof raw !== 'object' || Object.getPrototypeOf(raw) !== Object.prototype) return unavailable();
  const descriptors = Object.getOwnPropertyDescriptors(raw);
  if (Reflect.ownKeys(raw).length !== 4 ||
      !['schema', 'state', 'reason', 'generation'].every(key => descriptors[key] && 'value' in descriptors[key])) {
    return unavailable();
  }
  const value = raw as WorkAuthorization;
  if (value.schema !== 'mastermind.native_work_authorization.v1' ||
      !Number.isSafeInteger(value.generation) || value.generation < 0) return unavailable();
  const {schema, state, reason, generation} = value;
  if (state === 'INELIGIBLE' && reason === 'NOT_ELIGIBLE') return Object.freeze({schema, state, reason, generation});
  if (state === 'ADMIN_ACTION_REQUIRED' && reason === 'AUTHORIZATION_REFUSED') {
    return Object.freeze({schema, state, reason, generation});
  }
  return unavailable();
}

/** This facet exposes a local observation only. */
export function bindNativeWorkAuthorization(client: RawClient, hostEpoch: () => number): NativeWorkAuthorizationOwner | undefined {
  const read = client.readWorkAuthorization;
  const getState = client.getState;
  const generation = client.invalidationGeneration;
  if (!read || !generation) return undefined;

  return {
    async read({signal}) {
      const epoch = hostEpoch();
      const nativeEpoch = generation.call(client);
      const snapshot = getState.call(client);
      const current = () => {
        if (signal.aborted || client.readWorkAuthorization !== read || client.getState !== getState ||
            client.invalidationGeneration !== generation || hostEpoch() !== epoch ||
            !Number.isSafeInteger(nativeEpoch) || nativeEpoch < 0 || generation.call(client) !== nativeEpoch) return false;
        const state = getState.call(client);
        return state.status === 'signed_in' && state.acquisition && state.content &&
          state.status === snapshot.status && state.reason === snapshot.reason &&
          state.acquisition === snapshot.acquisition && state.content === snapshot.content;
      };
      if (!current()) throw Error('WORK_AUTHORIZATION_UNAVAILABLE');
      const result = await read.call(client);
      if (!current()) throw Error('WORK_AUTHORIZATION_UNAVAILABLE');
      return decodeWorkAuthorization(result);
    },
  };
}
