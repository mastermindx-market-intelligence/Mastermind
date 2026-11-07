// Candidate-artifact test only: no ACP admission, provider calls or live repository inputs.
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { randomUUID, createHash } from 'node:crypto'
import { setTimeout as sleep } from 'node:timers/promises'
import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'

const scenario = process.argv[2]
assert.ok(['normal', 'disabled-core', 'startup-refused', 'pre-aborted'].includes(scenario))
const here = dirname(fileURLToPath(import.meta.url)), cache = resolve(here, '.cache')
const receipt = JSON.parse(readFileSync(resolve(cache, 'profile-build-result.json'), 'utf8'))
assert.match(receipt.artifact, /^profile-build-[A-Za-z0-9]+\/index\.mjs$/)
const artifact = resolve(cache, receipt.artifact)
const hash = data => createHash('sha256').update(data).digest('hex')
assert.equal(hash(readFileSync(artifact)), receipt.artifact_sha256)
const { ToolRuntime, createDshToolProfile } = await import(pathToFileURL(artifact).href)
const root = mkdtempSync(resolve(cache, 'native-profile-')), nonce = randomUUID()
const home = resolve(root, 'home'); mkdirSync(home)
const inputs = { 'memo.txt': `artifact\nneedle ${nonce}\n`, 'signals.txt': `needle ${nonce}\n` }
writeFileSync(resolve(root, 'fixture.json'), JSON.stringify({ kind: 'mmx-synthetic-stdio-test', nonce }))
for (const [file, text] of Object.entries(inputs)) writeFileSync(resolve(root, file), text)
const events = () => existsSync(resolve(root, 'events.jsonl'))
  ? readFileSync(resolve(root, 'events.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : []
const ctx = new Context(), prompt = await ctx.plugin(SystemPrompt)
const runtime = await ctx.plugin(ToolRuntime, { strictDispatchBinding: scenario !== 'disabled-core' })
const controller = new AbortController()
if (scenario === 'pre-aborted') controller.abort()
let fiber, workload, refusal
const config = { transport: 'stdio', serverName: 'artifact', command: process.execPath,
  args: [resolve(here, 'stdio-fixture-server.mjs'), root, scenario === 'startup-refused' ? 'reject-list' : 'normal'],
  env: { HOME: home, PATH: `${dirname(process.execPath)}:/usr/bin:/bin`, TMPDIR: root },
  cwd: root, toolCallTimeoutMs: 1500, failOnStartupError: true, reconnect: { enabled: false } }
const admitGeneration = snapshot => {
  assert.equal(snapshot.serverInfo.name, 'mmx-stdio-fixture')
  return snapshot.tools.filter(t => ['read_file', 'search_files'].includes(t.name))
    .map(t => ({ rawName: t.name, allow: () => !controller.signal.aborted }))
}
try {
  fiber = ctx.plugin(createDshToolProfile({ admitGeneration, signal: controller.signal }), config)
  if (scenario === 'normal') {
    await fiber
    assert.deepEqual(ctx.tools.schemas().map(t => t.name).sort(), [
      'mcp__artifact__read_file', 'mcp__artifact__search_files'])
    const call = (name, args) => ctx.tools.execute({ name: `mcp__artifact__${name}`,
      arguments: args, callId: randomUUID(), signal: controller.signal })
    const read = await call('read_file', { file: 'memo.txt' })
    const search = await call('search_files', { query: nonce })
    assert.equal(read.isError, false); assert.equal(search.isError, false)
    workload = { read: JSON.parse(read.value.content[0].text), search: JSON.parse(search.value.content[0].text) }
    assert.equal(workload.read.nonce, nonce); assert.equal(workload.read.text, inputs['memo.txt'])
    assert.equal(workload.read.sha256, hash(workload.read.text))
    assert.equal(workload.search.nonce, nonce)
    assert.deepEqual(workload.search.matches, [
      { file: 'memo.txt', line: 2, text: `needle ${nonce}` },
      { file: 'signals.txt', line: 1, text: `needle ${nonce}` }])
    assert.equal((await call('write_file', {})).isError, true)
  } else {
    await assert.rejects(Promise.resolve(fiber).then(() => 'ACTIVATED'), error => {
      refusal = { name: error.name, code: error.code ?? null, message: error.message }
      return scenario === 'disabled-core' ? error.code === 'DSH_DISPATCH_PREFLIGHT_REFUSED'
        : scenario === 'pre-aborted' ? error.name === 'AbortError'
        : error.message.includes('initial connection or tool synchronization failed')
    })
  }
} finally {
  controller.abort(); await fiber?.dispose(); await runtime.dispose(); await prompt.dispose()
}
function alive(pid) {
  try { process.kill(pid, 0); return true }
  catch (error) { if (error.code === 'ESRCH') return false; throw error }
}
const starts = events().filter(e => e.event === 'start')
for (const start of starts) {
  const until = Date.now() + 3000
  while (alive(start.pid) && Date.now() < until) await sleep(10)
  assert.equal(alive(start.pid), false, 'original fixture process did not settle')
}
assert.equal(starts.length, ['disabled-core', 'pre-aborted'].includes(scenario) ? 0 : 2)
assert.ok(Object.entries(inputs).every(([file, text]) => readFileSync(resolve(root, file), 'utf8') === text))
assert.equal(events().some(e => e.event === 'ungranted-write'), false)
const result = { success: true, scenario, artifact_sha256: receipt.artifact_sha256,
  node: process.version, parent_pid: process.pid, fixture_pids: starts.map(e => e.pid),
  fixture_children_absent: true, inputs_unchanged: true, nonce, workload, refusal,
  read_calls: events().filter(e => e.event === 'read').length,
  search_calls: events().filter(e => e.event === 'search').length,
  model_requests: 0, scope: 'Built artifact in plain Node; synthetic MCP workload, not Executive/ACP admission' }
assert.equal(result.read_calls, scenario === 'normal' ? 1 : 0)
assert.equal(result.search_calls, scenario === 'normal' ? 1 : 0)
writeFileSync(resolve(cache, `native-profile-${scenario}.json`), JSON.stringify(result, null, 2) + '\n')
console.log(JSON.stringify({ success: true, scenario, artifact_sha256: receipt.artifact_sha256 }))
