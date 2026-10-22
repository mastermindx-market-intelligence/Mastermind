# CR-RT-4 — failover on a typed provider failure (SPEC ONLY · RESERVED to the seat · no behaviour change in wave 1)

Owner: pbr-runtime (W4). Status: specification for the acceptance row. Nothing here is implemented in wave 1; L-R2 ships
typing only (`brain/provider_failure.py` record attached to the waterfall result, never read by the rung loop).

## Current behaviour (origin/master d31aade9, `brain/provider_waterfall.py::reason` L217-263)
- oauth rung: advance only when the error contains `all pool keys cooling/dead` or `_failure_kind(err)` is auth/window/weekly
  (Macro `llm_auth._is_auth_error` / `_is_rate_limit_error`); otherwise **return** (no replay).
- codex rung: advance only when `_failure_kind` is not None.
- 10-12 → 10-21: every CN/HK/US failure carried `Exception('Claude Code returned an error result: success')` (SDK 0.2.110 join
  bug). `_failure_kind` → None, `key_rotor.classify_failure` → None ⇒ the revoked slot `claude_code_oauth_2` was never cooled and
  the waterfall returned at the first oauth rung for 10 days while slot 3 was usable (US recovered on oauth_3 10-21 23:10).

## Proposed rule (for seat decision; one change, three guards)
Advance to the next rung **iff all** hold for the failed attempt's typed record `r = result["provider_failure"]`:
1. `r.kind in {"credential", "quota"}` and `r.source in {"sdk_assistant_error", "api_error_status"}` — i.e. typed from a
   structured SDK field, never from free-text needles alone;
2. `r.tool_activity_observed is False` — explicitly False, recorded by `cli_bridge._via_sdk` before any tool_use/tool_result
   frame; `None` (unknown, e.g. codex rung or a crash before the first frame was recorded) ⇒ **no advance**;
3. no submission evidence for the run: `brain.autonomous_mcp.read_submission(<book>)` is None — the per-book submission file
   that the typed `submit_book` tool writes atomically (`submission_path`, cleared before the run) is absent (RUNTIME family;
   read-only check, nothing is deleted or rewritten to make the guard pass).
Also: cool the failed slot through the existing `key_rotor` cooling path with the typed kind (credential ⇒ dead/auth,
quota ⇒ window/weekly), so the next cycle does not re-select it. Max one advance per rung; the rung list is unchanged.

## Negative tests that must ship with any implementation (fail-closed fences)
| id | input on rung 1 | expected |
|---|---|---|
| N1 | typed credential, `tool_activity_observed=True` | return rung-1 failure; `_reason` called once; no cooling side effect beyond today's |
| N2 | typed credential, `tool_activity_observed=None` | return rung-1 failure (unknown ⇒ no replay) |
| N3 | typed credential, `tool_activity_observed=False`, but a submission file exists for the book | return; no rung 2 |
| N4 | needle-only typing (`source="text_needle"`, e.g. "401" in prose) | return (needles never authorize replay) |
| N5 | `kind="application"` / `"unclassified"` / `"availability"` (other than the existing cooling/dead marker) | return |
| N6 | typed credential, all guards pass, rung 2 also typed credential | rung 2 called once, rung 3 once, … at most len(rungs) calls; final result is the last failure with all attempts recorded |
| N7 | guards pass and rung 2 succeeds | exactly one submission path executed (count `submit_decision` calls = 1 across both rungs via a fake tool server) |
| N8 | SDK diagnostic collector unavailable / raising (`_new_sdk_diagnostic` → None) | identical rung decisions to a healthy collector (diagnostics never change results) |
| P1 | today's control: `all pool keys cooling/dead` | still advances (regression) |

## Acceptance evidence (for the seat's acceptance row)
- Tests above at the implementation PR head, plus `tests/test_provider_waterfall.py`, `tests/test_key_rotor.py`,
  `tests/test_retry_no_duplicate_effect.py` (L-R4) green.
- Independent review lane VERDICT: PASS on that exact head.
- Installed by blob (INSTALL_PROOF_PLAN) and observed on the first natural CN/HK/US cycle after install: either a success or a
  typed failure whose `provider_failures` list shows the advance decision and its reason.

## Why reserved
It changes retry semantics on the submission path (MASTERPLAN W4: replay after typed tools is the one way to duplicate a target).
The typed record makes the decision possible; whether to take it, and in which release, is the seat's.
