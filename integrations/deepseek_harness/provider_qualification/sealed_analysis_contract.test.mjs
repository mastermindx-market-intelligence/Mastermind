import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import {
  FIXTURE_PROVIDER, prepareSealedAnalysisFixture,
} from './sealed_analysis_contract.mjs';

const donor = resolve(process.argv[2]);
const vectors = JSON.parse(readFileSync(0, 'utf8'));
const source = join(donor, 'packages/llm/llm/src/index.ts');
const dsh = await import(pathToFileURL(source).href);
const donorRequire = createRequire(join(donor, 'packages/llm/llm/package.json'));
const { Context } = await import(pathToFileURL(donorRequire.resolve('@deepseek-ai/cordis')).href);
const primary = vectors[0];
const copy = value => structuredClone(value);
const sha256 = value => createHash('sha256').update(value).digest('hex');
const request = vector => ({
  provider: FIXTURE_PROVIDER, model: vector.descriptor.paid_route.model,
  messages: [{ role: 'user', content: [{ type: 'text', text: vector.prompt }] }],
});
const reply = vector => ({
  kind: 'complete-text-fixture',
  requestBodySha256: vector.descriptor.request_body_sha256,
  text: vector.resultText, textSha256: vector.resultSha256,
});
const collect = async stream => {
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return chunks;
};
async function setup(t, vector = primary, reader = async () => reply(vector)) {
  let calls = 0;
  const fixture = await prepareSealedAnalysisFixture({
    dsh, Context, vector,
    readFixture: async input => { calls++; return reader(input); },
  });
  t.after(() => fixture.dispose());
  return { fixture, calls: () => calls };
}
function noSuccess(chunks) {
  assert(!chunks.some(chunk => chunk.type === 'finish' && chunk.reason.kind === 'stop'));
}

for (const vector of vectors) {
  test('actual DSH text projection: ' + vector.descriptor.paid_route.model, async t => {
    const { fixture, calls } = await setup(t, vector, async input => {
      assert.equal(input.requestBody, vector.requestBody);
      assert.equal(sha256(input.requestBody), input.requestBodySha256);
      assert(Object.isFrozen(input));
      return reply(vector);
    });
    assert.equal(fixture.retryPolicy.mode, 'normal');
    assert.equal(fixture.retryPolicy.maxRetries, 0);
    assert(Object.isFrozen(fixture.retryPolicy));
    assert(Object.isFrozen(fixture.config));
    const chunks = await collect(fixture.stream(request(vector)));
    const assembled = new dsh.BlockAssembler();
    chunks.forEach(chunk => assembled.push(chunk));
    assert.deepEqual(assembled.blocks(), [{ type: 'text', text: vector.resultText }]);
    assert.deepEqual(assembled.finish, { kind: 'stop' });
    assert.equal(assembled.usage, undefined);
    assert.equal(chunks.some(chunk => 'replayState' in chunk || chunk.type === 'usage'), false);
    assert.equal(calls(), 1);
  });
}

const unsupported = [
  ['system', value => { value.system = 'new instructions'; }],
  ['empty system', value => { value.system = ''; }],
  ['tools', value => { value.tools = [{ name: 'shell', parameters: {}, description: 'forbidden' }]; }],
  ['empty tools', value => { value.tools = []; }],
  ['tool history', value => { value.toolHistory = { tools: [], updates: [] }; }],
  ['auxiliary purpose', value => { value.purpose = 'compaction'; }],
  ['session title', value => { value.purpose = 'session-title'; }],
  ['session binding', value => { value.sessionId = 'fixture-session'; }],
  ['temperature', value => { value.temperature = 0; }],
  ['reasoning control', value => { value.reasoningEffort = 'high'; }],
  ['stop sequences', value => { value.stop = ['END']; }],
  ['changed token cap', value => { value.maxTokens = 1; }],
  ['multi-turn', value => { value.messages.push(copy(value.messages[0])); }],
  ['system message', value => { value.messages[0].role = 'system'; }],
  ['tool result', value => { value.messages[0].role = 'tool'; }],
  ['durable identity', value => { value.messages[0].id = 'message-id'; }],
  ['durable source', value => { value.messages[0].source = { kind: 'user' }; }],
  ['image', value => { value.messages[0].content[0] = { type: 'image', attachment: {} }; }],
  ['file', value => { value.messages[0].content[0] = { type: 'file', attachment: {} }; }],
  ['tool-call block', value => { value.messages[0].content[0] = { type: 'tool-call', name: 'shell' }; }],
  ['changed prompt', value => { value.messages[0].content[0].text += ' changed'; }],
  ['unknown field', value => { value.endpoint = 'https://invalid.example'; }],
  ['non-enumerable tool request', value => { Object.defineProperty(value, 'tools', { value: [] }); }],
  ['inherited field', value => { Object.setPrototypeOf(value, { tools: [] }); }],
];
for (const [name, mutate] of unsupported) {
  test('refuse before native projection/callback: ' + name, async t => {
    const { fixture, calls } = await setup(t);
    const options = request(primary);
    mutate(options);
    await assert.rejects(collect(fixture.stream(options)), { code: 'SEALED_ANALYSIS_REQUEST_REFUSED' });
    assert.equal(calls(), 0);
  });
}

for (const [name, mutate] of [
  ['body bytes', value => { value.requestBody += ' '; }],
  ['descriptor model', value => { value.descriptor.paid_route.model = 'other'; }],
  ['prompt', value => { value.prompt += ' different'; }],
  ['result digest', value => { value.resultSha256 = '0'.repeat(64); }],
]) {
  test('refuse inconsistent compiler vector: ' + name, async () => {
    const vector = copy(primary);
    mutate(vector);
    await assert.rejects(prepareSealedAnalysisFixture({
      dsh, Context, vector, readFixture: () => { throw new Error('must not call'); },
    }), { code: 'SEALED_FIXTURE_VECTOR_REFUSED' });
  });
}

test('native prepared call refuses a changed model and does not read the fixture', async t => {
  const { fixture, calls } = await setup(t);
  const options = request(primary);
  options.model = 'glm-5.3-flash';
  if (options.model === primary.descriptor.paid_route.model) options.model = 'glm-5.3';
  let code;
  try {
    const chunks = await collect(fixture.stream(options));
    code = chunks.at(-1)?.reason?.failure?.code;
    noSuccess(chunks);
  } catch (error) { code = error.code; }
  assert.equal(code, 'INVALID_PREPARED_CALL');
  assert.equal(calls(), 0);
});

test('native prepared call cannot be reused after a completed request', async t => {
  const { fixture, calls } = await setup(t);
  await collect(fixture.stream(request(primary)));
  let code;
  try {
    const chunks = await collect(fixture.stream(request(primary)));
    code = chunks.at(-1)?.reason?.failure?.code;
    noSuccess(chunks);
  } catch (error) { code = error.code; }
  assert.equal(code, 'INVALID_PREPARED_CALL');
  assert.equal(calls(), 1);
});

test('compiler vector is detached before the caller can mutate it', async t => {
  const vector = copy(primary);
  const { fixture, calls } = await setup(t, vector, async () => reply(primary));
  vector.prompt = 'mutated';
  vector.requestBody = '{}';
  vector.resultText = 'mutated';
  const chunks = await collect(fixture.stream(request(primary)));
  assert.equal(chunks.at(-1).reason.kind, 'stop');
  assert.equal(calls(), 1);
});

test('pre-abort never invokes the fixture reader', async t => {
  const { fixture, calls } = await setup(t);
  const controller = new AbortController();
  controller.abort();
  const chunks = await collect(fixture.stream({ ...request(primary), signal: controller.signal }));
  noSuccess(chunks);
  assert.equal(chunks.at(-1).reason.kind, 'aborted');
  assert.equal(calls(), 0);
});

test('abort during an unsettled read completes without retry or successful finish', { timeout: 3000 }, async t => {
  let started;
  const didStart = new Promise(resolve => { started = resolve; });
  const { fixture, calls } = await setup(t, primary, async () => {
    started();
    return new Promise(() => {});
  });
  const controller = new AbortController();
  const pending = collect(fixture.stream({ ...request(primary), signal: controller.signal }));
  await didStart;
  controller.abort();
  const chunks = await pending;
  noSuccess(chunks);
  assert.equal(chunks.at(-1).reason.kind, 'aborted');
  assert.equal(calls(), 1);
});

test('consumer stop has no synthetic successful finish', async t => {
  const { fixture, calls } = await setup(t);
  const chunks = [];
  for await (const chunk of fixture.stream(request(primary))) {
    chunks.push(chunk);
    if (chunk.type === 'text-delta') break;
  }
  noSuccess(chunks);
  assert.equal(calls(), 1);
});

test('abort between projected chunks has no successful finish', async t => {
  const { fixture, calls } = await setup(t);
  const controller = new AbortController();
  const chunks = [];
  for await (const chunk of fixture.stream({ ...request(primary), signal: controller.signal })) {
    chunks.push(chunk);
    if (chunk.type === 'text-delta') controller.abort();
  }
  noSuccess(chunks);
  assert.equal(calls(), 1);
});

for (const [code, status] of [['RATE_LIMIT', 429], ['TIMEOUT', undefined], ['TRANSPORT', undefined], ['AUTH', 403]]) {
  test('actual DSH preserves failure without retries: ' + code, async t => {
    const { fixture, calls } = await setup(t, primary, async () => {
      throw new dsh.LlmError('fixture failure', code, status === undefined ? undefined : { status });
    });
    const chunks = await collect(fixture.stream(request(primary)));
    noSuccess(chunks);
    assert.equal(chunks.at(-1).reason.failure.code, code);
    assert.equal(calls(), 1);
    assert.equal(fixture.retryPolicy.maxRetries, 0);
  });
}

for (const [name, mutate] of [
  ['partial', value => { value.kind = 'partial-text-fixture'; }],
  ['tool-shaped', value => { value.kind = 'tool-call'; value.name = 'shell'; }],
  ['wrong owner body', value => { value.requestBodySha256 = '0'.repeat(64); }],
  ['truncated text', value => { value.text = value.text.slice(0, -1); }],
  ['invented usage', value => { value.usage = { inputTokens: 0, outputTokens: 0 }; }],
]) {
  test('incomplete or widened result emits no content: ' + name, async t => {
    const bad = reply(primary);
    mutate(bad);
    const { fixture, calls } = await setup(t, primary, async () => bad);
    const chunks = await collect(fixture.stream(request(primary)));
    noSuccess(chunks);
    assert(chunks.every(chunk => chunk.type === 'finish'));
    assert.equal(calls(), 1);
  });
}
