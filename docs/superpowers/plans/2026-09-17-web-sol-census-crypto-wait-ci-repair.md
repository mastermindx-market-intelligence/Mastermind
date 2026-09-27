# Web Sol Census Crypto-Wait CI Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the native-census repository gate observe actual asynchronous acquisition conditions instead of assuming WebCrypto and Chrome-read work completes within a fixed number of event-loop turns.

**Architecture:** Keep every production census and extension byte unchanged. Add test-only delayed-WebCrypto fixtures that deterministically reproduce the hosted probe race and the shared-slot read race, then use one wall-clock-bounded condition helper for positive asynchronous expectations. Preserve intentional no-response behavior by waiting for a popup callback only when the production listener synchronously returns `true` and therefore promises an asynchronous response channel.

**Tech Stack:** Node.js 24 test runner, CommonJS, `node:assert/strict`, `node:vm`, WebCrypto, Docker for runner parity, Pytest wrapper gate.

**Spec:** `tests/web_sol_native_census.test.cjs` native-census deadline/slot contract and GitHub Actions run `35187812354`, job `105093614804`.

## Global Constraints

- Operation: `web-sol-census-crypto-wait-ci-repair-20260917-sol-001`.
- Base: protected Mastermind `b14982837cc8146e3dc49e5862558ee399a1aa3d`.
- Do not edit PR #738 or either of its exact consultation paths.
- Do not change production census semantics, deadlines, slot accounting, schemas, browser acquisition order, transport identity, or retry behavior.
- Do not hide real failures with reruns, skips, or relaxed assertions.
- Retain fixed-turn drains only where the test intentionally proves absence after a released negative path; positive conditions must use the bounded condition helper.
- Keep implementation changes to `tests/web_sol_native_census.test.cjs`; this plan is the only supporting documentation path.

---

### Task 1: Replace positive scheduler-count guesses with bounded condition waits

**Files:**
- Modify: `tests/web_sol_native_census.test.cjs`
- Modify: `docs/superpowers/plans/2026-09-17-web-sol-census-crypto-wait-ci-repair.md`
- Test: `tests/test_web_sol_native_census.py`

**Interfaces:**
- Consumes: the production listener's synchronous `true` return for a promised popup callback; test-local `release`, `reads`, `gets`, `digests`, message-count, and UI-disabled conditions.
- Produces: `waitFor(predicate, message, timeoutMs)`, `delayedCrypto(delayMs)`, optional `cryptoApi` injection for test VMs, and no production export or schema change.

- [x] **Step 1: Prove the hosted probe race RED**

Inject a 100 ms WebCrypto digest delay into the probe-stage `collectorClock` fixture while retaining the 50-`setImmediate` loop. Run the focused Node 24 test and require failure at `actual probe acquisition`.

- [x] **Step 2: Prove the shared-slot read race RED**

Allow the full extension harness to receive the same delayed crypto surface, including `getRandomValues`. Apply it to the shared-slot case while retaining the 30-turn read loop. Run the focused Node 24 test and require the exact `0 !== 8` failure.

- [x] **Step 3: Implement the minimal scheduler-independent harness**

Add:

```javascript
async function waitFor(predicate,message,timeoutMs=2000) {
 const deadline=Date.now()+timeoutMs;
 while(!predicate()) {
  const remainingMs=deadline-Date.now();
  if(remainingMs<=0) assert.fail(message+' after '+timeoutMs+'ms');
  await new Promise(resolve=>setTimeout(resolve,Math.min(10,remainingMs)));
 }
}
```

Use it for every positive asynchronous condition in this file: digest acquisition, probe acquisition, Chrome-read acquisition, popup completion, reconnect receipt, and UI refresh completion. Change `popup()` to await a response only when at least one listener return is exactly `true`; keep invalid/refused requests immediately response-free. Retain the bounded post-release drain in the outer-expiry negative test because that test asserts absence rather than eventual presence.

- [x] **Step 4: Verify GREEN, repetition, and mutation sensitivity**

Run both focused delayed-crypto cases, the complete Node 24 suite, at least 50 repeated full Node 24 runs, and the Python wrapper gate. In temporary same-directory mutants, restore the old 50-turn probe loop and old 30-turn shared-slot loop; each mutant must fail with its original signature.

- [x] **Step 5: Verify scope and current-base compatibility**

Run `git diff --check`; confirm the only candidate paths are this plan and `tests/web_sol_native_census.test.cjs`; confirm all production directories are byte-identical to the base; re-pin protected master and classify any movement under the current compatibility law.

- [ ] **Step 6: Commit and publish the bounded repair carrier**

Commit with `test(web-sol): wait for actual census acquisitions`, push `sol/web-sol-census-crypto-wait-ci-repair-20260917-sol-001`, and open a draft PR against `master`. Record capability state `BUILT_NOT_PROVEN`, both RED signatures, exact local proof, the unrelated #738 dependency, and explicit non-goals. Hosted CI and current-head review are required before any merge or #738 requalification.
