// Real native renderer/gateway journey with the upstream scripted provider.
// This is NOT live Nous login, real model intelligence or physical-phone acceptance.
// Requires the donor's already-qualified Python environment and built Webapp bundle.
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { createServer } from 'node:net'
import { createRequire } from 'node:module'
import { cp, mkdir, mkdtemp, symlink, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const donor = resolve(process.env.MOBILE_QUALIFICATION_ROOT || '')
const python = process.env.MOBILE_TEST_PYTHON
const bundle = process.env.MOBILE_DONOR_BUNDLE
const output = process.env.MOBILE_NATIVE_PROOF_OUTPUT
if (!python || !bundle || !output || !process.env.MOBILE_QUALIFICATION_ROOT) throw new Error('Explicit qualified source, test Python, bundle and output paths are required')
if (donor.includes('/.hermes/') || !existsSync(join(donor, 'tests/gateway/fixtures'))) throw new Error('Use the disposable qualification source, not the live Hermes installation')
const require = createRequire(join(donor, 'package.json'))
const { chromium } = require('playwright')
const { startScriptedProvider, gate } = await import(pathToFileURL(join(donor, 'apps/desktop/e2e/core/provider.ts')).href)
await mkdir(output, { recursive: true })
const sandbox = await mkdtemp(join(resolve(output), 'native-'))
const home = join(sandbox, 'home'), hermesHome = join(home, '.hermes'), bin = join(sandbox, 'bin')
await mkdir(hermesHome, { recursive: true }); await mkdir(bin)
await writeFile(join(bin, 'gh'), '#!/bin/sh\necho "test fixture: no GitHub credentials" >&2\nexit 1\n', { mode: 0o700 })
const targetBundle = join(donor, 'apps/desktop/dist-webapp')
if (!existsSync(targetBundle)) await symlink(resolve(bundle), targetBundle, 'dir')
assert.ok(existsSync(join(targetBundle, 'index.html')))
const provider = await startScriptedProvider()
const reserve = createServer()
await new Promise((yes, no) => { reserve.once('error', no); reserve.listen(0, '127.0.0.1', yes) })
const port = reserve.address().port
await new Promise(yes => reserve.close(yes))
const origin = `http://127.0.0.1:${port}`
const config = `model:\n  default: mock-model\n  provider: mock\nproviders:\n  mock:\n    api: ${provider.url}/v1\n    name: Mock\n    api_mode: chat_completions\n    key_env: MOCK_API_KEY\n    models:\n      mock-model: {}\n    context_length: 64000\nauxiliary:\n  title_generation:\n    enabled: false\napprovals:\n  mode: "manual"\nplugins:\n  enabled: [mastermind-mobile]\n`
for (const profile of ['default', 'secretary', 'meta-ceo-uncensored']) {
  const directory = profile === 'default' ? hermesHome : join(hermesHome, 'profiles', profile)
  await mkdir(directory, { recursive: true })
  await writeFile(join(directory, 'config.yaml'), config + (profile === 'default' ? `webapp:\n  enabled: true\n  host: 127.0.0.1\n  port: ${port}\n` : ''))
  await writeFile(join(directory, '.env'), 'MOCK_API_KEY=fixture-only\n', { mode: 0o600 })
}
const pluginDir = join(hermesHome, 'plugins/mastermind-mobile')
await mkdir(pluginDir, { recursive: true })
for (const name of ['plugin.yaml', '__init__.py', 'desktop', 'dashboard']) await cp(join(packageRoot, name), join(pluginDir, name), { recursive: true })
const env = {
  PATH: `${bin}:${process.env.PATH || '/usr/bin:/bin'}`,
  HOME: home, USERPROFILE: home, HERMES_HOME: hermesHome,
  TMPDIR: sandbox, LANG: 'en_US.UTF-8', TZ: 'UTC',
  PYTHONPATH: donor, PYTHONUNBUFFERED: '1', GIT_NO_LAZY_FETCH: '1'
}
let gateway, browser, page, gatewayExit, failure, holding
const log = [], errors = [], requests = []
const report = { scope: 'native renderer and gateway with isolated fixture profiles and upstream scripted provider', productionTouched: false, sandbox, origin, steps: [] }
const collect = chunk => { log.push(String(chunk)); while (log.reduce((n, s) => n + s.length, 0) > 100000) log.shift() }
const within = async (promise, milliseconds, label) => {
  let timer
  try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(label + ' timed out')), milliseconds) })]) }
  finally { clearTimeout(timer) }
}
const waitForInteractive = async page => {
  await page.locator('[data-slot="composer-root"] [contenteditable="true"]').first().waitFor({ timeout: 60000 })
  // Same criterion as the upstream core harness: a mounted composer under a
  // connecting/setup mask is not an interactive application. Never force-click it.
  await page.waitForFunction(() => {
    let node = document.elementFromPoint(innerWidth / 2, innerHeight / 2)
    if (!node) return false
    while (node) {
      const rectangle = node.getBoundingClientRect()
      if (getComputedStyle(node).position === 'fixed' && rectangle.left <= 1 && rectangle.top <= 1 && rectangle.right >= innerWidth - 1 && rectangle.bottom >= innerHeight - 1) return false
      node = node.parentElement
    }
    return true
  }, undefined, { timeout: 60000, polling: 250 })
}
try {
  gateway = spawn(python, ['-m', 'hermes_cli.main', 'gateway', 'run'], { cwd: donor, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'] })
  gateway.stdout.on('data', collect); gateway.stderr.on('data', collect)
  gatewayExit = new Promise(resolveExit => gateway.once('exit', (code, signal) => resolveExit({ code, signal })))
  const deadline = Date.now() + 60000
  let ready = false
  while (Date.now() < deadline && gateway.exitCode === null) {
    try { const response = await fetch(origin + '/api/status', { signal: AbortSignal.timeout(2000) }); ready = [200, 401].includes(response.status) } catch {}
    if (ready) break
    await new Promise(resolveWait => setTimeout(resolveWait, 150))
  }
  assert.ok(ready, 'isolated gateway did not become ready')
  const launchOutput = execFileSync(python, ['-m', 'hermes_cli.main', 'webapp', '--no-open', '--skip-build'], { cwd: donor, env, encoding: 'utf8', timeout: 45000 })
  const link = launchOutput.split(/\r?\n/).map(line => line.trim()).find(line => line.startsWith(origin + '/webapp/'))
  assert.ok(link, 'native CLI did not return this fixture gateway launch link')
  report.steps.push('isolated gateway ready; native one-use launch link acquired without logging it')
  browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light', hasTouch: true, reducedMotion: 'reduce' })
  await context.addInitScript(() => localStorage.setItem('hermes.desktop.pluginDecisions.v2', JSON.stringify({ 'mastermind-mobile': true })))
  page = await context.newPage()
  const frames = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('response', response => { if (response.status() >= 400) requests.push({ path: new URL(response.url()).pathname, status: response.status() }) })
  page.on('requestfailed', request => requests.push({ path: new URL(request.url()).pathname, failure: request.failure()?.errorText }))
  page.on('websocket', socket => { socket.on('framereceived', event => frames.push(String(event.payload))) })
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    return [origin, provider.url].includes(url.origin) || ['data:', 'blob:'].includes(url.protocol) ? route.continue() : route.abort()
  })
  await page.goto(link)
  await waitForInteractive(page)
  report.steps.push('native initial boot became interactive without bypassing an overlay')
  await page.evaluate(() => { location.hash = '/mastermind' })
  await page.getByRole('heading', { name: 'Your team', exact: true }).waitFor({ timeout: 45000 })
  await page.getByRole('button', { name: /Secretary.*Connection:/ }).click()
  const draft = page.getByRole('button', { name: 'New separate chat', exact: true })
  await draft.waitFor(); await draft.click()
  const composer = page.locator('[data-slot="composer-root"] [contenteditable="true"]').filter({ visible: true }).first()
  await composer.waitFor({ timeout: 45000 })
  report.steps.push('shipping plugin discovered by native Webapp; Secretary opens through native navigation')
  const marker = 'U1-mastermindmobileproof'
  holding = gate()
  provider.script(marker, [{ text: ['## Native mobile proof\n\n', 'This **formatted reply** came through the native stream.\n\n', '```python\nprint("MOBILE_STREAM_OK")\n```\n\n', '| Check | Result |\n| --- | --- |\n| Native renderer | Ready |\n'], holdAfterFirstChunk: holding }])
  await composer.fill(`${marker} Reply with the prepared formatting sample.`)
  await composer.press('Enter')
  await within(provider.streamStarted(marker), 45000, 'native provider stream')
  await page.getByRole('heading', { name: 'Native mobile proof', exact: true }).waitFor({ timeout: 30000 })
  assert.equal(provider.completions.find(row => row.marker === marker)?.finished, false)
  report.steps.push('native renderer displays the heading before the provider finishes streaming')
  holding.open()
  await page.getByText('MOBILE_STREAM_OK', { exact: false }).last().waitFor({ timeout: 45000 })
  await page.waitForFunction(() => document.querySelectorAll('table').length > 0)
  assert.ok(await page.locator('strong').filter({ hasText: 'formatted reply' }).count())
  assert.ok(await page.locator('code').filter({ hasText: 'MOBILE_STREAM_OK' }).count())
  const sessionHash = new URL(page.url()).hash
  assert.ok(sessionHash && sessionHash !== '#/mastermind')
  await page.screenshot({ path: join(output, 'native-mobile-stream.png'), fullPage: true })
  const completed = provider.completions.filter(row => row.marker === marker)
  assert.equal(completed.length, 1, 'the uniquely marked turn was dispatched more than once')
  await page.reload()
  await page.getByText('MOBILE_STREAM_OK', { exact: false }).last().waitFor({ timeout: 45000 })
  assert.equal(new URL(page.url()).hash, sessionHash)
  assert.equal(provider.completions.filter(row => row.marker === marker).length, 1)
  report.steps.push('native Markdown, strong text, code block and table render; reload retains the original session without redispatch')
  report.sessionHash = sessionHash
  report.streamFrames = frames.length
  report.providerCallsForMarker = completed.length
  report.accepted = true
} catch (error) {
  failure = error
  report.accepted = false
  report.error = String(error)
  if (page) {
    report.pageState = await page.evaluate(() => ({ route: location.hash, text: document.body.innerText.replace(/\s+/g, ' ').slice(0, 1800), host: document.documentElement.dataset.hermesDesktopHost })).catch(() => null)
    await page.screenshot({ path: join(output, 'native-failure.png'), fullPage: true }).catch(() => {})
  }
} finally {
  holding?.open()
  report.pageErrors = errors.slice(-20)
  report.failedRequests = requests.slice(-25)
  if (browser) await browser.close()
  if (gateway && gateway.exitCode === null) {
    try { process.kill(-gateway.pid, 'SIGTERM') } catch (error) { if (error.code !== 'ESRCH') throw error }
    try { report.gatewayExit = await within(gatewayExit, 12000, 'fixture shutdown') }
    catch { try { process.kill(-gateway.pid, 'SIGKILL') } catch (error) { if (error.code !== 'ESRCH') throw error }; report.gatewayExit = await within(gatewayExit, 5000, 'fixture kill') }
  } else if (gatewayExit) report.gatewayExit = await gatewayExit
  await provider.close()
  await writeFile(join(output, 'native-gateway.log'), log.join(''), { mode: 0o600 })
  await writeFile(join(output, 'native-browser-result.json'), JSON.stringify(report, null, 2) + '\n', { mode: 0o600 })
}
console.log(JSON.stringify(report))
if (failure) process.exitCode = 1
