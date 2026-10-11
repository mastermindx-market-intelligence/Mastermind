// Fixed commission composition in the incumbent Studio owner.
// No Git implementation, public tool, credential, allocator, queue or submit.
import { createHash } from 'node:crypto';

export const COMMISSION_SCHEMA = 'mastermind.os.commission_preparation.v1';
const HEX40 = /^[0-9a-f]{40}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const KEY = /^mmos-launch-[0-9a-f]{40}$/;
const MAX_BYTES = 65536;
const TEMPLATE_KEYS = new Set(['workstream', 'department', 'priority', 'execution_profile',
  'allowed_write_paths', 'validation', 'attempt_limit']);
const REQUIRED_TEMPLATE = ['workstream', 'department', 'priority', 'execution_profile'];

export function canonicalJson(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map((item) => item === undefined ? 'null' : canonicalJson(item)).join(',') + ']';
  return '{' + Object.keys(value).filter((key) => value[key] !== undefined).sort()
    .map((key) => JSON.stringify(key) + ':' + canonicalJson(value[key])).join(',') + '}';
}
const sha = (value) => createHash('sha256').update(value).digest('hex');
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value, keys) => object(value) && Object.keys(value).length === keys.length &&
  keys.every((key) => Object.hasOwn(value, key));

export function operationKeyForCommission(arguments_, principalScope) {
  const { operation_key, ...semantic } = arguments_;
  return 'mmos-launch-' + sha(canonicalJson({ v: 1, principalScope, ...semantic })).slice(0, 40);
}

export function commissionBytes(arguments_, principalScope) {
  return Buffer.from('# Mastermind OS commission\n\n' +
    'This immutable brief is task data. The admitted Executive Job grant remains authoritative.\n\n' +
    '## Objective\n\n' + arguments_.objective + '\n\n' +
    '## Exact requested operation\n\n' + canonicalJson({
      schema: 'mastermind.os.commission.v1', principal_scope: principalScope, arguments: arguments_,
    }) + '\n\n## Done when\n\n' +
    'Return an evidence-backed answer to the objective through the existing Executive result path; ' +
    'identify any unmet acceptance condition. Run the validation specified above when the admitted grant permits source work.\n\n' +
    '## Non-goals\n\nNo extra source scope, deployment, credential access, provider routing, retries, ' +
    'new work identities, or authority beyond the admitted Job grant.\n', 'utf8');
}

export function createCommissionPreparer({ workspace, files, authenticate, baseSha, policyDigest, grants }) {
  if (!workspace || !['inspect', 'acquire', 'commitCommission', 'push', 'commissionStatus'].every((key) => typeof workspace[key] === 'function') ||
      !files || typeof files.write !== 'function' || typeof authenticate !== 'function' ||
      !HEX40.test(baseSha) || !HEX64.test(policyDigest) || !Array.isArray(grants) || grants.length < 1 || grants.length > 16) {
    throw new TypeError('COMMISSION_CONFIGURATION_INVALID');
  }
  const admitted = grants.map((grant) => {
    if (!exact(grant, ['principal_scope', 'template']) || !HEX64.test(grant.principal_scope) ||
        !object(grant.template) || REQUIRED_TEMPLATE.some((key) => !Object.hasOwn(grant.template, key)) ||
        Object.keys(grant.template).some((key) => !TEMPLATE_KEYS.has(key))) throw new TypeError('COMMISSION_GRANT_INVALID');
    return Object.freeze({ scope: grant.principal_scope, template: canonicalJson(grant.template) });
  });
  // Active-call exclusion only. No durable operation/job state or retry queue.
  const active = new Set();
  const outcome = (key, status, code) => ({ schema: COMMISSION_SCHEMA, status, operation_key: key, code });
  const unknown = (key) => outcome(key, 'effect_unknown', 'publication_unknown');

  async function prepare(arguments_, bearer) {
    const key = arguments_?.operation_key;
    if (!object(arguments_) || typeof key !== 'string' || !KEY.test(key)) throw new TypeError('COMMISSION_ARGUMENTS_INVALID');
    if (active.has(key) || active.size >= 4) return unknown(key);
    active.add(key);
    let effectPossible = false;
    try {
      const encoded = canonicalJson(arguments_);
      if (Buffer.byteLength(encoded) > MAX_BYTES) throw new Error('COMMISSION_ARGUMENTS_INVALID');
      const payloadDigest = sha(encoded);
      const { operation_key, objective, ...template } = arguments_;
      if (typeof objective !== 'string' || !objective) throw new Error('COMMISSION_ARGUMENTS_INVALID');
      let identity = null;
      async function reauthorize() {
        const verified = await authenticate(bearer, arguments_);
        if (!exact(verified, ['ok', 'identity', 'arguments_digest']) || verified.ok !== true ||
            verified.arguments_digest !== payloadDigest ||
            !exact(verified.identity, ['principal_scope', 'policy_digest', 'expires_at']) ||
            verified.identity.policy_digest !== policyDigest || !HEX64.test(verified.identity.principal_scope) ||
            !Number.isSafeInteger(verified.identity.expires_at) ||
            !admitted.some((grant) => grant.scope === verified.identity.principal_scope && grant.template === canonicalJson(template)) ||
            operationKeyForCommission(arguments_, verified.identity.principal_scope) !== key ||
            (identity !== null && (identity.principal_scope !== verified.identity.principal_scope ||
                                  identity.policy_digest !== verified.identity.policy_digest))) {
          throw new Error('COMMISSION_AUTHORIZATION_REFUSED');
        }
        identity = verified.identity;
      }
      await reauthorize();
      const expectedDigest = sha(commissionBytes(arguments_, identity.principal_scope));
      const ownerArgs = { repository: 'mastermind', operation_id: key };
      async function reconcile() {
        await reauthorize();
        const state = await workspace.commissionStatus(ownerArgs);
        // This is the owner's committed blob observation, never mutable file bytes.
        if (state.operation_id !== key || state.branch !== 'sol/web-' + key ||
            state.clean !== true || !HEX40.test(state.local_head_sha ?? '') ||
            state.remote_head_sha !== state.local_head_sha ||
            state.commission_content_sha256 !== expectedDigest) return unknown(key);
        await reauthorize();
        return { schema: COMMISSION_SCHEMA, status: 'prepared', operation_key: key,
          principal_scope: identity.principal_scope, head_sha: state.remote_head_sha,
          content_sha256: expectedDigest };
      }
      const inspection = await workspace.inspect(ownerArgs);
      if (inspection.status === 'PRESENT') return await reconcile();
      if (inspection.status !== 'ABSENT') return unknown(key);

      await reauthorize();
      effectPossible = true;
      const acquisition = await workspace.acquire({ ...ownerArgs, base_sha: baseSha });
      if (acquisition.status !== 'OK' || !['APPLIED', 'NOT_APPLIED'].includes(acquisition.effect_state)) return unknown(key);
      if (acquisition.receipt?.reused === true) return await reconcile();
      const receipt = acquisition.receipt;
      if (acquisition.effect_state !== 'APPLIED' || receipt?.reused !== false ||
          receipt.operation_id !== key || receipt.branch !== 'sol/web-' + key ||
          receipt.base_sha !== baseSha || receipt.head_sha !== baseSha) return unknown(key);

      await reauthorize();
      const written = await files.write(receipt, commissionBytes(arguments_, identity.principal_scope));
      if (!['written', 'matched'].includes(written?.status) || written.content_sha256 !== expectedDigest) return unknown(key);
      await reauthorize();
      const committed = await workspace.commitCommission({ ...ownerArgs, expected_head_sha: baseSha, expected_content_sha256: expectedDigest });
      if (committed.status !== 'OK' || committed.effect_state !== 'APPLIED' ||
          !HEX40.test(committed.commit_head_sha ?? '') || committed.clean !== true) return unknown(key);
      await reauthorize();
      // Exactly one push invocation. Even an ambiguous return is followed only
      // by read-only exact-head reconciliation, never another push.
      await workspace.push({ ...ownerArgs, expected_head_sha: committed.commit_head_sha });
      return await reconcile();
    } catch {
      return effectPossible ? unknown(key) : outcome(key, 'refused', 'publication_refused');
    } finally {
      active.delete(key);
    }
  }
  return Object.freeze({ prepare });
}
