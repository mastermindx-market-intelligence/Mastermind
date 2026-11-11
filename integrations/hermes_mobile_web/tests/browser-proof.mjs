// Component-browser proof, not production OAuth, provider or physical-phone acceptance.
// Uses the donor's installed esbuild/Playwright toolchain; no dependency installation.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { createRequire } from 'node:module'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const donor = process.env.HERMES_ROOT
if (!donor) throw new Error('Set HERMES_ROOT to the qualified donor source/toolchain')
const require = createRequire(join(resolve(donor), 'package.json'))
const { build } = require('esbuild')
const { chromium, webkit } = require('playwright')
const output = resolve(process.env.MOBILE_PROOF_OUTPUT || join(root, '.proof'))
await mkdir(output, { recursive: true })
const compiled = await build({
  entryPoints: [join(root, 'tests/browser-entry.jsx')], bundle: true, write: false,
  format: 'esm', platform: 'browser', jsx: 'automatic',
  alias: { '@hermes/plugin-sdk': join(root, 'tests/sdk-fixture.js') },
  nodePaths: [join(resolve(donor), 'node_modules')], define: { 'process.env.NODE_ENV': '"production"' }
})
const script = compiled.outputFiles[0].contents
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><title>Mastermind integration proof</title>
<style>
/* Explicit fixture theme tokens. The installed plugin inherits Hermes's actual theme. */
:root{--ui-text-primary:#202124;--ui-text-secondary:#555860;--ui-stroke-secondary:#d7d9dd;--ui-bg-editor:#fff;--ui-bg-secondary:#eceef1;--ui-accent:#315cab;--proof-canvas:#f5f6f8;color-scheme:light}
@media(prefers-color-scheme:dark){:root{--ui-text-primary:#ededee;--ui-text-secondary:#adafb5;--ui-stroke-secondary:#393b40;--ui-bg-editor:#222326;--ui-bg-secondary:#303238;--ui-accent:#a7c4fa;--proof-canvas:#191a1d;color-scheme:dark}}
body{margin:0;background:var(--proof-canvas);font:15px system-ui,sans-serif}.proof-label{padding:10px 14px;border-bottom:1px solid var(--ui-stroke-secondary);color:var(--ui-text-secondary);font-size:12px}.proof-label strong{color:var(--ui-text-primary)}
</style></head><body><aside class="proof-label"><strong>Integration preview</strong> — isolated test data, not live agents</aside><div id="root"></div><script type="module" src="/proof.js"></script></body></html>`
const manifest = { id: '/?app=mastermind-mobile', name: 'Mastermind', short_name: 'Mastermind', start_url: '/?mastermind-agent=meta-ceo-uncensored#/mastermind', scope: '/', display: 'standalone' }
const server = createServer((request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname
  response.setHeader('Cache-Control', 'no-store')
  if (path === '/proof.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(script) }
  else if (path === '/api/plugins/mastermind-mobile/manifest.webmanifest') { response.setHeader('Content-Type', 'application/manifest+json'); response.end(JSON.stringify(manifest)) }
  else if (path === '/') { response.setHeader('Content-Type', 'text/html'); response.end(html) }
  else { response.statusCode = 404; response.end('Not found') }
})
await new Promise((yes, no) => { server.once('error', no); server.listen(0, '127.0.0.1', yes) })
const origin = `http://127.0.0.1:${server.address().port}`
const cases = [], failures = []
const viewports = [{ name: 'narrow', width: 320, height: 740 }, { name: 'phone', width: 390, height: 844 }, { name: 'desktop', width: 1280, height: 900 }]
try {
  for (const [engine, browserType] of [['chromium', chromium], ['webkit', webkit]]) {
    const browser = await browserType.launch({ headless: true })
    try {
      for (const theme of ['light', 'dark']) for (const viewport of viewports) {
        const context = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: 'reduce', hasTouch: viewport.width < 768 })
        const page = await context.newPage(), errors = []
        page.on('pageerror', error => errors.push(error.message))
        await page.route('**/*', route => {
          const url = new URL(route.request().url())
          return url.origin === origin ? route.continue() : route.abort()
        })
        const name = `${engine}-${theme}-${viewport.name}`
        try {
          await page.goto(`${origin}/?mastermind-agent=meta-ceo-uncensored#/mastermind`)
          await page.getByRole('button', { name: 'Open Bot Chat', exact: true }).waitFor()
          assert.equal(await page.evaluate(() => window.__proofCalls.filter(row => ['open', 'draft'].includes(row.kind)).length), 0)
          assert.equal(await page.locator('link[rel="manifest"]').getAttribute('crossorigin'), 'use-credentials')
          const geometry = await page.evaluate(() => ({
            width: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
            undersized: [...document.querySelectorAll('.mm-mobile button,.mm-mobile summary')].filter(element => {
              const rect = element.getBoundingClientRect()
              return rect.width > 0 && rect.height > 0 && (rect.width < 44 || rect.height < 44)
            }).map(element => element.textContent)
          }))
          assert.ok(geometry.scrollWidth <= geometry.width + 1, `${name}: horizontal overflow`)
          assert.deepEqual(geometry.undersized, [], `${name}: undersized tap targets`)
          await page.screenshot({ path: join(output, `${name}.png`), fullPage: true })
          await page.getByRole('button', { name: /Secretary.*Connection:/ }).click()
          await page.getByRole('button', { name: 'Continue the launch readiness discussion', exact: true }).waitFor()
          await page.getByRole('button', { name: 'Open Bot Chat', exact: true }).click()
          await page.waitForFunction(() => window.__proofCalls.some(row => row.kind === 'open'))
          const opened = await page.evaluate(() => window.__proofCalls.find(row => row.kind === 'open'))
          assert.equal(opened.id, 'secretary-current')
          assert.deepEqual(opened.options.route, { connectionId: 'm2-fixture', profile: 'secretary', targetProfile: 'secretary', mode: 'local' })
          assert.equal(opened.options.workspaceMode, 'bots')
          assert.equal(opened.options.workspaceOwnerKey, 'bot:m2-fixture::secretary')
          assert.equal(await page.evaluate(() => window.__proofCalls.filter(row => row.kind === 'draft').length), 0)
          await page.getByRole('button', { name: /Show specialists/ }).click()
          await page.getByRole('button', { name: /engineering.*Connection:/ }).waitFor()
          await page.keyboard.press('Tab')
          assert.ok(await page.evaluate(() => document.activeElement?.tagName === 'BUTTON' || document.activeElement?.tagName === 'SUMMARY'))
          if (viewport.width < 768) {
            await page.setViewportSize({ width: viewport.width, height: 420 })
            const button = page.getByRole('button', { name: 'New separate chat', exact: true })
            await button.scrollIntoViewIfNeeded()
            const box = await button.boundingBox()
            assert.ok(box && box.y >= -1 && box.y + box.height <= 421, `${name}: control unreachable with reduced viewport`)
          }
          await page.evaluate(() => window.__proofDisconnect())
          await page.waitForFunction(() => document.body.innerText.includes('Hermes is disconnected'))
          assert.equal(await page.getByRole('button', { name: /Secretary.*Connection:/ }).isDisabled(), true)
          assert.deepEqual(errors, [], `${name}: page errors`)
          cases.push({ name, passed: true, viewport, exactRoute: opened.options.route, horizontalOverflow: false, tapTargets: 'at least 44px' })
        } catch (error) {
          await page.screenshot({ path: join(output, `${name}-failure.png`), fullPage: true }).catch(() => {})
          failures.push({ name, message: String(error), pageErrors: errors })
        } finally { await context.close() }
      }
    } finally { await browser.close() }
  }
} finally { await new Promise(resolve => server.close(resolve)) }
const receipt = { scope: 'shipping plugin in real browser engines with explicit SDK/test-data fixtures; not live OAuth, provider or physical-device proof', cases, failures }
await writeFile(join(output, 'browser-results.json'), JSON.stringify(receipt, null, 2) + '\n')
console.log(JSON.stringify({ passed: cases.length, failed: failures.length, failures, output }))
if (failures.length) process.exitCode = 1
