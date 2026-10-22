# Lane L-R2 — typed provider-failure record (replaces the success-labelled error terminal as evidence) (class build, C2)

You are a bounded Fabric worker in the Mastermind repository (paper-only portfolio bot). Your working tree is the current
directory, a detached checkout of `origin/master`. You may create/edit ONLY these files and must edit nothing else:
- NEW `brain/provider_failure.py`
- NEW `tests/test_provider_failure_typing.py`
- NEW `tests/test_thinking_log_provider_label.py`
- `brain/cli_bridge.py` — ONLY `_via_sdk` (new side-channel param) and the SDK candidate loop in `_reason` (attach evidence), as specified
- `brain/provider_waterfall.py` — ONLY `reason()` (attach the typed record), as specified
- `bot/autonomous.py`, `bot/china.py`, `bot/hk.py` — ONLY one added key in the `entry` dict of `_append_decision_log`
- `brain/thinking_log.py` — ONLY the `provider = ...` label expression in `build_row`
- `tests/test_key_rotor.py` — ONLY add `failure_out=None` to the parameter list of the local `_fake_via_sdk` (~line 496); no other change
Do not commit, push, run the bot, open network connections, read or print any credential, or touch any other file.

## Why (production evidence, 2026-10-10 → 10-21, CN/HK/US books)
The Claude Agent SDK (0.2.110) handles a CLI result with `is_error=True` by joining `errors` (empty) or falling back to
`str(subtype)`; the subtype is `"success"`, so it raises `Exception("Claude Code returned an error result: success")`.
The real cause was carried one message EARLIER, on the SDK `AssistantMessage`: its `error` attribute was the literal
`"authentication_failed"` and its text was `"Failed to authenticate. API Error: 401 OAuth access token has been revoked."`.
`brain/cli_bridge.py::_via_sdk` ignores `AssistantMessage.error`, so every failed manager cycle recorded only
`error = "Exception('Claude Code returned an error result: success')"` — a label that reads as success and carries no cause.
Your job: TYPE the failure (credential / quota / availability / ...) from evidence the handler already sees, and carry that
typed record next to the unchanged legacy `error` string. This is EVIDENCE ONLY.

## Hard invariants (a reviewer will check each one; violating any fails the lane)
1. `ok`, `text`, `error`, `backend`, `key_id`, `tools_used`, `provider`, `provider_attempts` values are byte-identical to today
   for every path. You only ADD keys.
2. No change to: which provider/candidate is invoked, how many times, key cooling (`_kr.classify_failure`/`mark_cooling`
   inputs and calls), the `continue`/`break`/`return` decisions in `_reason` and `provider_waterfall.reason`, the subprocess
   fallback, auth handling, env handling, prompt/options. The typed record must NEVER be read by any retry, failover,
   cooling or submission decision. (Failover-on-typed-failure is a reserved seat decision, not this lane.)
3. Never store response text, prompt text, exception repr, stderr, tokens or credential material in the typed record or the
   evidence box. Evidence is: one allowlisted literal, small ints/bools, a bounded subtype word, and at most an 80-char needle
   that you matched (never the surrounding text).
4. Diagnostics on/off equality must still hold: `tests/test_sdk_diagnostic_bridge.py::test_diagnostics_preserve_all_legacy_control_and_result_fields`
   and `tests/test_sdk_generation_compatibility.py` run `_reason` with `_new_sdk_diagnostic`/`_record_sdk_diagnostic` patched
   to `None` and require equal results. Therefore capture evidence in the HANDLER (`_via_sdk`), never via `brain/sdk_diagnostics.py`
   (do not edit that module).

## 1. `brain/provider_failure.py` (new, pure: no I/O, no logging, no imports from brain/, bot/, app/)
```python
SCHEMA = "mastermind.bot.provider_failure.v1"
KINDS = ("credential", "quota", "availability", "transport", "tool_contract", "schema",
         "stale_evidence", "deadline", "application", "unclassified")
SDK_ASSISTANT_ERRORS = {            # the SDK's AssistantMessageError literal set — exact strings
    "authentication_failed": "credential", "billing_error": "quota", "rate_limit": "quota",
    "server_error": "availability", "invalid_request": "schema", "unknown": "unclassified"}
def sdk_assistant_error_literal(value) -> str | None   # value if it is a str exactly in SDK_ASSISTANT_ERRORS, else None
def classify(*, error=None, evidence=None, provider=None, key_id=None, tools_used=None) -> dict
```
`classify` returns exactly these keys (always present):
`schema, kind, evidence, source, sdk_assistant_error, sdk_result_subtype, sdk_result_is_error, api_error_status,
label_misleading, tool_activity_observed, provider, key_id`.

Rules — `evidence` is the dict from `provider_failure_evidence` (may be None/non-dict → treat as `{}`); `error` is any
object (use `str(error)` when not None, else `""`); first match wins:
1. `evidence["assistant_error"]` is a known literal other than `"unknown"` → kind from the map,
   evidence `"sdk_assistant_error:<literal>"`, source `"sdk_assistant_error"`.
2. `evidence["api_error_status"]` is an `int` (not bool): 401/403 → credential, 429 → quota, 500/502/503/529 → availability,
   400 → schema; evidence `"api_error_status:<n>"`, source `"api_error_status"`. Other ints fall through.
3. `evidence["result_subtype"] == "error_max_turns"` → deadline, source `"sdk_result_subtype"`, evidence `"sdk_result_subtype:error_max_turns"`.
4. Needles over the lowercased error text, groups in this order (numeric needles must match on word boundaries, e.g.
   regex `\b401\b`, so "4012" does not match):
   - credential: `401`, `revoked`, `authentication_failed`, `failed to authenticate`, `invalid api key`, `unauthorized`,
     `access token could not be refreshed`
   - quota: `weekly limit`, `session limit`, `usage limit`, `rate_limit`, `rate limit`, `429`
   - availability: `all pool keys cooling`, `all pool keys dead`, `overloaded`, `529`,
     `no shared codex or claude oauth provider is available`, `shared provider waterfall exhausted`
   - transport: `timeout`, `timed out`, `connection reset`, `cliconnectionerror`
   - tool_contract: `failed write tool call`
   → kind = group, evidence = the needle (≤80 chars), source `"error_text"`.
5. Otherwise kind `"unclassified"`, evidence None, source None.
`label_misleading` (independent of kind) = `"error result: success"` in the lowercased error text, OR
(`evidence.result_is_error is True` and `evidence.result_subtype == "success"`).
`sdk_assistant_error` = the literal (incl. "unknown") or None. `sdk_result_subtype` = evidence value if a str matching
`^[a-z_]{1,40}$` else None. `sdk_result_is_error` = evidence value if a bool else None. `api_error_status` = int or None.
`tool_activity_observed` = `evidence["tool_activity_observed"]` if it is a bool; else True if `tools_used` is a non-empty
list; else None. `provider`/`key_id` = the arguments when str, else None. Never raises (wrap the body; on an internal
error return kind "unclassified" with every other optional field None).

## 2. `brain/cli_bridge.py` (narrow)
a. `_via_sdk`: add keyword parameter `failure_out: dict | None = None` (after `thinking_out`, before `before_provider_start`;
   all existing parameters keep their order and defaults). Document it in the docstring as a LOG/EVIDENCE side channel like
   `thinking_out`. It must be written INCREMENTALLY inside the loop (not only at the end), because the SDK raises after the
   evidence was seen and the exception must still leave the box filled:
   - immediately after `_require_provider_start(before_provider_start)` succeeds: if `failure_out is not None`, set
     `failure_out["tool_activity_observed"] = False`.
   - on an AssistantMessage (the `hasattr(msg, "content")` branch): `lit = provider_failure.sdk_assistant_error_literal(getattr(msg, "error", None))`;
     if `lit` and the box is not None → `failure_out["assistant_error"] = lit` (latest wins).
   - on a `tool_use` block or a tool-result message → `failure_out["tool_activity_observed"] = True`.
   - on a ResultMessage: record `result_is_error` (only if `getattr(msg,"is_error",None)` is a bool), `result_subtype`
     (only if a str matching `^[a-z_]{1,40}$`), `api_error_status` (only if `getattr(msg,"api_error_status",None)` is an int
     and not a bool).
   - Every write is guarded so that a failure to record never changes control flow (wrap in `try/except Exception: pass`).
   - Do not change the return dict of `_via_sdk`.
b. `_reason` SDK candidate loop: next to `_think_box`, create `_failure_box: dict = {}` and `.clear()` it per candidate
   exactly where `_think_box.clear()` happens at the top of the loop. Pass `failure_out=_failure_box` to `_via_sdk`
   UNCONDITIONALLY (keep the existing `**({"_diagnostic": ...})` and `**_veto_kw` expansions as they are). Then attach
   `"provider_failure_evidence": dict(_failure_box)` (a copy) to the result ONLY on these two existing paths, right where
   `result`/`used_key_id` are set and before `break`:
   - the `if result.get("error") == _SDK_TERMINAL_ERROR:` branch → `result["provider_failure_evidence"] = dict(_failure_box)`
   - the armed exception branch (`if arm:` → `result = {**base, "ok": False, "backend": "none", ...}`) → add the key to
     that dict.
   Nothing else in `_reason` changes. Import `provider_failure` lazily or at module top (it has no dependencies).

## 3. `brain/provider_waterfall.py` — `reason()` only
- Keep a list `failures: list = []` beside `attempts`.
- After `attempts.append(attempt)` / `result["provider_attempts"] = list(attempts)` and BEFORE the
  `if result.get("ok") and result.get("text"): return result` check, compute
  `failure = None if (result.get("ok") and result.get("text")) else provider_failure.classify(error=result.get("error"),
  evidence=result.get("provider_failure_evidence"), provider=rung["provider"], key_id=rung["key_id"],
  tools_used=result.get("tools_used"))`, then `failures.append(failure)`, `result["provider_failures"] = list(failures)`,
  `result["provider_failure"] = failure`. Do NOT put the record inside the `attempt` dicts (existing tests compare them).
- Do not read `failure`/`provider_failure` anywhere in the continue/return logic below it; leave that logic byte-identical.
- The two literal fallback dicts (no rungs; "shared provider waterfall exhausted") each gain
  `"provider_failure": provider_failure.classify(error=<that dict's error string>)` and `"provider_failures": list(failures)`
  (`[]` for the no-rungs case). Both will type as kind "availability".

## 4. `bot/autonomous.py`, `bot/china.py`, `bot/hk.py`
In `_append_decision_log`'s `entry` dict, directly after the existing `"error": brain.get("error") if isinstance(brain, dict) else None,`
line, add `"provider_failure": brain.get("provider_failure") if isinstance(brain, dict) else None,`. Nothing else.

## 5. `brain/thinking_log.py` — provider label only (`build_row`)
Bug: `str(model).startswith(("gpt-", "o"))` labels the Claude alias `"opus"` as `"openai"` whenever backend is not
sdk/cli/codex (e.g. backend `"none"` on the armed SDK failure path). Replace the expression so that:
- model starts with `claude` → `"claude_api"` (unchanged);
- model is a Claude Code alias — lowercased model, with any `[...]` suffix removed and split at the first `-`, is one of
  `opus`, `sonnet`, `haiku` (so `opus`, `opus[1m]`, `sonnet`, `haiku-fast` all match) → `"claude_code"`;
- model starts with `gpt-` OR matches `^o\d` (o1, o3, o4-mini) → `"openai"`;
- contains `deepseek` → `"deepseek"`; else None.
The existing `backend == "codex"` → `openai_codex` and `backend in ("sdk","cli")` → `claude_code` overrides stay as they are.

## Required tests
### `tests/test_provider_failure_typing.py` (no network, no real data dir writes outside tmp_path)
Reuse the dispatcher harness: `from test_sdk_diagnostic_bridge import Harness, ResultMessage, TextBlock, ToolUseBlock`
(tests/ is importable; see how `tests/test_provider_legacy_failure.py` imports sibling test modules). Define locally
`@dataclass class AssistantMessage: content: list; error: str | None = None` (the real SDK class has this `error` attribute).
The production failure sequence (`PLAN_401`) for one candidate is:
`[AssistantMessage(content=[TextBlock("Failed to authenticate. API Error: 401 OAuth access token has been revoked.")], error="authentication_failed"),
  ResultMessage(subtype="success", is_error=True, result="", errors=[]),
  Exception("Claude Code returned an error result: success")]`
Tests (each must FAIL on the current origin/master code — state in your RETURN which assertion fails on old code):
1. Armed exception path through the real `_reason` (`Harness.run([PLAN_401], arm=True)`): `result["error"] ==
   "Exception('Claude Code returned an error result: success')"` (unchanged legacy string), `result["backend"] == "none"`,
   `result["ok"] is False`, and `result["provider_failure_evidence"] == {"tool_activity_observed": False,
   "assistant_error": "authentication_failed", "result_is_error": True, "result_subtype": "success"}`.
2. Same, with a `ToolUseBlock()` in an AssistantMessage before the 401 message → `tool_activity_observed is True`.
3. Terminal-error path without a raise (`[AssistantMessage(..., error="rate_limit"), ResultMessage(subtype="success",
   is_error=True, result="x")]`) → `result["error"] == "sdk_terminal_error"` and evidence `assistant_error == "rate_limit"`.
4. Diagnostics on/off: run case 1 twice, once with `_new_sdk_diagnostic`/`_record_sdk_diagnostic` patched to
   `lambda *a: None` (copy the pattern in test_sdk_diagnostic_bridge.py ~L257) → `Harness.legacy(result)` equal.
5. Unknown/forged literal: `error="something_else"` or a non-str → no `assistant_error` key in the evidence.
6. Evidence never carries text: `json.dumps(result["provider_failure_evidence"])` contains neither `"401"`, `"revoked"`,
   `"Failed to authenticate"` nor `"Exception"`.
7. Waterfall typing (patch `provider_waterfall.provider_rungs` to one oauth rung `{"provider":"oauth","key_id":"claude_code_oauth_1",
   "env_name":"CLAUDE_CODE_OAUTH_TOKEN_1","cooling":False}` and `cli_bridge._reason` to an async fake returning the case-1
   result dict; patch `_shared_modules` exactly as tests/test_provider_waterfall.py does): `out["provider_failure"]["kind"] ==
   "credential"`, `["evidence"] == "sdk_assistant_error:authentication_failed"`, `["label_misleading"] is True`,
   `["tool_activity_observed"] is False`, `["provider"] == "oauth"`; `out["error"]` unchanged; `out["provider_attempts"] ==
   [{"provider":"oauth","key_id":"claude_code_oauth_1","ok":False,"cooling":False}]`; `out["provider_failures"] == [out["provider_failure"]]`.
8. Typing never authorizes failover: two rungs `[codex, oauth]` where the codex fake returns
   `{"ok":False,"text":None,"error":"codex CLI not installed","backend":"codex"}`, and separately two oauth rungs where the
   first returns the case-1 dict → the waterfall still returns after the first rung exactly as on old code (assert the fake
   was called once) even though the typed record says "credential". (On old code this passes for the call count but fails on
   the provider_failure assertions — include both in the same test.)
9. `provider_failure.classify` unit table: HK quota text `"You've hit your weekly limit · resets Oct 18, 7pm (UTC)"` → quota;
   `"API Error: 401 OAuth access token has been revoked"` → credential; `"elapsed 4012s"` → unclassified;
   `"Exception('Claude Code returned an error result: success')"` → unclassified + label_misleading True;
   evidence `{"api_error_status": 529}` → availability; `{"api_error_status": True}` (bool) → not used;
   `{"result_subtype": "error_max_turns"}` → deadline; codex `WRITE_TOOL_FAILURE_ERROR` text → tool_contract;
   `classify()` with no args → unclassified; every result has exactly the documented key set; evidence ≤ 80 chars;
   `classify(error=object_whose___str___raises)` does not raise.
10. No-rungs fallback: `provider_rungs` → `[]` → `out["provider_failure"]["kind"] == "availability"`, `out["provider_failures"] == []`,
    and `out["error"]` unchanged.
11. Decision rows carry the record for all three books: for book module in (`bot.autonomous`, `bot.china`, `bot.hk`),
    `monkeypatch.setattr(portfolio.registry, "_ROOT", tmp_path)` (pattern: tests/test_paper_transaction_boundary.py
    `isolated_books`), call `_append_decision_log("2026-10-20", None, [], [], brain, target_status="rejected_no_submission")`
    with `brain = {"error": "Exception('Claude Code returned an error result: success')", "provider_failure": <a classify() result>}`,
    read `registry.data_dir(<book id>) / "decisions.jsonl"` → the row's `provider_failure` equals the record and `error` equals
    the legacy string. A brain dict without the key → `provider_failure` is None.
12. Source guard: the text of `brain/provider_waterfall.py` after the `failures.append(` line up to the end of `reason()`
    must not reference `failure` or `provider_failure` inside any `if`/`continue` condition (simple string check of the
    `if ` lines is enough).

### `tests/test_thinking_log_provider_label.py`
Use `brain.thinking_log.build_row` exactly as `tests/test_thinking_log.py` calls it. Cases (model, backend) → provider:
("opus","none")→claude_code, ("opus[1m]","none")→claude_code, ("sonnet","api")→claude_code, ("haiku","none")→claude_code,
("o3","none")→openai, ("o4-mini","api")→openai, ("gpt-5","none")→openai, ("claude-opus-4-1","api")→claude_api,
("deepseek-v4","none")→deepseek, ("orca","none")→None, ("opus","codex")→openai_codex, ("gpt-5","sdk")→claude_code.
The first case must fail on old code (it returns "openai").

## Run (all must pass; report counts)
`mkdir -p ~/lanes/tmp/pytest && PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <files>`
(fall back to `python3` if the venv python is missing). Run, in this order:
0. BEFORE editing anything: run the keep-green list below on the pristine tree and save the failing node ids to
   `~/lanes/tmp/pbr-rt-lr2/baseline_fail.txt` (`mkdir -p` it). On these hosts `claude_agent_sdk` is NOT installed and
   `vendor/macro` may be a dangling symlink, so some suites fail or error at collection on pristine code — that is the
   baseline, not your problem. `tests/test_sdk_generation_compatibility.py` imports `claude_agent_sdk` at module top: if it
   errors at collection, run the rest without it and say so. Your acceptance for keep-green = the failing set after your
   change is a SUBSET of the baseline set (no new failure, no new error).
1. `tests/test_provider_failure_typing.py tests/test_thinking_log_provider_label.py`
2. Keep-green (failing set must be a subset of the step-0 baseline; report pre-existing failures separately and do not "fix" unrelated code):
   `tests/test_executive_provider_inference_canary.py tests/test_cli_bridge.py tests/test_key_rotor.py tests/test_provider_waterfall.py
   tests/test_sdk_diagnostic_bridge.py tests/test_sdk_generation_compatibility.py tests/test_sdk_diagnostics.py
   tests/test_sdk_terminal_failure.py tests/test_codex_terminal_failure.py tests/test_sdk_diagnostic_terminal_composition.py
   tests/test_sdk_diagnostic_mounted_consumer.py tests/test_secret_redaction.py tests/test_provider_start_veto.py
   tests/test_provider_start_veto_cleanup.py tests/test_provider_start_veto_two_phase.py tests/test_provider_start_run_binding.py
   tests/test_provider_legacy_failure.py tests/test_provider_diagnostic_read.py tests/test_thinking_log.py tests/test_decision_rows.py
   tests/test_codex_bridge.py tests/test_paper_transaction_boundary.py`
3. Old-code proof: `git diff --stat` must list only the allowed files. Then temporarily restore ONLY the six production files
   to origin/master with `git show origin/master:<path> > <path>` for brain/cli_bridge.py, brain/provider_waterfall.py,
   brain/thinking_log.py, bot/autonomous.py, bot/china.py, bot/hk.py (and move brain/provider_failure.py aside), run step 1,
   record which tests fail, then put your versions back and re-run step 1 green. Report both counts.

## Final message
Emit the full RETURN block as your last message:
```
RETURN L-R2
files: <path (+added/-removed lines)> for every changed/new file
tests: typing <n passed/n failed>; label <n/n>; keep-green before <p/f/e> after <p/f/e>; new failures vs baseline <none | node ids>
old-code proof: <n> of the new tests fail on origin/master code: <node ids>
invariants: ok/error/text/backend/provider_attempts unchanged = <yes|no + where>; record read by any retry/failover/cooling decision = <no|yes + where>
deviations from packet: <none | list>
```
