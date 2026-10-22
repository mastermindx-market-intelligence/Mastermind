# claude-agent-sdk error-result evidence (orchestrator-collected 2026-10-22, read-only)

pyproject.toml @ origin/master d31aade9 line 14: `"claude-agent-sdk>=0.2",` — floor only; no lock file in the repo.

## VPS installed: 0.2.110 (`/opt/mastermind/.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/query.py` L304-344)
    if message.get("is_error"):
        errors = message.get("errors") or []
        self._last_error_result_text = "; ".join(errors) or str(
            message.get("subtype", "unknown error")
        )
    ...
    if isinstance(e, ProcessError) and self._last_error_result_text is not None:
        error_text = (
            f"Claude Code returned an error result: "
            f"{self._last_error_result_text}"
        )
=> an API failure frame {subtype:"success", is_error:true, errors:[]} produces the plain Exception text
   "Claude Code returned an error result: success" (the 18 credential + 2 quota failures 10-12..10-21 all carry it).

## Reference: 0.2.151 (`_internal/query.py` `_error_result_text`, L55-80 and L405-425)
    errors = _normalize_result_errors(message.get("errors"))
    if errors: return "; ".join(errors)
    result = message.get("result")
    if isinstance(result, str) and result.strip(): return result.strip()
    subtype = message.get("subtype")
    if isinstance(subtype, str) and subtype and subtype != "success": return subtype
    status = message.get("api_error_status")
    if status is not None: return f"API error (HTTP {status})"
    return "unknown error"
    ...
    pending_error = ResultError(error_text, data=self._last_error_result, exit_code=e.exit_code)
=> same frame produces "Claude Code returned an error result: API Error: 401 ..." (the CLI's prose), raised as a typed
   `ResultError` whose `.data` is the result frame. The docstring names the old message "self-contradictory".

## Independent of SDK version
The root cause is also delivered earlier on `AssistantMessage.error` (literal e.g. "authentication_failed"), which
`brain/cli_bridge.py` never reads at ff16c192/d31aade9; `brain/key_rotor.py::classify_failure` returns None for the
"success" text, so no key is cooled and `brain/provider_waterfall.py` returns at the first oauth rung.
