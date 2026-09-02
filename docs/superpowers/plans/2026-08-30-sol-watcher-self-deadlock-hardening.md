# Sol Watcher Self-Deadlock Hardening Implementation Plan

**Goal:** Replace free-form watcher authority parsing with one exact renderer-owned prompt document, then roll it out account-locally and prove one-authoritative/two-observer behavior.

**Carrier:** Mastermind PR #268 / `sol/sol-watcher-self-deadlock-hardening-20260830`  
**Spec:** `docs/superpowers/specs/2026-08-30-sol-watcher-self-deadlock-hardening-design.md`

## Global constraints

- Preserve quarantined regex commit `4454f607ae02b990c8418ab6f946ddd568fe486c` as historical ancestry; never reset, rebase, force-update, or award it release credit.
- Existing final PR scope remains exactly nine paths.
- No native task mutation before source protection and a fresh account-local continuation.
- No watcher/task store, lifecycle, action-owner table, queue, retry/failover plane, cursor, provider session, credential bridge, or cross-account controller.
- TDD and exact-head hosted/security proof are mandatory.

## Task 1 — Preserve exact RED evidence

- [x] Retain prior regex/polarity failures and quarantined head as evidence.
- [x] Publish renderer/body-identity tests before exact implementation.
- [x] Capture hosted RED where canonical APIs/finding are absent.
- [x] Strengthen RED to literal numbered body text and `CANONICAL_PROMPT_MISMATCH`.

## Task 2 — Implement exact renderer identity

**Files:** `control_plane/sol_watcher_contract.py`, `tests/test_sol_watcher_contract.py`

- [x] Add keyword-only `render_watcher_prompt(...)`.
- [x] Derive role events/outcome/sister policy; callers cannot author them.
- [x] Freeze exact `MMX_SOL_WATCHER_BODY_V1` common prefix and role tails.
- [x] Normalize only CRLF/lone-CR and terminal newline characters.
- [x] Require normalized byte equality with renderer output.
- [x] Emit `CANONICAL_PROMPT_MISMATCH` for otherwise parseable drift.
- [x] Remove natural-language polarity from validity authority while retaining legacy finding enum values.
- [x] Preserve task export identity, Boolean, classification, duplicate, and report behavior.

## Task 3 — Prove the contract

- [x] All four role round-trips.
- [x] Exact Slack and lawful aggregate carriers.
- [x] Invalid role/operation/carrier/edge renderer inputs.
- [x] Exact seven-header order and role derivation.
- [x] CRLF, lone-CR, and terminal-newline acceptance.
- [x] BOM, whitespace, reorder, internal blank, body-line, role-body, Markdown, and extra-prose rejection.
- [x] Every B1/B2/B3 and second-stage composition witness rejected by document identity.
- [x] Disabled/non-watcher, ID alias, duplicate, Boolean, classification, and CLI behavior.
- [x] Local exact-focused suite: 65 PASS before publication.

## Task 4 — Synchronize procedure and rollout records

**Files:** Skill, runbook, design, plan, source tests.

- [x] Skill requires renderer-produced canonical prompts and STOP-before-disarm lifetime law.
- [x] Runbook requires full prompt replacement and exact native readback.
- [x] Module invocation is `python3 -m scripts.audit_sol_watchers`.
- [x] Design declares regex/polarity candidates historical and non-releaseable.
- [x] Procedure tests reject prompt patching/synonym repair.
- [x] Account-runbook tests require `EFFECT_UNKNOWN` no-cross-account-retry behavior.

## Task 5 — Current-base verification and source release

- [ ] Re-pin current protected Mastermind/Skillpack.
- [ ] History-preservingly join current protected master if branch is behind and all nine paths are collision-free.
- [ ] Require exact nine-path diff and quarantine ancestry.
- [ ] Run focused tests, repository gate, compile, diff check, and module CLI smoke on immutable head.
- [ ] Require hosted repository test and all security/CodeQL checks green.
- [ ] Obtain independent exact-head adversarial review from an identity distinct from source author.
- [ ] Update PR body with immutable head/tree/base/path/proof receipts.
- [ ] Final Sol expected-head source-only release; no production claim.

## Task 6 — Three-account rollout

Existing account carriers remain the only rollout carriers:

- ChatGPT1: `C0BSBM78V1N/1788074126.468539`
- ChatGPT2: `C0BSBM78V1N/1788074146.955509`
- ChatGPT3: `C0BSBM78V1N/1788074158.598619`

- [ ] After source protection, re-read each account-local native task store.
- [ ] Establish exactly one current `ACTION_AUTHORITATIVE` task and two non-authoritative observers for the canary.
- [ ] Render, replace, and read back each prompt on the same native task ID.
- [ ] On ambiguous write/readback, record `EFFECT_UNKNOWN`; no cross-account retry/failover.
- [ ] Require account-local audit exit 0 and receipt for every account.
- [ ] Prove one authoritative action, two observer refusals, canonical transfer, and exact prompt-drift failure.
- [ ] Prove one real no-Chairman continuation cycle.

## Task 7 — Permanent runtime continuation

- [ ] Continue existing W3C/ACK1/AD-SOL/RET/fleet carriers; create no replacements.
- [ ] Retire temporary watchers only after the equivalent Agent Dialogue -> Wake -> exact target/current writer -> acknowledgement -> source-resolution path is production-proven.

## Completion ruler

Source merge: `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

Program completion: three-account native receipts, exact readback, one-authoritative/two-observer and transfer canaries, and one unattended continuation loop. Green CI, merged source, or Slack delivery alone is not completion.
