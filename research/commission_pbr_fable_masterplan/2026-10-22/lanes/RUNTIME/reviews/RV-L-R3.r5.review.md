<!-- run-id pbr-rt-rv-lr3-r5 | host ubuntu1 | model glm-5.3 | class review C2 | PR #1711 head 2c787cf36f3866f9bb710c988db60a6418183d55 | source sha256 78dd9659c6df5308d20a7016f0fd28b79067ab6cfc4be69b35eca327a99879de | retained 2026-10-22T11:33:52Z -->
All checks are complete. Cleaning up my understanding into the review report:

---

## Review report — RV-L-R3, PR #1711 (head `2c787cf`)

### 1. Contract fidelity — PASS
Every packet-required name exists verbatim: `SCHEMA` (brain/management_lifecycle.py:51), `STATES` in the packet's exact names/order (:53–62), `classify_failure_text` returning `{kind, evidence, label_misleading}` (:196–214), `project_cycle`/`project_cycles` signatures (:272, :284), and all 17 packet return keys always present in `_blank` (:401–421; pinned by `KEYS` in tests/test_management_lifecycle.py:20–24). Matching rules implemented as specified: earliest start in `[due−60s, due+grace]` (:323–339), finish by `extra.run_id` identity (:345–349, :256–258), latest packet in `[started, (finished|now)+60s]` (:354–357), row identity-then-window (:429–447), superseded flag (:459–476), lock_held (:328–334). Every state-mapping branch of packet lines 63–83 is present in `_map_finished`/`_map_accepted` (:491–537). Additions beyond the packet (`started_at`/`finished_at`, `missing_due_at`) come from the orchestrator commit or degrade conservatively. All four declared judgment calls: acceptable (see RETURN).

### 2. Purity / inertness — PASS
Imports are exactly `__future__`, `datetime`, `typing` (:46–49; AST-pinned by the test at tests/…:740). No `open(`/`.write(`/`json.dump`/`append(`/subprocess/threading/socket; no wall-clock read (`datetime.now`/`time.time`/`utcnow` grep: zero hits). Module-level names are constants only (one private lookup dict `_RUN_STATUS_BY_STATE`, never mutated). Repo-wide grep: nothing references `brain.management_lifecycle` except its own test and its own docstring; no execution-plane code (app/, bot/, control_plane/, portfolio/) imports it.

### 3. Vocabulary mirror — PASS
I traced every emission of `app/scheduler.py:84–135 _brain_job_outcome` against `_map_finished`: `invalid_result`→failed/application; `projection_failed` (error)→incomplete_uncertain; `cost_capped` (skip)→rejected; `market_closed`/`nothing_queued`/`legacy_etf_migration_pending` (skip)→not_due; `runner_failed`→failed; `settlement_finalization_incomplete` (error, target queued/executed)→incomplete_uncertain; ok+queued/executed→`_map_accepted`; `inconsistent_result`→failed; `missing_submission`→failed+classify; `rejected_execution_error` (error)→failed; other `rejected_*`/`frozen_*` (warn, reason=target)→rejected with reason=target_status. The exception path (`_ledger_end(handle,"error")`, app/scheduler.py:72–81, no reason/target) hits the `status=="error" and not reason` arm (:505) → failed/application. `ACCEPTED_TARGET_STATUSES = frozenset({"executed","queued"})` (brain/decision_submission.py:81) equals `ACCEPTED_TARGETS` (:91), drift-guarded by tests/…:796–801. No emitted value falls through to a wrong state; the only fall-through (`unrecognized_outcome`) is the packet's own else-branch.

### 4. Conservative matching — PASS (probes under `~/lanes/tmp/pbr-rt-rv-lr3/adv_probe.py`, all passed)
- **(a) different-run row, same date:** with brain_run_id known (a1): superseded=True, settlement stays `pending`, foreign row's `executed/5` and packet not taken. With brain_run_id unknown and the foreign row *inside* the window (a2): adopted — this is the packet's own fallback rule (packet line 57–58), used only for the display label/identity. Outside the window (a3): not adopted, superseded stays False.
- **(b) another book's `run_finished` in the same window:** never adopted — finish matching is by `extra.run_id` (uuid-suffixed, namespace-unique), not window/book; a same-book different-run finish is likewise rejected (test tests/…:509). State correctly stays `started`.
- **(c) naive/malformed stamps:** naive parsed as UTC, malformed `ts` → record excluded from matching, junk `due_at` → `incomplete_uncertain`/`missing_due_at`, junk `now` → evidence-clock fallback. Never raises, never borrows.

### 5. Failure text — PASS
Evidence is always the matched needle (max needle 21 chars, marker 19) or None, clipped at 80 (:210–213, :217–218) — raw caller text is never returned. `error result: success` is checked only after all four needle tables, so it yields `unclassified`/`label_misleading=True` and is never typed credential/quota/availability/transport (:211–213).

### 6. Tests — PASS
Tests assert concrete states/reasons/values (e.g. tests/…:101–117 pins `failed`+`missing_submission`+kind+evidence+identities; :411–434 pins the superseded behavior: `pending`, boundary packet, not the 06:20 row's). A wrong `missing_submission` mapping or superseded handling fails multiple tests. Weakest test: `test_scheduler_ledger_reason_vocabulary_is_covered` (tests/…:816–833) — its per-reason loop only asserts `state in STATES` (near-tautological); its real value is the set-equality vocabulary guard, and every specific mapping has a dedicated test, so this is not a defect.

### 7. Run — 236 passed / 0 failed
(`tests/test_management_lifecycle.py` + `tests/test_scheduler_decision_outcomes.py` + `tests/test_decision_rows.py`; both pre-existing files are untouched by the diff, result unchanged.)

### 8. R1 fold (`book_status`, commit 2c787cf3) — PASS
Names/nullability match R1_CONTRACT.md: `run_status|last_decision_at|last_attempt_at|next_scheduled_at|failure_reason_code|halted_by` all present and nullable except `run_status`, which is never null — `"unavailable"` is the no-projection state (:96, :571–572). It is decided only by `max` over dated cycles with an outcome (:596–601); `started`, `not_due` (future *and* ledger skips) are absent from `_RUN_STATUS_BY_STATE` and `awaiting_start` is explicitly excluded (:611–616). `failure_reason_code` set only when failed/degraded (:602–604). `halted_by` only from the caller (:605–607), clipped to 80. The fold reads no I/O/clock and does not mutate its input (pinned by tests/…:947–956 and my probe). Adversarials: an older failed cycle listed after a newer ok cycle → `ok` with `failure_reason_code` None in *both* list orders (decided by `due_at`, not order); junk/undated dispositions never decide `run_status` (junk-only input → `unavailable`) — note an undated cycle's `started_at` may still surface in `last_attempt_at`, an aggregation field R1 does not constrain.

Two packet-unspecified edges examined and judged non-defects: ledger `executed` with no matched row → `accepted_change`/`settled` (:530–537) — the packet enumerates only row-executed and still-queued sub-cases; the module echoes the ledger's own completed claim and never claims `accepted_no_change` without a proven zero-fill row; reachable only under double record loss (in-session execution always writes both boundary and row). And `_was_superseded` stays False when no brain run id is known — "a DIFFERENT run_id" is undefined then, and the docstring documents the refusal to guess.

```
RETURN RV-L-R3
head: 2c787cf36f3866f9bb710c988db60a6418183d55
checklist: 1=PASS 2=PASS 3=PASS 4=PASS 5=PASS 6=PASS 7=236 passed/0 failed 8=PASS
findings: none
judgment calls: 1=acceptable — the packet itself mandates the key names "settlement"/"settled", so a literal substring ban on "settle" is self-contradictory; the word-boundary/settle_/.settle regex (tests:737) still bans the settle job functions/imports while allowing the required vocabulary. 2=acceptable — uncertain reasons ordered before the rejected_*/frozen_* bucket: packet line 82 states those reasons map to incomplete_uncertain unconditionally, and _brain_job_outcome never emits them with status warn, so no reachable record distinguishes the orderings. 3=acceptable — that bucket requiring status "warn" is the packet's own text ("(status warn)"); prefixed targets reaching status error are exactly the ones handled earlier (missing_submission, rejected_execution_error), and projection_failed+rejected_* target (error) correctly lands uncertain. 4=acceptable — missing_due_at: the packet's mapping assumes a parseable due_at; degrading to incomplete_uncertain with a named reason instead of raising honors the never-raises/never-invents contract (same for carrying brain_run_id/packet_id/asof from a window-matched row: fill-only-when-unset implements "refined by the matched decision row" without ever overwriting boundary identity).
VERDICT: PASS
```
