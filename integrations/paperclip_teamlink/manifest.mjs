import { readFileSync } from 'node:fs';
const teamlinkSkill = readFileSync(new URL('./agent_skill/SKILL.md', import.meta.url), 'utf8');
const string = { type: 'string', minLength: 1, maxLength: 256 };
const schema = (properties, required = []) => ({ type: 'object', additionalProperties: false, properties, required });
const issue = { issueId: string };
export const tools = [
  ['teamlink_inventory', 'T3 environment and team', 'Read the configured T3 environment, projects, root sessions, native subagents and scoped process observations. Missing data stays unavailable. This never starts or interrupts work.', schema({ projectId: string, cursor: { type: 'integer', minimum: 0 }, includeProcesses: { type: 'boolean' } })],
  ['teamlink_inspect', 'Inspect the linked COO session', 'Read bounded native activity and messages from this issue\'s exact T3 root, including active run and pending-input state. Tool arguments/environment variables are omitted. This is observation only; it never consumes a child transcript or changes native work.', schema({ ...issue, cursor: { type: 'integer', minimum: 0 } }, ['issueId'])],
  ['teamlink_bind', 'Link a T3 COO session', 'Bind the current Paperclip issue to an exact existing T3 root session. Requires issue checkout ownership and expectedRevision (0 for a new binding). Does not launch work or change a provider.', schema({ ...issue, projectId: string, threadId: string, expectedRevision: { type: 'integer', minimum: 0 } }, ['issueId', 'projectId', 'threadId', 'expectedRevision'])],
  ['teamlink_send', 'Message the T3 COO', 'Send one actionable message to the issue\'s exact bound T3 session in native queue mode. Use a stable unique operationId. Identical repeats return the existing receipt; changed reuse refuses. Delivery is not execution or acceptance. Results/questions return to this issue and wake its original assignee once. Never replace an uncertain operation with a new ID.', schema({ ...issue, operationId: string, message: { type: 'string', minLength: 1, maxLength: 24000 }, replyTo: string, wakeOnReply: { type: 'boolean' }, expiresAt: { type: 'string', format: 'date-time' } }, ['issueId', 'operationId', 'message'])],
  ['teamlink_status', 'Read a Teamlink exchange', 'Recover the original operation, native run, result and transport uncertainties. Reconcile only existing effects; never resend. Reading a result is separate from acknowledging its consumption.', schema({ ...issue, operationId: string, reconcile: { type: 'boolean' } }, ['issueId', 'operationId'])],
  ['teamlink_ack', 'Acknowledge a T3 reply', 'After reading the returned T3 result/question, acknowledge consumption as the actual original Paperclip agent run. This does not accept code, mark an issue done, or authorize new work.', schema({ ...issue, operationId: string }, ['issueId', 'operationId'])],
  ['teamlink_context', 'Recover project continuity', 'Read the native Paperclip issue, documents, exact T3 binding, source references and unsettled exchanges. Optionally save a bounded context packet with expectedRevision. The packet is advisory continuity, not a task/permission/lease owner. Preserve original DONE_WHEN and uncertain effects.', schema({ ...issue, expectedRevision: { type: 'integer', minimum: 1 }, context: { type: 'object', additionalProperties: false, properties: { objective: { type: 'string', maxLength: 4000 }, doneWhen: { type: 'string', maxLength: 4000 }, sourceRefs: { type: 'array', maxItems: 20, items: { type: 'string', maxLength: 1500 } }, remaining: { type: 'array', maxItems: 30, items: { type: 'string', maxLength: 1000 } }, decisions: { type: 'array', maxItems: 20, items: { type: 'string', maxLength: 1000 } }, unknownEffects: { type: 'array', maxItems: 20, items: { type: 'string', maxLength: 1000 } }, expiresAt: { type: 'string', format: 'date-time' } }, required: ['objective', 'doneWhen', 'sourceRefs', 'remaining', 'unknownEffects', 'expiresAt'] } }, ['issueId'])],
].map(([name, displayName, description, parametersSchema]) => ({ name, displayName, description, parametersSchema }));

export default {
  id: 'mastermind.teamlink', apiVersion: 1, version: '1.1.0',
  displayName: 'Mastermind Teamlink', author: 'MastermindX',
  description: 'Two-way Paperclip ↔ T3 conversations, exact-run returns, shared project context and live environment visibility.',
  categories: ['automation'],
  entrypoints: { worker: './worker.mjs' },
  capabilities: ['issues.read', 'issues.checkout', 'issue.comments.read', 'issue.comments.create', 'issue.documents.read', 'agents.invoke', 'agents.read', 'database.namespace.read', 'database.namespace.write', 'database.namespace.migrate', 'events.subscribe', 'jobs.schedule', 'agent.tools.register', 'ui.action.register', 'skills.managed'],
  database: { namespaceSlug: 'mastermind_teamlink', migrationsDir: './migrations' },
  jobs: [{ jobKey: 'reconcile', displayName: 'Reconcile original T3 exchanges', description: 'Observe original runs and reconcile transport receipts. Never redispatch a message.', schedule: '* * * * *' }],
  tools,
  skills: [{ skillKey: 'teamlink', displayName: 'Paperclip Teamlink',
    description: 'Communicate with exact T3 COO sessions, consume replies and recover project continuity through native Paperclip tools.',
    markdown: teamlinkSkill }],
  instanceConfigSchema: schema({
    companyId: string, environmentId: string,
    projectIds: { type: 'array', minItems: 1, maxItems: 32, uniqueItems: true, items: string },
    nativeCliPath: string, nodePath: string, pythonPath: string, portPath: string, t3Home: string,
    t3Port: { type: 'integer', minimum: 1, maximum: 65535 },
    enabled: { type: 'boolean', default: false },
    realtime: { type: 'boolean', default: true },
  }, ['companyId', 'environmentId', 'projectIds', 'nativeCliPath', 'nodePath', 'pythonPath', 'portPath', 't3Home', 't3Port']),
};

