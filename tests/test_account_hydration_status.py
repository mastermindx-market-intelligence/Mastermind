"""Account broker hydration must not show a sign-in/upgrade pitch on uncertainty."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "app" / "static" / "account.js"


def test_account_failure_state_uses_no_premium_grant_or_false_guest():
    source = ASSET.read_text()
    assert "function hasSessionHint()" in source
    assert "if (!res.ok) { finishLoad({ access_unconfirmed: true }); return; }" in source
    assert "if (!a.authenticated && hasSessionHint())" in source
    assert "accessUnconfirmedHTML()" in source
    assert "if (_accountRequest) return _accountRequest" in source


@pytest.mark.skipif(not shutil.which("node"), reason="Node required for browser-script behavioral proof")
def test_account_restoration_behaviour():
    script = r"""
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
let source = fs.readFileSync(process.argv[2], "utf8");
const marker = "  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);";
assert(source.includes(marker), "source-entry seam moved; update behavior test");
source = source.replace(marker,
  "  window.__test = {load, state: () => state, bind: root => {_root = root; _mode = 'standalone';}, hasSessionHint};\n" + marker);
const tick = () => new Promise(resolve => setImmediate(resolve));

async function harness(cookie) {
  const replies = [], root = {innerHTML: ""};
  const document = {
    cookie, readyState: "loading",
    documentElement: {getAttribute: () => "en"},
    addEventListener() {},
    getElementById: () => null,
  };
  const window = {
    MM_API: "", SUPABASE_CFG: {url: "https://example.supabase.co", anonKey: "public-test-key"},
  };
  const context = {
    window, document, localStorage: {length: 0, key: () => null},
    fetch: (_url, init) => {
      assert.equal(init.credentials, "include");
      return new Promise(resolve => replies.push(resolve));
    },
    Promise, JSON, Date, String, Array, Number, RegExp,
    setTimeout, clearTimeout,
  };
  vm.runInNewContext(source, context);
  window.__test.bind(root);
  function reply(i, status, body) {
    assert(replies[i], "missing requested API call " + i);
    replies[i]({ok: status >= 200 && status < 300, status, json: async () => body});
  }
  return {window, root, replies, reply, document};
}

(async () => {
  // A paid account can survive a temporarily anonymous broker answer, with no
  // sign-in or upgrade frame between the first and second authority reads.
  {
    const h = await harness("sb-proj-auth-token.0=shared");
    const work = h.window.__test.load();
    await tick(); assert.equal(h.replies.length, 1);
    h.reply(0, 200, {authenticated: false});
    await tick(); assert.equal(h.replies.length, 2);
    assert.match(h.root.innerHTML, /Loading/);
    assert.doesNotMatch(h.root.innerHTML, /Sign in to Mastermind|Upgrade to Pro/);
    h.reply(1, 200, {authenticated: true, email:"operator@example.org", plan_label:"Pro"});
    await work;
    assert.equal(h.window.__test.state().acct.authenticated, true);
    assert.match(h.root.innerHTML, /Signed in/);
  }
  // When authentication or network cannot be checked, the user is not
  // reclassified as Free/guest. A neutral retry is the only account CTA.
  {
    const h = await harness("sb-proj-auth-token=shared");
    const work = h.window.__test.load();
    await tick(); h.reply(0, 503, {error:"gateway"}); await work;
    assert.equal(h.window.__test.state().acct.access_unconfirmed, true);
    assert.match(h.root.innerHTML, /Account access could not be verified/);
    assert.match(h.root.innerHTML, /Check access again/);
    assert.doesNotMatch(h.root.innerHTML, /Sign in to Mastermind|Upgrade to Pro/);
  }
  // A cookie-bearing account that never verifies after the bounded re-read
  // remains unconfirmed, not upgraded or signed out by inference.
  {
    const h = await harness("sb-proj-auth-token=shared");
    const work = h.window.__test.load();
    await tick(); h.reply(0, 200, {authenticated:false});
    await tick(); h.reply(1, 200, {authenticated:false}); await work;
    assert.equal(h.window.__test.state().acct.access_unconfirmed, true);
    assert.doesNotMatch(h.root.innerHTML, /Sign in to Mastermind/);
  }
  // A real guest with no cookie is allowed to see the normal sign-in form.
  {
    const h = await harness("");
    const work = h.window.__test.load();
    await tick(); h.reply(0, 200, {authenticated:false}); await work;
    assert.equal(h.window.__test.state().acct.authenticated, false);
    assert.match(h.root.innerHTML, /Sign in to Mastermind/);
  }
  // Idle warm + account click reuse one network request, no stale response
  // racing to repaint a later verified identity.
  {
    const h = await harness("");
    const first = h.window.__test.load(), second = h.window.__test.load();
    await tick(); assert.equal(h.replies.length, 1);
    h.reply(0, 200, {authenticated:true, email:"owner@example.org"});
    await Promise.all([first, second]);
    assert.equal(h.window.__test.state().acct.authenticated, true);
  }
  process.stdout.write("PASS: Bot Portfolio account pending/unavailable/guest/recovery/no-duplicate-read\n");
})().catch(err => { console.error(err); process.exitCode = 1; });
"""
    result = subprocess.run(
        [shutil.which("node"), "-", str(ASSET)],
        input=script, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
