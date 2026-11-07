import { describe, expect, it, vi } from 'vitest'
import { createHandler, runIdFor } from './core.ts'
import { fixture, submitArgs } from './test-fixture.ts'

describe('original-parent Fabric effects and recovery', () => {
  it('retains logical identity across native generations and separates parents/profiles/tasks', () => {
    const f = fixture()
    expect(runIdFor({ ...f.grant, generation: 'reconnected' }, submitArgs.task_key)).toBe(f.runId)
    expect(runIdFor({ ...f.grant, session_id: 'other' }, submitArgs.task_key)).not.toBe(f.runId)
    expect(runIdFor({ ...f.grant, profile_id: 'other' }, submitArgs.task_key)).not.toBe(f.runId)
    expect(runIdFor(f.grant, 'different-task')).not.toBe(f.runId)
  })

  it.each([
    { ...submitArgs, root_id: 'forged-root' },
    { ...submitArgs, pool: 'another-account' },
    { ...submitArgs, host: 'ubuntu3' },
    { ...submitArgs, action: 'cancel' },
    { ...submitArgs, task_key: '../escape' },
    { ...submitArgs, task_complexity: 'C3_FRONTIER_JUDGMENT', escalation_reason: '' },
    { ...submitArgs, work_packet: '😀'.repeat(9000) },
    { action: 'status', task_key: submitArgs.task_key, work_packet: 'unexpected' },
  ])('rejects model authority/invalid arguments without owner calls: %j', async args => {
    const f = fixture()
    expect((await f.invoke(args)).state).toBe('REFUSED')
    expect(f.host.authorizeSession).not.toHaveBeenCalled()
    expect(f.host.callTool).not.toHaveBeenCalled()
  })

  it('requires exact live Agent identity, not an equal session id', async () => {
    const f = fixture()
    const r = await f.handler(submitArgs, { id: f.agent.id }, new AbortController().signal)
    expect(r.reason).toBe('NATIVE_PARENT_MISMATCH')
    expect(f.host.callTool).not.toHaveBeenCalled()
  })

  it('does not promote NOT_FOUND to fresh admission', async () => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValue(f.status('NOT_FOUND'))
    expect((await f.invoke(submitArgs)).reason).toBe('FABRIC_ORIGINAL_ADMISSION_REFUSED')
    expect(f.host.callTool).toHaveBeenCalledTimes(1)
    expect(f.host.authorizeNewRun).toHaveBeenCalledWith(f.grant, f.runId)
  })

  it('submits only after the original owner grants the exact run', async () => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValueOnce(f.status('NOT_FOUND')).mockResolvedValueOnce(f.receipt())
    vi.mocked(f.host.authorizeNewRun).mockResolvedValue(true)
    const r = await f.invoke(submitArgs)
    expect(r).toMatchObject({ state: 'CONTROLLER_CREATED', worker_started: false,
      retry_authorized: false, submission_recorded: true })
    expect(f.host.callTool).toHaveBeenLastCalledWith('fabric_request', {
      run_id: f.runId, root_id: f.grant.root_id, parent_id: f.grant.parent_id,
      task_class: submitArgs.task_class, task_complexity: submitArgs.task_complexity,
      work_packet: submitArgs.work_packet,
    })
  })

  it.each(['ACTIVE_OR_WAITING', 'TERMINAL'])('observes %s without another submit', async state => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValue(f.status(state))
    expect((await f.invoke(submitArgs)).state).toBe(state)
    expect(f.host.authorizeNewRun).not.toHaveBeenCalled()
    expect(f.host.callTool).toHaveBeenCalledTimes(1)
  })

  it('keeps ambiguous dispatch unknown; a new handler cannot authorize replay', async () => {
    const f = fixture()
    vi.mocked(f.host.authorizeNewRun).mockResolvedValueOnce(true).mockResolvedValue(false)
    vi.mocked(f.host.callTool)
      .mockResolvedValueOnce(f.status('NOT_FOUND'))
      .mockRejectedValueOnce(new Error('request may have reached owner; secret stderr'))
      .mockResolvedValueOnce(f.status('NOT_FOUND'))
    const first = await f.invoke(submitArgs)
    const recreated = createHandler(f.agent, f.host)
    const second = await recreated(submitArgs, f.agent, new AbortController().signal)
    expect(first).toMatchObject({ state: 'EFFECT_UNKNOWN', run_id: f.runId, retry_authorized: false })
    expect(JSON.stringify(first)).not.toContain('secret')
    expect(second.reason).toBe('FABRIC_ORIGINAL_ADMISSION_REFUSED')
    expect(vi.mocked(f.host.callTool).mock.calls.filter(([name]) => name === 'fabric_request')).toHaveLength(1)
  })

  it('depends on the incumbent atomic gate for simultaneous same-key calls', async () => {
    const f = fixture()
    let claimed = false
    vi.mocked(f.host.authorizeNewRun).mockImplementation(async () => {
      if (claimed) return false
      claimed = true
      return true
    })
    vi.mocked(f.host.callTool).mockImplementation(async name =>
      name === 'fabric_status' ? f.status('NOT_FOUND') : f.receipt())
    const replies = await Promise.all([f.invoke(submitArgs), f.invoke(submitArgs)])
    expect(replies.map(r => r.state).sort()).toEqual(['CONTROLLER_CREATED', 'REFUSED'])
    expect(vi.mocked(f.host.callTool).mock.calls.filter(([name]) => name === 'fabric_request')).toHaveLength(1)
  })

  it('treats a malformed post-dispatch receipt as an unknown effect', async () => {
    const f = fixture()
    vi.mocked(f.host.authorizeNewRun).mockResolvedValue(true)
    vi.mocked(f.host.callTool).mockResolvedValueOnce(f.status('NOT_FOUND'))
      .mockResolvedValueOnce({ ...f.receipt(), parent_id: 'foreign' })
    expect((await f.invoke(submitArgs)).state).toBe('EFFECT_UNKNOWN')
  })

  it('withholds after revocation but retains a verified control receipt', async () => {
    const f = fixture()
    vi.mocked(f.host.authorizeNewRun).mockResolvedValue(true)
    vi.mocked(f.host.callTool).mockResolvedValueOnce(f.status('NOT_FOUND'))
      .mockImplementationOnce(async () => { f.revoke(); return f.receipt() })
    expect(await f.invoke(submitArgs)).toMatchObject({
      state: 'CONTROLLER_CREATED', run_id: f.runId, response_withheld: true,
      submission_recorded: true, worker_started: false, retry_authorized: false,
    })
  })

  it('drains an interrupted submitted request without issuing remote cancellation', async () => {
    const f = fixture(), abort = new AbortController()
    const pending = Promise.withResolvers<unknown>()
    const entered = Promise.withResolvers<void>()
    vi.mocked(f.host.authorizeNewRun).mockResolvedValue(true)
    vi.mocked(f.host.callTool).mockResolvedValueOnce(f.status('NOT_FOUND'))
      .mockImplementationOnce(() => { entered.resolve(); return pending.promise })
    let settled = false
    const call = f.invoke(submitArgs, abort.signal).finally(() => { settled = true })
    await entered.promise
    abort.abort()
    await Promise.resolve()
    expect(settled).toBe(false)
    pending.resolve(f.receipt())
    expect(await call).toMatchObject({ state: 'CONTROLLER_CREATED', response_withheld: true,
      remote_cancellation_requested: false })
    expect(vi.mocked(f.host.callTool).mock.calls.map(([name]) => name))
      .toEqual(['fabric_status', 'fabric_request'])
  })

  it('refuses an already interrupted invocation before any owner call', async () => {
    const f = fixture(), abort = new AbortController()
    abort.abort()
    expect((await f.invoke(submitArgs, abort.signal)).reason).toBe('LOCAL_CALL_INTERRUPTED')
    expect(f.host.callTool).not.toHaveBeenCalled()
  })

  it('refuses pre-dispatch currentness loss after admission', async () => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValue(f.status('NOT_FOUND'))
    vi.mocked(f.host.authorizeNewRun).mockImplementation(async () => { f.revoke(); return true })
    expect((await f.invoke(submitArgs)).reason).toBe('NATIVE_RESPONSE_WITHHELD')
    expect(f.host.callTool).toHaveBeenCalledTimes(1)
  })
})

describe('bounded original-parent result release', () => {
  it('verifies bytes and digest between exact terminal lineage reads without accepting', async () => {
    const f = fixture()
    const r = await f.invoke({ action: 'result', task_key: submitArgs.task_key })
    expect(r).toMatchObject({ state: 'TERMINAL', result_transfer_verified: true,
      result_text: f.responseText, acceptance_changed: false, worker_started: false })
    expect(vi.mocked(f.host.callTool).mock.calls.map(([name]) => name))
      .toEqual(['fabric_status', 'fabric_result', 'fabric_status'])
    expect(f.host.callTool).toHaveBeenNthCalledWith(2, 'fabric_result',
      { run_id: f.runId, root_id: f.grant.root_id, max_bytes: 8192 })
  })

  it.each([
    ['response_sha256', '0'.repeat(64), 'FABRIC_RESULT_DIGEST_MISMATCH'],
    ['response_bytes', 8193, 'FABRIC_RESULT_TRANSFER_INVALID'],
    ['response_bytes', 0, 'FABRIC_RESULT_DIGEST_MISMATCH'],
    ['accept_run_id', 'foreign-attempt', 'FABRIC_RESULT_IDENTITY_MISMATCH'],
    ['root_id', 'foreign-root', 'FABRIC_RESULT_IDENTITY_MISMATCH'],
  ])('withholds altered %s', async (key, value, reason) => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValueOnce(f.status())
      .mockResolvedValueOnce({ ...f.result(), [key]: value })
    const r = await f.invoke({ action: 'result', task_key: submitArgs.task_key })
    expect(r.reason).toBe(reason)
    expect(r).not.toHaveProperty('result_text')
  })

  it('withholds a result when canonical attempt changes after transfer', async () => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValueOnce(f.status()).mockResolvedValueOnce(f.result())
      .mockResolvedValueOnce(f.status('TERMINAL', { effective_run_id: 'another-attempt' }))
    const r = await f.invoke({ action: 'result', task_key: submitArgs.task_key })
    expect(r.reason).toBe('FABRIC_RESULT_LINEAGE_CHANGED')
    expect(r).not.toHaveProperty('result_text')
  })

  it('withholds after final native permission revocation', async () => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValueOnce(f.status()).mockResolvedValueOnce(f.result())
      .mockImplementationOnce(async () => { f.revoke(); return f.status() })
    const r = await f.invoke({ action: 'result', task_key: submitArgs.task_key })
    expect(r.reason).toBe('NATIVE_RESPONSE_WITHHELD')
    expect(r).not.toHaveProperty('result_text')
  })

  it('does not release or submit on status without proven parent lineage', async () => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValue(f.status('ACTIVE_OR_WAITING', { root_verified: false }))
    expect((await f.invoke(submitArgs)).state).toBe('UNVERIFIED')
    expect(f.host.authorizeNewRun).not.toHaveBeenCalled()
    expect((await f.invoke({ action: 'result', task_key: submitArgs.task_key })).reason)
      .toBe('FABRIC_RESULT_NOT_TERMINAL')
    expect(vi.mocked(f.host.callTool).mock.calls.every(([name]) => name === 'fabric_status')).toBe(true)
  })

  it('rejects foreign canonical parent and never echoes raw transport errors', async () => {
    const f = fixture(), raw = f.status()
    raw.status.parent_run_id = 'different-parent'
    vi.mocked(f.host.callTool).mockResolvedValue(raw)
    expect((await f.invoke()).state).toBe('UNAVAILABLE')
    vi.mocked(f.host.callTool).mockRejectedValue(new Error('credential=do-not-render'))
    const r = await f.invoke()
    expect(JSON.stringify(r)).not.toContain('credential')
    expect(r.state).toBe('UNAVAILABLE')
  })
})

describe('retained refusal and grant boundaries', () => {
  it('reports the exact retained prelaunch refusal as correlation, never canonical admission', async () => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValue({
      schema: 'mastermind.fabric_mcp.v1', action: 'fabric_status',
      run_id: f.runId, root_id: f.grant.root_id, root_verified: false, effective_run_id: f.runId,
      status: {
        schema: 'mastermind.fabric_task_status.v1', state: 'REQUEST_REFUSED_BEFORE_LAUNCH',
        run_id: f.runId, request_root_id: f.grant.root_id, request_parent_run_id: f.grant.parent_id,
        request_retained: true, execution_absence_proven: true, result_available: false,
        same_run_replay_allowed: false,
        continuation: { controller_return: 'RECORDED', requested_run_id: f.runId, effective_run_id: f.runId },
      },
      parent_recovery: {
        schema: 'mastermind.fabric_parent_recovery_projection.v1', requested_run_id: f.runId,
        effective_run_id: f.runId, request_correlation_only: true, disposition: 'RECONCILE_PRELAUNCH_REFUSAL',
      },
    })
    expect(await f.invoke(submitArgs)).toMatchObject({
      state: 'REQUEST_REFUSED_BEFORE_LAUNCH', request_correlation_only: true,
      root_verified: false, retry_authorized: false, result_consumption_authorized: false,
    })
    expect(f.host.authorizeNewRun).not.toHaveBeenCalled()
    expect(f.host.callTool).toHaveBeenCalledTimes(1)
  })

  it('rejects a host grant for another session before any Fabric observation', async () => {
    const f = fixture()
    vi.mocked(f.host.authorizeSession).mockResolvedValue({ ...f.grant, session_id: 'other-session' })
    expect((await f.invoke()).reason).toBe('NATIVE_SESSION_NOT_AUTHORIZED')
    expect(f.host.callTool).not.toHaveBeenCalled()
  })

  it('does not accept a truthy malformed admission response', async () => {
    const f = fixture()
    vi.mocked(f.host.callTool).mockResolvedValue(f.status('NOT_FOUND'))
    vi.mocked(f.host.authorizeNewRun).mockResolvedValue('yes' as unknown as boolean)
    expect((await f.invoke(submitArgs)).reason).toBe('FABRIC_ORIGINAL_ADMISSION_REFUSED')
    expect(f.host.callTool).toHaveBeenCalledTimes(1)
  })
})
