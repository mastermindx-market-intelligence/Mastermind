import { createHash } from 'node:crypto'
import { Socket } from 'node:net'
import { isAbsolute, normalize } from 'node:path'

const FRAME = 32768
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
const SHA40 = /^[a-f0-9]{40}$/
const SHA64 = /^[a-f0-9]{64}$/
const ENV_KEYS = ['MMX_ACP_WORKSPACE_PATH', 'MMX_ACP_WORKSPACE_BASE_SHA',
  'MMX_ACP_RUN_ID', 'MMX_ACP_JOB_ID', 'MMX_ACP_WORKER_ID', 'MMX_ACP_DEADLINE_MS']
const SEED_KEYS = ['schema', 'run_id', 'job_id', 'worker_id', 'launch_nonce',
  'pid', 'base_sha', 'projection_sha256', 'artifact_sha256', 'admitted_tools', 'attempt_overlay']
function refuse() {
  return Object.assign(new Error('DSH_NATIVE_ATTEMPT_REFUSED'), { code: 'DSH_NATIVE_ATTEMPT_REFUSED' })
}
function obj(x, keys) {
  return x !== null && typeof x === 'object' && !Array.isArray(x)
    && Object.getPrototypeOf(x) === Object.prototype
    && JSON.stringify(Object.keys(x).sort()) === JSON.stringify([...keys].sort())
}
function canonical(x) {
  if (typeof x === 'string') return JSON.stringify(x).replace(/[\u007f-\uffff]/g,
    ch => '\\u' + ch.charCodeAt(0).toString(16).padStart(4, '0'))
  if (Array.isArray(x)) return '[' + x.map(canonical).join(',') + ']'
  if (x !== null && typeof x === 'object') return '{'
    + Object.keys(x).sort().map(k => canonical(k) + ':' + canonical(x[k])).join(',') + '}'
  return JSON.stringify(x)
}
// Pure parsing: callers cannot self-grant tools from a seed. The incumbent
// native owner still verifies nonce, process, artifact and live Attempt.
export function validateNativeDshAttemptSeed(seed, projectionDigest, artifactDigest, now = Date.now()) {
  if (!obj(seed, SEED_KEYS) || seed.schema !== 'mastermind.acp_tools_ready/v2'
    || seed.pid !== process.pid || !/^[a-f0-9]{32}$/.test(seed.launch_nonce)
    || ![seed.run_id, seed.job_id, seed.worker_id].every(x => typeof x === 'string' && ID.test(x))
    || !SHA40.test(seed.base_sha) || !SHA64.test(seed.projection_sha256)
    || !SHA64.test(seed.artifact_sha256)
    || seed.projection_sha256 !== projectionDigest || seed.artifact_sha256 !== artifactDigest
    || !Array.isArray(seed.admitted_tools) || seed.admitted_tools.length < 1
    || seed.admitted_tools.length > 16 || seed.admitted_tools.some(t =>
      !obj(t, ['name', 'contract_sha256']) || !ID.test(t.name) || !SHA64.test(t.contract_sha256)))
    throw refuse()
  const overlay = seed.attempt_overlay
  if (!obj(overlay, ['cwd', 'env']) || !obj(overlay.env, ENV_KEYS)
    || typeof overlay.cwd !== 'string' || !isAbsolute(overlay.cwd) || overlay.cwd === '/'
    || normalize(overlay.cwd) !== overlay.cwd || overlay.cwd !== overlay.env.MMX_ACP_WORKSPACE_PATH
    || overlay.env.MMX_ACP_WORKSPACE_BASE_SHA !== seed.base_sha
    || overlay.env.MMX_ACP_RUN_ID !== seed.run_id
    || overlay.env.MMX_ACP_JOB_ID !== seed.job_id
    || overlay.env.MMX_ACP_WORKER_ID !== seed.worker_id)
    throw refuse()
  for (const key of ENV_KEYS) {
    const value = overlay.env[key]
    if (typeof value !== 'string' || !value || value.length > 4096
      || /[\r\n\0]/.test(value)) throw refuse()
  }
  const d = overlay.env.MMX_ACP_DEADLINE_MS, deadline = Number(d)
  if (!/^\d{1,16}$/.test(d) || !Number.isSafeInteger(deadline)
    || String(deadline) !== d || deadline <= now || deadline > now + 86400000
    || deadline > 8640000000000000) throw refuse()
  return Object.freeze({
    attemptOverlay: structuredClone(overlay),
    digest: createHash('sha256').update(canonical(overlay)).digest('hex'),
  })
}
// One-shot client for the existing inherited ACP admission FD. No separate
// socket, provider request, Retry, auth, Job/Attempt or worker owner.
export async function acceptNativeDshAttempt({ fd, signal, projectionDigest, artifactDigest, activate }) {
  if (!Number.isInteger(fd) || fd < 3 || !(signal instanceof AbortSignal)
    || !SHA64.test(projectionDigest ?? '') || !SHA64.test(artifactDigest ?? '')
    || typeof activate !== 'function') throw refuse()
  signal.throwIfAborted()
  const socket = new Socket({ fd, readable: true, writable: true })
  let held = '', pending, error
  const queue = []
  const deliver = () => {
    if (!pending) return
    if (error) { const p = pending; pending = null; p.reject(error) }
    else if (queue.length) { const p = pending; pending = null; p.resolve(queue.shift()) }
  }
  const fail = () => { error = refuse(); deliver() }
  const onData = chunk => {
    held += chunk.toString('utf8')
    if (Buffer.byteLength(held) > FRAME * 2) return fail()
    let i
    while ((i = held.indexOf('\n')) >= 0) {
      const row = held.slice(0, i)
      if (Buffer.byteLength(row) > FRAME) return fail()
      queue.push(row); held = held.slice(i + 1)
    }
    deliver()
  }
  const line = () => error ? Promise.reject(error) : queue.length
    ? Promise.resolve(queue.shift()) : new Promise((resolve, reject) => { pending = { resolve, reject } })
  const onAbort = () => fail()
  socket.on('data', onData); socket.on('end', fail); socket.on('error', fail)
  signal.addEventListener('abort', onAbort, { once: true })
  if (signal.aborted) fail()
  let opened
  try {
    const seed = JSON.parse(await line())
    const verified = validateNativeDshAttemptSeed(seed, projectionDigest, artifactDigest)
    signal.throwIfAborted()
    // Only an attested installed factory may supply this callback. It must
    // resolve AFTER real governed MCP discovery, never at profile allocation.
    opened = await activate(verified.attemptOverlay, seed.admitted_tools)
    if (opened?.ready !== true) throw refuse()
    signal.throwIfAborted()
    // No parent early ACK, duplicate seed or second command may be queued.
    if (queue.length || held.length) throw refuse()
    if (Date.now() >= Number(verified.attemptOverlay.env.MMX_ACP_DEADLINE_MS)) throw refuse()
    const echo = JSON.stringify({ ...seed, ready: true, attempt_overlay_sha256: verified.digest }) + '\n'
    if (Buffer.byteLength(echo) > FRAME) throw refuse()
    await new Promise((resolve, reject) => socket.write(echo, e => e ? reject(refuse()) : resolve()))
    const ack = JSON.parse(await line())
    if (!obj(ack, ['accepted']) || ack.accepted !== true
      || queue.length || held.length) throw refuse()
    signal.throwIfAborted()
    if (Date.now() >= Number(verified.attemptOverlay.env.MMX_ACP_DEADLINE_MS)) throw refuse()
    return { activation: opened, attemptOverlay: verified.attemptOverlay }
  } catch {
    try { await opened?.dispose?.() } catch { /* incumbent settles child */ }
    throw refuse()
  } finally {
    signal.removeEventListener('abort', onAbort)
    socket.off('data', onData)
    socket.off('end', fail)
    socket.off('error', fail)
    socket.end()
  }
}
