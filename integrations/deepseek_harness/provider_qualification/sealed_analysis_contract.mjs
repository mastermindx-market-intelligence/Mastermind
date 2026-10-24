/**
 * Offline compatibility fixture for the existing sealed-analysis compiler.
 * This module has no provider transport, admission, lease or credential logic.
 * A matching digest is data consistency, never authority or result acceptance.
 */
import { createHash } from 'node:crypto';

export const FIXTURE_PROVIDER = 'mastermind-sealed-analysis-fixture';
const PROFILE = 'fabric.paid.glm.sealed-input.v1';
const VECTOR_SCHEMA = 'mastermind.dsh_sealed_analysis_fixture/v1';
const sha256 = value => createHash('sha256').update(value, 'utf8').digest('hex');
const record = value => value !== null && typeof value === 'object'
  && [Object.prototype, null].includes(Object.getPrototypeOf(value));
const exactKeys = (value, keys) => record(value)
  && Reflect.ownKeys(value).length === keys.length
  && keys.every(key => Object.hasOwn(value, key));

export class SealedAnalysisFixtureRefused extends Error {
  constructor(code) {
    super(code);
    this.name = 'SealedAnalysisFixtureRefused';
    this.code = code;
  }
}
function requireCondition(condition, code) {
  if (!condition) throw new SealedAnalysisFixtureRefused(code);
}

/** Consume inert vectors emitted by the Python compiler; do not replace it. */
function snapshotVector(vector) {
  const fail = 'SEALED_FIXTURE_VECTOR_REFUSED';
  requireCondition(exactKeys(vector, [
    'schema', 'prompt', 'requestBody', 'descriptor', 'resultText', 'resultSha256',
  ]), fail);
  requireCondition(vector.schema === VECTOR_SCHEMA, fail);
  for (const key of ['prompt', 'requestBody', 'resultText']) {
    requireCondition(typeof vector[key] === 'string' && vector[key].length > 0
      && vector[key].isWellFormed(), fail);
  }
  const descriptor = vector.descriptor;
  requireCondition(record(descriptor)
    && descriptor.schema === 'mastermind.paid_model_execution_descriptor/v1'
    && descriptor.profile_id === PROFILE
    && descriptor.execution_surface === 'glm-model-only'
    && record(descriptor.paid_route)
    && descriptor.paid_route.provider === 'glm'
    && descriptor.request_body_sha256 === sha256(vector.requestBody)
    && descriptor.prompt_sha256 === sha256(vector.prompt)
    && vector.resultSha256 === sha256(vector.resultText), fail);
  let body;
  try { body = JSON.parse(vector.requestBody); } catch { throw new SealedAnalysisFixtureRefused(fail); }
  requireCondition(exactKeys(body, ['input', 'max_output_tokens', 'model', 'stream'])
    && body.stream === false && body.max_output_tokens === 8192
    && typeof body.model === 'string' && body.model.length > 0
    && body.model === descriptor.paid_route.model
    && typeof body.input === 'string', fail);
  const prefix = vector.prompt + '\n\nRESULT_SCHEMA_JSON:\n';
  requireCondition(body.input.startsWith(prefix)
    && sha256(body.input.slice(prefix.length)) === descriptor.result_schema_sha256, fail);
  return Object.freeze({
    prompt: vector.prompt,
    model: body.model,
    requestBody: vector.requestBody,
    requestBodySha256: descriptor.request_body_sha256,
    resultText: vector.resultText,
    resultSha256: vector.resultSha256,
  });
}

/**
 * Validate before native DSH projection can turn file or tool history into text.
 * Only identity-free one-shot user input is supported. Snapshot its primitives
 * before awaiting anything; keep only the caller's actual cancellation signal.
 */
function snapshotRequest(options, vector, nativeProjection = false) {
  const fail = 'SEALED_ANALYSIS_REQUEST_REFUSED';
  requireCondition(record(options), fail);
  const allowed = new Set([
    'provider', 'model', 'messages', 'signal', 'maxTokens',
    'temperature', 'reasoningEffort', 'stop',
  ]);
  for (const key of Reflect.ownKeys(options)) {
    if (!allowed.has(key)) {
      requireCondition(nativeProjection && options[key] === undefined, fail);
    }
  }
  requireCondition(options.provider === FIXTURE_PROVIDER
    && typeof options.model === 'string' && options.model.length > 0
    && options.temperature === undefined && options.reasoningEffort === undefined
    && options.stop === undefined
    && (options.maxTokens === undefined || options.maxTokens === 8192)
    && (options.signal === undefined || options.signal instanceof AbortSignal)
    && Array.isArray(options.messages) && options.messages.length === 1, fail);
  const message = options.messages[0];
  requireCondition(exactKeys(message, ['role', 'content']) && message.role === 'user'
    && Array.isArray(message.content) && message.content.length === 1, fail);
  const block = message.content[0];
  requireCondition(exactKeys(block, ['type', 'text'])
    && block.type === 'text' && block.text === vector.prompt, fail);
  return Object.freeze({
    provider: options.provider,
    model: options.model,
    maxTokens: 8192,
    messages: Object.freeze([Object.freeze({
      role: 'user',
      content: Object.freeze([Object.freeze({ type: 'text', text: block.text })]),
    })]),
    ...(options.signal === undefined ? {} : { signal: options.signal }),
  });
}
function throwIfAborted(signal) {
  if (signal?.aborted) throw new DOMException('Fixture request aborted', 'AbortError');
}

/** Stop awaiting an uncooperative fixture on abort; never start a replacement. */
function readOnce(readFixture, input, signal) {
  throwIfAborted(signal);
  return new Promise((resolve, reject) => {
    const onAbort = () => reject(new DOMException('Fixture request aborted', 'AbortError'));
    signal?.addEventListener('abort', onAbort, { once: true });
    Promise.resolve().then(() => {
      throwIfAborted(signal);
      return readFixture(input);
    }).then(resolve, reject).finally(() => signal?.removeEventListener('abort', onAbort));
  });
}

/**
 * Create one disposable actual-DSH prepared call for OFFLINE fixture execution.
 * Dependencies must be the pinned donor modules. Nothing is globally registered.
 * readFixture supplies already-complete local fixture text; it is not transport.
 * resultText must come from the existing Python result_bytes validator.
 */
export async function prepareSealedAnalysisFixture({ dsh, Context, vector, readFixture }) {
  const sealed = snapshotVector(vector);
  requireCondition(typeof readFixture === 'function', 'SEALED_FIXTURE_READER_REQUIRED');
  const { default: LlmRuntime, LlmAdapter, LlmError, resolveRetryPolicy } = dsh;
  const retryPolicy = resolveRetryPolicy({
    mode: 'normal', maxRetries: 0,
  }, 'sealed-analysis fixture');
  let readStarted = false;
  class FixtureAdapter extends LlmAdapter {
    providerRetryPolicy() { return retryPolicy; }
    async resolveModel(provider, model) {
      if (provider !== FIXTURE_PROVIDER || model !== sealed.model) {
        throw new LlmError('Sealed fixture model mismatch', 'SEALED_ANALYSIS_MODEL_REFUSED');
      }
      return { provider, id: model, name: model, defaultMaxTokens: 8192, inputModalities: ['text'] };
    }
    async *stream(options) {
      const request = snapshotRequest(options, sealed, true);
      if (request.model !== sealed.model) {
        throw new LlmError('Sealed fixture model mismatch', 'SEALED_ANALYSIS_MODEL_REFUSED');
      }
      throwIfAborted(request.signal);
      if (readStarted) throw new LlmError('Fixture read already attempted', 'SEALED_FIXTURE_REPLAY_REFUSED');
      readStarted = true; // A failed or ambiguous callback never grants replay.
      const reply = await readOnce(readFixture, Object.freeze({
        requestBody: sealed.requestBody,
        requestBodySha256: sealed.requestBodySha256,
        signal: request.signal,
      }), request.signal);
      throwIfAborted(request.signal);
      requireCondition(exactKeys(reply, ['kind', 'requestBodySha256', 'text', 'textSha256'])
        && reply.kind === 'complete-text-fixture'
        && reply.requestBodySha256 === sealed.requestBodySha256
        && reply.text === sealed.resultText
        && reply.textSha256 === sealed.resultSha256
        && sha256(reply.text) === reply.textSha256, 'SEALED_FIXTURE_RESULT_REFUSED');
      // This is projection of a complete buffered result, not provider streaming.
      for (const chunk of [
        { type: 'block-start', index: 0, blockType: 'text' },
        { type: 'text-delta', index: 0, text: reply.text },
        { type: 'block-end', index: 0, block: { type: 'text', text: reply.text } },
        { type: 'finish', reason: { kind: 'stop' } },
      ]) {
        throwIfAborted(request.signal);
        yield chunk;
      }
      // No usage, served-model, account, replay or Executive acceptance claims.
    }
  }
  const ctx = new Context();
  let disposed = false;
  const dispose = async () => {
    if (!disposed) { disposed = true; await ctx.fiber.dispose(); }
  };
  try {
    await ctx.plugin(LlmRuntime);
    ctx.llm.registerAdapter([FIXTURE_PROVIDER], new FixtureAdapter());
    const prepared = await ctx.llm.prepareCall({ provider: FIXTURE_PROVIDER, model: sealed.model });
    return Object.freeze({
      config: prepared.config,
      retryPolicy: prepared.retryPolicy,
      dispose,
      async *stream(options) {
        try {
          const request = snapshotRequest(options, sealed);
          yield* prepared.stream(request);
        } finally { await dispose(); }
      },
    });
  } catch (error) { await dispose(); throw error; }
}
