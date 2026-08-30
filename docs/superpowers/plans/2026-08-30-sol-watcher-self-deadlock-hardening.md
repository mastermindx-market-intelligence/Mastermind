# Sol Watcher Self-Deadlock Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make temporary Sol watcher prompts mechanically reject notification-only self-deadlock and enforce safe three-account action-authority roles.

**Architecture:** Add one pure standard-library prompt validator plus a read-only JSON audit CLI, then bind the contract into the existing `WATCHER_ACTION_LOOP.md` Skillpack and account-local deployment runbook. Preserve existing Agent Dialogue, Wake, RuntimeBinding, Executive, and action-authority owners; this wave creates no runtime watcher or control plane.

**Tech Stack:** Python 3.11+, dataclasses, enum, argparse, json, pytest, existing Mastermind Skillpack source tests.

**Spec:** `docs/superpowers/specs/2026-08-30-sol-watcher-self-deadlock-hardening-design.md`

## Global Constraints

- Authoring pickup was `Mastermind@fefd774701ea285b466cac2646a584801f4a976a`, Skillpack v1.0.1/bootstrap 1. The branch was history-preservingly composed onto protected `5a7046c46046a2ecf597c849aaab914b4f7cd5e1`; re-pin again before final release.
- Do not modify #147 Continuation Delta Skillpack paths except `WATCHER_ACTION_LOOP.md`, which #147 does not own.
- No task-store, watcher, Slack, GitHub, Executive, provider, credential, lifecycle, queue, retry, cursor, or persistence mutation from production code.
- One current child turn has one action-authoritative Sol target; sister Sol surfaces remain observers until canonical transfer.
- `ACTION_AUTHORITATIVE` requires one exact Slack carrier. Observer/parent/triage roles may use a closed `aggregate:<stable-scope-id>` only as bounded read/oversight scope.
- Account exports distinguish `audit_kind: SOL_WATCHER | NON_WATCHER`; non-watchers remain visible but are excluded from conformance counts.
- The three native watcher stores belong to three ChatGPT web/app accounts. One rotating Codex OAuth/CTO slot may resolve to only one account at a time and is neither an account identity nor a prerequisite for watcher-store audit.
- TDD is mandatory for production behavior.

---

### Task 1: Freeze the incident as RED prompt-contract tests

**Files:**
- Create: `tests/test_sol_watcher_contract.py`

- [x] Write tests for a valid action-authoritative contract, FF/FIF notification-only self-deadlock, observer modification, missing fields, malformed carrier, cross-account policy, and audit summary.
- [x] Verify collection fails because `control_plane.sol_watcher_contract` does not exist.
- [x] Commit the RED test carrier.

### Task 2: Implement the pure watcher contract validator

**Files:**
- Create: `control_plane/sol_watcher_contract.py`
- Test: `tests/test_sol_watcher_contract.py`

- [x] Implement strict header parsing and closed role/event/outcome/policy combinations.
- [x] Implement body-law checks and action-authoritative notification-only anti-pattern detection.
- [x] Implement stable task audit aggregation without I/O or mutation.
- [x] Run focused tests and compile checks.
- [x] Commit GREEN.

### Task 3: Add the account-local read-only audit CLI

**Files:**
- Create: `scripts/audit_sol_watchers.py`
- Modify: `tests/test_sol_watcher_contract.py`

- [x] Add RED CLI tests for valid, invalid, malformed-input, and disabled-task handling.
- [x] Verify the new tests fail because the CLI is absent.
- [x] Implement exit codes 0 valid, 1 contract findings, 2 invalid input.
- [x] Run focused tests and compile checks.
- [x] Commit GREEN.

### Task 4: Tighten the Skillpack and source-law tests

**Files:**
- Modify: `docs/sol_skills/WATCHER_ACTION_LOOP.md`
- Modify: `tests/test_sol_watcher_action_loop_skill.py`

- [x] Add RED assertions for the discriminator, role vocabulary, self-deadlock failure, audit command, aggregate scope, and non-watcher classification.
- [x] Verify the assertions fail before procedure changes.
- [x] Make the bounded procedure amendment without changing Skillpack version or touching #147-owned files.
- [x] Commit GREEN.

### Task 5: Add the three-account deployment runbook

**Files:**
- Create: `docs/runbooks/SOL_WATCHER_ACCOUNT_HARDENING.md`
- Create/modify: `tests/test_sol_watcher_account_hardening_runbook.py`

- [x] Add RED assertions for account-local-only mutation, receipt fields, no recency election, aggregate scope and `audit_kind` classification.
- [x] Verify RED.
- [x] Write the export, validation, repair, readback, receipt and canary ceremony.
- [x] Commit GREEN.

### Task 5A: Adversarial false-positive and aggregate-scope repair

- [x] Add RED proving positive notification-only instructions fail while explicit prohibitions pass.
- [x] Add RED proving action authority refuses aggregate scope while triage accepts one closed aggregate scope.
- [x] Add RED proving declared `NON_WATCHER` tasks are excluded from watcher counts.
- [x] Repair validator, Skillpack, runbook and design without adding runtime state or authority.

### Task 5B: Clause-polarity, classification and rotating-Codex correction

**Why:** Exact-head review found that a long line could hide a positive `wait for Sol` behind an unrelated earlier negation; observer prohibitions could be false-rejected; disabled tasks with unknown audit classifications could leave the overall report green; and the initial deployment packet risked conflating three web-account watcher stores with one rotating Codex OAuth slot.

- [x] Add RED proving a later positive wait in a mixed clause is rejected.
- [x] Add RED proving positive observer actuation is rejected and explicit observer prohibitions pass.
- [x] Add RED proving unknown audit kinds fail the report even when the native task is disabled.
- [x] Implement clause-local polarity rather than whole-line marker suppression.
- [x] Add `invalid_classification_tasks` to the stable audit summary.
- [x] Record that one rotating Codex OAuth slot does not identify or authorize the three web-account task stores.
- [x] Correct all three preflight carriers and the Grok placement carrier in place; no replacement carrier or Codex-session multiplication.
- [x] Local exact validator/CLI proof: 19 focused tests passed; `py_compile` passed; four additional polarity/authority mutation probes passed.

### Task 6: Exact-head verification and release packet

**Files:** all nine carrier paths.

- [x] Run local focused validator/CLI proof on exact authored bytes: 19 passed.
- [x] Run validator/CLI `py_compile`.
- [ ] Require current protected-base ancestry and exact nine-file census on the final head.
- [x] Open one DRAFT/HOLD pull request on the same branch: Mastermind #268.
- [x] Request independent review from `mastermindx-2` and `MastermindX1`.
- [ ] Require exact-head hosted repository/security checks and independent review.
- [ ] Reconcile any protected-source movement history-preservingly; no reset/rebase/force.
- [ ] Update PR metadata to the immutable final head and proof.
- [ ] Final Sol review, ready transition and expected-head release only after all gates.
- [ ] Do not call merge/CI/Slack delivery production proof.

### Task 7: Account-local rollout and permanent-runtime continuation

**Carriers:**
- ChatGPT1: `C0BSBM78V1N/1788074126.468539`, child `sol-watcher-account-hardening-chatgpt1-20260830-sol-001`.
- ChatGPT2: `C0BSBM78V1N/1788074146.955509`, child `sol-watcher-account-hardening-chatgpt2-20260830-sol-001`.
- ChatGPT3: `C0BSBM78V1N/1788074158.598619`, child `sol-watcher-account-hardening-chatgpt3-20260830-sol-001`.
- Placement/attention bridge only: `C0BSBM78V1N/1788074188.046229`, `sol-watcher-three-account-placement-20260830-gs-001`.
- Existing permanent owners: W3A #250, W3C under accepted Wake runtime plan, MAS-229 ACK/source resolution, AD-SOL1 exact action-target enforcement.

- [x] Create exact account-local read-only preflight carriers for all three web accounts.
- [x] Send one bounded exact-account placement/attention request to Grok Secretary; it has zero task-store authority.
- [x] Correct placement law after Chairman clarified the one rotating Codex OAuth slot.
- [ ] Collect account `PICKUP_ACK`, `WATCH_ARMED`, and `RESULT / PREFLIGHT` receipts.
- [ ] After #268 is protected, issue same-carrier mutation CONTINUE to each account with the current protected SHA.
- [ ] Audit every enabled account-local Sol watcher and rewrite only invalid prompts in place, preserving watcher IDs/operations/carriers where possible.
- [ ] Collect native readback receipts and validator exit 0 from all three accounts.
- [ ] Run the three-account adverse canary: one authoritative action, two observers, then fail-closed transfer test.
- [ ] Continue existing W3A/W3C/MAS-229/AD-SOL1 carriers; create no replacements.
- [ ] Mark temporary watcher hardening `PROVEN_LIVE` only after all three account receipts and a real no-Chairman continuation canary.
