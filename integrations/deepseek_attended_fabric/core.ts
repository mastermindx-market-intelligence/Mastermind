/**
 * DeepSeek-native ingress to the existing Fabric MCP owner.
 * No credentials, transport, admission ledger, scheduler, retries or polling.
 */
import { createHash } from 'node:crypto'

export const TOOL = 'mmx_fabric_worker'
export const SCHEMA = 'mastermind.deepseek_fabric_native.v1'
export const MAX_RESULT_BYTES = 8192
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/
const KEY = /^[a-z][a-z0-9_-]{0,63}$/
const STATE = /^[A-Z][A-Z0-9_]{0,63}$/
const CLASSES = ['mechanical', 'fix_build', 'review', 'census', 'audit'] as const
const COMPLEXITIES = ['C0_MECHANICAL', 'C1_ROUTINE_BOUNDED', 'C2_COMPLEX_BOUNDED', 'C3_FRONTIER_JUDGMENT'] as const
type MaybePromise<T> = T | Promise<T>
type RecordValue = Record<string, unknown>

export interface SessionGrant {
  readonly profile_id: string
  readonly session_id: string
  readonly root_id: string
  readonly parent_id: string
  readonly generation: string
}

/** Authenticated native host callbacks. None are model/config supplied. */
export interface FabricHost<Agent> {
  authorizeSession(agent: Agent): MaybePromise<SessionGrant | undefined>
  isCurrent(grant: Readonly<SessionGrant>, agent: Agent): MaybePromise<boolean>
  /**
   * Existing original owner must durably fence this exact run across concurrent
   * calls/restarts BEFORE returning true. NOT_FOUND is never that authority.
   */
  authorizeNewRun(grant: Readonly<SessionGrant>, runId: string): MaybePromise<boolean>
  /** Existing enrolled single-owner MCP client; return its normalized payload. */
  callTool(name: 'fabric_status' | 'fabric_request' | 'fabric_result',
    arguments_: Readonly<RecordValue>): Promise<unknown>
}

export const parameters = {
  type: 'object', additionalProperties: false, required: ['action', 'task_key'],
  properties: {
    action: { type: 'string', enum: ['submit', 'status', 'result'] },
    task_key: { type: 'string', pattern: KEY.source },
    task_class: { type: 'string', enum: CLASSES },
    task_complexity: { type: 'string', enum: COMPLEXITIES },
    work_packet: { type: 'string', maxLength: 16000 },
    escalation_reason: { type: 'string', maxLength: 500 },
  },
} as const

class Refusal extends Error {}
function fail(reason: string): never { throw new Refusal(reason) }
function record(value: unknown): value is RecordValue {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function validString(value: unknown, max: number): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= max
    && !value.includes('\0') && value.isWellFormed()
}
function identity(grant: SessionGrant, runId: string) {
  return { run_id: runId, root_id: grant.root_id, parent_id: grant.parent_id }
}
function projection(state: string, reason: string | null, extra: RecordValue = {}) {
  return {
    schema: SCHEMA, state, reason, worker_started: false,
    retry_authorized: false, acceptance_changed: false,
    remote_cancellation_requested: false, ...extra,
  }
}
function snapshotGrant(value: unknown, sessionId: string): Readonly<SessionGrant> {
  if (!record(value)) fail('NATIVE_SESSION_NOT_AUTHORIZED')
  for (const key of ['profile_id', 'session_id', 'generation']) {
    if (!validString(value[key], 256)) fail('NATIVE_SESSION_NOT_AUTHORIZED')
  }
  for (const key of ['root_id', 'parent_id']) {
    if (typeof value[key] !== 'string' || !ID.test(value[key])) fail('NATIVE_SESSION_NOT_AUTHORIZED')
  }
  if (value.session_id !== sessionId) fail('NATIVE_SESSION_NOT_AUTHORIZED')
  return Object.freeze({
    profile_id: value.profile_id as string, session_id: value.session_id,
    root_id: value.root_id as string, parent_id: value.parent_id as string,
    generation: value.generation as string,
  })
}

/** Stable across connection/process generations; never chosen by the model. */
export function runIdFor(grant: SessionGrant, taskKey: string): string {
  if (!KEY.test(taskKey)) fail('TASK_KEY_INVALID')
  return 'deepseek-native-' + createHash('sha256')
    .update(JSON.stringify([grant.profile_id, grant.session_id, taskKey])).digest('hex').slice(0, 40)
}

function argumentsFor(value: unknown): RecordValue {
  if (!record(value)) fail('ARGUMENTS_INVALID')
  const allowed = new Set(Object.keys(parameters.properties))
  if (Object.keys(value).some(key => !allowed.has(key))) fail('ARGUMENTS_INVALID')
  if (!['submit', 'status', 'result'].includes(value.action as string)
    || typeof value.task_key !== 'string' || !KEY.test(value.task_key)) fail('ARGUMENTS_INVALID')
  if (value.action !== 'submit') {
    if (Object.keys(value).some(key => key !== 'action' && key !== 'task_key')) fail('READ_ARGUMENTS_INVALID')
    return value
  }
  if (!CLASSES.includes(value.task_class as typeof CLASSES[number])
    || !COMPLEXITIES.includes(value.task_complexity as typeof COMPLEXITIES[number])
    || !validString(value.work_packet, 16000) || !value.work_packet.trim()
    || Buffer.byteLength(value.work_packet, 'utf8') > 32768) fail('SUBMIT_ARGUMENTS_INVALID')
  const reason = value.escalation_reason ?? ''
  if (typeof reason !== 'string' || reason.length > 500 || reason.includes('\0')
    || !reason.isWellFormed()
    || (value.task_complexity === 'C3_FRONTIER_JUDGMENT' && !reason.trim())) fail('ESCALATION_REASON_INVALID')
  return { ...value, escalation_reason: reason }
}

function wire(value: unknown, action: string): RecordValue {
  if (!record(value) || value.schema !== 'mastermind.fabric_mcp.v1' || value.action !== action)
    fail('FABRIC_FACADE_RESPONSE_INVALID')
  if (value.error != null) fail('FABRIC_FACADE_OBSERVATION_REFUSED')
  return value
}
function statusProjection(raw: RecordValue, grant: SessionGrant, runId: string): RecordValue {
  const status = raw.status
  if (raw.run_id !== runId || !record(status)
    || status.schema !== 'mastermind.fabric_task_status.v1'
    || typeof status.state !== 'string' || !STATE.test(status.state)
    || (status.run_id != null && status.run_id !== runId)) fail('FABRIC_STATUS_INVALID')
  const root = status.root_id, parent = status.parent_run_id
  if ((raw.root_id != null && raw.root_id !== grant.root_id)
    || (root != null && root !== grant.root_id)) fail('FABRIC_STATUS_FOREIGN_ROOT')
  if (parent != null && parent !== grant.parent_id) fail('FABRIC_STATUS_FOREIGN_PARENT')
  const ids = identity(grant, runId)
  if (status.state === 'NOT_FOUND') {
    if (raw.root_verified === true || status.result_available !== false)
      fail('FABRIC_STATUS_ABSENCE_INVALID')
    return projection('NOT_FOUND', 'ORIGINAL_ID_OBSERVED_NOT_FOUND', ids)
  }
  const continuation = status.continuation, recovery = raw.parent_recovery
  if (status.state === 'REQUEST_REFUSED_BEFORE_LAUNCH' && root == null && parent == null
    && raw.root_verified === false && status.run_id === runId && raw.effective_run_id === runId
    && status.request_root_id === grant.root_id && status.request_parent_run_id === grant.parent_id
    && status.request_retained === true && status.execution_absence_proven === true
    && status.result_available === false && status.same_run_replay_allowed === false
    && record(continuation) && continuation.controller_return === 'RECORDED'
    && continuation.requested_run_id === runId && continuation.effective_run_id === runId
    && record(recovery) && recovery.schema === 'mastermind.fabric_parent_recovery_projection.v1'
    && recovery.requested_run_id === runId && recovery.effective_run_id === runId
    && recovery.request_correlation_only === true
    && recovery.disposition === 'RECONCILE_PRELAUNCH_REFUSAL') {
    return projection(status.state, 'PRELAUNCH_REFUSAL_CAUSE_UNRESOLVED', {
      ...ids, request_correlation_only: true, root_verified: false,
      result_consumption_authorized: false,
    })
  }
  if (raw.root_verified !== true || root !== grant.root_id || parent !== grant.parent_id)
    return projection('UNVERIFIED', 'FABRIC_STATUS_LINEAGE_NOT_PROVEN', ids)
  if (typeof raw.effective_run_id !== 'string' || !ID.test(raw.effective_run_id))
    fail('FABRIC_STATUS_EFFECTIVE_ID_INVALID')
  return projection(status.state, null, {
    ...ids, effective_run_id: raw.effective_run_id,
    worker_started: record(status.controller_lineage) && status.controller_lineage.worker_started === true,
  })
}

/** One invocation, no background work. Every pending owner call is drained. */
export function createHandler<Agent extends { readonly id: string }>(
  agent: Agent, host: FabricHost<Agent>, isMounted: () => boolean = () => true,
) {
  if (!agent || !validString(agent.id, 256) || !host
    || ['authorizeSession', 'isCurrent', 'authorizeNewRun', 'callTool']
      .some(key => typeof (host as unknown as RecordValue)[key] !== 'function'))
    fail('FABRIC_AUTHENTICATED_HOST_UNBOUND')
  const originalSessionId = agent.id
  return async (input: unknown, caller: Agent | undefined, signal: AbortSignal): Promise<RecordValue> => {
    let args: RecordValue
    try { args = argumentsFor(input) } catch (error) {
      return projection('REFUSED', error instanceof Refusal ? error.message : 'ARGUMENTS_INVALID')
    }
    if (caller !== agent || agent.id !== originalSessionId || !isMounted())
      return projection('REFUSED', 'NATIVE_PARENT_MISMATCH')
    if (!signal || signal.aborted) return projection('REFUSED', 'LOCAL_CALL_INTERRUPTED')
    let grant: Readonly<SessionGrant>
    try { grant = snapshotGrant(await host.authorizeSession(agent), originalSessionId) }
    catch { return projection('REFUSED', 'NATIVE_SESSION_NOT_AUTHORIZED') }
    const current = async (): Promise<boolean> => {
      try {
        if (signal.aborted || !isMounted() || agent.id !== originalSessionId) return false
        const allowed = await host.isCurrent(grant, agent)
        return allowed === true && !signal.aborted && isMounted() && agent.id === originalSessionId
      } catch { return false }
    }
    if (!await current()) return projection('REFUSED', 'NATIVE_SESSION_NOT_CURRENT')
    const runId = runIdFor(grant, args.task_key as string)
    const ids = identity(grant, runId)
    const withheld = () => projection('REFUSED', 'NATIVE_RESPONSE_WITHHELD', { run_id: runId })
    const observe = async () => statusProjection(
      wire(await host.callTool('fabric_status', { run_id: runId, root_id: grant.root_id }), 'fabric_status'),
      grant, runId,
    )
    let observed: RecordValue
    try { observed = await observe() }
    catch { return projection('UNAVAILABLE', 'FABRIC_ORIGINAL_OBSERVATION_UNAVAILABLE', ids) }
    if (!await current()) return withheld()
    if (args.action === 'status') return observed

    if (args.action === 'submit') {
      // Existing/unknown/unverified/refused runs are observed, never resubmitted.
      if (observed.state !== 'NOT_FOUND') return observed
      let authorized: boolean
      try { authorized = await host.authorizeNewRun(grant, runId) }
      catch { return projection('UNAVAILABLE', 'FABRIC_ORIGINAL_ADMISSION_UNAVAILABLE', ids) }
      if (authorized !== true) return projection('REFUSED', 'FABRIC_ORIGINAL_ADMISSION_REFUSED', ids)
      if (!await current()) return withheld()
      const request: RecordValue = {
        ...ids, task_class: args.task_class, task_complexity: args.task_complexity,
        work_packet: args.work_packet,
        ...(args.escalation_reason ? { escalation_reason: args.escalation_reason } : {}),
      }
      let receipt: RecordValue
      // From here, every failure may hide a dispatch. Never infer absence.
      try {
        const raw = wire(await host.callTool('fabric_request', request), 'fabric_request')
        if (raw.run_id !== runId || raw.root_id !== grant.root_id || raw.parent_id !== grant.parent_id
          || raw.delivery !== 'CONTROLLER_CREATED' || !Number.isSafeInteger(raw.controller_pid)
          || (raw.controller_pid as number) <= 0 || raw.worker_start_proven !== false)
          fail('FABRIC_REQUEST_RECEIPT_UNVERIFIED')
        receipt = projection('CONTROLLER_CREATED', 'WORKER_START_NOT_YET_PROVEN', {
          ...ids, submission_recorded: true,
          ...(raw.response_withheld === true ? { response_withheld: true } : {}),
        })
      } catch { return projection('EFFECT_UNKNOWN', 'RECONCILE_ORIGINAL_RUN', ids) }
      if (!await current()) {
        return projection('CONTROLLER_CREATED', 'NATIVE_RESPONSE_WITHHELD', {
          run_id: runId, submission_recorded: true, response_withheld: true,
        })
      }
      return receipt
    }

    if (observed.state !== 'TERMINAL')
      return projection('REFUSED', 'FABRIC_RESULT_NOT_TERMINAL', ids)
    try {
      const raw = wire(await host.callTool('fabric_result', {
        run_id: runId, root_id: grant.root_id, max_bytes: MAX_RESULT_BYTES,
      }), 'fabric_result')
      if (!await current()) return withheld()
      if (raw.run_id !== runId || raw.root_id !== grant.root_id
        || raw.effective_run_id !== observed.effective_run_id
        || raw.accept_run_id !== observed.effective_run_id) fail('FABRIC_RESULT_IDENTITY_MISMATCH')
      const body = raw.adapter_response, digest = raw.response_sha256, count = raw.response_bytes
      if (typeof body !== 'string' || !body.isWellFormed() || typeof digest !== 'string'
        || !/^[0-9a-f]{64}$/.test(digest) || !Number.isSafeInteger(count)
        || (count as number) < 0 || (count as number) > MAX_RESULT_BYTES)
        fail('FABRIC_RESULT_TRANSFER_INVALID')
      const data = Buffer.from(body, 'utf8')
      if (data.length !== count || createHash('sha256').update(data).digest('hex') !== digest)
        fail('FABRIC_RESULT_DIGEST_MISMATCH')
      const final = await observe()
      if (!await current()) return withheld()
      if (final.state !== 'TERMINAL' || final.effective_run_id !== observed.effective_run_id)
        fail('FABRIC_RESULT_LINEAGE_CHANGED')
      return projection('TERMINAL', null, {
        ...ids, effective_run_id: final.effective_run_id,
        worker_started: final.worker_started, result_transfer_verified: true,
        result_digest: digest, result_text: body,
      })
    } catch (error) {
      return projection('UNAVAILABLE',
        error instanceof Refusal ? error.message : 'FABRIC_ORIGINAL_RESULT_UNAVAILABLE', ids)
    }
  }
}
