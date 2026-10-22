# Lane L-R1 — CN/HK manager failure-chain census (class census, C1)

You are a bounded Fabric worker for the Mastermind repository (a paper-only US/China/HK portfolio bot).
Your working tree is the current directory (a detached checkout of `origin/master` 230e9a301). Git history is available
(`git show <sha>:<path>`). Input data is in `~/lanes/tmp/pbr-rt-lr1/aux/` (already trimmed and secret-scanned).
You write exactly ONE new file and nothing else:
`research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/FAILURE_CHAIN.md`.
Do not edit source, do not run the bot, do not open network connections, do not commit or push.

## Inputs (all under ~/lanes/tmp/pbr-rt-lr1/aux/)
- `attempts.tsv` / `attempts.jsonl` — one row per brain run (`run_id`), books autonomous(=US)/china/hk, 2026-10-09 → 10-22:
  key_id, backend, provider_label, latency_ms, first assistant text, sdk_error, target_status, decision_effective, executed_n.
- `decisions_trimmed.jsonl` — the per-book decision log rows (ONE row per `asof`: a later substantive run for the same asof
  replaces the earlier row — see `bot/decision_rows.py::replace_for_asof`).
- `run_events_all_jobs.jsonl` — scheduler run ledger (`run_started`/`run_finished` with `extra.run_id`, `extra.target_status`,
  `extra.reason`; `app_started` with `extra.git_sha`; `packet_accepted` with the brain run id). Flags stripped.
- `runlogs_trimmed/<brain_run_id>.jsonl` — per-run reasoning log excerpts (the assistant text carries provider banners).
- `sdk_0.2.110_vps_excerpt.txt` — the installed claude-agent-sdk 0.2.110 code that builds the terminal error message.
- `journal_manager_provider_redacted.log` — systemd journal excerpt (retention starts 10-21).

## Facts you may rely on (verified by the orchestrator; cite them as "orchestrator-verified")
- Installed code windows: 732cf7be 10-09 01:03 → 10-20 10:54; fe7afd01 → 10-21 12:40; 7ab47f0b → 15:32; ff16c192 since 10-21 15:32.
  `git diff 732cf7be fe7afd01` changes none of the provider files, so all failures through 10-21 09:00 ran 732cf7be provider code.
- The failing code path (read it yourself at 732cf7be): `brain/cli_bridge.py::_via_sdk` → SDK raises
  `Exception('Claude Code returned an error result: success')`; `_reason` except-path calls `brain/key_rotor.py::classify_failure`
  which deliberately returns None for that text (see `tests/test_key_rotor.py`); `brain/provider_waterfall.py::reason` then
  returns at the first oauth rung because the error is neither "all pool keys cooling/dead" nor a `_failure_kind`.
- SDK 0.2.110 `query.py`: `self._last_error_result_text = "; ".join(errors) or str(message.get("subtype","unknown error"))`
  — a ResultMessage with `is_error=True`, empty `errors` and subtype `"success"` yields the literal "error result: success".
  `types.py` defines `AssistantMessage.error: Literal["authentication_failed","billing_error","rate_limit","invalid_request",
  "server_error","unknown"] | None`; `cli_bridge._via_sdk` never reads it.

## Taxonomy (MASTERPLAN §10.1) — classify every failed attempt into exactly one
credential/availability · quota · transport · tool contract · schema · stale evidence · deadline · application error ·
incomplete/no-record (due cycle with no complete record). Classify from the run-log banner text when present
(e.g. "401 OAuth access token has been revoked" ⇒ credential; "You've hit your weekly limit" ⇒ quota). Where only the SDK
"success" text exists, say "unclassified (label misleading)".

## Required content of FAILURE_CHAIN.md
1. **Per-attempt table, CN and HK, 2026-10-10 → 10-21** (every due weekday cycle: china_daily 08:00Z, hk_daily 09:00Z, plus any
   manual/overnight attempt), columns: date · book · scheduler run_id · brain run_id · key slot · backend · latency_ms ·
   banner (≤90 chars) · target_status · class · installed code window. Weekends: list as not due. Include 10-16 (runlog
   created 08:00:25 with 0 bytes, no run_started/finished, no 08:30 app_started that day) and say exactly what is and is not
   known.
2. **US table, same window**, same columns (autonomous_daily 23:10Z + watch_us_overnight re-decides that produced a run).
3. **Origin of "error result: success"**: the exact code path (file:line at 732cf7be and at ff16c192) and why the word
   "success" appears (SDK subtype fallback), plus why the waterfall never tried another rung and why the same slot stayed first.
4. **Classification counts** per book.
5. **What the US resumed path shows** (10-21 23:10, 10-22 02:20, 06:20): which key slot, backend, code window; whether it used
   the same `_via_sdk` path; that the 02:20 run's decision row was superseded by the 06:20 row for the same asof (identity loss
   in `decisions.jsonl`; the `packet_accepted` run_event still names it).
6. **Carrier claims** (do not verify; report as claims): the renewal carrier #1357 recorded a revoked OAuth token and missing
   Codex authentication. State which observations in the data are consistent with them (no `codex` backend appears in any
   attempt) and which are not provable from this data.
7. **Uncertainties** — list each with what evidence would resolve it.

Report only what the data shows. Never print any credential, token, email address or key material.

## Final message
End with a RETURN block (this is your last message; emit the full RETURN block as your last message):
```
RETURN L-R1
file: research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/FAILURE_CHAIN.md (<lines> lines)
cn_attempts: <n> · hk_attempts: <n> · us_attempts: <n>
counts: <class=n, ...> per book
origin: <one sentence>
uncertainties: <n> listed
```
