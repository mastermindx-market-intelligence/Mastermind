import { createHash } from 'node:crypto'
import { vi } from 'vitest'
import { createHandler, runIdFor } from './core.ts'
import type { FabricHost, SessionGrant } from './core.ts'

export const submitArgs = {
  action: 'submit', task_key: 'source-census', task_class: 'census',
  task_complexity: 'C1_ROUTINE_BOUNDED', work_packet: 'Inspect the authorized source only.',
}
export function fixture<A extends { readonly id: string }>(agent: A = { id: 'native-session' } as A) {
  const grant: SessionGrant = {
    profile_id: 'company-profile', session_id: agent.id,
    root_id: 'company-root', parent_id: 'company-parent', generation: 'native-generation-1',
  }
  const runId = runIdFor(grant, submitArgs.task_key)
  const responseText = 'Verified child evidence: source-consistent-result.'
  let current = true
  const status = (state = 'TERMINAL', overrides: Record<string, unknown> = {}) => ({
    schema: 'mastermind.fabric_mcp.v1', action: 'fabric_status', run_id: runId,
    root_id: grant.root_id, root_verified: state !== 'NOT_FOUND', effective_run_id: runId,
    status: {
      schema: 'mastermind.fabric_task_status.v1', state, run_id: runId,
      ...(state === 'NOT_FOUND' ? {} : { root_id: grant.root_id, parent_run_id: grant.parent_id }),
      result_available: state === 'TERMINAL', controller_lineage: { worker_started: false },
    }, ...overrides,
  })
  const receipt = () => ({
    schema: 'mastermind.fabric_mcp.v1', action: 'fabric_request',
    run_id: runId, root_id: grant.root_id, parent_id: grant.parent_id,
    delivery: 'CONTROLLER_CREATED', controller_pid: 1234, worker_start_proven: false,
  })
  const result = () => ({
    schema: 'mastermind.fabric_mcp.v1', action: 'fabric_result',
    run_id: runId, root_id: grant.root_id, effective_run_id: runId, accept_run_id: runId,
    adapter_response: responseText,
    response_bytes: Buffer.byteLength(responseText),
    response_sha256: createHash('sha256').update(responseText).digest('hex'),
  })
  const host: FabricHost<A> = {
    authorizeSession: vi.fn(async () => grant),
    isCurrent: vi.fn(async () => current),
    authorizeNewRun: vi.fn(async () => false),
    callTool: vi.fn(async name => name === 'fabric_status' ? status()
      : name === 'fabric_result' ? result() : receipt()),
  }
  const handler = createHandler(agent, host)
  const invoke = (args: unknown = { action: 'status', task_key: submitArgs.task_key },
    signal = new AbortController().signal) => handler(args, agent, signal)
  return { agent, grant, runId, host, status, receipt, result, handler, invoke, responseText,
    revoke: () => { current = false } }
}
