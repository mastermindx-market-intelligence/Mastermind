# 2026-08-25 XPV2 continuation replay (Sol Continuation Delta founding incident)

Incident class: continuation replay / stale durable-state / ambiguous handoff
scope. This is a **commission-lint** incident, not a trading-stack incident: the
canonical shapes here are replay findings from `scripts/sol_commission_lint.py`,
not dwell/severity/firm/cycle gates.

## Chronology (all receipts in `github_truth.json`)

1. Macro Agent OS workstream `WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2` lagged
   GitHub for days: it still presented R3B as `todo` while GitHub had progressed
   through R3B, R3B.1, R3B.2, final critics, and approval preparation.
2. `#6388` (merge `4faf00a44510`) correctly repaired the workstream at that
   moment: R3B/R3B.1 `done`, R3B.2 `in_progress` at head `90ce21ac…`, with a
   next_action instructing Sol to resolve F1/F2 and issue the final verdict.
3. Hours later the canonical carrier `#6337` **completed and merged**
   (merge `8b303a58e8c0…`): APPROVE_WITH_CONDITIONS, reference law only, five
   R3C-owned conditions carried, no production migration, R3C explicitly NOT
   authorized. The newer workstream reconciliation itself became stale.
4. The 2026-08-21 handoff was independently stale the whole time: its
   `next_actions` still said "Review and dispatch R3B_HANDOFF_DRAFT.md … to a
   fresh design session."

The hard property this replay pins: the system must not merely notice the OLD
stale handoff — it must survive the state in which a NEWER workstream
reconciliation became stale after a later carrier completed.

## Fixtures

- `stale_workstream_excerpt.md` — the R3B.2 block + top-level next_action as
  frozen from macro `origin/main` (`15ce6525dd64`) on 2026-08-25, AFTER #6337
  had already merged. Everything executable in it was already completed.
- `stale_handoff_excerpt.md` — the 08-21 handoff's `do_not_redo` /
  `next_actions` as frozen from the same tree. Historical evidence; preserved,
  never rewritten.
- `github_truth.json` — the carrier truth at the same instant.
- `current_context_bundle.json` — the REPAIRED organizational do_not_redo set
  (statement-identical to the 2026-08-25 Agent OS handoff shipped by the macro
  records repair PR).
- `naive_copied_commission.md` — failure shape 1: a prior commission copied
  forward wholesale; completed/superseded obligations remain in
  `execution.ordered`. Must stay RED forever
  (`HANDOFF_REPLAY_COLLISION`, `SUPERSEDED_WORK_REOPENED`).
- `naive_stale_derived_commission.md` — failure shape 2 (the harder one): a
  commission lawfully derived from the STALE-BUT-RECENTLY-REPAIRED records —
  F1/F2 re-opened, final verdict re-commissioned, R3C conditions surfaced as
  OPEN. Under the current context bundle it must stay RED forever
  (`DNR_COVERAGE_MISSING`).
- `lawful_continuation.md` — the correct continuation delta derived from
  current canonical state: completed work recognized DONE, the Agent OS repair
  as the only OPEN work, the five R3C-owned conditions BLOCKED and held.
  Must lint clean (exit 0) under the current context bundle.
