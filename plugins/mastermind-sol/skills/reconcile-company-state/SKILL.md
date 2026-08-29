---
name: reconcile-company-state
description: Use when Mastermind canonical sources, projections, transports, session bindings, or modifying effects disagree or are ambiguous.
---

# Reconcile Company State

Use for stale or conflicting Agent OS, Executive OS, GitHub, Linear, Slack, RuntimeBinding, watcher, or app results.

## Mandatory current-source gate

Read protected Mastermind `master`, record its exact commit, load `docs/sol_skills/INDEX.md`, `RECONCILE_STATE.md`, and `CLOSEOUT.md` from that same exact commit, and verify compatibility. Run `bootstrap-mastermind` first. If compatibility cannot be established, modifying workflow is unavailable.

## Required package reference

Read `../../references/authority-boundaries.md` before interpreting any app, record, or action as authority. The reference summarizes canonical ownership; current protected source still controls.

## Procedure

1. Classify the disagreement: projection, organizational, implementation, runtime, grounding, transport uncertainty, dialogue or watcher uncertainty, or duplicate conflict.
2. Freeze exact identities and revisions before repair.
3. Identify the canonical owner of each disputed fact. Do not majority-vote among sources.
4. For a possible modifying effect, classify `EFFECT_UNKNOWN`, retain the same operation, app, and carrier, and query canonical status. Never blind-retry or fail over.
5. For duplicate identity: same key plus the same normalized payload reconciles; the same key plus changed payload conflicts; changed work requires a new operation.
6. For dialogue: silence is never STOP; a worker return without a later explicit Sol edge remains awaiting Sol.
7. For Linear, Slack, or Control Room disagreement, repair only the wrong owner or projection after canonical evidence is known.
8. Record unresolved uncertainty and the exact next action.

## Output

```text
disagreement class
canonical owner per fact
exact identities/revisions
known / uncertain
wrong or stale layer
repair performed or withheld
whether modification is safe
exact next action
```

## Forbidden inferences

- Client timeout is not proof of no effect.
- Newest chat, tab, or message does not win a Sol authority conflict.
- A leftover watcher cannot originate retry, merge, continuation, or successor work.
- A projection mismatch is not permission to rewrite canonical truth.

## Stop conditions

Stop when canonical status, effect, current writer, action target, current grounding, or carrier identity remains ambiguous.
