// Supplemental native-browser proof. All state belongs to the caller's fresh fixture home.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { DatabaseSync } from 'node:sqlite'
import { join } from 'node:path'

const CANONICAL = 'mastermind-fixture-secretary-bot'

export function seedCanonicalFixture({ python, env, donor, hermesHome }) {
  // The real SessionDB owner creates fixture preconditions; no production DB is copied.
  const code = `from pathlib import Path
from hermes_state import SessionDB
home = Path(__import__('os').environ['HERMES_HOME'])
assert 'native-browser-proof' in str(home) and home.name == '.hermes'
db = SessionDB(home / 'profiles' / 'secretary' / 'state.db')
db.create_session('${CANONICAL}', 'cli', model='mock-model', profile_name='secretary')
assert db.set_session_title('${CANONICAL}', 'Bot Chat')
db.set_session_title_source('${CANONICAL}', 'user')
assert db.set_session_hidden('${CANONICAL}', True)
db.close()
`
  execFileSync(python, ['-c', code], { cwd: donor, env, timeout: 30000, stdio: ['ignore', 'pipe', 'pipe'] })
  return join(hermesHome, 'profiles/secretary/state.db')
}

export async function verifyNativeContinuity({ page, context, origin, provider, gate, within, report, output, database }) {
  await page.goto(origin + '/?mastermind-agent=secretary#/mastermind')
  const openBot = page.getByRole('button', { name: 'Open Bot Chat', exact: true })
  await openBot.waitFor({ timeout: 45000 })
  await openBot.click({ timeout: 45000 })
  const composer = page.locator('[data-slot="composer-root"] [contenteditable="true"]').filter({ visible: true }).first()
  await composer.waitFor({ timeout: 45000 })
  await page.waitForFunction(expected => decodeURIComponent(location.hash.slice(2)) === expected, CANONICAL, { timeout: 45000 })
  report.steps.push('home-screen shortcut cold entry opens the pre-existing hidden Secretary Bot Chat without a replacement')
  const marker = 'U2-mastermindmobileproof'
  const held = gate()
  provider.script(marker, [{ text: ['CANONICAL_STREAM_RUNNING\n\n', 'MUST_NOT_FINISH_AFTER_STOP'], holdAfterFirstChunk: held }])
  try {
    const prompt = `${marker} This isolated turn tests reconnect and Stop.`
    await composer.fill(prompt)
    await composer.press('Enter')
    await within(provider.streamStarted(marker), 45000, 'canonical stream')
    await page.getByText('CANONICAL_STREAM_RUNNING', { exact: true }).last().waitFor({ timeout: 30000 })
    const interruptedUrl = page.url()
    await context.setOffline(true)
    await page.reload({ timeout: 10000 }).catch(() => {})
    await context.setOffline(false)
    await page.goto(interruptedUrl)
    await page.getByText(prompt, { exact: true }).last().waitFor({ timeout: 45000 })
    const stop = page.locator('[data-slot="composer-root"] button[aria-label="Stop"]').filter({ visible: true }).first()
    await stop.waitFor({ timeout: 45000 })
    // The native runtime can retain the turn while its already-emitted prefix
    // awaits another event. Observe that separately; do not claim prefix recovery
    // merely because the original running turn and Stop control were recovered.
    report.partialPrefixRehydratedBeforeNextDelta = await page.getByText('CANONICAL_STREAM_RUNNING', { exact: true }).last().isVisible().catch(() => false)
    assert.equal(provider.completions.filter(row => row.marker === marker).length, 1, 'reconnection must not resubmit the turn')
    await stop.click()
    await stop.waitFor({ state: 'hidden', timeout: 45000 })
    const end = Date.now() + 15000
    while (!provider.completions.find(row => row.marker === marker)?.aborted && Date.now() < end) await new Promise(done => setTimeout(done, 50))
    const calls = provider.completions.filter(row => row.marker === marker)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].finished, false, 'Stop must end the held stream before its final chunk')
    assert.equal(calls[0].aborted, true, 'the native stop must cancel the original provider stream')
    assert.equal(await page.getByText('MUST_NOT_FINISH_AFTER_STOP', { exact: true }).count(), 0)
    assert.equal(decodeURIComponent(new URL(page.url()).hash.slice(2)), CANONICAL)
    const db = new DatabaseSync(database, { readOnly: true })
    try {
      const bots = db.prepare("SELECT id FROM sessions WHERE title = 'Bot Chat'").all()
      assert.deepEqual(bots.map(row => row.id), [CANONICAL])
      const messages = db.prepare("SELECT session_id FROM messages WHERE role = 'user' AND content LIKE ?").all(`%${marker}%`)
      assert.equal(messages.length, 1)
      assert.equal(messages[0].session_id, CANONICAL)
    } finally { db.close() }
    report.canonical = { id: CANONICAL, providerCalls: 1, reconnectResubmits: 0, titleRows: 1, stoppedOriginalProvider: true }
    report.steps.push('network loss/reload returns to the same Bot Chat; native Stop cancels the original stream; DB proves one canonical row and one user submission')
    await page.screenshot({ path: join(output, 'native-canonical-reconnect-stop.png'), fullPage: true })
  } finally {
    held.open()
    await context.setOffline(false).catch(() => {})
  }

  const toolMarker = 'U3-mastermindmobileproof'
  provider.script(toolMarker, [
    { text: ['Checking the native tool display.'], toolCalls: [{ name: 'terminal', args: { command: 'printf MOBILE_TOOL_OK' } }] },
    { text: ['Tool display confirmed: MOBILE_TOOL_OK.'] }
  ])
  await composer.fill(`${toolMarker} Run the harmless fixture printf and confirm its result.`)
  await composer.press('Enter')
  const approval = page.locator('[data-approval-run]').filter({ visible: true }).first()
  const final = page.getByText('Tool display confirmed: MOBILE_TOOL_OK.', { exact: true }).last()
  const outcome = await Promise.race([
    final.waitFor({ timeout: 45000 }).then(() => 'finished'),
    approval.waitFor({ timeout: 45000 }).then(() => 'approval')
  ])
  if (outcome === 'approval') await approval.click()
  await final.waitFor({ timeout: 45000 })
  await page.getByText(/printf MOBILE_TOOL_OK/).first().waitFor({ timeout: 30000 })
  const calls = provider.completions.filter(row => row.marker === toolMarker)
  assert.equal(calls.length, 2, 'one tool request and one result continuation')
  assert.deepEqual(calls.flatMap(row => row.toolCalls), ['terminal'])
  assert.equal(decodeURIComponent(new URL(page.url()).hash.slice(2)), CANONICAL)
  report.nativeTool = { name: 'terminal', command: 'printf MOBILE_TOOL_OK', toolRequests: 1, providerCompletions: 2, approvalUsed: outcome === 'approval' }
  report.steps.push('the same canonical chat completes a native harmless terminal tool and renders its command/result after reconnect and Stop')
  await page.screenshot({ path: join(output, 'native-canonical-tool.png'), fullPage: true })
}
