# Sol Watcher Self-Deadlock Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make temporary Sol watcher prompts mechanically reject notification-only self-deadlock and enforce safe three-account action-authority roles.

**Architecture:** Add one pure standard-library prompt validator plus a read-only JSON audit CLI, then bind the contract into the existing `WATCHER_ACTION_LOOP.md` Skillpack and account-local deployment runbook. Preserve existing Agent Dialogue, Wake, RuntimeBinding, Executive, and action-authority owners; this wave creates no runtime watcher or control plane.

**Tech Stack:** Python 3.11+, dataclasses, enum, argparse, json, pytest, existing Mastermind Skillpack source tests.

**Spec:** `docs/superpowers/specs/2026-08-30-sol-watcher-self-deadlock-hardening-design.md`

## Global Constraints

- Protected pickup is `Mastermind@fefd774701ea285b466cac2646a584801f4a976a`, Skillpack v1.0.1/bootstrap 1.
- Do not modify #147 Continuation Delta Skillpack paths except `WATCHER_ACTION_LOOP.md`, which #147 does not own.
- No task-store, watcher, Slack, GitHub, Executive, provider, credential, lifecycle, queue, retry, cursor, or persistence mutation from production code.
- One current child turn has one action-authoritative Sol target; sister Sol surfaces remain observers until canonical transfer.
- TDD is mandatory for production behavior.

---

### Task 1: Freeze the incident as RED prompt-contract tests

**Files:**
- Create: `tests/test_sol_watcher_contract.py`

**Interfaces:**
- Consumes: future `WatcherRole`, `FindingCode`, `validate_watcher_prompt`, and `audit_tasks` from `control_plane.sol_watcher_contract`.
- Produces: discriminating tests for the validator and CLI integration.

- [ ] Write tests for a valid action-authoritative contract, FF/FIF notification-only self-deadlock, observer modification, missing fields, malformed carrier, cross-account policy, and audit summary.
- [ ] Run `pytest -q tests/test_sol_watcher_contract.py` and verify collection fails because `control_plane.sol_watcher_contract` does not exist.
- [ ] Commit the RED test carrier.

### Task 2: Implement the pure watcher contract validator

**Files:**
- Create: `control_plane/sol_watcher_contract.py`
- Test: `tests/test_sol_watcher_contract.py`

**Interfaces:**
- Produces: `WatcherRole`, `FindingCode`, `Severity`, `ContractFinding`, `PromptAudit`, `TaskAudit`, `AuditReport`, `validate_watcher_prompt(prompt)`, and `audit_tasks(tasks)`.

- [ ] Implement strict header parsing and closed role/event/outcome/policy combinations.
- [ ] Implement body-law checks and action-authoritative notification-only anti-pattern detection.
- [ ] Implement stable task audit aggregation without I/O or mutation.
- [ ] Run `pytest -q tests/test_sol_watcher_contract.py`; all tests must pass.
- [ ] Run `python -m py_compile control_plane/sol_watcher_contract.py`.
- [ ] Commit GREEN.

### Task 3: Add the account-local read-only audit CLI

**Files:**
- Create: `scripts/audit_sol_watchers.py`
- Modify: `tests/test_sol_watcher_contract.py`

**Interfaces:**
- Consumes: `audit_tasks`.
- Produces: `main(argv: Sequence[str] | None = None) -> int`; accepts a JSON list or `{\"tasks\": [...]}` from file/stdin and emits stable JSON.

- [ ] Add RED CLI tests for valid, invalid, malformed-input, and disabled-task handling.
- [ ] Run the focused tests and verify the new tests fail because the CLI is absent.
- [ ] Implement the minimal CLI with exit codes 0 valid, 1 contract findings, 2 invalid input.
- [ ] Run focused tests and compile checks.
- [ ] Commit GREEN.

### Task 4: Tighten the Skillpack and source-law tests

**Files:**
- Modify: `docs/sol_skills/WATCHER_ACTION_LOOP.md`
- Modify: `tests/test_sol_watcher_action_loop_skill.py`

**Interfaces:**
- Produces: protected procedure requiring `MMX_SOL_WATCHER_V1`, explicit watcher role, same-carrier action-or-typed-blocker, and sister-Sol observer law.

- [ ] Add RED source-law assertions for the discriminator, role vocabulary, self-deadlock failure, and account-local audit command.
- [ ] Run the two focused test modules and verify source-law assertions fail.
- [ ] Make the smallest procedure amendment without changing Skillpack version or touching #147-owned files.
- [ ] Run focused tests and compile checks.
- [ ] Commit GREEN.

### Task 5: Add the three-account deployment runbook

**Files:**
- Create: `docs/runbooks/SOL_WATCHER_ACCOUNT_HARDENING.md`
- Modify: `tests/test_sol_watcher_contract.py`

**Interfaces:**
- Produces: account-local audit/repair/receipt ceremony and cross-account adverse canary.

- [ ] Add source assertions for account-local-only mutation, required receipt fields, and no action-target election by recency.
- [ ] Run focused tests and verify RED.
- [ ] Write the runbook with exact export, validation, repair, receipt, and canary sequence.
- [ ] Run focused tests and markdown/source checks.
- [ ] Commit GREEN.

### Task 6: Exact-head verification and release packet

**Files:**
- All files above.

- [ ] Run `pytest -q tests/test_sol_watcher_contract.py tests/test_sol_watcher_action_loop_skill.py`.
- [ ] Run `python -m py_compile control_plane/sol_watcher_contract.py scripts/audit_sol_watchers.py`.
- [ ] Run `git diff --check` or equivalent connector-side changed-file census.
- [ ] Open one DRAFT/HOLD pull request on the same branch.
- [ ] Require exact-head hosted repository/security checks and independent review.
- [ ] Do not call merge/CI/Slack delivery production proof.

### Task 7: Account-local rollout and permanent-runtime continuation

**Carriers:**
- Current ChatGPT account: native task store, account-local only.
- Sister accounts: one exact coordination carrier each; no cross-account task mutation.
- Existing permanent owners: W3A #250, W3C under accepted Wake runtime plan, MAS-229 ACK/source resolution, AD-SOL1 exact action-target enforcement.

- [ ] Audit every enabled current-account Sol watcher and rewrite only invalid prompts in place, preserving watcher IDs/operations/carriers where possible.
- [ ] Send exact account-local audit commissions to the other two ChatGPT Sol accounts and collect receipts.
- [ ] Run the three-account adverse canary: one authoritative action, two observers, then fail-closed transfer test.
- [ ] Continue existing W3A/W3C/MAS-229/AD-SOL1 carriers; create no replacements.
- [ ] Mark temporary watcher hardening `PROVEN_LIVE` only after all three account receipts and a real no-Chairman continuation canary.
