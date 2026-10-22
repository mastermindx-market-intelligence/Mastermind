STATUS: COMPLETE

```
RETURN L-R3
files: brain/management_lifecycle.py (516), tests/test_management_lifecycle.py (829)
tests: 86 passed / 0 failed management_lifecycle (56 test functions, inline fixtures, no file I/O beyond
        inspect/ast source read); scheduler_decision_outcomes 124 passed — unchanged from the pre-change
        baseline (also adjacent sanity: test_decision_rows + test_scheduler_governance 43 passed, 2 skipped)
states covered: not_due, disabled, started, accepted_no_change, accepted_change, rejected, failed,
        incomplete_uncertain — all 8 reached from real records (test_all_eight_states_are_reachable…);
        reasons covered: skipped_lock_held / awaiting_start / no_start_record / no_finish_record /
        market_closed / nothing_queued / legacy_etf_migration_pending / cost_capped / missing_submission /
        rejected_execution_error / runner_failed / invalid_result / inconsistent_result / exception-path
        (no reason) / rejected_* / frozen_* / projection_failed / settlement_finalization_incomplete /
        unrecognized_outcome / missing_due_at; failure kinds credential, quota, availability, transport,
        application, unclassified (+ label_misleading on "error result: success")
deviations from packet: none in contract; four documented judgment calls —
        (1) inertness guard cannot forbid the raw substring "settle" (the mandated `settlement` key and
            "settled" value contain it), so it forbids the word forms instead: \bsettle\b, settle_, .settle,
            plus bot.settle/settle_us/settle_asia shapes; all other listed needles (open(, .write(,
            json.dump, append(, import app.scheduler, apscheduler, paper_account, subprocess) are forbidden
            verbatim, and an ast-derived check pins the module's imports to {__future__, datetime, typing}
            only, so brain.decision_submission is named in prose and never imported.
        (2) Mapping order safety tweak: projection_failed / settlement_finalization_incomplete are matched
            BEFORE the generic rejected_*/frozen_* bucket, and that bucket additionally requires the ledger's
            own "warn" status — so an error run carrying a rejected_* target plus a projection reason reads
            incomplete_uncertain, never a clean rejection. No enumerated packet case changes outcome.
        (3) Unenumerated edges made explicit: unparseable/absent due_at → incomplete_uncertain reason
            "missing_due_at"; unusable `now` falls back to the freshest record stamp (never a wall-clock read);
            project_cycles projects a malformed opportunity as such a row rather than dropping it, so the
            packet's "one row per opportunity in order" holds literally.
        (4) Field-carrying detail: with no packet_accepted matched, brain_run_id/packet_id/asof are carried
            from the cycle's own window-matched decision row (the CN/HK fixtures depend on this); with a
            failure_kind of "application", failure_evidence stays None because evidence is defined as a
            matched needle, never smuggled raw text. A superseded row is flagged but never appears in
            `sources`, which lists only records actually used.
```
