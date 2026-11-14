"""Offline account preference event batching; execute the actual JS function."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "app/static/account.js"


@pytest.mark.parametrize("case", [
    "two_keys", "latest_value", "separate_batches", "signed_out",
    "hydrating", "account_changed", "pending_account_changed", "revoked",
])
def test_preference_batch(case):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for actual JavaScript behavior")
    source = SOURCE.read_text()
    start = source.index("  function persistPref(")
    end = source.index("\n\n  //", start)
    function = source[start:end]
    harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const timers = new Map(), sent = [];
let seq = 0;
const ctx = {
  _hydrating:false, _prefTimer:null, _prefPending:{}, _prefAccount:null,
  state:{acct:{id:'synthetic-a',authenticated:true}},
  clearTimeout:id=>timers.delete(id),
  setTimeout:fn=>{timers.set(++seq,fn);return seq;},
  api:(path,options)=>sent.push(JSON.parse(JSON.stringify(options.body)))
};
vm.createContext(ctx);
vm.runInContext(FUNCTION, ctx);
const send=(k,v)=>ctx.persistPref(k,v);
function flush() { const batch=[...timers.values()];timers.clear();batch.forEach(fn=>fn()); }
switch (CASE) {
case 'two_keys':
  send('theme','dark');send('lang','zh');flush();
  assert.deepEqual(sent,[{theme:'dark',lang:'zh'}]);break;
case 'latest_value':
  send('theme','dark');send('lang','zh');send('theme','light');flush();
  assert.deepEqual(sent,[{theme:'light',lang:'zh'}]);break;
case 'separate_batches':
  send('theme','dark');flush();send('lang','zh');flush();
  assert.deepEqual(sent,[{theme:'dark'},{lang:'zh'}]);break;
case 'signed_out':
  ctx.state.acct.authenticated=false;send('theme','dark');flush();
  assert.deepEqual(sent,[]);break;
case 'hydrating':
  ctx._hydrating=true;send('theme','dark');flush();
  assert.deepEqual(sent,[]);break;
case 'account_changed':
  send('theme','dark');ctx.state.acct={id:'synthetic-b',authenticated:true};flush();
  assert.deepEqual(sent,[]);break;
case 'pending_account_changed':
  send('theme','dark');ctx.state.acct={id:'synthetic-b',authenticated:true};
  send('lang','zh');flush();assert.deepEqual(sent,[{lang:'zh'}]);break;
case 'revoked':
  send('theme','dark');ctx.state.acct.authenticated=false;flush();
  assert.deepEqual(sent,[]);break;
}
"""
    harness = "const FUNCTION=" + json.dumps(function) + ";const CASE=" + json.dumps(case) + ";\n" + harness
    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
