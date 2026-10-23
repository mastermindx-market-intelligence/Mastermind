#!/usr/bin/env python3
"""Bounded provider diagnostics for the incumbent single-attempt executor.

Only CLI-owned structured fields are classified. Agent prose, tool output and
stderr are never quota evidence. This module neither retries nor grants work.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

SCHEMA = "mastermind.provider_outcome.v1"
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
CAPACITY = frozenset({"rate_limit", "quota_exhausted"})
ERRORS = {
    "rate_limit": "rate_limit",
    "authentication_failed": "authentication",
    "oauth_org_not_allowed": "authentication",
    "account_on_hold": "authentication",
    "verification_required": "authentication",
    "cloud_credential_error": "authentication",
    "billing_error": "billing",
    "invalid_request": "invalid_request",
    "server_error": "provider_error",
    "overloaded": "provider_error",
    "model_not_found": "invalid_request",
    "unknown": "unknown",
    "max_output_tokens": "output_limit",
}
STOP_REASONS = {
    "error_max_turns": "turn_limit",
    "error_max_budget_usd": "budget_limit",
    "error_max_structured_output_retries": "output_limit",
}
TERMINAL_REASONS = {
    "prompt_too_long": "context_limit", "max_turns": "turn_limit",
    "budget_exhausted": "budget_limit", "structured_output_retry_exhausted": "output_limit",
    "aborted_streaming": "interrupted", "aborted_tools": "interrupted",
    "hook_stopped": "permission", "stop_hook_prevented": "permission",
}
# Derived outcomes contain closed diagnostics, never arbitrary provider text.
# Raw event values remain local to classification and the private raw capture.
CLI_SUBTYPES = frozenset({'success', 'error_during_execution', *STOP_REASONS})
CLI_TERMINAL_REASONS = frozenset({'completed', *TERMINAL_REASONS})


def _closed_cli_label(value: str | None, known: frozenset[str]) -> str | None:
    return None if value is None else value if value in known else 'other'


CODEX_ERRORS = {
    "ContextWindowExceeded": "context_limit",
    "SessionBudgetExceeded": "budget_limit",
    "UsageLimitExceeded": "quota_exhausted",
    "RateLimitExceeded": "rate_limit",
    "Unauthorized": "authentication",
    "context_window_exceeded": "context_limit",
    "session_budget_exceeded": "budget_limit",
    "usage_limit_exceeded": "quota_exhausted",
    "rate_limit_exceeded": "rate_limit",
    "unauthorized": "authentication",
    "server_overloaded": "provider_error",
    "flex_unavailable": "provider_error",
    "bad_request": "invalid_request",
    "invalid_prompt": "invalid_request",
    "sandbox_error": "permission",
    "too_many_denials": "permission",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_bytes(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("outcome_input_unqualified")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        after = os.fstat(fd)
        if (len(data) != before.st_size or before.st_ino != after.st_ino
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ValueError("outcome_input_changed")
        return data
    finally:
        os.close(fd)


def write_new(path: Path, value: dict) -> None:
    data = (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def retain_capture(source: Path, target: Path) -> dict:
    """Preserve bounded private diagnostics without putting raw thoughts on stdout."""
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("capture_kind_unqualified")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(64 * 1024 * 1024)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("capture_changed")
        capture = target.with_suffix(".capture.jsonl")
        dest = os.open(capture, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(dest,"wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        value = {"file": capture.name, "sha256": digest(raw), "bytes": len(raw),
                 "source_bytes": before.st_size, "truncated": before.st_size > len(raw)}
        write_new(target.with_suffix(".capture.json"), value)
        # A durable bounded replacement now exists. The caller's exact original
        # tempfile is only removed if it still names the same captured inode.
        current = source.lstat()
        if (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino):
            source.unlink()
        return value
    finally:
        os.close(fd)


def parse_claude(raw: bytes, command_rc: int) -> tuple[str, dict, dict | None]:
    """Parse JSON/verbose JSON/stream JSON; never expose private thought fields."""
    messages = []
    complete = False
    try:
        parsed = json.loads(raw)
        messages = parsed if isinstance(parsed, list) else [parsed]
        complete = isinstance(parsed, list)
    except (ValueError, RecursionError):
        try:
            messages = [json.loads(line) for line in raw.splitlines() if line.strip()]
            complete = bool(messages)
        except (ValueError, RecursionError):
            messages = []
    if not messages or any(not isinstance(m, dict) for m in messages):
        messages, complete = [], False
    finals = [m for m in messages if m.get("type") == "result"]
    final = finals[-1] if len(finals) == 1 else None
    if final is None and len(messages) == 1 and "subtype" in messages[0]:
        final = messages[0]  # Old non-verbose result: diagnostics only.
        complete = False
    fields = final or {}
    subtype = fields.get("subtype") if isinstance(fields.get("subtype"), str) else None
    terminal_reason = fields.get("terminal_reason") if isinstance(fields.get("terminal_reason"), str) else None
    display = fields.get("result")
    display = display if isinstance(display, str) else ""
    if display and not display.endswith("\n"):
        display += "\n"
    errors = [m.get("error") for m in messages if m.get("type") == "assistant"
              and isinstance(m.get("error"), str)]
    kind = STOP_REASONS.get(subtype) or TERMINAL_REASONS.get(terminal_reason)
    denials = fields.get("permission_denials", [])
    denied = bool(denials)
    # Claude reports the history of denied tool requests even when the CLI
    # subsequently completes successfully. That history is useful for parent
    # review, but is not a terminal permission failure. Require an unambiguous
    # complete success before treating it as historical; a missing/failing CLI,
    # real terminal error, malformed denial list or ambiguous stream keeps the
    # existing fail-closed behavior. This grants neither acceptance nor replay.
    denial_history_only = (
        denied and isinstance(denials, list)
        and all(isinstance(item, dict) for item in denials)
        and complete and len(finals) == 1 and final is messages[-1]
        and type(command_rc) is int and command_rc == 0
        and subtype == "success" and fields.get("is_error") is False
        and fields.get("terminal_reason") in (None, "completed")
        and fields.get("api_error_status") is None
        and not fields.get("errors") and not errors
    )
    permission_failure = denied and not denial_history_only
    if permission_failure:
        kind = "permission"
    elif kind is None:
        kind = next((ERRORS[e] for e in reversed(errors) if e in ERRORS), None)
    failed = (command_rc != 0 or fields.get("is_error") is True
              or subtype in STOP_REASONS or kind is not None or bool(errors)
              or permission_failure)
    code = fields.get("api_error_status")
    if type(code) is not int or not 100 <= code <= 599:
        code = None
    if kind is None and failed and code == 429:
        kind = "rate_limit"
    if kind is None:
        kind = "unknown" if failed or final is None else "success"
    if final is None and not raw.lstrip().startswith((b"{", b"[")):
        # An old plain-text responder/proxy diagnostic remains useful output.
        # Its words are never classification or replay evidence. Malformed
        # structured streams are retained separately, never echoed as thoughts.
        display = raw.decode("utf-8", errors="replace")
    # This CLI observation is diagnostic only. Startup hooks or MCP servers can
    # have effects before the first visible model turn. Only the separate bound
    # pre-task wrapper probe can qualify automatic continuation.
    safe_events = all(
        (m.get("type") == "system" and m.get("subtype") == "init")
        or (m.get("type") == "assistant" and isinstance(m.get("error"), str) and m.get("error") in ERRORS
            and not m.get("parent_tool_use_id")
            and isinstance(m.get("message"), dict)
            and isinstance(m["message"].get("content"), list)
            and all(isinstance(b, dict) and b.get("type") == "text"
                    for b in m["message"]["content"]))
        or (isinstance(m.get("type"), str) and m.get("type") in {"result", "rate_limit_event"})
        for m in messages
    )
    initial_rejection = (
        complete and len(finals) == 1 and final is messages[-1]
        and any(m.get("type") == "system" and m.get("subtype") == "init" for m in messages)
        and len(errors) == 1 and safe_events and not denied
        and fields.get("is_error") is True and kind in CAPACITY
        and type(fields.get("num_turns")) is int and 0 <= fields["num_turns"] <= 1
    )
    reset = None
    for m in messages:
        if m.get("type") != "rate_limit_event":
            continue
        info = m.get("rate_limit_info", m.get("rateLimitInfo"))
        if not isinstance(info, dict) or info.get("status") != "rejected":
            continue
        value = info.get("resetsAt", info.get("resets_at"))
        if type(value) in (int, float) and math.isfinite(value) and value > 0:
            reset = float(value)
    sid = fields.get("session_id")
    if not isinstance(sid, str) or not IDENT.fullmatch(sid):
        sid = None
    return display, {
        "kind": kind, "command_rc": command_rc, "initial_rejection": initial_rejection,
        "complete_event_capture": complete, "api_status": code,
        "cli_command_rc": command_rc,
        "cli_subtype": _closed_cli_label(subtype, CLI_SUBTYPES),
        "cli_terminal_reason": _closed_cli_label(terminal_reason, CLI_TERMINAL_REASONS),
        "permission_denial_count": len(denials) if isinstance(denials, list) else None,
        "permission_denials_role": ("historical_nonterminal" if denial_history_only
                                   else "failure_evidence" if denied else "none"),
        "reset_at": reset, "reset_source": "provider_event" if reset else None,
        "session_id": sid, "capture_sha256": digest(raw), "capture_bytes": len(raw),
        "stdout_sha256": digest(display.encode()),
    }, final


def bound_outcome(fields: dict, env: dict, provider: str, model: str) -> dict:
    names = {"run_id": "REMOTE_SUB_RUN_ID", "lease_id": "POOL_LEASE_ID",
             "account": "POOL_ACCOUNT", "root_id": "POOL_ORCHESTRATOR_ID",
             "host": "LANE_REMOTE_HOST"}
    scope = {name: env.get(key, "") for name, key in names.items()}
    if any(not IDENT.fullmatch(value) for value in scope.values()):
        raise ValueError("outcome_scope_unavailable")
    return {"schema": SCHEMA, **fields, **scope, "provider": provider,
            "model": model, "observed_at": time.time()}


def parse_codex(home: Path, command_rc: int, last_message: bytes) -> dict:
    """Read CLI-owned rollout error enums, never search its prose or reasoning."""
    files = sorted((home / "sessions").rglob("*.jsonl"))
    if len(files) != 1:
        raise ValueError("codex_single_session_unqualified")
    raw = regular_bytes(files[0], 64 * 1024 * 1024)
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(e, dict) or not isinstance(e.get("payload"), dict) for e in events):
        raise ValueError("codex_event_invalid")
    errors, session_ids, work_observed = [], [], False
    safe_event_types = {"task_started", "turn_started", "token_count", "user_message", "error"}
    for event in events:
        typ, data = event.get("type"), event["payload"]
        if typ == "session_meta":
            session_ids.append(data.get("id"))
            if data.get("forked_from_id"):
                work_observed = True
        elif typ == "event_msg":
            if data.get("type") == "error":
                info = data.get("codex_error_info")
                # serde unit variants are strings. Other variants/HTTP text
                # remain unknown until their exact producer contract is qualified.
                if isinstance(info, str):
                    errors.append(CODEX_ERRORS.get(info, "unknown"))
                else:
                    errors.append("unknown")
            elif data.get("type") not in safe_event_types:
                work_observed = True
        elif typ == "response_item":
            if not (data.get("type") == "message" and data.get("role") in {"user", "system", "developer"}):
                work_observed = True
        elif typ != "turn_context":
            work_observed = True
    kind = errors[-1] if errors else ("success" if events and command_rc == 0 else "unknown")
    sid = session_ids[0] if len(session_ids) == 1 else None
    if not isinstance(sid, str) or not IDENT.fullmatch(sid):
        sid = None
    return {"kind": kind, "command_rc": command_rc,
        "initial_rejection": command_rc != 0 and sid is not None and len(errors) == 1
            and kind in CAPACITY and not work_observed,
        "complete_event_capture": True, "api_status": None, "reset_at": None,
        "reset_source": None, "session_id": sid,
        "capture_sha256": digest(raw), "capture_bytes": len(raw),
        "stdout_sha256": digest(last_message)}


QWEN_FEEDBACK_SCHEMA = "mastermind.qwen_adaptive429_feedback.v1"
QWEN_FEEDBACK_POLICY_SOURCE = "bailian_keys.adaptive_http_429"
QWEN_FEEDBACK_KEYS = frozenset({
    "schema", "account", "classification_source", "classification",
    "policy_source", "observed_at", "until_ts", "duration_seconds",
    "soft_cap", "soft_cap_enabled"})
QWEN_FEEDBACK_SOURCES = frozenset({"qwen_wrapper_inference", "codex_error_enum"})


def load_qwen_feedback(path: Path, account: str) -> tuple[dict | None, str]:
    """Load one real helper adaptive-429 receipt, or withhold it with a reason.

    Only a plain bounded file written by the cooldown helper under its own lock
    qualifies: the exact closed key set, closed classification sources and
    policy identity, the leased account, integer times with
    until_ts == observed_at + duration_seconds. Malformed, foreign or missing
    receipts are withheld here; they are never repaired or synthesized, and a
    receipt is diagnostic policy feedback, never a numeric HTTP proof.
    """
    try:
        raw = regular_bytes(path, 4096)
    except (OSError, ValueError):
        return None, "receipt_unreadable"
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        return None, "receipt_unparseable"
    if not isinstance(value, dict) or set(value) != QWEN_FEEDBACK_KEYS:
        return None, "receipt_fields_unqualified"
    if (value.get("schema") != QWEN_FEEDBACK_SCHEMA
            or value.get("policy_source") != QWEN_FEEDBACK_POLICY_SOURCE
            or value.get("classification") != "429"
            or value.get("classification_source") not in QWEN_FEEDBACK_SOURCES):
        return None, "receipt_identity_unqualified"
    if not isinstance(account, str) or not IDENT.fullmatch(account) \
            or value.get("account") != account:
        return None, "receipt_account_unqualified"
    for key in ("observed_at", "until_ts", "duration_seconds", "soft_cap"):
        if type(value.get(key)) is not int:
            return None, "receipt_types_unqualified"
    if not isinstance(value.get("soft_cap_enabled"), bool):
        return None, "receipt_types_unqualified"
    if value["observed_at"] <= 0 or value["duration_seconds"] < 1 \
            or value["until_ts"] != value["observed_at"] + value["duration_seconds"]:
        return None, "receipt_times_unqualified"
    return value, "receipt_qualified"


def codex_main(args: list[str]) -> int:
    home, rc, provider, model, last = args[:5]
    feedback_path = args[5] if len(args) > 5 else ""
    target = os.environ.get("POOL_OUTCOME_FILE")
    if not target:
        return 0
    try:
        path = Path(last)
        display = regular_bytes(path, 8388608) if path.exists() else b""
        fields = parse_codex(Path(home), int(rc), display)
        if provider in {"qwen", "bailian"} and fields.get("command_rc") != 0:
            cli_kind = fields.get("kind")
            if cli_kind in CAPACITY:
                # Preserve the actual closed CLI diagnostic without turning an
                # unqualified Qwen capacity event into the generic HARD policy.
                fields["qwen_cli_kind"] = cli_kind
                fields["qwen_cli_initial_rejection"] = fields["initial_rejection"]
                fields["kind"] = "unknown"
                fields["initial_rejection"] = False
            if feedback_path and os.path.lexists(feedback_path):
                receipt, reason = load_qwen_feedback(
                    Path(feedback_path), os.environ.get("POOL_ACCOUNT", ""))
                if cli_kind == "authentication":
                    receipt, reason = None, "typed_auth_contradicts_inferred_429"
                elif cli_kind == "quota_exhausted":
                    receipt, reason = None, "typed_quota_contradicts_inferred_429"
                elif (receipt is not None
                      and receipt["classification_source"] == "codex_error_enum"
                      and cli_kind != "rate_limit"):
                    receipt, reason = None, "typed_rate_limit_unconfirmed"
                if receipt is not None:
                    # A wrapper-classified policy event remains inferred even
                    # when the private capture independently reports a CLI
                    # rate-limit enum. Neither source proves provider HTTP429.
                    if receipt["classification_source"] == "codex_error_enum":
                        fields["kind"] = "rate_limit"
                        fields["initial_rejection"] = fields.get(
                            "qwen_cli_initial_rejection", False)
                    else:
                        fields["kind"] = "unknown"
                        fields["initial_rejection"] = False
                    fields["qwen_policy_feedback"] = receipt
                else:
                    print("PROVIDER_FEEDBACK_WITHHELD reason=" + reason,
                          file=sys.stderr)
        write_new(Path(target), bound_outcome(fields, os.environ, provider, model))
    except (OSError, ValueError, RecursionError):
        print("PROVIDER_OUTCOME_UNAVAILABLE", file=sys.stderr)
    return 0


def validate_receipt(value: dict, process: dict, run_id: str) -> None:
    from lane_runtime import cleanup_receipt_is_proven
    if (value.get("schema") != SCHEMA or value.get("run_id") != run_id
            or process.get("schema") != "mastermind.local_owned_process_receipt.v1"
            or process.get("label") != run_id
            or not cleanup_receipt_is_proven(process.get("cleanup") or {})
            or process.get("stdout_truncated") is not False
            or process.get("stderr_truncated") is not False
            or process.get("timed_out") is not False
            or process.get("stdout_sha256") != value.get("stdout_sha256")
            or process.get("returncode") != value.get("command_rc")):
        raise ValueError("outcome_process_binding_unqualified")


def claude_main(args: list[str]) -> int:
    raw_path, rc_s, provider, model = args
    rc = int(rc_s)
    try:
        raw = regular_bytes(Path(raw_path), 64 * 1024 * 1024)
        display, fields, final = parse_claude(raw, rc)
        target = os.environ.get("POOL_OUTCOME_FILE")
        if raw == b"" and rc in (75,78) and target:
            path=Path(target).with_suffix('.preflight.json')
            start_marker=Path(target).with_suffix('.task-cli-started.json')
            if path.exists() and not os.path.lexists(start_marker):
                pre=json.loads(regular_bytes(path,16384))
                binding=bound_outcome({},os.environ,provider,model)
                keys=('schema','run_id','lease_id','account','root_id','host','provider','model')
                evidence=pre.get('pre_task_evidence')
                if (all(pre.get(k)==binding[k] for k in keys)
                        and pre.get('command_rc')==rc and isinstance(evidence,dict)
                        and evidence.get('schema')=='mastermind.capacity_preflight.v1'
                        and evidence.get('task_cli_started') is False
                        and pre.get('stdout_sha256')==digest(b'')):
                    fields=pre
    except (OSError, ValueError, RecursionError):
        display, fields, final = "", {"kind": "unknown"}, None
    # A CLI success exit with a structured failure must not publish success.
    if rc == 0 and fields["kind"] != "success":
        rc = 1
    fields["command_rc"] = rc
    sys.stdout.write(display)
    sys.stdout.flush()
    target = os.environ.get("POOL_OUTCOME_FILE")
    if target and rc != 0:
        try:
            fields["diagnostic_capture"] = retain_capture(Path(raw_path), Path(target))
        except (OSError, ValueError):
            print("PROVIDER_CAPTURE_RETAINED_AT_SOURCE path=" + raw_path, file=sys.stderr)
    elif rc != 0:
        print("PROVIDER_CAPTURE_RETAINED_AT_SOURCE path=" + raw_path, file=sys.stderr)
    if target and "stdout_sha256" in fields:
        try:
            value = bound_outcome(fields, os.environ, provider, model)
            write_new(Path(target), value)
        except (OSError, ValueError):
            print("PROVIDER_OUTCOME_UNAVAILABLE", file=sys.stderr)
    if fields["kind"] != "success":
        print("PROVIDER_TERMINAL kind=" + fields["kind"] + " rc=" + str(rc), file=sys.stderr)
    # Preserve incumbent best-effort local usage ledger. The controller's
    # strict terminal ledger remains authoritative; no acceptance is inferred.
    try:
        import pool_ledger
        usage = (final or {}).get("usage") or {}
        tokens = {k: usage.get(k) for k in ("input_tokens", "cache_creation_input_tokens",
                                          "cache_read_input_tokens", "output_tokens")}
        valid = all(type(v) is int and 0 <= v <= 2**53 for v in tokens.values())
        kwargs = {}
        if valid:
            kwargs = dict(input_tokens=tokens["input_tokens"] + tokens["cache_creation_input_tokens"],
                          cached_tokens=tokens["cache_read_input_tokens"], output_tokens=tokens["output_tokens"])
        task_class = os.environ.get("POOL_TASK_CLASS") or provider
        pool_ledger.append(pool=provider, task_class=task_class, rc=rc,
                           signal="ok" if rc == 0 else "other", model=model, **kwargs)
    except Exception:
        pass
    return rc


if __name__ == "__main__":
    if len(sys.argv) == 7 and sys.argv[1] == "codex":
        raise SystemExit(codex_main(sys.argv[2:]))
    if len(sys.argv) == 8 and sys.argv[1] == "codex":
        raise SystemExit(codex_main(sys.argv[2:]))
    if len(sys.argv) == 6 and sys.argv[1] == "claude":
        raise SystemExit(claude_main(sys.argv[2:]))
    raise SystemExit("usage: provider_outcome.py claude RAW RC PROVIDER MODEL")
