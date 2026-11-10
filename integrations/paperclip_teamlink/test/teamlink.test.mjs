import test from 'node:test';
import assert from 'node:assert/strict';
import { Teamlink } from '../core.mjs';
import { validate } from '../validation.mjs';
import manifest from '../manifest.mjs';

const clone = value => structuredClone(value);
class MemoryStore {
  constructor() { this.links = new Map(); this.rows = new Map(); }
  async binding(company, issue) { return clone(this.links.get(`${company}/${issue}`) || null); }
  async saveBinding(company, issue, expected, payload) {
    const key = `${company}/${issue}`, old = this.links.get(key);
    if ((old?.revision || 0) !== expected) throw new Error('BINDING_REVISION_CONFLICT');
    this.links.set(key, { ...clone(payload), revision: expected + 1 });
    return this.binding(company, issue);
  }
  async get(company, op) { return clone(this.rows.get(`${company}/${op}`) || null); }
  async insert(row) {
    const key = `${row.companyId}/${row.operationId}`, inserted = !this.rows.has(key);
    if (inserted) this.rows.set(key, { ...clone(row), revision: 1 });
    return { inserted, row: await this.get(row.companyId, row.operationId) };
  }
  async change(row, patch) {
    const key = `${row.companyId}/${row.operationId}`, old = this.rows.get(key);
    if (old.revision !== row.revision) throw new Error('OPERATION_REVISION_CONFLICT');
    this.rows.set(key, { ...clone(old), ...clone(patch), revision: old.revision + 1 });
    return this.get(row.companyId, row.operationId);
  }
  async list(company, issue = null) {
    return clone([...this.rows.values()].filter(x => x.companyId === company && (issue ? x.issueId === issue : !['consumed','returned','wake_requested','refused','expired'].includes(x.phase))));
  }
  async bindings(company) { return clone([...this.links.values()].filter(x => x.companyId === company)); }
  async outgoingRun(company, binding, run) {
    return [...this.rows.values()].some(x => x.companyId === company && x.bindingId === binding && x.direction === 'paperclip_to_t3' && x.nativeRun?.runId === run);
  }
  async attempted() {}
  async scanAttempted() {}
}

async function fixture(options = {}) {
  const store = new MemoryStore();
  const actor = { kind: 'agent', companyId: 'company', agentId: 'meta-ceo', runId: 'paperclip-run-1' };
  const issue = { id: 'issue', companyId: 'company', assigneeAgentId: 'meta-ceo', status: 'in_progress', description: 'Original DONE_WHEN' };
  const comments = [], invokes = [], sends = [], observations = [];
  let incoming = [], replyFailure = options.replyFailure, sendFailure = options.sendFailure;
  const target = { environmentId: 'environment', projectId: 'project', threadId: 'root' };
  const native = { async call(action, p) {
    if (action === 'bind') return { ...target, threadId: p.threadId, watchCursor: 30 };
    if (action === 'send') {
      sends.push(clone(p));
      if (sendFailure) { const code = sendFailure; sendFailure = null; throw new Error(code); }
      return { ...target, runId: 'original-run', requestId: p.operationId, messageId: 'native-user-message', delivery: 'queued' };
    }
    if (action === 'recover_send') return { complete: true, cursor: 40, matches: options.noMatch ? [] : [{ itemId: 'native-user-message', messageId: 'native-user-message', runId: 'original-run' }] };
    if (action === 'observe') {
      observations.push(p.run.runId);
      if (options.changeRecipient) issue.assigneeAgentId = 'other-agent';
      return { status: options.nativeStatus || 'completed', complete: !options.nativeStatus || options.nativeStatus === 'completed', terminal: !options.nativeStatus || ['completed','failed','cancelled','interrupted'].includes(options.nativeStatus), answer: 'Exact original answer', pendingRequests: options.pendingIds?.length || 0, pendingRequestIds: options.pendingIds || [], observedAt: '2026-11-10T01:00:00Z' };
    }
    if (action === 'scan') return { messages: clone(incoming.filter(x => p.cursor === null || x.position > p.cursor)), cursor: 55, hasMore: false };
    throw new Error('UNEXPECTED_NATIVE_ACTION');
  } };
  const ctx = {
    issues: {
      async get() { return clone(issue); },
      async assertCheckoutOwner(p) { if (p.actorAgentId !== issue.assigneeAgentId || !p.actorRunId) throw new Error('CHECKOUT_REFUSED'); },
      async createComment(issueId, body, companyId) {
        const comment = { id: `comment-${comments.length + 1}`, issueId, companyId, body, authorAgentId: null, authorUserId: null };
        if (body.includes(' reply\n') && replyFailure === 'before') { replyFailure = null; throw new Error('NETWORK_LOSS'); }
        comments.push(comment);
        if (body.includes(' reply\n') && ['after','after_no_event'].includes(replyFailure)) {
          if (replyFailure === 'after') await service.commentEvent({ eventId: 'native-comment-event', eventType: 'issue.comment.created', actorType: 'plugin', actorId: 'plugin-installation', companyId, entityId: issueId, occurredAt: '2026-11-10T01:00:00Z', payload: { sourcePluginKey: 'mastermind.teamlink', pluginKey: 'mastermind.teamlink', sourcePluginId: 'plugin-installation', pluginId: 'plugin-installation', commentId: comment.id } });
          replyFailure = null; throw new Error('NETWORK_LOSS');
        }
        return clone(comment);
      },
      async listComments() { return clone(comments); },
      documents: { async list() { return [{ key: 'plan', title: 'Canonical plan' }]; } },
    },
    agents: { async invoke(agentId, companyId, input) {
      invokes.push({ agentId, companyId, input });
      if (options.wakeFailure) throw new Error('NETWORK_LOSS');
      return { runId: 'paperclip-run-2' };
    } },
    logger: { warn() {} },
  };
  const config = { enabled: true, companyId: 'company', environmentId: 'environment', projectIds: ['project'] };
  const service = new Teamlink(ctx, store, native, config);
  const binding = await service.bind({ issueId: 'issue', projectId: 'project', threadId: 'root', expectedRevision: 0 }, actor);
  return { service, ctx, store, native, config, actor, issue, comments, invokes, sends, observations,
    setIncoming(value) { incoming = value.map(x => ({ bindingId: binding.bindingId, ...x })); } };
}
const message = { issueId: 'issue', operationId: 'op-1', message: 'Please answer the original question.' };

test('exact original return, native recipient wake and explicit agent consumption survive a new worker', async () => {
  const f = await fixture();
  const first = await f.service.send(message, f.actor);
  assert.equal(first.phase, 'wake_requested');
  assert.equal(f.invokes[0].agentId, 'meta-ceo');
  assert.equal(first.consumedAt, undefined);
  assert.equal(f.comments.length, 2);
  const restarted = new Teamlink(f.ctx, f.store, f.native, f.config);
  const read = await restarted.status({ ...message, reconcile: true }, f.actor);
  assert.match(read.reply, /Exact original answer/);
  const consumed = await restarted.ack(message, { ...f.actor, runId: 'paperclip-run-2' });
  assert.equal(consumed.phase, 'consumed');
  assert.equal(consumed.consumedByRunId, 'paperclip-run-2');
  assert.deepEqual(f.observations, ['original-run']);
});

test('identical cross-run retry returns same effect; changed semantic payload conflicts', async () => {
  const f = await fixture(); await f.service.send(message, f.actor);
  await f.service.send(message, { ...f.actor, runId: 'later-run' });
  assert.equal(f.sends.length, 1); assert.equal(f.comments.length, 2); assert.equal(f.invokes.length, 1);
  await assert.rejects(f.service.send({ ...message, message: 'Different command' }, f.actor), /OPERATION_ID_REUSE_CONFLICT/);
  await assert.rejects(f.service.send({ ...message, wakeOnReply: false }, f.actor), /OPERATION_ID_REUSE_CONFLICT/);
});

test('two simultaneous send calls produce one native command and one return', async () => {
  const f = await fixture();
  await Promise.all([f.service.send(message, f.actor), f.service.send(message, f.actor)]);
  assert.equal(f.sends.length, 1); assert.equal(f.comments.length, 2); assert.equal(f.invokes.length, 1);
});

test('competing return observers cannot both acquire the publication fence', async () => {
  const f = await fixture({ nativeStatus: 'running' });
  await f.service.send(message, f.actor);
  let row = await f.store.get('company', 'op-1');
  row = await f.store.change(row, { phase: 'result_ready' });
  const before = f.comments.length;
  await Promise.all([f.service.publish(row, 'Returned', 'completed'), f.service.publish(row, 'Returned', 'completed')]);
  assert.equal(f.comments.length - before, 1);
});

test('lost send receipt rejoins exact native message without resending', async () => {
  const f = await fixture({ sendFailure: 'NATIVE_EFFECT_UNKNOWN' });
  assert.equal((await f.service.send(message, f.actor)).phase, 'send_unknown');
  const recovered = await f.service.status({ ...message, reconcile: true }, f.actor);
  assert.equal(recovered.nativeRun.runId, 'original-run'); assert.equal(recovered.phase, 'wake_requested');
  assert.equal(f.sends.length, 1);
});

test('unproven native effect remains fenced and blocks replacement IDs', async () => {
  const f = await fixture({ sendFailure: 'NATIVE_EFFECT_UNKNOWN', noMatch: true });
  await f.service.send(message, f.actor);
  for (let i = 0; i < 3; i++) assert.equal((await f.service.status({ ...message, reconcile: true }, f.actor)).phase, 'send_unknown');
  await assert.rejects(f.service.send({ ...message, operationId: 'replacement' }, f.actor), /BINDING_MISSING_OR_BUSY/);
  assert.equal(f.sends.length, 1); assert.equal(f.invokes.length, 0);
});

test('lost committed reply comment is recovered once; missing comment is never blindly recreated', async () => {
  for (const mode of ['after', 'before', 'after_no_event']) {
    const f = await fixture({ replyFailure: mode }); await f.service.send(message, f.actor);
    const row = await f.service.status({ ...message, reconcile: true }, f.actor);
    assert.equal(row.phase, mode === 'after' ? 'wake_requested' : 'reply_inflight');
    assert.equal(f.comments.length, mode === 'before' ? 1 : 2);
    assert.equal(f.invokes.length, mode === 'after' ? 1 : 0);
  }
});

test('uncertain native wake is never replayed and actual agent consumption can reconcile it', async () => {
  const f = await fixture({ wakeFailure: true });
  assert.equal((await f.service.send(message, f.actor)).phase, 'wake_unknown');
  await f.service.status({ ...message, reconcile: true }, f.actor);
  assert.equal(f.invokes.length, 1);
  assert.equal((await f.service.ack(message, { ...f.actor, runId: 'actual-consuming-run' })).phase, 'consumed');
});

test('a reassigned issue keeps the result without waking its replacement', async () => {
  const f = await fixture({ changeRecipient: true });
  const result = await f.service.send(message, f.actor);
  assert.equal(result.phase, 'returned'); assert.equal(result.wakeDisposition, 'recipient_or_issue_changed');
  assert.equal(f.invokes.length, 0); assert.equal(f.comments.length, 2);
  await assert.rejects(f.service.ack(message, { ...f.actor, agentId: 'other-agent' }), /ORIGINAL_RECIPIENT_REQUIRED/);
});

test('terminal failure is returned as failure rather than successful completion', async () => {
  const f = await fixture({ nativeStatus: 'failed' });
  const result = await f.service.send(message, f.actor);
  assert.equal(result.disposition, 'failed');
  assert.match(f.comments[1].body, /No complete successful answer/);
});

test('native input requirement produces one referenced notice without approving or resending', async () => {
  const f = await fixture({ nativeStatus: 'waiting_for_input', pendingIds: ['native-question'] });
  const row = await f.service.send(message, f.actor);
  assert.equal(row.phase, 'in_native');
  await f.service.status({ ...message, reconcile: true }, f.actor);
  assert.equal(f.sends.length, 1); assert.equal(f.invokes.length, 1); assert.equal(f.comments.length, 2);
  assert.match(f.comments[1].body, /native-question/);
  assert.match(f.comments[1].body, /does not approve/);
});

test('a COO can initiate a question; duplicate scans yield one comment/wake; reply targets same root', async () => {
  const f = await fixture();
  f.setIncoming([{ itemId: 'incoming-item', runId: 'coo-initiated-run', position: 40, kind: 'question', message: 'Which source should I use?', sourceHash: 'source-digest' }]);
  await f.service.tick(); await f.service.tick();
  const row = (await f.store.list('company', 'issue'))[0];
  assert.equal(row.direction, 't3_to_paperclip'); assert.equal(row.phase, 'wake_requested');
  assert.equal(f.comments.length, 1); assert.equal(f.invokes.length, 1);
  await f.service.ack({ issueId: 'issue', operationId: row.operationId }, f.actor);
  await f.service.send({ ...message, replyTo: row.operationId, message: 'Use the canonical source.' }, f.actor);
  assert.equal(f.sends[0].threadId, 'root'); assert.match(f.sends[0].wire, new RegExp(row.operationId));
});

test('informational COO updates are durable but do not wake a model', async () => {
  const f = await fixture();
  f.setIncoming([{ itemId: 'update-item', runId: 'coo-update', position: 40, kind: 'update', message: 'Read-only inventory complete.', sourceHash: 'source-digest' }]);
  await f.service.tick();
  assert.equal(f.invokes.length, 0); assert.equal(f.comments.length, 1);
  assert.equal((await f.store.list('company', 'issue'))[0].phase, 'returned');
});

test('a proactive message naming another binding cannot fan out to this issue', async () => {
  const f = await fixture();
  f.setIncoming([{ bindingId: 'different-binding', itemId: 'wrong-destination', runId: 'coo-update', position: 40, kind: 'question', message: 'Question for another issue', sourceHash: 'source-digest' }]);
  await f.service.tick();
  assert.equal(f.comments.length, 0); assert.equal(f.invokes.length, 0);
});

test('a partially re-read completed result stays pending until original bytes are available', async () => {
  const f = await fixture({ nativeStatus: 'running' });
  await f.service.send(message, f.actor);
  let row = await f.store.get('company', 'op-1'); row = await f.store.change(row, { phase: 'result_ready' });
  const original = f.native.call;
  f.native.call = async (action, p) => action === 'observe' ? { status: 'completed', complete: false, terminal: true, progress: { cursor: 100 }, observedAt: 'now' } : original(action, p);
  const value = await f.service.reconcile(row);
  assert.equal(value.phase, 'result_ready'); assert.equal(f.comments.length, 1); assert.equal(f.invokes.length, 0);
});

test('explicit protocol embedded in a tracked result is not echoed as a new incoming message', async () => {
  const f = await fixture(); await f.service.send(message, f.actor);
  f.setIncoming([{ itemId: 'same-result', runId: 'original-run', position: 40, kind: 'question', message: 'Question', sourceHash: 'source-digest' }]);
  await f.service.tick(); assert.equal(f.comments.length, 2); assert.equal(f.invokes.length, 1);
});

test('cursor advances only after incoming receipt persistence', async () => {
  const f = await fixture();
  f.setIncoming([{ itemId: 'incoming-item', runId: 'coo-run', position: 40, kind: 'question', message: 'Question', sourceHash: 'source-digest' }]);
  const original = f.store.insert.bind(f.store); f.store.insert = async () => { throw new Error('DATABASE_UNAVAILABLE'); };
  await f.service.tick(); assert.equal((await f.store.binding('company', 'issue')).watchCursor, 30);
  f.store.insert = original; await f.service.tick(); assert.equal(f.comments.length, 1);
});

test('caller cannot inject origin identity, change connection paths or acknowledge as board', async () => {
  const f = await fixture();
  const schema = manifest.tools.find(x => x.name === 'teamlink_send').parametersSchema;
  assert.throws(() => validate(schema, { ...message, actorAgentId: 'meta-ceo' }), /INVALID_/);
  await assert.rejects(f.service.send(message, { ...f.actor, companyId: 'other-company' }), /COMPANY_SCOPE_MISMATCH/);
  await f.service.send(message, f.actor);
  await assert.rejects(f.service.ack(message, { kind: 'board', userId: 'user', companyId: 'company' }), /ORIGINAL_RECIPIENT_REQUIRED/);
});

test('context is CAS-protected and preserves canonical document references', async () => {
  const f = await fixture(); const b = await f.store.binding('company', 'issue');
  const packet = { objective: 'Mission', doneWhen: 'Original acceptance', sourceRefs: ['github:plan'], remaining: ['Consumer proof'], unknownEffects: [], expiresAt: new Date(Date.now() + 60000).toISOString() };
  const result = await f.service.context({ issueId: 'issue', expectedRevision: b.revision, context: packet }, f.actor);
  assert.equal(result.binding.context.doneWhen, 'Original acceptance'); assert.equal(result.documents[0].key, 'plan');
  await assert.rejects(f.service.context({ issueId: 'issue', expectedRevision: b.revision, context: packet }, f.actor), /BINDING_REVISION_CONFLICT/);
});
