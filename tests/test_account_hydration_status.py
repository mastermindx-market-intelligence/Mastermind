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
    # Only a real account document may speak for identity: api() masks a decode
    # failure into {} with ok still true, so load() must shape-check before the
    # payload can influence identity, config or any guest classification.
    assert "function validAccountDoc(d)" in source
    assert "!Array.isArray(d)" in source
    assert "typeof d.authenticated === 'boolean'" in source
    assert "if (!res.ok || !validAccountDoc(a)) { finishLoad({ access_unconfirmed: true }); return; }" in source
    assert "r2.ok && validAccountDoc(r2.data) && r2.data.authenticated === true" in source
    assert "if (!a.authenticated && hasSessionHint())" in source
    assert "accessUnconfirmedHTML()" in source
    assert "if (_accountRequest) return _accountRequest" in source
    assert 'a.plan_verified === true && a.plan === "free"' in source
    assert "a.plan_verified === true && a.plan_label" in source


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
// Marks a response whose body cannot be JSON-decoded at all (api() must still
// surface it through the same reply seam as any other status).
const DECODE_FAIL = Symbol("json-decode-failure");

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
    replies[i]({ok: status >= 200 && status < 300, status, json: async () => {
      if (body === DECODE_FAIL) throw new SyntaxError("Unexpected end of JSON input");
      return body;
    }});
  }
  return {window, root, replies, reply, document};
}

// A 200 whose body is not a valid account document (decode failure, JSON null,
// array, plain object) is uncertainty on ANY read: never a guest classification.
async function expectUnconfirmed(body, label) {
  const h = await harness("");
  const work = h.window.__test.load();
  await tick(); assert.equal(h.replies.length, 1, label);
  h.reply(0, 200, body); await work;
  assert.equal(h.window.__test.state().acct.access_unconfirmed, true, label);
  assert.equal(h.window.__test.state().acct.authenticated, undefined, label);
  assert.match(h.root.innerHTML, /Account access could not be verified/, label);
  assert.match(h.root.innerHTML, /Check access again/, label);
  assert.doesNotMatch(h.root.innerHTML, /Sign in to Mastermind|Upgrade to Pro|mmacc-pro-card/, label);
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
    assert.doesNotMatch(h.root.innerHTML, /Upgrade to Pro/,
      "a paid signed-in account must not see an unverified tier-based upsell");
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
    assert.doesNotMatch(h.root.innerHTML, /mmacc-pro-card/,
      "verified identity alone cannot grant or upsell a marketing plan");
  }
  // A malformed account payload on the first read stays unconfirmed whether
  // or not a session hint exists: {} and decode failures previously kept
  // ok=true and slid the user into the sign-in form.
  for (const [label, body] of [
    ["empty-object", {}],
    ["json-null", null],
    ["array", [{authenticated: true}]],
    ["decode-failure", DECODE_FAIL],
  ]) {
    await expectUnconfirmed(body, "initial read " + label + " must not become a guest or identity");
  }
  // A non-Boolean authenticated flag cannot establish identity on the first
  // read either, with or without a readable session hint.
  for (const cookie of ["", "sb-proj-auth-token=shared"]) {
    const h = await harness(cookie);
    const work = h.window.__test.load();
    await tick(); assert.equal(h.replies.length, 1);
    h.reply(0, 200, {authenticated: "yes"}); await work;
    assert.equal(h.window.__test.state().acct.access_unconfirmed, true,
      "a non-Boolean authenticated hint must not sign the user in");
    assert.equal(h.window.__test.state().acct.authenticated, undefined);
    assert.doesNotMatch(h.root.innerHTML, /Signed in|Sign in to Mastermind|Upgrade to Pro/);
    assert.match(h.root.innerHTML, /Check access again/);
  }
  // The bounded second read is held to the same standard: only a valid
  // document whose authenticated === true may establish identity there.
  // A truthy non-Boolean flag previously passed the bare truthiness check and
  // was adopted as a signed-in identity.
  for (const [label, body] of [
    ["empty-object", {}],
    ["json-null", null],
    ["array", [1]],
    ["wrong-type-authenticated", {authenticated: "yes"}],
  ]) {
    const h = await harness("sb-proj-auth-token=shared");
    const work = h.window.__test.load();
    await tick(); assert.equal(h.replies.length, 1, label);
    h.reply(0, 200, {authenticated: false});
    await tick(); assert.equal(h.replies.length, 2, label);
    h.reply(1, 200, body); await work;
    assert.equal(h.window.__test.state().acct.access_unconfirmed, true,
      "second read " + label + " must stay unconfirmed");
    assert.equal(h.window.__test.state().acct.authenticated, undefined,
      "second read " + label + " cannot establish identity");
    assert.doesNotMatch(h.root.innerHTML, /Signed in|Sign in to Mastermind|Upgrade to Pro/, label);
  }
  // A decode failure on the bounded second read is also unconfirmed, and the
  // neutral retry stays the only account CTA.
  {
    const h = await harness("sb-proj-auth-token=shared");
    const work = h.window.__test.load();
    await tick(); h.reply(0, 200, {authenticated: false});
    await tick(); h.reply(1, 200, DECODE_FAIL); await work;
    assert.equal(h.window.__test.state().acct.access_unconfirmed, true);
    assert.match(h.root.innerHTML, /Check access again/);
    assert.doesNotMatch(h.root.innerHTML, /Signed in|Sign in to Mastermind|Upgrade to Pro/);
  }
  process.stdout.write("PASS: Bot Portfolio account pending/unavailable/guest/recovery/malformed/no-duplicate-read\n");
})().catch(err => { console.error(err); process.exitCode = 1; });
"""
    result = subprocess.run(
        [shutil.which("node"), "-", str(ASSET)],
        input=script, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
