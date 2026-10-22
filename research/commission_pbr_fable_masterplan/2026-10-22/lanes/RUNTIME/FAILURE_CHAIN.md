# L-R1 — CN/HK manager failure-chain census, 2026-10-10 → 2026-10-21

Bounded Fabric worker L-R1 (class census, C1), paper-only portfolio bot. Read-only analysis;
no source, bot run, network, or git write performed.

**Inputs** (`~/lanes/tmp/pbr-rt-lr1/aux/`): `attempts.tsv` (32 brain-run rows, 10-09→10-22),
`run_events_all_jobs.jsonl` (scheduler ledger), `decisions_trimmed.jsonl` (one row per
`asof`×book after `replace_for_asof`, `bot/decision_rows.py:287-299` at 732cf7be),
`runlogs_trimmed/*.jsonl` (32 files, one 0 bytes), `sdk_0.2.110_vps_excerpt.txt`,
`journal_manager_provider_redacted.log` (systemd retention starts 10-21 12:40).

**Method / joins.** "Banner" = first `assistant text` step in the run log. Scheduler-run ↔
brain-run linkage for *failed* attempts is inferred by job name + time adjacency (the failed
runs emit no `packet_accepted`; successful runs are linked directly by `packet_accepted.extra.run_id`);
the linkage is exact for the three successful in-window attempts. All in-window scheduler events
carry `trigger=cron` — no manual/http-triggered book runs appear in the ledger. Key slot column
is the non-secret `key_id` string (`claude_code_oauth_N`), per the key_rotor redline. No token,
email, or key material appears anywhere in this file or the inputs.

**Installed code windows** (orchestrator-verified; app_started ledger confirms):
732cf7be 10-09 01:03 → 10-20 10:54 · fe7afd01 → 10-21 12:40 · 7ab47f0b → 15:32 · ff16c192 since
10-21 15:32. `git diff 732cf7be fe7afd01` changes no provider files (orchestrator-verified), so
every failure below ran 732cf7be-equivalent provider code. I verified independently that ff16c192
*does* change provider files but preserves the failure path bit-for-bit in behaviour (§3).

**Baseline note:** the last successes before the outage are the 2026-10-09 runs (7 brain runs,
all `backend=sdk`, all submitted/executed or queued). 10-10 Sat, 10-11 Sun, 10-17 Sat, 10-18 Sun:
**not due** — `china_daily`/`hk_daily`/`autonomous_daily` are Mon–Fri jobs (registered Mon–Fri,
`app/scheduler.py`); the ledger shows only 08:30 restarts (+ weekly jobs on 10-11/10-18) and zero
book attempts on those days.

---

## 1. Per-attempt table — CN and HK, every due weekday cycle

Manual/overnight extras: none produced a CN/HK brain run in-window. `watch_asia_overnight`
(00:20/14:20/20:20) fired most days but finished in ~0 s with `artifacts=[]` and no
`packet_accepted`; no CN/HK brain run exists outside the 08:00/09:00 slots.

| date | book | scheduler run_id | brain run_id | key slot | backend | latency_ms | banner (≤90 ch) | target_status | class | code window |
|---|---|---|---|---|---|---|---|---|---|---|
| 10-12 Mon | china | 2026-10-12_08-00-00_89c54934 | 2026-10-12T08-00-15-434Z00-00 | claude_code_oauth_2 | none | 8,099 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission (reason=missing_submission) | credential/availability | 732cf7be |
| 10-12 Mon | hk | 2026-10-12_09-00-00_e1783428 | 2026-10-12T09-00-08-738Z00-00 | claude_code_oauth_2 | none | 7,482 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-13 Tue | china | 2026-10-13_08-00-00_76ffd685 | 2026-10-13T08-00-17-481Z00-00 | claude_code_oauth_2 | none | 7,334 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-13 Tue | hk | 2026-10-13_09-00-00_0c228094 | 2026-10-13T09-00-08-574Z00-00 | claude_code_oauth_2 | none | 6,538 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-14 Wed | china | 2026-10-14_08-00-00_cfd9a859 | 2026-10-14T08-00-18-824Z00-00 | claude_code_oauth_2 | none | 6,071 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-14 Wed | hk | 2026-10-14_09-00-00_3e77b007 | 2026-10-14T09-00-08-408Z00-00 | claude_code_oauth_2 | none | 8,891 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-15 Thu | china | 2026-10-15_08-00-00_45dce2f3 | 2026-10-15T08-00-18-249Z00-00 | claude_code_oauth_3 | none | 4,536 | You've hit your weekly limit · resets Oct 18, 7pm (UTC) | rejected_no_submission | quota | 732cf7be |
| 10-15 Thu | hk | 2026-10-15_09-00-00_a385895c | 2026-10-15T09-00-08-208Z00-00 | claude_code_oauth_3 | none | 5,778 | You've hit your weekly limit · resets Oct 18, 7pm (UTC) | rejected_no_submission | quota | 732cf7be |
| 10-16 Fri | china | **— no run_started, no run_finished** | 2026-10-16T08-00-25-646Z00-00 (0-byte runlog) | unknown | unknown | — | *(log empty — no banner, no sdk_error)* | none recorded | incomplete/no-record | 732cf7be (by date) |
| 10-16 Fri | hk | **— no run_started, no run_finished** | **no brain run at all** (no runlog file) | — | — | — | — | none recorded | incomplete/no-record | 732cf7be (by date) |
| 10-19 Mon | china | 2026-10-19_08-00-00_8fac5508 | 2026-10-19T08-00-16-366Z00-00 | claude_code_oauth_2 | none | 10,045 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-19 Mon | hk | 2026-10-19_09-00-00_4077eac5 | 2026-10-19T09-00-18-762Z00-00 | claude_code_oauth_2 | none | 14,724 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-20 Tue | china | 2026-10-20_08-00-00_dcda4618 | 2026-10-20T08-00-19-590Z00-00 | claude_code_oauth_2 | none | 6,876 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-20 Tue | hk | 2026-10-20_09-00-00_e0ae7143 | 2026-10-20T09-00-19-302Z00-00 | claude_code_oauth_2 | none | 10,008 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-21 Wed | china | 2026-10-21_08-00-00_6a440e79 | 2026-10-21T08-00-40-070Z00-00 | claude_code_oauth_2 | none | 16,035 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | fe7afd01 (provider files identical to 732cf7be — orchestrator-verified) |
| 10-21 Wed | hk | 2026-10-21_09-00-00_7cce8eed | 2026-10-21T09-00-26-194Z00-00 | claude_code_oauth_2 | none | 11,152 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | fe7afd01 (identical provider files) |

Every "rejected_no_submission" row above was recorded by the scheduler as
`status=error, severity=FREEZE, reason=missing_submission`
(`app/scheduler.py:111-112` at 732cf7be maps target `rejected_no_submission` → error/FREEZE/missing_submission),
and every such run also wrote a barren decision row (`decision_effective=false`,
`target_status=rejected_no_submission`, `error="Exception('Claude Code returned an error result: success')"`,
`holdings_n=0`) — the asof row for those days is a failure stub, not a decision.

### 2026-10-16 — exactly what is and is not known

**Known (direct records):** a runlog path `data/brain/runs/2026-10-16T08-00-25-646Z00-00.jsonl`
exists and is **0 bytes**. The id's format is `runlog.start_run`'s clock stamp
(`brain/runlog.py:46-56` at 732cf7be), so *some* process allocated a brain run id at 08:00:25.646 —
25 s after the 08:00Z china slot. But `start_run` writes a `_meta` line at allocation
(same function, line 55); a 0-byte file means the process died at or before its very first write.
The ledger records **nothing** that day between 06:20:00 (`watch_us_overnight` finished normally)
and 22:35:00 (`daily_mark` started): no `run_started`/`run_finished` for china_daily or hk_daily,
no 08:30 app restart (every other day 10-10→10-20 has one), and also no 11:20 watch_us,
14:20 watch_asia, 15:00 settle_pending, 15:05 portfolio_risk, 20:20 watch_asia. There is no 09:00
hk runlog file at all — the hk cycle never even allocated a run id. No china/hk decision row
exists for asof 2026-10-16. That evening the scheduler logged events again normally, and the
23:10 US attempt crashed differently (section 2).

**Not known:** whether the 08:00 launch came through the normal `china_daily` wrapper (the
`run_started` append is best-effort and never raises, `control_plane/run_ledger.py:141-146`, so a
silently-failed append cannot be excluded — but that would not explain the missing 09:00/11:20/
14:20/15:00/15:05/20:20 events *and* the missing 08:30 restart); which key/backend the 08:00
attempt would have used; why hk allocated no run id; whether the service paused, hung, was
SIGSTOPped, or the host stalled — systemd journal retention starts 10-21, so this dataset holds
no journal coverage of 10-16. Classified **incomplete/no-record** for both books.

## 2. US table (autonomous) — same window, 23:10Z cycles + overnight re-decides

`watch_us_overnight` produced **no** brain run between 10-10 and 10-21 (every event is a ~0 s
finish with `artifacts=[]`, no `packet_accepted`); the first overnight re-decide that produced a
run is 10-22 02:20 (section 5). Weekends: no US attempts, none due.

| date | book | scheduler run_id | brain run_id | key slot | backend | latency_ms | banner | target_status | class | code window |
|---|---|---|---|---|---|---|---|---|---|---|
| 10-12 Mon | autonomous | 2026-10-12_23-10-00_966836de | 2026-10-12T23-10-28-226Z00-00 | claude_code_oauth_2 | none | 10,094 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-13 Tue | autonomous | 2026-10-13_23-10-00_0f743783 | 2026-10-13T23-10-11-977Z00-00 | claude_code_oauth_2 | none | 5,765 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-14 Wed | autonomous | 2026-10-14_23-10-00_2275b6fb | 2026-10-14T23-10-11-819Z00-00 | claude_code_oauth_2 | none | 5,021 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-15 Thu | autonomous | 2026-10-15_23-10-00_8fdd79e2 | 2026-10-15T23-10-11-457Z00-00 | claude_code_oauth_2 | none | 5,560 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-16 Fri | autonomous | 2026-10-16_23-10-00_06f28da4 | 2026-10-16T23-10-11-128Z00-00 | claude_code_oauth_3 | none | 2,266 | *(no banner — raw ProcessError exit 1; stderr not captured, see U3)* | rejected_no_submission | application error *(see U3)* | 732cf7be |
| 10-19 Mon | autonomous | 2026-10-19_23-10-00_8aef2b80 | 2026-10-19T23-10-23-692Z00-00 | claude_code_oauth_2 | none | 11,860 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | 732cf7be |
| 10-20 Tue | autonomous | 2026-10-20_23-10-00_69d8d9df | 2026-10-20T23-10-08-021Z00-00 | claude_code_oauth_2 | none | 9,399 | Failed to authenticate. API Error: 401 OAuth access token has been revoked. | rejected_no_submission | credential/availability | fe7afd01 (identical provider files) |
| 10-21 Wed | autonomous | 2026-10-21_23-10-00_0b07978c | 2026-10-21T23-10-44-493Z00-00 | claude_code_oauth_3 | sdk | 358,542 | *(success path — no error banner)* | queued (decision_effective, submitted via `mcp__desk__submit_book`) | not a failure | ff16c192 |

Census-label caveat: the attempts census shows `provider_label=openai` on every `backend=none`
row. That is an artifact of the response-ledger provider heuristic — `model` string "opus" starts
with "o" → `openai` unless backend is `sdk`/`cli`/`codex` (`brain/thinking_log.py:183-189` at
732cf7be). No attempt in this census actually used an OpenAI/Codex backend.

## 3. Origin of "Claude Code returned an error result: success"

**The exception string is built inside the installed claude-agent-sdk 0.2.110, not by the bot.**

1. On auth failure the Claude Code CLI streams its assistant text (the 401/quota banner), then
   emits a terminal `result` message with `is_error=True`, an **empty `errors` list**, and
   `subtype` left at `"success"`. The SDK records
   `self._last_error_result_text = "; ".join(errors) or str(message.get("subtype", "unknown error"))`
   → `"success"` (`_internal/query.py` excerpt lines 304-308). The CLI then exits non-zero on
   purpose, and the SDK **replaces** that trailing `ProcessError` with
   `f"Claude Code returned an error result: {self._last_error_result_text}"`
   (excerpt lines 334-348). So "success" is not the outcome — it is the subtype-fallback token of
   an error result whose `errors` array was empty. The word is literally the last field the CLI
   left un-flipped.
2. Bot path at **732cf7be** (`brain/cli_bridge.py`): `_reason` (def line 273) takes the pool
   (`_kr.candidates()`, lines 420-424) and calls `_via_sdk` per candidate (line 446). `_via_sdk`
   (def line 732) iterates `_sdk_query` (line 767); it reads content blocks (lines 773-812) and
   logs the banner as a log-only `assistant text` step (lines 795-800) — **it never reads
   `AssistantMessage.error`**, which SDK `types.py:1025-1031` defines with exactly the values
   this failure needed (`authentication_failed`, `rate_limit`, …; zero references to `msg.error`
   in either 732cf7be or ff16c192 `cli_bridge.py`). The SDK exception then propagates to
   `_reason`'s `except` (line 481). The repr slice `repr(e)[:200]` (line 491) is passed to
   `brain/key_rotor.py::classify_failure` (line 504 → `key_rotor.py:789`), which by design
   returns None: *"The SDK oddity 'Claude Code returned an error result' alone is NOT
   classifiable"* (`key_rotor.py:813-814`; asserted in `tests/test_key_rotor.py:85`). The banner
   that *would* have classified (`401 … revoked` → auth; `weekly limit … resets` → weekly) only
   ever lived in the streamed assistant text, which the raise discards before the result-text
   classifier at lines 451-462 can see it. No `mark_cooling` (`key_rotor.py:286`) is ever called;
   unclassified → else-branch records `base["sdk_error"]` (line 528) and, because book jobs are
   armed (`arm=True`: `bot/china.py:594`, `bot/hk.py:590`, `bot/autonomous.py:654`), returns
   `{ok: False, backend: "none", text: None, error: "Exception('Claude Code returned an error
   result: success')"}` and breaks the key loop (lines 537-542).
3. **Why the waterfall never tried another rung** (`brain/provider_waterfall.py` at 732cf7be):
   `reason()` (line 147) builds rungs (52-87): codex only if `codex_bridge.available()` (59-69 →
   `codex_bridge.py:100-102`: binary **and** `$CODEX_HOME/auth.json`), then OAuth rungs from
   `llm_auth._oauth_pool_candidates` (line 72), stable-sorted by cooling only (line 87). It calls
   `cli_bridge._reason` with a **single** candidate per rung (181-186), and at the oauth rung
   advances only if the error contains `"all pool keys cooling/dead"` (emitted solely when
   cli_bridge's own pool loop exhausts every candidate, `cli_bridge.py:614-621` — impossible with
   a one-candidate list that broke at line 542) **or** `_failure_kind(err)` matches (97-117:
   `access token could not be refreshed`, or Macro's HTTP-shaped auth/rate-limit vocabularies).
   `"Claude Code returned an error result: success"` matches neither → `return result` at line 210.
   One slot tried, one rung returned, zero failovers — confirmed empirically: no runlog in the
   entire window contains a `key rotation` step.
4. **Why the same slot stayed first:** cooling flags and ordering inputs only mutate through
   `mark_cooling` / usage-ledger rows; an attempt that dies this way writes **neither**
   (failures record no `ok` row via `record_session`, `key_rotor.py:246`). With nothing cooling
   and nothing recorded, `provider_rungs` re-derived the same order each day — slot 2 first for
   10-12→10-14 and 10-19→10-21. The visible alternations (oauth_3 first on 10-15 CN/HK and
   10-16 US) cannot be explained by bot-side state, since the ranking lives in the vendored
   Macro `llm_auth._oauth_pool_candidates` (cooling/window-load/weekly-budget inputs; `vendor/macro`
   is a symlink not readable in this checkout) — see U4.
5. **At ff16c192 (current since 10-21 15:32) the same path still exists:** `_via_sdk` def 994,
   stream loop 1037, assistant-text log 1071, still no `msg.error` read; `_reason` except 712,
   repr slice 722, `classify_failure` 735, `sdk_error` 769, armed break 778-783; waterfall
   `reason()` 195, rung loop 217, single-slot oauth call with renamed param
   `_subscription_slots=[candidate]` 229-233, gate `254-258` (`return result` at 258). New
   `brain/sdk_diagnostics` is captured on the raise (`cli_bridge.py:739-747`) but its own comment
   states diagnostics "never become cooling/fallback inputs". A repeat of the same revoked-token
   failure under ff16c192 would therefore again surface as "…error result: success", again
   unclassified, again with no failover. The 10-21 23:10 recovery came from a working credential
   (slot 3), not from this code path being fixed.

## 4. Classification counts (taxonomy MASTERPLAN §10.1), in-window failures

| class | china | hk | autonomous (US) | total |
|---|---|---|---|---|
| credential/availability | 6 | 6 | 6 | 18 |
| quota | 1 | 1 | 0 | 2 |
| transport | 0 | 0 | 0 | 0 |
| tool contract | 0 | 0 | 0 | 0 |
| schema | 0 | 0 | 0 | 0 |
| stale evidence | 0 | 0 | 0 | 0 |
| deadline | 0 | 0 | 0 | 0 |
| application error | 0 | 0 | 1 | 1 |
| incomplete/no-record | 1 | 1 | 0 | 2 |
| **failed cycles total** | **8** | **8** | **7** | **23** |
| successful attempts | 0 | 0 | 1 (10-21 23:10) | 1 |

No row falls into "unclassified (label misleading)": every failed attempt that reached the SDK
exception also has a banner in its runlog, and classification was done from the banner per the
house rule. (Where only "error result: success" existed without a banner, that is exactly what
would have been said; the 10-16 23:10 row has neither banner nor the success string — its
terminal text is the raw `ProcessError`, hence "application error", flagged U3.) CN/HK lost all
8 due cycles each; US lost 7 of 8 and recovered on 10-21.

## 5. What the US resumed path shows

| run | job / scheduler run_id | brain run_id | slot | backend | code window | evidence |
|---|---|---|---|---|---|---|
| 10-21 23:10 | autonomous_daily `2026-10-21_23-10-00_0b07978c` | 2026-10-21T23-10-44-493Z00-00 | claude_code_oauth_3 | sdk | ff16c192 (since 10-21 15:32; journal shows the 15:55:56 restart instance) | 358.5 s, 9 assistant-text steps, tool calls incl. `mcp__desk__submit_book`, `packet_accepted` 23:16:43 asof 10-21, target `queued`, decision row effective (executed_n 0) |
| 10-22 02:20 | watch_us_overnight `2026-10-22_02-20-00_10e4da4f` | 2026-10-22T02-20-43-426Z00-00 | claude_code_oauth_3 | sdk | ff16c192 (15:55:56 instance; next restart 10-22 06:02:22 same sha) | 163.3 s, submitted (`packet_accepted` 02:23:26, asof 2026-10-22) |
| 10-22 06:20 | watch_us_overnight `2026-10-22_06-20-00_a1b5dc92` | 2026-10-22T06-20-17-535Z00-00 | claude_code_oauth_3 | sdk | ff16c192 (06:02:22 instance) | 165.1 s, submitted; `packet_accepted` 06:23:02; decision row target `queued`, effective, executed_n 0 |

All three used the **same `_via_sdk` success path** (`backend=sdk` is recorded only from a
completed `_via_sdk` stream; waterfall single-slot oauth rung under ff16c192's
`_subscription_slots`). Same key slot (oauth_3) throughout; no `codex` backend anywhere in the
census. Notably the recovered US lane ran on the slot whose 10-15 failure was **quota**
(reset promised "Oct 18, 7pm (UTC)"), consistent with oauth_3 never having had the 401-revoked
token that oauth_2 carried; but that inference is bounded by U5.

**Identity loss on 10-22:** both the 02:20 and 06:20 submits were for `asof 2026-10-22`.
`replace_for_asof` (`bot/decision_rows.py:287-299`) persists a later substantive entry for the
same asof **replacing** the earlier row. `decisions_trimmed.jsonl` therefore contains only ONE
2026-10-22 autonomous row — run_id `2026-10-22T06-20-17-535Z00-00`. The 02:20 run's decision
identity survives **only** in the `run_events` ledger (`packet_accepted` 02:23:26 names
`2026-10-22T02-20-43-426Z00-00`, mode shadow) and its runlog. From decisions.jsonl alone, the
02:20 submission never existed.

## 6. Carrier claims (reported, not verified)

Claim per renewal carrier **#1357**: a **revoked OAuth token** and **missing Codex
authentication**.

**Consistent with this data:**
- 18 attempts print the CLI's literal banner "Failed to authenticate. API Error: 401 OAuth
  access token has been revoked." — every single 401 attempt used `claude_code_oauth_2`.
- No `codex` backend or `openai_codex` provider appears in any attempt row (10-09→10-22);
  consistent with the waterfall never prepending a codex rung, which under 732cf7be
  `provider_waterfall.py:59-69` requires `codex_bridge.available()` = binary +
  `$CODEX_HOME/auth.json` (`codex_bridge.py:100-102`). A missing auth file drops the rung
  silently — exactly the shape of the absence seen here.

**Not provable from this data:**
- The renewal act itself — no token material, credential-rotation event, or pre-10-21 journal is
  in scope; the first post-claim success (10-21 23:10) ran on slot 3, whose only recorded 10-15
  failure was a weekly quota that its own banner said reset 10-18 19:00. This census cannot
  distinguish "slot 3 token was renewed" from "slot 3 was never revoked and simply became
  usable again after quota reset" (U5).
- Whether the revocation covered slots beyond oauth_2 (no other slot ever emitted 401).
- Whether Codex auth was missing because the binary was absent, the auth.json was absent, or
  both — `available()` returns a single bool and the ledger records no negative event for a
  skipped rung (U6).

## 7. Uncertainties (each with resolving evidence)

- **U1 — Cause of the 10-16 08:00→22:35 scheduler blackout** (0-byte runlog, no
  china/hk/afternoon-event records, no 08:30 restart, ledger healthy again by 22:35). Resolve:
  systemd journal + `dmesg`/uptime for 10-16 (retention began 10-21, so not in this dataset),
  uvicorn app logs, and the APScheduler in-memory jobstore behaviour with
  `misfire_grace_time=3600, coalesce=True` (`app/scheduler.py:1757`) — a ≥6 h process stall
  explains "no events, then clean resume" better than an append failure alone.
- **U2 — Why the 08:00 runlog is 0 bytes** when `runlog.start_run` writes a `_meta` line at id
  allocation (`brain/runlog.py:46-56`). Resolve: `stat` of the raw VPS file, index.jsonl entry,
  process-exit records — kills between allocation and flush vs a different writer path.
- **U3 — Class of the 10-16 23:10 US attempt.** Raw `ProcessError` exit 1, no preceding error
  result, no banner, stderr never captured. Assigned "application error"; a credential cause
  cannot be excluded or confirmed. Resolve: CLI stderr capture (the message says "Check stderr
  output for details" but the details were not persisted), or the ff16c192 `sdk_diagnostics`
  payloads for comparable crashes (ff16c192 deployed 10-21, after this row).
- **U4 — Why the first-attempt slot alternated oauth_2/oauth_3** (10-15 CN/HK and 10-16 US ran
  slot 3 while 10-12→10-14 and 10-19→10-21 ran slot 2). Bot-side state visible here does not
  change on failures; the ranking inputs are in Macro's vendored `llm_auth._oauth_pool_candidates`
  (cooling/window-load/weekly-budget), unreadable through this checkout's `vendor/macro` symlink.
  Resolve: Macro-side `key_ledger.jsonl` / pool-status artifacts for 10-12→10-21.
- **U5 — What actually restored service at 10-21 23:10** (new token on slot 2? slot 3 healthy
  all along after its 10-18 reset; any role of the 15:32 ff16c192 deploy — whose failure path is
  behaviourally identical, §3.5). Resolve: carrier #1357 artifacts / credential-rotation records;
  not resolvable from bot data.
- **U6 — Codex availability state.** No event names "codex rung skipped"; absence of codex rows
  is consistent-but-not-proof for #1357's claim. Resolve: `$CODEX_HOME` presence check on the
  VPS, or a rung-selection diagnostic.
- **U7 — Scheduler↔brain-run linkage for the 20 failed attempts is temporal (job+time), not
  identity-based** — failed runs emit no `packet_accepted`. The adjacency is tight (every failure
  falls inside exactly one scheduler window ending seconds later), but a resolve exists: record
  the brain run_id inside `run_finished.extra` / artifacts.
- **U8 — Whether macro-side shared-pool cooling fired during the outage** (the bot never cooled
  a key; the shared ledger might have, which could feed the sister-site panel state). Resolve:
  Macro shared ledger 10-12→10-21 (`_mirror_shared_cooling` path, `key_rotor.py:330-342`).

*End of census. Data shown, claims labelled as claims; credentials/tokens/emails never
emitted.*
