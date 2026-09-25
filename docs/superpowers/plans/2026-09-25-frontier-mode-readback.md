# Frontier Mode Readback Implementation Plan

> For agentic workers: use superpowers:executing-plans for the bounded source task; existing source custody and protected law remain controlling.

**Goal:** Qualify exact-session, fresh, stable selector evidence without actuating a browser or granting action authority.

**Architecture:** One production-inert pure JavaScript leaf inside the incumbent Web-Sol extension directory. The existing #836 owner may integrate it after current source/protocol/release gates; this task leaves all existing runtime and application files untouched.

**Tech Stack:** JavaScript, Web Crypto SHA-256, Node built-in test runner; no added dependencies.

**Spec:** docs/superpowers/specs/2026-09-25-frontier-company-convergence.md

## Global constraints

- Source basis: protected 63555e1f9405c79405fc30682aa502a68d8abf80; one installed mmx-workspace allocation for mastermind-os-frontier-company-convergence-20260925-sol-001, lane web.
- Source ceiling: this plan, its spec, integrations/chairman_surfaces/web_sol_extension/reasoning_mode_core.js, tests/web_sol_reasoning_mode_core.test.cjs.
- No manifest/background/content/native-host/router/app modification, no production browser call, no mode selection, no provider turn, no lifecycle or custody transfer.
- Reuse RuntimeBinding id/generation/fingerprint and document_epoch; no identity registry or stored mode state.
- Lifetime ceiling is 30,000 ms for candidate observation evidence only, never a provider/session time limit.
- Every result has action_authorized=false, capability_reprobe_required=true, served_model=null.
- Native authentication, current capability proof and admission remain outside this mathematical evidence reducer. A digest is not authentication.

## Review focus

Two samples of the same stale observation must not prove stable fresh readback. A→B→A navigation must not reuse the old document epoch. Generic PRO/LATEST labels must not invent served identity. Malformed/accessor-bearing or secret-bearing extra fields must not execute or be echoed. App/bridge restart must not cause this stateless helper to submit or retry anything.

## Task 1 — mode evidence qualification leaf

Create the core and Node test file named above. Export `qualifyModeReadback(request, observations, nowMs)` and the immutable API as `MMXWebSolModeReadbackCore` in a browser script and through module.exports in Node. The function is async only for digest computation, not for external I/O.

Consumes: a closed request with incumbent identity, requested_family, requested_effort, not_before_ms and expires_at_ms; exactly two closed normalized flat observations including identity, readiness, selected family/effort, selector cardinality, timestamp and selector_evidence_digest. Family selections are SOL/LATEST; requested efforts EXTRA_HIGH/PRO; observations may explicitly be OTHER/UNKNOWN. SHA-256 covers compact JSON with sorted keys, excluding the digest field.

Produces: a frozen closed result. Only MODE_READBACK_MATCH includes the two verified evidence digests and matched identity/selected values. All failures use closed statuses and omit input payloads. The helper never returns permission to submit.

- [x] Write the tests first. The initial assertion must fail because the core is absent, not because an unhandled module-import error masks the missing feature:

```javascript
test('mode core is available', () => {
  assert.equal(typeof core?.qualifyModeReadback, 'function');
});
```

- [x] Run `node --test tests/web_sol_reasoning_mode_core.test.cjs`; record the expected RED assertion.
- [x] Implement strict own-data-property validation, identity checks, bounded numeric/enumerated observations, request/sample freshness, canonical digest verification, exact single selected-family/single-effort-control proof, healthy idle authenticated surface, stable requested selection, and immutable no-authority result.
- [x] Run the same Node command and inspect actual PASS/FAIL output. Repair implementation failures, preserving valid adverse tests.
- [x] Run `node --test tests/web_sol_census_popup_truth.test.cjs tests/web_sol_native_census.test.cjs tests/web_sol_session_census.test.cjs` to detect incumbent observer regressions, then `git diff --check` and a four-path status check.
- [x] Inspect the final diff and syntax with `node --check integrations/chairman_surfaces/web_sol_extension/reasoning_mode_core.js`.
- [ ] Commit and publish only the four scoped paths through the current registered-workspace publication actions. Keep the PR draft; request exact-head review without claiming integration or production acceptance.

## Held integration task — not granted by this leaf

The next source owner is #836 for actual DOM normalization, native bridge wiring and mode actuation. Consume this leaf only after #836 current custody and its merge conflict are reconciled, and the closed mode action is reviewed under the browser/context-rotation laws. Authenticate the observation producer, fence exact RuntimeBinding/document generations and mode effect identity, and prove no-send selector canaries before a turn is allowed. The #890 capability producer/consumer and #936/#953/#958 read-only limitations remain explicit dependencies. Do not edit these carriers from this workspace.

## Completion evidence for this task

Exact source commit, four-path diff, observed RED/GREEN test receipts, incumbent regression receipts, no manifest change and published draft readback. Classification can be BUILT_NOT_PROVEN only; this task does not satisfy the parent production vertical. Continue through the parent checkpoint #600/5829163043 without replaying prior archaeology.

## Observed execution evidence

Initial RED: Node process 46432 asserted the absent API (0 pass / 1 fail). Initial implementation: process 48624, 46 pass / 0 fail. Adversarial array-shape tests: process 51380, 3 pass / 2 fail; extra array keys were ignored and an array accessor was invoked. The root cause was direct indexed array access before closed-shape validation. Fixed by copying only the two own data-property descriptors before asynchronous work. The trailing-newline hypothesis was falsified by passing tests; no speculative regex repair was made. Final focused run: process 52970, 51 pass / 0 fail, exit 0. Incumbent census regression process 48867: 89 pass / 0 fail, exit 0. Syntax and whitespace commands completed with exit 0; a final four-file byte/scope verification precedes publication.

Direct implementation reason: CRITICAL_PATH_SHORTCUT for one frozen, provider-free leaf; no Fable or unqualified worker was spawned. This is source evidence, not independent review, CI, live browser proof or production acceptance. Publication and readback receipts are maintained on the existing parent checkpoint #600/5829163043. No source writer is released by this document.
