# Watcher Resource + Carrier Freshness — Current-Source Reconciliation

**Carrier:** Mastermind PR #207 / `sol/watcher-resource-freshness-plan-20260828`

**Purpose:** narrow current-source amendment to the historical rollout plan in `2026-08-28-watcher-resource-freshness-implementation.md`. This record changes no watcher/source-law/runtime behavior. Where current carrier facts below conflict with the older plan's planning receipts or collision examples, this record wins; the rollout architecture and non-goals remain unchanged.

## Current protected predecessor

Chairman-approved design PR #205 is now protected as `Mastermind@dfd69451dce5e186ce05f65446023fbe21f07a58`.

That merge is records-only / `SPEC_ONLY`: it makes the resource/cadence + carrier-freshness design durable but does not implement 60m/15m cadence law, fresh-read-before-substantive-write procedure, runtime enforcement, a watcher registry, or any Executive lifecycle change.

## Mastermind Wave-A collision

Mastermind PR #147 (`Continuation Delta Law — Skillpack 1.1.0`) remains OPEN/DRAFT and currently nonmergeable. It overlaps Wave-A Skillpack paths including `docs/sol_skills/INDEX.md`, `COMMISSION_WAVE.md`, and `RECONCILE_STATE.md`.

Therefore Wave A must not mechanically apply the older plan text over current protected source. Immediately before RED/source-law implementation it must:

1. re-pin then-current protected `master` + same-SHA Skillpack;
2. read current #147 exact head/state and every overlapping Skillpack path;
3. preserve #147's independent continuation semantics without treating its unmerged bytes as protected law;
4. extend the one universal watcher owner `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` and project into the current Skillpack/root bootstraps without deleting newer placement/action-authority/continuation law;
5. STOP with a decision/collision return rather than overwrite either law if path-level reconciliation is materially ambiguous.

#147 is not a substitute carrier for watcher-resource/freshness and this plan does not authorize merging #147 or bypassing its fresh-Sol behavioral gate.

## Macro bootstrap collision — supersedes old #6381 fact

The older plan says Macro PR #6381 is the active overlapping `AGENTS.md`/`CLAUDE.md` carrier. That is now stale.

* Macro #6381 is **CLOSED / UNMERGED / donor-only** at `277b758315177dc394bec9ede7f917a37c3a4a08`; never reopen/rebase/merge it.
* Its active successor is Macro #6652, operation `ci-quiescence-v2-20260829-sol-001`, currently OPEN/DRAFT/HOLD. #6652 owns `AGENTS.md`, `CLAUDE.md`, ship-loop/quota hook files, tests and its current Agent OS handoff.

Therefore the later Macro bootstrap carrier in this rollout remains dependency-held until #6652 is terminally reconciled. Do not edit Macro `AGENTS.md` or `CLAUDE.md` from this program while #6652 remains nonterminal, and do not copy donor #6381 bytes around #6652.

## Current execution state

No Wave-A source-law implementation has STARTED from this plan. PR #207 remains planning/records only.

After this plan is reviewed/durable, ordinary unbound implementation work is `WAITING_CAPACITY / needs_placement` until the canonical placement owner selects an exact eligible receiver. Do not emit `OPEN_PICKUP` or `ACCOUNT_BINDING: CHAIRMAN_SELECTS` merely because automated placement is incomplete. Preferred bounded avenue is CTO Sol/Codex or Terra; Fable is not justified while the law and tests remain frozen and path-reconciliation is bounded.

## No-rebuild boundary

Preserve the original plan's architecture:

* one universal procedure owner, not a new watcher-policy store;
* existing Agent Dialogue / Worker Presence / Wake / owner-specific enforcement surfaces only;
* no new watcher daemon, watcher DB, queue, cursor, retry plane, lifecycle owner, session registry, capacity router, or provider authority;
* design/plan/CI/merge are not production proof;
* active-session visibility is transport only and never substitutes for a consumed carrier read.
