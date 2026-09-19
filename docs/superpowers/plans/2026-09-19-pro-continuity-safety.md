# Pro continuity safety implementation plan

> **For agentic workers:** Use superpowers:executing-plans for the approved direct source lane. Independent review and native canaries remain separate.

**Goal:** Let a substantial Web session end at a verified continuation boundary without losing pending effects or falsely completing its mission.
**Architecture:** Amend the existing ACTIVE_EXECUTION finalizer and its same-pin consumers; reuse Agent OS/Executive checkpoint and fresh-Sol evaluation owners. No runtime state, schema, store or provider effect is added.
**Tech Stack:** Markdown source contracts, Python/pytest and existing ScenarioPacket fixtures.
**Spec:** docs/superpowers/specs/2026-09-19-pro-continuity-safety.md. Chairman approved the proposal and directed direct implementation plus bounded manual fanout; source adoption, deployment and Project rollout remain separate.

## Global constraints
- Operation: pro-continuity-reliability-20260919-sol-001; protected basis ac6180d0ca9107daae54f9eea6bd4b8aef92d630; Skillpack 1.0.1 / bootstrap 1.
- No new Executive enum/Job/Attempt, checkpoint database, runtime, transcript store, auto-wake, provider spawn or metered route.
- Same-carrier effects, source custody, explicit incomplete mission and exact-source publication remain mandatory.
- PR #147 owns replay-prevention semantics; do not alter its branch or repeat accepted linter work. Overlapping procedure paths require composition review before either release.
- PR #506 owns ModelRouter duration/routing repair; this branch does not alter its code/laws or waive admission.
- PR #651 owns bounded Web continuation projection; #656 owns current-fact transfer drafts; #836 owns exact Web binding. Do not duplicate them.
- No source merge, Project rollout, native behavior or outage reduction follows from local tests.

## Review focus
- A stale checkpoint after a material write must not permit verified continuation: PCR06/PCR09 and exact gate coverage.
- A new chat with active incumbent effects must not inherit custody: PCR05/PCR07.
- An agent must not use a saved plan as a universal early-exit excuse: PCR02/PCR10/PCR15.
- A hidden deadline or model label must not become fake telemetry/permission: PCR03/PCR12.
- A working snapshot must not overwrite a prepared transfer capsule or newer concurrent revision: PCR13 and closeout contract.

## Task 1 — Source regressions and native pressure inputs
Files: tests/test_pro_continuity_reliability.py; research/fixtures/pro_continuity_reliability_2026-09-19.json.
Consumes existing scripts.ohf.fresh_sol_eval.ScenarioPacket; produces 16 exact evaluator packets, not model results.
- [x] Write contract tests before modifying the procedure files.
- [x] Run pytest --noconftest -p no:cacheprovider -q tests/test_pro_continuity_reliability.py on unchanged protected procedure; 14 expected assertions fail, no collection errors.
- [x] Keep the existing active-execution baseline (28 tests) as the regression reference.

## Task 2 — One existing finalizer, coherent consumers
Files: docs/sol_skills/{ACTIVE_EXECUTION,INDEX,COLD_START,CLOSEOUT,WEB_CEO_DELEGATION}.md. BOOTSTRAP_KERNEL.md remains byte-identical to protected source.
- [x] Add CHECKPOINTED_CONTINUATION only to ACTIVE_EXECUTION, with mission incomplete, justified boundary, current verified owner readback, all effects/obligations, next action/resume surface and custody gates.
- [x] Add checkpoint-first bounded recovery and pre-risk cumulative persistence; distinguish working snapshots from immutable capsules.
- [x] Deny host-compaction, total-context, hidden-deadline and automatic-wake claims.
- [x] Require decision-ready research, not minimum duration or first-outline acceptance.
- [ ] Separate rollout gate: compact Project bootstrap migration is NOT delivered by this slice. An initial draft lost guard clauses; baseline tests caught this. A subsequent repair request was blocked by the platform safety checker. Readback confirmed no repair effect, and the draft was rolled back byte-for-byte to protected source. Do not retry the rejected repair on another carrier or delegate it as a workaround. Resolve the platform limitation through supported review before any such effect.
- [x] Run the new and transitive selected suites: 211 passed, 1 skipped, no failures/errors. Exact evidence is research/PRO_CONTINUITY_RELIABILITY_IMPLEMENTATION_2026-09-19.md; full repository and native model proof remain owed.
- [ ] Publish one reviewed candidate on the acquired operation branch; no force, shared-branch mutation or self-merge.

## Task 3 — Existing-owner integration and real proof
- [ ] Independent exact-head policy review plus #147 composition adjudication.
- [ ] Continue #506 without rebuilding the floor change; explicitly reconcile the new preference with source and machine gate.
- [ ] Verify #840 on the actual serving Studio connector; preserve its 16-KiB contract and no-replay semantics.
- [ ] Continue #651 through canonical live Agent OS read and fresh-session resume; preserve #656/#836 owners.
- [ ] Run native PCR pressure cases via existing evaluation owner and paired fresh Web sessions. Static packet validation is not native proof.
- [ ] Only after accepted source: pilot Project copy/readback and non-destructive memory inventory, then evidence-based rollout.

## Safe return
Return exact commit/PR, actual tests, remaining owner gates and a compact next-action pointer. Do not claim a receiver STARTed, a verified organizational checkpoint or Project settings changed without that owner's evidence.
