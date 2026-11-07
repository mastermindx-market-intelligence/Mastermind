"""Bounded display of SDK observations for one already selected PM attempt.

Reads the existing run-log owner by exact retained run ID. This is a narrow,
versioned projection of selected diagnostic fields, not a complete SDK schema
validator or a decision, admission, retry, provider-start or effect verdict.
Free-form prompts, results, errors, exception text and notes are never returned.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.decision_availability import ACTIVE_BOOKS, _identity, _instant, _read, _signature

SCHEMA = "mastermind.bot.provider_diagnostic_inspection.v1"
_DIAGNOSTIC_SCHEMA = "mastermind.bot.sdk_diagnostic.v1"
_MAX_ENVELOPE_BYTES = 16_384
_MAX_CANDIDATES = 16
_MAX_INTEGER = (1 << 53) - 1
_ROLE = "deep"  # Current autonomous/china/hk _run_brain callers explicitly select this role.
_END_STATES = frozenset({"exhausted", "raised", "interrupted"})
_COMPLETENESS = frozenset({
    "complete_limited_to_observed_sdk_messages", "partial_abnormal_end_state",
    "incomplete_exhausted_without_terminal", "partial_observation_limits",
    "partial_json_cap", "degraded_projection_failure",
})
_SUBTYPES = frozenset({
    "success", "succeeded", "ok", "completed", "error", "error_during_execution",
    "error_max_turns", "error_max_budget_usd", "error_max_structured_output_retries",
})
_SUCCESS_SUBTYPES = frozenset({"success", "succeeded", "ok", "completed"})
_REASONS = frozenset({
    "api_error", "error", "end_turn", "max_turns", "max_tokens", "max_budget_usd",
    "stop_sequence", "tool_use", "pause_turn", "refusal", "model_context_window_exceeded",
})
_EXCEPTION_CLASSES = frozenset({
    "ProviderStartRefused",
    "ResultError", "ProcessError", "CLINotFoundError", "CLIConnectionError",
    "CLIJSONDecodeError", "MessageParseError", "TimeoutError", "RuntimeError",
    "PermissionError", "FileNotFoundError", "CancelledError", "KeyboardInterrupt",
})
_CAPTURE_REASONS = {
    "available": "collector_projection_available",
    "partial": "observer_call_failed",
    "unavailable": frozenset({"collector_unavailable", "finalization_failed"}),
}
_VERSION = re.compile(r"[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}(?:[-.][A-Za-z0-9]{1,12})?\Z")


def unavailable(portfolio_id: str, run_id: str | None, reason: str) -> dict:
    return {
        "schema": SCHEMA, "portfolio_id": portfolio_id, "run_id": run_id,
        "role": _ROLE, "status": "unavailable", "reason": reason,
        "run_binding": "unavailable", "source": None,
        "diagnostic_events_observed": None, "candidates_observed": None,
        "candidates": [], "candidate_omissions": None,
        "unattributed_capture_events": None, "unattributed_capture_reasons": [],
        "duplicate_candidate_ordinals": [], "duplicate_candidate_count": None,
        "duplicate_candidate_omissions": None, "latest_observation_at": None,
        "observation_age_seconds": None, "issues": [],
        "legacy_failure_observation": None,
        "attempt_coverage": "partial", "provider_start": "not_proven",
        "effect_reconciliation": "not_performed",
        "verification_scope": "selected_diagnostic_fields_and_exact_recorded_identity",
        "free_form_details": "omitted_from_display",
    }


def _object(value):
    return value if type(value) is dict else {}


def _integer(value, issues, *, signed=False):
    if value is None:
        return None
    if type(value) is int and (-_MAX_INTEGER if signed else 0) <= value <= _MAX_INTEGER:
        return value
    issues.add("malformed_numeric_field")
    return None


def _boolean(value, issues):
    if value is None or type(value) is bool:
        return value
    issues.add("malformed_boolean_field")
    return None


def _label(value, allowed, issues):
    if value is None:
        return None
    if type(value) is str and value in allowed:
        return value
    issues.add("unsupported_label_omitted")
    return None


def _version(value, issues):
    declaration = _object(value)
    if not declaration or declaration.get("status") == "unavailable":
        return None
    raw = declaration.get("declared_value")
    if (declaration.get("status") == "declared_only" and type(raw) is str
            and _VERSION.fullmatch(raw)):
        return raw
    issues.add("version_declaration_omitted")
    return None


def _terminal(value, issues):
    if value is None:
        return None
    if type(value) is not dict:
        issues.add("terminal_snapshot_unavailable")
        return None
    if value.get("omitted_reason") == "json_cap":
        issues.add("terminal_snapshot_omitted")
        return None
    flag = _boolean(value.get("is_error"), issues)
    subtype = _label(value.get("subtype"), _SUBTYPES, issues)
    contradiction = _boolean(value.get("contradictory_success_with_is_error"), issues)
    if contradiction is True and flag is not True:
        issues.add("contradictory_snapshot_fields")
        contradiction = None
    if subtype is not None and flag is not None and contradiction is not None:
        if contradiction != (flag is True and subtype in _SUCCESS_SUBTYPES):
            issues.add("contradictory_snapshot_fields")
            contradiction = None
    return {
        "is_error": flag, "subtype": subtype, "reported_contradiction": contradiction,
        "api_error_status": _integer(value.get("api_error_status"), issues, signed=True),
        "terminal_reason": _label(value.get("terminal_reason"), _REASONS, issues),
        "stop_reason": _label(value.get("stop_reason"), _REASONS, issues),
    }


def _project(envelope: dict, *, run_id: str, portfolio_id: str) -> tuple[dict | None, str | None]:
    """Admit exact identity and only the fields this view actually consumes."""
    if type(envelope) is not dict or envelope.get("schema") != _DIAGNOSTIC_SCHEMA:
        return None, "diagnostic_schema_unavailable"
    try:
        size = len(json.dumps(envelope, ensure_ascii=False, allow_nan=False,
                              separators=(",", ":"), sort_keys=True).encode("utf-8"))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None, "diagnostic_shape_invalid"
    if size > _MAX_ENVELOPE_BYTES:
        return None, "diagnostic_envelope_too_large"
    identity = _object(envelope.get("identity"))
    ordinal = identity.get("candidate_ordinal")
    if (identity.get("run_id") != run_id or identity.get("book") != portfolio_id
            or identity.get("role") != _ROLE or type(ordinal) is not int
            or not 0 <= ordinal < _MAX_INTEGER):
        return None, "diagnostic_identity_mismatch"
    qualifications = _object(envelope.get("qualifications"))
    if qualifications.get("effect_reconciliation") != "not_performed":
        return None, "diagnostic_effect_scope_invalid"
    issues = set()
    observation = _object(envelope.get("observation"))
    terminals = _object(envelope.get("terminals"))
    exit_section = _object(envelope.get("exit"))
    exception = _object(envelope.get("exception"))
    dependencies = _object(envelope.get("dependencies"))
    counts = {key: _integer(observation.get(key), issues) for key in (
        "sdk_messages_observed", "terminal_messages_observed", "tool_use_blocks_observed",
        "tool_result_blocks_observed", "contradictory_terminals_observed",
    )}
    terminal_count = _integer(terminals.get("count"), issues)
    omitted_middle_count = _integer(terminals.get("omitted_middle_count"), issues)
    if omitted_middle_count is None:
        issues.add("terminal_omission_count_unavailable")
    elif terminal_count is not None and omitted_middle_count != max(0, terminal_count - 2):
        return None, "diagnostic_terminal_counts_conflict"
    if terminal_count != counts["terminal_messages_observed"]:
        return None, "diagnostic_terminal_counts_conflict"
    if (terminal_count is not None and counts["sdk_messages_observed"] is not None
            and terminal_count > counts["sdk_messages_observed"]):
        return None, "diagnostic_terminal_counts_conflict"
    contradictions = counts["contradictory_terminals_observed"]
    if contradictions is not None and terminal_count is not None and contradictions > terminal_count:
        return None, "diagnostic_terminal_counts_conflict"
    first = _terminal(terminals.get("first"), issues)
    last = _terminal(terminals.get("last"), issues)
    if terminal_count is not None and terminal_count > 0 and (first is None or last is None):
        issues.add("terminal_snapshots_unavailable")
    if terminal_count == 0 and (first is not None or last is not None):
        return None, "diagnostic_terminal_counts_conflict"
    if terminal_count == 1 and first != last:
        return None, "diagnostic_single_terminal_conflict"
    if any(counts[key] is None for key in (
        "sdk_messages_observed", "terminal_messages_observed",
        "tool_use_blocks_observed", "tool_result_blocks_observed",
    )):
        issues.add("observation_counts_unavailable")
    end_state = _label(exit_section.get("end_state"), _END_STATES, issues)
    completeness = _label(qualifications.get("completeness"), _COMPLETENESS, issues)
    if end_state is None or completeness is None:
        issues.add("observation_qualification_unavailable")
    exception_summary = _terminal(exception, issues) if exception else None
    exception_observed = _boolean(exception.get("observed"), issues)
    exception_class = _label(exit_section.get("exception_class"), _EXCEPTION_CLASSES, issues)
    if exception_observed is None and end_state in {"raised", "interrupted"}:
        issues.add("exception_observation_unavailable")
    result = {
        "identity": {"run_id": run_id, "book": portfolio_id, "role": _ROLE,
                     "candidate_ordinal": ordinal},
        "observation": {**counts, "query_entered_observed":
                        _boolean(observation.get("query_entered_observed"), issues)},
        "terminals": {"count": terminal_count, "first": first, "last": last,
                      "omitted_middle_count": omitted_middle_count},
        "exception": {"observed": exception_observed, "class": exception_class,
                      "fields": exception_summary},
        "exit": {"end_state": end_state, "exit_code":
                 _integer(exit_section.get("exit_code"), issues, signed=True)},
        "completeness": completeness,
        "versions_declared_only": {
            "sdk": _version(dependencies.get("sdk_package_version"), issues),
            "bundled_cli": _version(dependencies.get("bundled_cli_version"), issues),
        },
    }
    if completeness == "complete_limited_to_observed_sdk_messages":
        if (end_state != "exhausted" or terminal_count in (None, 0)
                or result["observation"]["query_entered_observed"] is not True):
            issues.add("contradictory_completeness_fields")
    result["issues"] = sorted(issues)
    result["status"] = "available" if not issues and completeness == "complete_limited_to_observed_sdk_messages" else "partial"
    return result, None


# Exact legacy bridge emissions observed in the October 2026 incident.
# These are display signatures, never provider-error classification or retry input.
_LEGACY_AUTH_BANNER = (
    "Failed to authenticate. API Error: 401 OAuth access token has been revoked."
)
_LEGACY_SDK_ERROR = "Exception('Claude Code returned an error result: success')"


def _legacy_failure_observation(rows, source, *, portfolio_id, run_id, seed_time, observed):
    """Project one closed old-log sequence without asserting candidate identity.

    The decision journal supplies the book-to-run reference. Old run metadata
    does not positively identify the book or credential. A complete stable read
    and this exact emission layout qualify only the retained log observation;
    they do not establish provider startup, effect absence or retry eligibility.
    """
    if source.get("status") != "available" or len(rows) != 5:
        return None
    if (set(rows[0]) != {"_meta"}
            or rows[0]["_meta"].get("kind") != "research"):
        return None
    events = rows[1:]
    required = {"type", "title", "ts", "detail"}
    allowed = required | {"book", "portfolio_id", "run_id"}
    if any(not required <= set(row) <= allowed or type(row.get("detail")) is not str
           for row in events):
        return None
    titles = ("session start", "assistant text", "sdk error", "result")
    if any(row.get("type") != "reasoning" or row.get("title") != title
           for row, title in zip(events, titles)):
        return None
    if (events[1].get("detail") != _LEGACY_AUTH_BANNER
            or events[2].get("detail") != _LEGACY_SDK_ERROR
            or events[3].get("detail") != ""):
        return None
    for row in events:
        if any(key in row and row[key] != portfolio_id for key in ("book", "portfolio_id")):
            return None
        if "run_id" in row and row["run_id"] != run_id:
            return None
    times = [_instant(row.get("ts")) for row in events]
    if (any(stamp is None for stamp in times)
            or not seed_time <= times[0] <= times[1] <= times[2] <= times[3] <= observed):
        return None
    return {
        "schema": "mastermind.bot.recorded_failure_observation.v1",
        "kind": "recorded_authentication_revoked",
        "source_kind": "legacy_runlog_assistant_banner",
        "run_id": run_id, "portfolio_id": portfolio_id,
        "book_binding": "selected_decision_run_reference",
        "candidate_identity": "unavailable",
        "recorded_at": events[2]["ts"],
        "banner_recorded_at": events[1]["ts"],
        "observation_age_seconds": (observed - times[2]).total_seconds(),
        "verification_scope": "closed_legacy_sequence_only",
    }


def read_provider_diagnostic_evidence(
    portfolio_id: str, attempt: dict | None, *, runs_dir: Path, observed_at: str,
) -> dict:
    """Read exactly one named log, with no index search, mutation or implicit latest."""
    run_id = _identity(attempt.get("run_id")) if type(attempt) is dict else None
    result = unavailable(portfolio_id, run_id, "attempt_run_identity_unavailable")
    if portfolio_id not in ACTIVE_BOOKS:
        result.update(status="not_applicable", reason="book_not_applicable")
        return result
    if run_id is None:
        return result
    if any(key in attempt and attempt[key] != portfolio_id for key in ("book", "portfolio_id")):
        result["reason"] = "attempt_book_identity_mismatch"
        return result
    observed = _instant(observed_at)
    if observed is None:
        result["reason"] = "observation_clock_invalid"
        return result
    path = runs_dir / (run_id + ".jsonl")
    try:
        if path.is_symlink():
            result["reason"] = "run_source_symlink"
            return result
        rows, source, signature = _read(path, lines=True)
    except OSError:
        result["reason"] = "run_source_unreadable"
        return result
    result["source"] = source
    if rows is None:
        result["reason"] = "run_source_" + source["status"]
        return result
    metas = [row.get("_meta") for row in rows if "_meta" in row]
    if len(metas) != 1 or type(metas[0]) is not dict or metas[0].get("run_id") != run_id:
        result["reason"] = "run_metadata_identity_unavailable"
        return result
    if any(key in metas[0] and metas[0][key] != portfolio_id for key in ("book", "portfolio_id")):
        result["reason"] = "run_metadata_book_conflict"
        return result
    seed_time = _instant(metas[0].get("ts"))
    if seed_time is None or seed_time > observed:
        result["reason"] = "run_metadata_clock_invalid"
        return result
    result["run_binding"] = "matched_recorded_run_id"
    result["legacy_failure_observation"] = _legacy_failure_observation(
        rows, source, portfolio_id=portfolio_id, run_id=run_id,
        seed_time=seed_time, observed=observed,
    )
    issues = set()
    if source["status"] != "available":
        issues.add("run_source_partial")
    candidates = {}
    duplicates = set()
    events = unattributed = 0
    capture_reasons = set()
    for row in rows:
        if row.get("type") != "provider_diagnostic":
            continue
        events += 1
        stamp = _instant(row.get("ts"))
        if stamp is None or not seed_time <= stamp <= observed:
            issues.add("diagnostic_clock_invalid")
            continue
        capture = _object(row.get("provider_diagnostic_capture"))
        state, reason = capture.get("status"), capture.get("reason")
        if type(state) is not str or type(reason) is not str:
            issues.add("capture_qualification_unavailable")
            continue
        if state == "unavailable" and reason in _CAPTURE_REASONS["unavailable"]:
            # Existing unavailable events have no candidate/book/role identity.
            # Their only supported attribution is the exact named run.
            unattributed += 1
            capture_reasons.add(reason)
            issues.add("capture_unattributed_to_candidate")
            continue
        if (state not in {"available", "partial"}
                or reason != _CAPTURE_REASONS.get(state)):
            issues.add("capture_qualification_unavailable")
            continue
        candidate, problem = _project(row.get("provider_diagnostic"), run_id=run_id,
                                      portfolio_id=portfolio_id)
        if candidate is None:
            issues.add(problem)
            continue
        ordinal = candidate["identity"]["candidate_ordinal"]
        if ordinal in candidates:
            duplicates.add(ordinal)
        else:
            candidate.update(recorded_at=row["ts"], capture_status=state)
            if state == "partial":
                candidate["status"] = "partial"
            candidates[ordinal] = candidate
    for ordinal in duplicates:
        candidates.pop(ordinal, None)
    if duplicates:
        issues.add("duplicate_candidate_identity")
    ordered = [candidates[key] for key in sorted(candidates)]
    if ordered and [x["identity"]["candidate_ordinal"] for x in ordered] != list(range(len(ordered))):
        issues.add("candidate_ordinal_gap")
    omissions = max(0, len(ordered) - _MAX_CANDIDATES)
    if omissions:
        issues.add("candidate_display_limit")
    if any(row["status"] == "partial" for row in ordered):
        issues.add("candidate_observations_partial")
    # Only surviving exact-bound candidates own this clock. Wrong identity,
    # unattributed capture and duplicate records cannot lend freshness.
    observation_times = [_instant(item["recorded_at"]) for item in ordered]
    result.update(
        status="partial" if issues else "available", reason="recorded_sdk_observations",
        diagnostic_events_observed=events, candidates_observed=len(ordered),
        candidates=ordered[:_MAX_CANDIDATES], candidate_omissions=omissions,
        unattributed_capture_events=unattributed,
        unattributed_capture_reasons=sorted(capture_reasons),
        duplicate_candidate_ordinals=sorted(duplicates)[:_MAX_CANDIDATES],
        duplicate_candidate_count=len(duplicates),
        duplicate_candidate_omissions=max(0, len(duplicates) - _MAX_CANDIDATES),
        latest_observation_at=max(observation_times).isoformat() if observation_times else None,
        observation_age_seconds=(observed - max(observation_times)).total_seconds() if observation_times else None,
        issues=sorted(issues),
    )
    if not ordered:
        result.update(status="unavailable", reason="no_attributable_sdk_observation" if events else "no_sdk_diagnostic_event")
    try:
        changed = path.is_symlink() or _signature(path) != signature
    except OSError:
        changed = True
    if changed:
        result.update(status="provisional", reason="run_source_changed_during_read",
                      run_binding="provisional", candidates=[], candidates_observed=None,
                      candidate_omissions=None, latest_observation_at=None, observation_age_seconds=None,
                      legacy_failure_observation=None)
        result["issues"] = sorted(issues | {"run_source_changed_during_read"})
    return result
