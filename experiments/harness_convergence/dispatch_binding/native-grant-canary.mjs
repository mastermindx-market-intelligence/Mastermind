// Ordinary-Node policy-to-profile canary. All grants and disk inputs are synthetic.
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createHash, randomUUID } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { setTimeout as sleep } from 'node:timers/promises'
import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
const scenario = process.argv[2]
assert.ok(['normal', 'revoked', 'schema-drift', 'target-mismatch', 'source-mismatch', 'missing-tool', 'wrong-version', 'startup-revoked'].includes(scenario))
const here = dirname(fileURLToPath(import.meta.url)), cache = resolve(here, '.cache')
const sha = data => createHash('sha256').update(data).digest('hex')
const receipt = JSON.parse(readFileSync(resolve(cache, 'profile-build-result.json'), 'utf8'))
assert.match(receipt.artifact, /^profile-build-[A-Za-z0-9]+\/index\.mjs$/)
const artifact = resolve(cache, receipt.artifact)
assert.equal(sha(readFileSync(artifact)), receipt.artifact_sha256)
const built = await import(pathToFileURL(artifact).href)
assert.equal(typeof built.createDshGrantedToolProfile, 'function', 'Built grant-aware profile is missing')
const root = mkdtempSync(resolve(cache, 'native-grant-')), home = resolve(root, 'home'), nonce = randomUUID()
mkdirSync(home)
const inputs = { 'memo.txt': `grant\nneedle ${nonce}\n`, 'signals.txt': `needle ${nonce}\n` }
writeFileSync(resolve(root, 'fixture.json'), JSON.stringify({ kind: 'mmx-synthetic-stdio-test', nonce }))
for (const [file, text] of Object.entries(inputs)) writeFileSync(resolve(root, file), text)
const events = () => existsSync(resolve(root, 'events.jsonl'))
  ? readFileSync(resolve(root, 'events.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : []
const ctx = new Context(), prompt = await ctx.plugin(SystemPrompt)
const runtime = await ctx.plugin(built.ToolRuntime, { strictDispatchBinding: true })
const config = { transport: 'stdio', serverName: 'granted', command: process.execPath,
  args: [resolve(here, 'stdio-fixture-server.mjs'), root, 'normal'], cwd: root,
  env: { HOME: home, PATH: `${dirname(process.execPath)}:/usr/bin:/bin`, TMPDIR: root },
  toolCallTimeoutMs: 1500, failOnStartupError: true, reconnect: { enabled: false } }
const controller = new AbortController(), captureController = new AbortController()
let capture, fiber, projection, snapshot, workload, refusal, sourceBinding, discoveryPids
const state = { allowed: true }, phases = []
let preflightObserved = false, releaseRevocationHook = () => {}
try {
  // Discover only the known test fixture, using the incumbent profile/lifecycle.
  capture = ctx.plugin(built.createDshToolProfile({ signal: captureController.signal,
    admitGeneration(value) { snapshot = value; return [] } }), config)
  await capture; await capture.dispose(); captureController.abort()
  discoveryPids = events().filter(e => e.event === 'start').map(e => e.pid)
  assert.equal(discoveryPids.length, 2)
  const python = process.env.MMX_TEST_PYTHON
  assert.ok(python?.startsWith('/'), 'Exact test Python executable required')
  const generated = spawnSync(python, ['-B', resolve(here, 'grant-projection-fixture.py')], {
    cwd: here, input: JSON.stringify({ fixture: 'synthetic-dsh-grant-canary', config, snapshot }),
    env: { PATH: process.env.PATH, HOME: home, TMPDIR: root }, encoding: 'utf8', timeout: 15000, maxBuffer: 300000,
  })
  assert.equal(generated.status, 0, generated.stderr); assert.equal(generated.stderr, '')
  projection = JSON.parse(generated.stdout)
  assert.equal(projection.production_armed, false)
  sourceBinding = structuredClone({ source: projection.source, target: projection.target, serverInfo: projection.serverInfo })
  const actualConfig = structuredClone(config)
  if (scenario === 'schema-drift') projection.tools[0].inputSchema = { type: 'null' }
  if (scenario === 'target-mismatch') actualConfig.serverName = 'foreign'
  if (scenario === 'source-mismatch') projection.source.profile_digest = 'd'.repeat(64)
  if (scenario === 'missing-tool') projection.tools[0].name = 'absent'
  if (scenario === 'wrong-version') projection.serverInfo.version = '999'
  if (scenario === 'startup-revoked') releaseRevocationHook = ctx.on('tools/execute', async (execution, next) => {
    const result = await next()
    if (execution.name.startsWith('mmx_dispatch_probe_')) {
      preflightObserved = true
      state.allowed = false
    }
    return result
  })
  const activate = async () => {
    fiber = ctx.plugin(built.createDshGrantedToolProfile({ projection, signal: controller.signal,
      isCurrentBinding(binding, request) {
        phases.push(request.phase)
        // Fixture-only witness. Production must attest DSH/Attempt/realm separately.
        return state.allowed && binding.source.profile_digest === sourceBinding.source.profile_digest
          && binding.source.grant_digest === sourceBinding.source.grant_digest
      },
    }), actualConfig)
    await fiber
  }
  if (['normal', 'revoked'].includes(scenario)) {
    await activate()
    const call = (name, args) => ctx.tools.execute({ name: `mcp__granted__${name}`, arguments: args,
      signal: controller.signal, callId: randomUUID() })
    const read = await call('read_file', { file: 'memo.txt' }); assert.equal(read.isError, false)
    workload = { read: JSON.parse(read.value.content[0].text) }
    assert.equal(workload.read.nonce, nonce); assert.equal(workload.read.text, inputs['memo.txt'])
    assert.equal(workload.read.sha256, sha(workload.read.text))
    if (scenario === 'revoked') state.allowed = false
    const search = await call('search_files', { query: nonce })
    assert.equal(search.isError, scenario === 'revoked')
    if (!search.isError) {
      workload.search = JSON.parse(search.value.content[0].text)
      assert.deepEqual(workload.search.matches, [
        { file: 'memo.txt', line: 2, text: `needle ${nonce}` },
        { file: 'signals.txt', line: 1, text: `needle ${nonce}` }])
    }
    assert.equal((await call('write_file', {})).isError, true)
  } else {
    await assert.rejects(activate(), error => {
      refusal = { name: error.name, code: error.code ?? null, message: error.message }
      if (scenario === 'startup-revoked') return true // Process count below distinguishes the boundary.
      return ['target-mismatch', 'source-mismatch'].includes(scenario)
        ? error.code === 'DSH_MCP_GRANT_REFUSED'
        : error.message.includes('initial connection or tool synchronization failed')
    })
  }
} finally {
  controller.abort(); captureController.abort(); releaseRevocationHook()
  await fiber?.dispose(); await capture?.dispose(); await runtime.dispose(); await prompt.dispose()
}
function alive(pid) {
  try { process.kill(pid, 0); return true }
  catch (error) { if (error.code === 'ESRCH') return false; throw error }
}
const starts = events().filter(e => e.event === 'start')
for (const start of starts) {
  const until = Date.now() + 3000
  while (alive(start.pid) && Date.now() < until) await sleep(10)
  assert.equal(alive(start.pid), false)
}
const reads = events().filter(e => e.event === 'read').length
const searches = events().filter(e => e.event === 'search').length
assert.equal(reads, ['normal', 'revoked'].includes(scenario) ? 1 : 0)
assert.equal(searches, scenario === 'normal' ? 1 : 0)
assert.equal(starts.length, ['target-mismatch', 'source-mismatch', 'startup-revoked'].includes(scenario) ? 2 : 4,
  'Revoked startup must not create MCP processes after preflight')
if (scenario === 'startup-revoked') {
  assert.equal(preflightObserved, true)
  assert.equal(refusal.code, 'DSH_MCP_GRANT_REFUSED')
}
assert.equal(events().some(e => e.event === 'ungranted-write'), false)
assert.ok(Object.entries(inputs).every(([file, text]) => readFileSync(resolve(root, file), 'utf8') === text))
const result = { success: true, scenario, artifact_sha256: receipt.artifact_sha256,
  sourceBinding, projection_sha256: sha(JSON.stringify(projection)), phases, preflightObserved,
  read_calls: reads, search_calls: searches, discovery_pids: discoveryPids,
  fixture_pids: starts.map(e => e.pid), fixture_children_absent: true, inputs_unchanged: true,
  workload, refusal, model_requests: 0,
  scope: 'Synthetic existing Python grant types/digest -> compiled DSH profile -> actual MCP process; no production admission' }
writeFileSync(resolve(cache, `native-grant-${scenario}.json`), JSON.stringify(result, null, 2) + '\n')
console.log(JSON.stringify({ success: true, scenario, read_calls: reads, search_calls: searches }))
