# Web Sol Census Crypto-Wait CI Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the native-census repository gate wait for the actual asynchronous probe acquisition condition instead of assuming WebCrypto settles within 50 `setImmediate` turns.

**Architecture:** Keep production census code byte-identical. In the Node contract harness, inject a bounded delayed WebCrypto implementation into the probe-stage scenario to reproduce the hosted race, then replace the fixed iteration count with one wall-clock-bounded condition wait. The test must still prove that the fake census deadline is advanced only after the actual Chrome probe promise has been acquired.

**Tech Stack:** Node.js 24 test runner, CommonJS, `node:assert/strict`, `node:vm`, WebCrypto, Docker for runner parity.

**Spec:** `tests/web_sol_native_census.test.cjs` native-census deadline contract and GitHub Actions run `35187812354`, job `105093614804`.

## Global Constraints

- Operation: `web-sol-census-crypto-wait-ci-repair-20260917-sol-001`.
- Base: protected Mastermind `b14982837cc8146e3dc49e5862558ee399a1aa3d`.
- Do not edit PR #738 or its exact two consultation paths.
- Do not change production census semantics, deadlines, slot accounting, schemas, or browser acquisition order.
- Do not hide a real failure with retries or a blanket skip; the repaired test must deterministically exercise delayed WebCrypto.
- Keep the implementation change to `tests/web_sol_native_census.test.cjs`; this plan is the only supporting documentation path.

---

### Task 1: Replace scheduler-count guessing with a bounded acquisition condition

**Files:**
- Modify: `tests/web_sol_native_census.test.cjs:38-45,86-96,165-181`
- Test: `tests/web_sol_native_census.test.cjs`

**Interfaces:**
- Consumes: `collectorClock(tabs, cryptoApi)` and the test-local `release` callback set by `tabs.sendMessage`.
- Produces: `waitFor(predicate, message, timeoutMs)` and `delayedCrypto(delayMs)` test helpers; production exports remain unchanged.

- [ ] **Step 1: Write the deterministic failing regression fixture**

Change `collectorClock` to accept `cryptoApi = webcrypto`, pass it into the VM context, and add:

```javascript
function delayedCrypto(delayMs) {
 return {subtle:{digest(...args){return new Promise((resolve,reject)=>
  setTimeout(()=>webcrypto.subtle.digest(...args).then(resolve,reject),delayMs));}}};
}
```

Use `delayedCrypto(100)` only for the `probe` stage while retaining the existing fixed 50-tick acquisition loop.

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
docker run --rm -v "$PWD:/repo:ro" -w /repo node:24 \
  node --test --test-reporter=tap \
  --test-name-pattern='short timely collection remains measured' \
  tests/web_sol_native_census.test.cjs
```

Expected: FAIL at `actual probe acquisition`, proving the regression fixture catches the scheduler assumption.

- [ ] **Step 3: Implement the minimal bounded condition wait**

Add:

```javascript
async function waitFor(predicate, message, timeoutMs=2000) {
 const deadline=Date.now()+timeoutMs;
 while(!predicate()) {
  if(Date.now()>=deadline) assert.fail(message);
  await tick();
 }
}
```

Replace the fixed 50-tick loop with:

```javascript
await waitFor(()=>Boolean(release),'actual '+stage+' acquisition');
```

- [ ] **Step 4: Verify GREEN and mutation sensitivity**

Run the focused Node 24 test, the complete Node 24 native-census suite, and the Python wrapper gate. Restore the fixed 50-tick loop in-memory or in a temporary copy and confirm the delayed-crypto regression fails again.

- [ ] **Step 5: Verify repository compatibility**

Run:

```bash
python -m pytest tests/test_web_sol_native_census.py -q
git diff --check
git status --short
```

Expected: all tests pass; only the plan and native-census test path are changed.

- [ ] **Step 6: Commit and publish the bounded repair carrier**

```bash
git add docs/superpowers/plans/2026-09-17-web-sol-census-crypto-wait-ci-repair.md \
  tests/web_sol_native_census.test.cjs
git commit -m "test(web-sol): wait for census probe acquisition"
git push -u origin sol/web-sol-census-crypto-wait-ci-repair-20260917-sol-001
```

Open a draft PR against `master` with capability state `BUILT_NOT_PROVEN`, link the exact hosted failure, and keep merge/activation out of scope until hosted CI and current-base integration proof are green.
