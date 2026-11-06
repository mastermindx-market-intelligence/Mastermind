import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, realpathSync, rmSync, symlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { compileDshAttemptOverlay } from '../../integrations/acp_worker/dsh_attempt_overlay.mjs'

function setup(t) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'mmx-attempt-overlay-')))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const projection = {
    source: {
      profile_id: 'worker.acp.providerfree.readonly.v1',
      capability_id: 'mastermind-acp-workspace-read-v1',
      execution_surface: 'acp-agent', auth_realm: 'dedicated-worker-no-auth',
      auth_status: 'unsupported',
    },
    target: { serverName: 'mastermindAcpWorkspaceRead', transport: 'stdio',
      command: '/usr/bin/python3', args: [] },
  }
  const env = {
    MMX_ACP_WORKSPACE_PATH: root,
    MMX_ACP_WORKSPACE_BASE_SHA: 'a'.repeat(40),
    MMX_ACP_RUN_ID: 'run-1', MMX_ACP_JOB_ID: 'job-1',
    MMX_ACP_WORKER_ID: 'worker-1',
    MMX_ACP_DEADLINE_MS: String(Date.now() + 30_000),
  }
  const overlay = { cwd: root, env }
  const config = { ...projection.target, failOnStartupError: true,
    reconnect: { enabled: false }, toolCallTimeoutMs: 2500 }
  return { root, projection, overlay, config }
}
const denied = f => assert.throws(f, { code: 'DSH_ACP_ATTEMPT_OVERLAY_REFUSED' })

test('exact trusted Attempt binds real child cwd/env and never inherits ambient secrets', t => {
  const f = setup(t)
  const compiled = compileDshAttemptOverlay(f.projection, f.overlay)
  const bound = compiled.bind(f.config)
  compiled.assertConfig(bound)
  assert.equal(bound.command, f.projection.target.command)
  assert.deepEqual(bound.args, f.projection.target.args)
  assert.deepEqual(Object.keys(bound.env).sort(),
    ['PATH', 'HOME', 'TMPDIR', ...Object.keys(f.overlay.env)].sort())
  const secretKey = 'OPENAI_API_KEY'
  const previous = process.env[secretKey]
  process.env[secretKey] = 'must-never-reach-child'
  try {
    const child = spawnSync(process.execPath, ['-e', 'process.stdout.write(JSON.stringify({cwd:process.cwd(),env:process.env}))'],
      { cwd: bound.cwd, env: bound.env, encoding: 'utf8', timeout: 3000 })
    assert.equal(child.status, 0, child.stderr)
    const seen = JSON.parse(child.stdout)
    assert.equal(seen.cwd, f.root)
    assert.equal(seen.env.HOME, f.root)
    assert.equal(seen.env.TMPDIR, f.root)
    assert.equal(seen.env.MMX_ACP_JOB_ID, 'job-1')
    assert.equal(seen.env.MMX_ACP_WORKER_ID, 'worker-1')
    assert.equal(seen.env.OPENAI_API_KEY, undefined)
    // macOS launch services may inject this one OS text-encoding hint even
    // when spawnSync supplies an exact private environment.
    const observed = Object.keys(seen.env).filter(key => key !== '__CF_USER_TEXT_ENCODING')
    assert.deepEqual(observed.sort(), Object.keys(bound.env).sort())
    assert.equal(seen.env.NODE_OPTIONS, undefined)
  } finally {
    if (previous === undefined) delete process.env[secretKey]
    else process.env[secretKey] = previous
  }
  f.overlay.env.MMX_ACP_JOB_ID = 'mutated-after-binding'
  assert.equal(compiled.claim.env.MMX_ACP_JOB_ID, 'job-1')
  assert.equal(compiled.bind(f.config).env.MMX_ACP_JOB_ID, 'job-1')
  assert.equal(Object.isFrozen(compiled.claim.env), true)
})

test('untrusted source identity, missing and borrowed ACP overlays fail closed', t => {
  const f = setup(t)
  denied(() => compileDshAttemptOverlay(f.projection))
  for (const source of [
    { ...f.projection.source, profile_id: 'operator.other.v1' },
    { ...f.projection.source, auth_realm: 'dedicated-worker-account' },
    { ...f.projection.source, capability_id: 'other-mcp-v1' },
  ]) denied(() => compileDshAttemptOverlay({ ...f.projection, source }, f.overlay))
  denied(() => compileDshAttemptOverlay({
    ...f.projection, target: { ...f.projection.target, transport: 'streamable-http' },
  }, f.overlay))
  const unrelated = { source: { profile_id: 'other', capability_id: 'other',
    execution_surface: 'codex-app-server' } }
  assert.equal(compileDshAttemptOverlay(unrelated), null)
  denied(() => compileDshAttemptOverlay(unrelated, f.overlay))
})

test('environment injection, malformed source and foreign/symlink paths fail before spawn', t => {
  const f = setup(t)
  for (const changed of [
    { cwd: f.root, env: { ...f.overlay.env, OPENAI_API_KEY: 'secret' } },
    { cwd: f.root, env: { ...f.overlay.env, MMX_ACP_RUN_ID: 'bad\nrun' } },
    { cwd: f.root, env: { ...f.overlay.env, MMX_ACP_WORKSPACE_BASE_SHA: 'zz' } },
    { cwd: f.root, env: { ...f.overlay.env, MMX_ACP_DEADLINE_MS: String(Date.now() - 100) } },
    { cwd: f.root, env: { ...f.overlay.env, MMX_ACP_DEADLINE_MS: String(Date.now() + 86_401_000) } },
    { cwd: f.root, env: { ...f.overlay.env, MMX_ACP_WORKSPACE_PATH: '/tmp/foreign' } },
    { cwd: '/tmp/missing-restricted-attempt-workspace', env: f.overlay.env },
    { cwd: f.root, env: Object.create({ MMX_ACP_JOB_ID: 'inherited' }) },
  ]) denied(() => compileDshAttemptOverlay(f.projection, changed))
  const link = join(f.root, 'symlink'); symlinkSync(f.root, link)
  denied(() => compileDshAttemptOverlay(f.projection, { cwd: link,
    env: { ...f.overlay.env, MMX_ACP_WORKSPACE_PATH: link } }))
  const getter = { cwd: f.root }
  Object.defineProperty(getter, 'env', { enumerable: true, get() { throw new Error('should not run') } })
  denied(() => compileDshAttemptOverlay(f.projection, getter))
})

test('configuration drift/reconnect/ambient environment are refused, including after snapshot', t => {
  const f = setup(t)
  const compiled = compileDshAttemptOverlay(f.projection, f.overlay)
  for (const change of [
    { cwd: '/tmp/foreign' }, { env: { PATH: '/usr/bin:/bin', NODE_OPTIONS: '--inspect' } },
    { env: { HOME: f.root } }, { env: { PATH: '/evil' } },
    { reconnect: { enabled: true } }, { failOnStartupError: false },
    { toolCallTimeoutMs: 60_000 }, { untrustedOption: true },
  ]) denied(() => compiled.bind({ ...f.config, ...change }))
  const bound = compiled.bind(f.config)
  bound.env.MMX_ACP_JOB_ID = 'later-mutated'
  denied(() => compiled.assertConfig(bound))
  const repaired = compiled.bind(f.config)
  repaired.cwd = '/tmp/foreign'
  denied(() => compiled.assertConfig(repaired))
  const cordisDefaults = { ...f.config, cwd: '', env: {},
    maxInstructionBytes: 32768, reconnect: {
      enabled: false, initialDelayMs: 500, maxDelayMs: 30000, maxAttempts: 10,
    } }
  compiled.assertConfig(compiled.bind(cordisDefaults))
  denied(() => compiled.bind({ ...cordisDefaults,
    reconnect: { ...cordisDefaults.reconnect, enabled: true } }))
  denied(() => compiled.bind({ ...cordisDefaults,
    reconnect: { ...cordisDefaults.reconnect, maxAttempts: 999 } }))
  denied(() => compiled.bind({ ...cordisDefaults, maxInstructionBytes: 32769 }))
  const validConfig = compiled.bind(f.config)
  const originalNow = Date.now
  try {
    Date.now = () => Number(f.overlay.env.MMX_ACP_DEADLINE_MS) + 1
    assert.equal(compiled.isLive(), false)
    denied(() => compiled.bind(f.config))
    denied(() => compiled.assertConfig(validConfig))
  } finally { Date.now = originalNow }
})
