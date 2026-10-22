# Lane L-R3 — read-only manager-cycle lifecycle disposition projection (class build, C2)

You are a bounded Fabric worker in the Mastermind repository (paper-only portfolio bot). Your working tree is the current
directory, a detached checkout of `origin/master`. You create exactly TWO new files and edit nothing else:
- `brain/management_lifecycle.py`
- `tests/test_management_lifecycle.py`
Do not commit, push, run the bot, open network connections, or touch any other file.

## Why
A manager cycle (one scheduled portfolio decision for one book on one day) currently has its truth spread over three
existing records. Operators cannot answer "what happened to today's CN/HK/US decision" from one place, and on 2026-10-16 a
cycle vanished with no record at all. You build a PURE, READ-ONLY projection that derives one disposition per cycle from the
existing records. It is NOT a second state machine: it stores nothing, writes nothing, schedules nothing, and must never be
read by retry, failover, scheduling or submission code.

## The three existing records (read these files to confirm field names; do not modify them)
1. Scheduler run ledger (`control_plane/run_ledger.py`, written by `app/scheduler.py::_ledger_start/_ledger_end`):
   - `{"kind":"run_started","job":"china_daily","book":"china","ts":ISO,"status":"ok","extra":{"run_id":"2026-10-20_08-00-00_dcda4618","trigger":"cron",...}}`
   - `{"kind":"run_finished","job":...,"book":...,"ts":ISO,"status":"ok|error|skip|warn","severity":"FREEZE|ADVISORY_ONLY"|absent,
      "extra":{"run_id":<same>,"target_status":...,"reason":...,"elapsed_s":float}}`
   - The exception path ends with status "error" and NO `target_status`/`reason`.
   - Lock held: `{"kind":"run_skipped","job":...,"book":...,"status":"lock_held"}` and no run_started.
   - `status`/`reason` vocabulary comes from `app/scheduler.py::_brain_job_outcome` — read it: reasons
     invalid_result, projection_failed, cost_capped, legacy_etf_migration_pending, market_closed, nothing_queued,
     runner_failed, settlement_finalization_incomplete, inconsistent_result, missing_submission,
     rejected_execution_error, and other `rejected_*` / `frozen_*` target statuses (warn).
2. Submission boundary event (same run_events stream): `{"kind":"packet_accepted","job":"","book":"autonomous","ts":ISO,
   "step":"submission_boundary","extra":{"run_id":"2026-10-21T23-10-44-493Z00-00","packet_id":"74797d0d21985a73","asof":"2026-10-21"}}`
   — note the BRAIN run id format differs from the scheduler run id.
3. Per-book decision row (`bot/decision_rows.py`; ONE row per (book, asof): `replace_for_asof` lets a later substantive run
   for the same asof replace the earlier row): `{"asof","book","decision_effective":bool,"error":str|None,"executed_n":int,
   "holdings_n":int,"packet_id":str|None,"run_id":<brain run id>,"target_status":str,"ts":ISO}`.
   A row's `target_status` may be updated later by settlement (queued → executed).

## API to implement (`brain/management_lifecycle.py`)
```python
SCHEMA = "mastermind.bot.management_cycle_disposition.v1"
STATES = ("not_due","disabled","started","accepted_no_change","accepted_change","rejected","failed","incomplete_uncertain")
def classify_failure_text(text: str | None) -> dict   # display-only; returns {"kind":..., "evidence":..., "label_misleading": bool}
def project_cycle(opportunity: dict, run_events: list[dict], decision_rows: list[dict], *, now: datetime,
                  evidence_text: str | None = None) -> dict
def project_cycles(opportunities: list[dict], run_events, decision_rows, *, now, evidence_by_run_id: dict | None = None) -> list[dict]
```
`opportunity = {"job": "china_daily", "book": "china", "due_at": ISO-or-datetime, "enabled": True,
"start_grace_s": 3600, "finish_deadline_s": 7200}` (grace defaults 3600 = the scheduler's misfire_grace_time;
deadline defaults 7200).

Return dict keys (always present; use None when unknown):
`schema, job, book, due_at, state, reason, failure_kind, failure_evidence, label_misleading, settlement ("settled"|"pending"|None),
scheduler_run_id, brain_run_id, packet_id, asof, decision_row_superseded (bool), overdue (bool), sources (list of the record
kinds actually used, e.g. ["run_started","run_finished","packet_accepted","decision_row"])`.

### Matching (never borrow evidence from another cycle)
- run_started: same `job`, `ts` within [due_at − 60 s, due_at + start_grace_s]; take the earliest.
- run_finished: same `extra.run_id` as that run_started.
- packet_accepted: same `book`, ts within [started.ts, (finished.ts or now) + 60 s]; take the latest → brain_run_id, packet_id, asof.
- decision row: same `book` and `run_id == brain_run_id` when known; otherwise the row whose `ts` is within
  [started.ts, (finished.ts or now) + 60 s]. If no row matches but a row exists for the same book with
  `asof == due_at.date()` (or the packet's asof) and a DIFFERENT run_id, set `decision_row_superseded=True` and do NOT use it.
- run_skipped lock_held within the start window with no run_started → handled below.

### State mapping (first match wins)
1. `enabled` false → `disabled`.
2. `now < due_at` → `not_due`.
3. No run_started: lock_held skip present → `incomplete_uncertain`, reason `skipped_lock_held`;
   else if `now <= due_at + start_grace_s` → `incomplete_uncertain`, reason `awaiting_start`, overdue False;
   else → `incomplete_uncertain`, reason `no_start_record`, overdue True.
4. Started, no run_finished: `now <= started + finish_deadline_s` → `started`; else `incomplete_uncertain`, reason
   `no_finish_record`, overdue True.
5. Finished — use the ledger's `status`/`extra.reason`/`extra.target_status`, refined by the matched decision row:
   - reason `market_closed` / `nothing_queued` / `legacy_etf_migration_pending` with status skip → `not_due`, reason = that reason.
   - reason `cost_capped` → `rejected`, reason `cost_capped`.
   - status ok and target in {queued, executed}: if the row exists and its target_status == "executed" and executed_n == 0
     → `accepted_no_change`, settlement "settled"; if row executed with executed_n > 0 → `accepted_change`, settlement
     "settled"; if row (or ledger) still "queued" → `accepted_change`, settlement "pending"; reason None.
     (Queued means a target was accepted for the next session; whether it changes holdings is unknown until settlement —
     keep it accepted_change/pending, never "no change".)
   - reason `missing_submission` (target `rejected_no_submission`) → `failed`, with `classify_failure_text(evidence_text or row.error)`.
   - reason `rejected_execution_error`, `runner_failed`, `invalid_result`, `inconsistent_result`, or status error with no
     reason (exception path) → `failed`, failure_kind `application`.
   - other `rejected_*` / `frozen_*` (status warn) → `rejected`, reason = the target_status.
   - reason `projection_failed` or `settlement_finalization_incomplete` → `incomplete_uncertain`, reason = that reason.
   - anything else → `incomplete_uncertain`, reason `unrecognized_outcome`.

### classify_failure_text (display only; never used for retry/failover)
Case-insensitive, first match wins:
- credential: "401", "revoked", "authentication_failed", "invalid api key", "unauthorized"
- quota: "weekly limit", "session limit", "usage limit", "rate_limit", "429"
- availability: "all pool keys cooling", "all pool keys dead", "overloaded", "529"
- transport: "timeout", "connection reset", "cliconnectionerror"
- otherwise, if the text contains "error result: success" → kind "unclassified", label_misleading True
  (the SDK reports subtype "success" on an error result; the word is not evidence of success)
- otherwise "unclassified", label_misleading False. `evidence` = the matched needle (never the full text; cap 80 chars).

## Required tests (`tests/test_management_lifecycle.py`) — inline fixtures, no file I/O, no network
Use these REAL record shapes (copied from production logs, identities intact):
- CN 2026-10-20 failed: run_started `2026-10-20T08:00:00+00:00` run_id `2026-10-20_08-00-00_dcda4618` job china_daily book china;
  run_finished `2026-10-20T08:00:39+00:00` status error severity FREEZE extra {reason missing_submission, target_status
  rejected_no_submission, elapsed_s 39.653}; decision row {asof 2026-10-20, book china, decision_effective false,
  error "Exception('Claude Code returned an error result: success')", executed_n 0, holdings_n 0, packet_id null,
  run_id "2026-10-20T08-00-19-590Z00-00", target_status rejected_no_submission, ts 2026-10-20T08:00:28.656800+00:00}.
  Expect: failed, failure_kind "unclassified", label_misleading True; with
  evidence_text "API Error: 401 OAuth access token has been revoked" → failure_kind "credential".
- HK 2026-10-15 failed (quota): run_started 09:00:00 run_id `2026-10-15_09-00-00_a385895c` job hk_daily; run_finished
  09:00:31 error FREEZE {missing_submission, rejected_no_submission, 31.235}; row run_id "2026-10-15T09-00-08-208Z00-00",
  ts 09:00:17.762658, same error string; evidence_text "You've hit your weekly limit · resets Oct 18, 7pm (UTC)"
  → failed, failure_kind "quota".
- US 2026-10-21 accepted, settlement pending: run_started `2026-10-21T23:10:00+00:00` run_id `2026-10-21_23-10-00_0b07978c`
  job autonomous_daily book autonomous; packet_accepted `2026-10-21T23:16:43+00:00` extra {run_id
  "2026-10-21T23-10-44-493Z00-00", packet_id "74797d0d21985a73", asof "2026-10-21"}; run_finished 23:17:08 status ok
  extra {target_status queued, elapsed_s 427.854}; row {asof 2026-10-21, book autonomous, decision_effective true,
  executed_n 0, run_id "2026-10-21T23-10-44-493Z00-00", target_status queued, packet_id "74797d0d21985a73",
  ts 2026-10-21T23:16:44.958859+00:00} → accepted_change, settlement pending, brain_run_id and packet_id carried,
  scheduler_run_id carried, both identities distinct.
- US 2026-10-09 accepted, settled, no change: run_started 23:10:00 run_id `2026-10-09_23-10-00_5acbb577`; packet_accepted
  23:13:46 {run_id "2026-10-09T23-10-09-296Z00-00", packet_id "e1c73675fa814c68", asof "2026-10-09"}; run_finished 23:14:04
  ok {target_status queued, elapsed_s 244.623}; row {target_status executed, executed_n 0, holdings_n 4, decision_effective
  true, run_id "2026-10-09T23-10-09-296Z00-00", ts 2026-10-09T23:13:48.513977+00:00} → accepted_no_change, settled.
- Accepted change (synthetic, same shape): row target_status executed, executed_n 3 → accepted_change, settled.
- 2026-10-16 vanished cycle: china_daily due `2026-10-16T08:00:00+00:00`, no events at all, now 2026-10-16T12:00Z
  → incomplete_uncertain, no_start_record, overdue True; now 2026-10-16T08:30Z → awaiting_start, overdue False.
- Superseded row: autonomous asof 2026-10-22 — a packet_accepted at 02:23:26 for brain run "2026-10-22T02-20-43-426Z00-00"
  exists, but the only decision row is run_id "2026-10-22T06-20-17-535Z00-00" (ts 06:23:03.763904). A cycle whose matched
  brain run is the 02:20 one must report decision_row_superseded True and must NOT take the 06:20 row's status/packet.
- Started not finished (before and after deadline); disabled; not_due; lock_held skip; market_closed skip → not_due;
  cost_capped → rejected; rejected_lesson_citations warn → rejected; exception path (status error, no reason) → failed
  application; projection_failed → incomplete_uncertain.
- Purity: inputs are not mutated (deep-copy compare); calling twice yields equal output.
- Not a state machine / no effects: read the module source text and assert it contains none of `open(`, `.write(`,
  `json.dump`, `append(` on a file path, `import app.scheduler`, `apscheduler`, `settle`, `paper_account`, `subprocess`.
- Vocabulary drift guard: assert `{"executed","queued"}` equals `brain.decision_submission.ACCEPTED_TARGET_STATUSES`
  (import inside the test only; the module itself must not import brain.decision_submission).
- `project_cycles` returns one row per opportunity in order; every row has exactly the documented keys and `state in STATES`.

## Run
`mkdir -p ~/lanes/tmp/pytest && PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q tests/test_management_lifecycle.py`
(fall back to `python3` if the venv python is missing). All tests must pass. Also run
`... -q tests/test_scheduler_decision_outcomes.py` and report its result unchanged.

## Final message
Emit the full RETURN block as your last message:
```
RETURN L-R3
files: brain/management_lifecycle.py (<lines>), tests/test_management_lifecycle.py (<lines>)
tests: <n passed / n failed> management_lifecycle; scheduler_decision_outcomes <result>
states covered: <list>
deviations from packet: <none | list>
```
