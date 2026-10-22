STATUS: COMPLETE

Lane L-R1 census finished. Deliverable written as the single new file `research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/FAILURE_CHAIN.md` (282 lines); `git status` shows nothing else touched, no commits, no network, no bot execution.

What the census found, from the data itself:
- **CN and HK lost all 8 due weekday cycles (10-12→10-21)**, US lost 7 of 8. 18 of the 21 recorded failures carry a classifiable banner in their runlog: 6+6+6 "401 OAuth access token has been revoked" (credential/availability, every one on slot `claude_code_oauth_2`), 1+1 "You've hit your weekly limit · resets Oct 18, 7pm (UTC)" (quota, slot 3, 10-15). US 10-16 23:10 is the lone banner-less raw `ProcessError` exit-1 (application error, U3). 10-16 morning: china has a 0-byte runlog (run id allocated 08:00:25, no first write, no scheduler events 06:20→22:35, no 08:30 restart, no journal coverage due to 10-21 retention) and hk has no trace at all — both classified incomplete/no-record with an explicit known/not-known section.
- **Origin of "error result: success"**: built in claude-agent-sdk 0.2.110 (`query.py` — `"; ".join(errors) or str(subtype)` with empty `errors` and `subtype="success"`, then the deliberate ProcessError replacement), surfaced at `brain/cli_bridge.py:446/481/504` (732cf7be) where `classify_failure` refuses the bare SDK oddity (`key_rotor.py:813-814`, asserted `test_key_rotor.py:85`), so no `mark_cooling`, the armed run returns `backend=none` at `cli_bridge.py:537-542`, and the waterfall returns at the first oauth rung (`provider_waterfall.py:206-210`) because the error matches neither "all pool keys cooling/dead" nor `_failure_kind`. I verified line-by-line that ff16c192 preserves the identical failure path (its `sdk_diagnostics` is explicitly not a cooling/fallback input) and that `AssistantMessage.error` is still never read.
- **US resumed path**: 10-21 23:10, 10-22 02:20 and 06:20 all succeeded on slot `oauth_3`, `backend=sdk` (same `_via_sdk`), under ff16c192; the 02:20 submission's decision row was superseded by the 06:20 row for the same asof via `replace_for_asof` (`decision_rows.py:287-299`) — identity survives only in `packet_accepted` (02:23:26).
- Carrier #1357 claims reported as claims with the consistent/not-provable split; 8 uncertainties each name its resolving evidence. No credential/token/email/key material appears anywhere.

```
RETURN L-R1
file: research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/FAILURE_CHAIN.md (282 lines)
cn_attempts: 8 (7 recorded + 1 no-record) · hk_attempts: 7 recorded (+1 due cycle, no trace) · us_attempts: 8 (7 failed + 1 success)
counts: china: credential/availability=6, quota=1, incomplete/no-record=1; hk: credential/availability=6, quota=1, incomplete/no-record=1; us: credential/availability=6, application_error=1, incomplete/no-record=0 (+1 success)
origin: SDK 0.2.110 replaces the CLI's trailing exit-1 ProcessError with "Claude Code returned an error result: <errors or subtype>" where an error ResultMessage with empty errors and subtype "success" yields the literal word "success"; cli_bridge never reads AssistantMessage.error so key_rotor.classify_failure returns None by design, nothing is cooled, and provider_waterfall returns at the first oauth rung because the string matches neither "all pool keys cooling/dead" nor _failure_kind — so one slot was retried daily with no failover, at 732cf7be and unchanged in behaviour at ff16c192.
uncertainties: 8 listed
```
