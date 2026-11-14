"""Actual copyId control flow, synthetic account only; no browser or clipboard."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("scenario", [
    "success", "reject", "missing", "missing_method", "throws",
    "changed_account", "replaced_button", "newer_request", "language_reset",
])
def test_copy_feedback_is_bound_to_successful_current_request(scenario):
    source = ROOT / "app" / "static" / "account.js"
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const scenario = process.argv[2];
const start = source.indexOf('  function copyId()');
const end = source.indexOf('  function clearSharedCookie()', start);
assert(start >= 0 && end > start);
let button = {textContent:'Copy', disabled:false}, language='en', timers=[], calls=[];
let resolve, reject;
const promise = new Promise((a,b)=>{resolve=a; reject=b;});
const clipboard = scenario === 'missing' ? undefined :
 scenario === 'missing_method' ? {} :
 {writeText(id) { calls.push(id); if(scenario === 'throws') throw Error('denied'); return promise; }};
const ctx = { _copyGeneration:0, state:{acct:{id:'synthetic-id'}},
 _root:{querySelector(){return button;}}, navigator:{clipboard},
 Promise, T:k=>({copy:language==='zh'?'复制':'Copy',copied:'Copied',copying:'Copying',copy_failed:'Copy failed'})[k],
 setTimeout(fn){timers.push(fn);} };
vm.createContext(ctx); vm.runInContext(source.slice(start,end),ctx);
(async()=>{
 ctx.copyId();
 if (['missing','missing_method','throws'].includes(scenario)) {
  assert.equal(button.textContent,'Copy failed'); assert.equal(button.disabled,false); return;
 }
 assert.equal(button.textContent,'Copying');
 const oldButton=button;
 if(scenario==='changed_account') ctx.state.acct={id:'other-synthetic-id'};
 if(scenario==='replaced_button') button={textContent:'Copy'};
 if(scenario==='newer_request') {
   ctx.navigator.clipboard.writeText=()=>Promise.reject(Error('new denial'));
   ctx.copyId(); await new Promise(r=>setImmediate(r));
   assert.equal(button.textContent,'Copy failed');
 }
 if(scenario==='reject') reject(Error('denied')); else resolve();
 await new Promise(r=>setImmediate(r));
 if(['changed_account','replaced_button'].includes(scenario)) {
   assert.notEqual(oldButton.textContent,'Copied'); return;
 }
 if(scenario==='newer_request') { assert.equal(button.textContent,'Copy failed'); return; }
 assert.equal(button.textContent,scenario==='reject'?'Copy failed':'Copied');
 assert.equal(button.disabled,false);
 if(scenario==='language_reset') language='zh';
 timers.forEach(fn=>fn());
 assert.equal(button.textContent,language==='zh'?'复制':'Copy');
 assert.deepEqual(calls,['synthetic-id']);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(
        ["node", "-e", script, str(source), scenario],
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
