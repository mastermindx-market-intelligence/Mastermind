'use strict';
// Direct target acceptance cases against the actual selected DOM and Fernet
// engines. Mutations are fixture actions, never a production evaluate tool.
const fs = require('node:fs');
const path = require('node:path');
const p = JSON.parse(fs.readFileSync(0, 'utf8'));
const receiver = require(p.source);
const playwright = require(path.join(p.runtime, 'node_modules/playwright'));
async function main() {
  const owned = await receiver.createOwnedSession({ runtimeRoot: p.runtime,
    chromeExecutable: playwright.chromium.executablePath(), outputDir: p.output,
    resourceId: p.use.resource_id, resourceExpiry: p.use.grant.expires_at_ms });
  const browser = owned.context.browser();
  let observed;
  try {
    await owned.context.route('https://vault.test/**', route => route.fulfill({ status: 200, contentType: 'text/html',
      body: '<!doctype html><form action="/submit"><input name=username autocomplete=username><input type=password autocomplete=current-password></form>' }));
    const page = await owned.context.newPage();
    await page.goto('https://vault.test/login');
    if (p.mode === 'expiry') p.use.expires_at_ms = Date.now() + 300;
    const prepared = await owned.target.prepare({ use: p.use, action_id: 'a'.repeat(32) });
    if (prepared.status !== 'READY') throw new Error('TARGET_FIXTURE_NOT_READY');
    if (p.mode === 'navigation') await page.goto('https://vault.test/replaced');
    if (p.mode === 'replacement') await page.evaluate(() => { const el=document.querySelector('[type=password]');el.replaceWith(el.cloneNode()); });
    if (p.mode === 'hidden') await page.evaluate(() => { document.querySelector('[type=password]').style.display='none'; });
    if (p.mode === 'new-password') await page.evaluate(() => { document.querySelector('[type=password]').autocomplete='new-password'; });
    if (p.mode === 'form-origin') await page.evaluate(() => { document.querySelector('form').action='https://other.test'; });
    if (p.mode === 'second-page') await owned.context.newPage();
    if (p.mode === 'expiry') {
      await page.evaluate(() => { Date.now = () => 0; });
      await new Promise(resolve => setTimeout(resolve, 350));
    }
    observed = await owned.target.fill({ target_ref: prepared.target_ref, material: p.material });
    const passwordEmpty = await page.locator('[type=password]').inputValue() === '';
    if (!passwordEmpty || observed.effect_state !== 'NOT_APPLIED') throw new Error('TARGET_FIXTURE_FALSE_WRITE');
  } finally { await owned.close(); }
  process.stdout.write(JSON.stringify({ effect_state: observed.effect_state, browser_closed: !browser.isConnected() }));
}
main().catch(() => { process.exitCode=70;process.stderr.write('TARGET_FIXTURE_FAILED\n'); });
