import { realpathSync, statSync } from 'node:fs'
import { isAbsolute, normalize } from 'node:path'
import { isDeepStrictEqual } from 'node:util'

// A runtime *consumer* of the immutable overlay issued by the incumbent
// AcpInstalledHostPacket. No credential, Job, Attempt, grant, process, or retry
// authority is created here. The existing host callback must authenticate the
// exact binding at startup, discovery, and every dispatch.
const ACP_PROFILE = 'worker.acp.providerfree.readonly.v1'
const ACP_GRANT = 'mastermind-acp-workspace-read-v1'
const ENV_KEYS = Object.freeze([
  'MMX_ACP_DEADLINE_MS', 'MMX_ACP_JOB_ID', 'MMX_ACP_RUN_ID',
  'MMX_ACP_WORKER_ID', 'MMX_ACP_WORKSPACE_BASE_SHA', 'MMX_ACP_WORKSPACE_PATH',
])
const SAFE_PATH = '/usr/bin:/bin'
const MAX_DEADLINE_MS = 8_640_000_000_000_000
const MAX_TTL_MS = 86_400_000
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
const HEX40 = /^[0-9a-f]{40}$/

function refuse() {
  const error = new Error('DSH per-Attempt MCP overlay refused')
  error.code = 'DSH_ACP_ATTEMPT_OVERLAY_REFUSED'
  return error
}
function record(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return false
  return Object.values(Object.getOwnPropertyDescriptors(value))
    .every(descriptor => Object.hasOwn(descriptor, 'value'))
}
function keysEqual(value, keys) {
  return record(value) && isDeepStrictEqual(Object.keys(value).sort(), [...keys].sort())
}
function admittedProjection(projection) {
  const source = projection?.source
  if (!record(source) || !record(projection?.target)
    || source.profile_id !== ACP_PROFILE
    || source.capability_id !== ACP_GRANT
    || source.execution_surface !== 'acp-agent'
    || source.auth_realm !== 'dedicated-worker-no-auth'
    || source.auth_status !== 'unsupported'
    || projection.target.transport !== 'stdio'
    || projection.target.serverName !== 'mastermindAcpWorkspaceRead') throw refuse()
}

/**
 * ACP MUST provide one host-authenticated, exact per-Attempt overlay. All
 * other grant surfaces keep their current behavior and cannot borrow an ACP
 * overlay. The fixed target command/argv and grant catalog remain untouched.
 *
 * Only the incumbent isCurrentBinding callback can attest a live Attempt:
 * every callback receives the captured immutable attempt claim as request.attempt.
 */
export function compileDshAttemptOverlay(projection, rawOverlay) {
  const source = projection?.source
  const isAcp = source?.profile_id === ACP_PROFILE
    || source?.execution_surface === 'acp-agent'
    || source?.capability_id === ACP_GRANT
  if (!isAcp) {
    if (rawOverlay !== undefined) throw refuse()
    return null
  }
  admittedProjection(projection)
  if (!keysEqual(rawOverlay, ['cwd', 'env'])
    || typeof rawOverlay.cwd !== 'string'
    || !keysEqual(rawOverlay.env, ENV_KEYS)) throw refuse()

  const cwd = rawOverlay.cwd
  if (!isAbsolute(cwd) || cwd === '/' || normalize(cwd) !== cwd || cwd.includes('\0')) throw refuse()
  try {
    if (realpathSync(cwd) !== cwd || !statSync(cwd).isDirectory()) throw refuse()
  } catch { throw refuse() }

  const env = {}
  for (const key of ENV_KEYS) {
    const value = rawOverlay.env[key]
    if (typeof value !== 'string' || !value || Buffer.byteLength(value, 'utf8') > 4096
      || /[\0\r\n]/.test(value)) throw refuse()
    env[key] = value
  }
  if (env.MMX_ACP_WORKSPACE_PATH !== cwd
    || !HEX40.test(env.MMX_ACP_WORKSPACE_BASE_SHA)
    || ![env.MMX_ACP_JOB_ID, env.MMX_ACP_RUN_ID, env.MMX_ACP_WORKER_ID].every(v => ID.test(v)))
    throw refuse()
  const deadline = Number(env.MMX_ACP_DEADLINE_MS)
  const now = Date.now()
  if (!/^\d{1,16}$/.test(env.MMX_ACP_DEADLINE_MS)
    || !Number.isSafeInteger(deadline) || deadline <= now
    || deadline > MAX_DEADLINE_MS || deadline > now + MAX_TTL_MS) throw refuse()
  // The pinned donor transport fills omitted safe defaults from process.env.
  // Override its HOME/TMPDIR fallbacks with the already-admitted workspace,
  // never the caller's ambient credential-bearing home or temporary directory.
  const fixedEnv = Object.freeze({ PATH: SAFE_PATH, HOME: cwd, TMPDIR: cwd, ...env })
  const claim = Object.freeze({
    schema: 'mastermind.dsh_acp_attempt_binding.v1',
    cwd, env: Object.freeze({ ...env }),
  })

  const isLive = () => Date.now() < deadline
  function assertConfig(config) {
    if (!isLive() || !record(config) || config.transport !== 'stdio'
      || config.cwd !== cwd || !isDeepStrictEqual(config.env, fixedEnv)) throw refuse()
  }
  return Object.freeze({
    claim, isLive,
    bind(config) {
      if (!isLive()) throw refuse()
      // Cordis snapshots and normalizes its *documented* MCP defaults before
      // the profile callback: empty cwd/env, bounded instructions, disabled
      // reconnect with fixed inert backoff fields. These are not authority.
      const reconnect = config?.reconnect
      const keys = record(reconnect) ? Object.keys(reconnect).sort() : []
      const reduced = isDeepStrictEqual(keys, ['enabled'])
      const normalized = isDeepStrictEqual(keys,
        ['enabled', 'initialDelayMs', 'maxAttempts', 'maxDelayMs'].sort())
        && reconnect.initialDelayMs === 500
        && reconnect.maxDelayMs === 30000
        && reconnect.maxAttempts === 10
      if (!record(config) || config.transport !== 'stdio'
        || config.failOnStartupError !== true
        || !record(reconnect) || reconnect.enabled !== false
        || !(reduced || normalized)
        || (config.cwd !== undefined && config.cwd !== '' && config.cwd !== cwd)
        || (config.env !== undefined
          && !(keysEqual(config.env, [])
            || (keysEqual(config.env, ['PATH']) && config.env.PATH === SAFE_PATH)))
        || Object.keys(config).some(key => ![
          'transport', 'serverName', 'command', 'args', 'failOnStartupError',
          'reconnect', 'toolCallTimeoutMs', 'maxInstructionBytes', 'cwd', 'env',
        ].includes(key))
        || (config.toolCallTimeoutMs !== undefined
          && (!Number.isSafeInteger(config.toolCallTimeoutMs)
            || config.toolCallTimeoutMs < 1 || config.toolCallTimeoutMs > 30000))
        || (config.maxInstructionBytes !== undefined
          && (!Number.isSafeInteger(config.maxInstructionBytes)
            || config.maxInstructionBytes < 0 || config.maxInstructionBytes > 32768)))
        throw refuse()
      return { ...config, cwd, env: { ...fixedEnv } }
    },
    assertConfig,
  })
}
