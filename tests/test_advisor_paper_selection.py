"""Execute the served Advisor widget's paper-read lifecycle in a real DOM.

The repository CI installs app/mastermind_os's pinned Node dependencies before
pytest. Reuse that existing JSDOM package; do not add a second JS dependency tree.
All reads are in-process fixture promises. No chat request or account is used.
"""

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const [sourcePath, scenario, language, packageRoot] = process.argv.slice(1);
const {JSDOM} = createRequire(path.join(packageRoot, 'package.json'))('jsdom');
const dom = new JSDOM('<!doctype html><html><head></head><body class="page-mm"></body></html>', {
  url: 'https://advisor-fixture.invalid/', runScripts: 'outside-only'
});
const w = dom.window, doc = w.document;
doc.documentElement.setAttribute('data-lang', language);
w.localStorage.setItem('bc_conversation_id', 'fixture-conversation');
const calls = [];
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
w.fetch = (url, options) => {
  assert.equal(options, undefined, 'Paper navigation must remain a read only');
  const result = deferred();
  calls.push({url, ...result});
  return result.promise;
};
const flush = async () => { await new Promise(setImmediate); await new Promise(setImmediate); };
const get = selector => {
  const node = doc.querySelector(selector);
  assert.ok(node, `Missing rendered element ${selector}`);
  return node;
};
const click = selector => get(selector).click();
const paper = (id, marker, extra = {}) => ({
  id, ticker: marker, report_md: `${marker} source report`, summary: '',
  combined: 64, engine_score: 60, research_score: 70, confirmed: false,
  viability: 'HOLD', key_risks: [], ...extra,
});
const reply = (request, value) => request.resolve({ok: true, json: async () => value});
const snapshot = () => ({
  title: get('#bc-sheet .sh-t').textContent,
  scores: get('#bc-sheet .sh-scores').textContent,
  body: get('#bc-sheet .sh-body').textContent,
  open: get('#bc-sheet').classList.contains('open'),
});
const select = index => {
  const cards = doc.querySelectorAll('.bc-paper');
  assert.equal(cards.length, 2);
  cards[index].click();
  return calls[calls.length - 1];
};
const assertCurrent = marker => {
  const current = snapshot();
  assert.ok(current.open, 'The newest explicitly opened paper remains open');
  assert.ok(current.title.startsWith(marker + ' — '), `Wrong paper title: ${current.title}`);
  assert.ok(current.body.includes(marker + ' source report'), `Wrong paper content: ${current.body}`);
};

(async () => {
  // Execute the complete actual source, then use only its rendered controls.
  w.eval(fs.readFileSync(sourcePath, 'utf8'));
  click('#bc-launch');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/chat/history?conversation_id=fixture-conversation');
  reply(calls[0], {turns: [{role: 'assistant', content: 'Two supplied papers', papers: [
    {paper_id: 'paper-a', ticker: 'AAA'}, {paper_id: 'paper b/中文', ticker: 'BBB'}
  ]}]});
  await flush();
  get('#bc-in').value = 'Keep this unsent draft';
  const first = select(0);
  assert.equal(first.url, '/chat/paper?id=paper-a');
  assert.equal(snapshot().title, '…');
  assert.equal(snapshot().scores, '');

  if (scenario === 'latest-success' || scenario === 'stale-failure' ||
      scenario === 'stale-not-found' || scenario === 'stale-json-failure' ||
      scenario === 'stale-json-success' || scenario === 'same-paper-reopen' ||
      scenario === 'stale-while-pending') {
    let json;
    if (scenario.startsWith('stale-json-')) {
      json = deferred();
      first.resolve({ok: true, json: () => json.promise});
      await flush();
    }
    click('#bc-sheet-x');
    const second = select(scenario === 'same-paper-reopen' ? 0 : 1);
    assert.equal(second.url, scenario === 'same-paper-reopen' ? '/chat/paper?id=paper-a'
      : '/chat/paper?id=paper%20b%2F%E4%B8%AD%E6%96%87');
    if (scenario === 'stale-while-pending') {
      const pending = snapshot();
      first.reject(new Error('obsolete read failure'));
      await flush();
      assert.deepEqual(snapshot(), pending, 'Obsolete failure must not replace newer loading state');
    } else {
      reply(second, paper(scenario === 'same-paper-reopen' ? 'paper-a' : 'paper b/中文', 'CURRENT'));
      await flush();
      const current = snapshot();
      if (scenario === 'stale-failure') first.reject(new Error('obsolete read failure'));
      else if (scenario === 'stale-not-found') reply(first, {error: 'not found'});
      else if (scenario === 'stale-json-failure') json.reject(new Error('obsolete JSON failure'));
      else if (scenario === 'stale-json-success') json.resolve(paper('paper-a', 'OBSOLETE'));
      else reply(first, paper('paper-a', 'OBSOLETE'));
      await flush();
      assert.deepEqual(snapshot(), current, 'Newest selected paper must survive an obsolete completion');
    }
    if (scenario === 'stale-while-pending') { reply(second, paper(scenario === 'same-paper-reopen' ? 'paper-a' : 'paper b/中文', 'CURRENT')); await flush(); }
    assertCurrent('CURRENT');
    assert.equal(calls.length, 3);
  } else if (scenario === 'back-dismiss' || scenario === 'panel-dismiss' || scenario === 'new-chat') {
    if (scenario === 'back-dismiss') click('#bc-sheet-x');
    if (scenario === 'panel-dismiss') { click('#bc-min'); click('#bc-launch'); }
    if (scenario === 'new-chat') {
      click('#bc-new');
      assert.equal(w.localStorage.getItem('bc_conversation_id'), null);
      assert.equal(doc.querySelectorAll('.bc-paper').length, 0);
    }
    const closed = snapshot();
    assert.equal(closed.open, false);
    reply(first, paper('paper-a', 'OBSOLETE'));
    await flush();
    assert.deepEqual(snapshot(), closed, 'A dismissed paper read must not repopulate its old sheet');
    assert.equal(calls.length, 2, 'Dismissal must not trigger any read or send');
  } else if (scenario === 'panel-reopen') {
    click('#bc-min'); click('#bc-launch');
    const second = select(1);
    reply(second, paper(scenario === 'same-paper-reopen' ? 'paper-a' : 'paper b/中文', 'CURRENT'));
    await flush();
    const current = snapshot();
    first.reject(new Error('obsolete read failure'));
    await flush();
    assert.deepEqual(snapshot(), current);
    assertCurrent('CURRENT');
    assert.equal(calls.length, 3);
  } else if (scenario === 'current-success') {
    reply(first, paper('paper-a', 'CURRENT', {combined: 0, engine_score: 0, research_score: 0,
      report_md: '', summary: 'CURRENT source report', key_risks: ['Supplied risk']}));
    await flush();
    assertCurrent('CURRENT');
    assert.deepEqual(Array.from(doc.querySelectorAll('#bc-sheet .sc b')).slice(0, 3).map(n => n.textContent), ['0', '0', '0']);
    assert.ok(snapshot().body.includes('Supplied risk'));
    assert.ok(snapshot().title.includes(language === 'zh' ? '研究报告' : 'Research Report'));
    assert.equal(calls.length, 2);
  } else if (scenario === 'current-not-found' || scenario === 'current-null') {
    reply(first, scenario === 'current-null' ? null : {error: 'not found'});
    await flush();
    assert.equal(snapshot().body, language === 'zh' ? '找不到该报告。' : 'Paper not found.');
    assert.equal(snapshot().title, '');
    assert.equal(snapshot().scores, '');
    assert.equal(snapshot().open, true);
  } else if (scenario === 'current-failure-recovery') {
    first.reject(new Error('current read failure'));
    await flush();
    assert.equal(snapshot().body, language === 'zh' ? '加载失败。' : 'Failed to load.');
    click('#bc-sheet-x');
    const retry = select(0);
    assert.equal(retry.url, first.url);
    reply(retry, paper('paper-a', 'CURRENT'));
    await flush();
    assertCurrent('CURRENT');
    assert.equal(calls.length, 3);
  } else {
    throw new Error('Unknown scenario ' + scenario);
  }
  assert.equal(get('#bc-in').value, 'Keep this unsent draft');
  assert.equal(get('#bc-send').disabled, false);
  console.log(JSON.stringify({scenario, language, requests: calls.map(c => c.url), state: snapshot()}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; }).finally(() => w.close());
"""


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("scenario", [
    "latest-success", "stale-failure", "stale-not-found", "stale-json-failure",
    "stale-json-success", "same-paper-reopen", "stale-while-pending",
    "back-dismiss", "panel-dismiss", "new-chat", "panel-reopen",
    "current-success", "current-not-found", "current-null", "current-failure-recovery",
])
def test_advisor_paper_read_lifetime(scenario: str, language: str) -> None:
    result = subprocess.run(
        ["node", "-e", SCRIPT, str(ROOT / "app/static/chat.js"), scenario, language,
         str(ROOT / "app/mastermind_os")],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
