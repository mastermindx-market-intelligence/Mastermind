"""Passive per-invocation diagnostics for Claude Agent SDK invocations.

``SDKInvocationDiagnostics`` accumulates best-effort, bounded observations of
one SDK ``query`` iteration and renders them as a JSON-safe envelope meant for
the EXISTING ``runlog.log_step(..., provider_diagnostic=envelope)`` nested
``extra``. The caller owns integration; this collector alone does not capture
an installed invocation. This module builds no logger or lifecycle store and
does not itself call filesystem, network, process or provider APIs.

Hard scope limits (all deliberate):

* No SDK import.  SDK objects are recognised only by ``type(obj).__name__``
  against a strict allowlist; dict fixtures by their ``type`` key.  Arbitrary
  objects are never serialized, never coerced to ``str`` and never inspected
  via ``__dict__``, ``model_dump`` or transport/settings/env attributes.
* No filesystem, network, provider, process or model access and no config
  reading.  The sole dependency is ``common.redaction.sanitize_external_text``.
* Allowlisted SDK attribute reads assume library-created message objects.
  Foreign Python attribute getters can execute code; the collector does not
  promise they are side-effect-free. Dictionary subclasses are not inspected.
* No invocation wrapper: the caller keeps its own iteration and owns
  KeyboardInterrupt/CancelledError propagation. Collector tests alone cannot
  establish the calling bridge's propagation behavior.
* Strictly observational.  The envelope never claims "no effects", never
  classifies a retry, never decides whether a submission was accepted, and
  carries no ``ok``/``error``/``text`` verdict fields.
"""

from __future__ import annotations

import copy
import json
from typing import Any

try:
    from common.redaction import sanitize_external_text

    REDACTION_SANITIZER = "imported"
except Exception:  # diagnostic degradation must not create a second redactor
    sanitize_external_text = None  # type: ignore[assignment]
    REDACTION_SANITIZER = "unavailable_omitting_text"

__all__ = ["SDKInvocationDiagnostics", "ENVELOPE_SCHEMA"]

ENVELOPE_SCHEMA = "mastermind.bot.sdk_diagnostic.v1"
JSON_CAP_BYTES = 16384
MAX_SAFE_INTEGER = (1 << 53) - 1
SUBTYPE_LIMIT = 120
TEXT_LIMIT = 200
EXCEPTION_TEXT_LIMIT = 300
# Sources larger than this are omitted entirely (with a visible reason and raw
# length) instead of being truncated: cutting before redaction can slice a
# secret-shaped run below the matcher threshold and print the residue.
OVERSIZE_TEXT_LIMIT = 4096
MAX_ERRORS = 8
MAX_ERROR_ITEM_LEN = 160
MAX_CONTENT_BLOCKS_SCANNED = 64
MAX_NOTES = 32
NOTE_LIMIT = 200
IDENTITY_LIMIT = 200
VALID_END_STATES = ("exhausted", "raised", "interrupted")
_SUCCESS_SUBTYPE_PREFIXES = ("success", "succeeded", "ok", "completed")
_ERROR_SUBTYPE_PREFIX = "error"

_OBSERVATION_LIMITS = (
    "counts_cover_observed_sdk_messages_only",
    "counts_never_prove_absence_of_execution_effects",
    "unknown_or_malformed_structures_are_omitted_not_coerced",
    "oversize_sources_omitted_entirely_not_truncated_pre_redaction",
    "query_entry_is_not_provider_start_proof",
)

# Strict SDK class-name allowlist.  Anything else is "unknown" and only counted.
_TERMINAL_CLASS_NAMES = frozenset({"ResultMessage"})
_TOOL_USE_CLASS_NAMES = frozenset({"ToolUseBlock"})
_TOOL_RESULT_CLASS_NAMES = frozenset({"ToolResultBlock"})
_USER_CLASS_NAMES = frozenset({"UserMessage"})
_ASSISTANT_CLASS_NAMES = frozenset({"AssistantMessage"})

_DICT_TYPE_KINDS = {
    "result": "terminal",
    "tool_use": "tool_use",
    "tool_result": "tool_result",
    "user": "user_message",
    "assistant": "assistant_message",
}

_MISSING = object()


def _safe_classname(obj: Any) -> str:
    try:
        name = type(obj).__name__
    except Exception:
        return "unknown"
    if type(name) is not str or not name or len(name) > OVERSIZE_TEXT_LIMIT:
        return "unknown"
    return name


def _bounded_classname(obj: Any) -> str:
    # Class identifiers can also be supplied by foreign Python code. Sanitize
    # the complete bounded source before retaining a shortened identifier.
    return _sanitize(_safe_classname(obj), 80) or "unknown"


def _read_field(message: Any, name: str) -> tuple[Any, bool]:
    """Read an allowlisted field; AttributeError remains an absent-field limit."""
    try:
        if type(message) is dict:
            return dict.get(message, name, _MISSING), False
        if isinstance(message, dict):
            return _MISSING, True
        return getattr(message, name, _MISSING), False
    except Exception:
        return _MISSING, True


def _strict_bool(value: Any) -> bool | None:
    return value if type(value) is bool else None


def _strict_int(value: Any) -> int | None:
    if type(value) is int and -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
        return value
    return None


def _strict_exit_code(value: Any) -> int | None:
    """Retain bounded signed integers without coercing bool, float or string."""
    return _strict_int(value)


def _sanitize(value: Any, limit: int) -> str | None:
    """Use the canonical redactor on a full source, then bound its output."""
    if sanitize_external_text is None or type(value) is not str:
        return None
    if len(value) > OVERSIZE_TEXT_LIMIT:
        return None
    try:
        value.encode("utf-8")
        text = sanitize_external_text(value, limit=limit)
        if type(text) is not str:
            return None
        text.encode("utf-8")
        return text
    except Exception:
        return None


class SDKInvocationDiagnostics:
    """Passive collector for ONE SDK invocation (see module docstring).

    Ordinary malformed SDK properties are contained by observe_message, and
    ordinary projection failures in finish degrade to a visible minimal envelope.
    BaseException interruption remains caller-owned. Invalid end_state is a
    programming error and raises ValueError.
    """

    def __init__(
        self,
        *,
        run_id: str | None,
        book: str | None,
        role: str | None,
        candidate_ordinal: int,
        sdk_version: str | None = None,
        cli_version: str | None = None,
    ) -> None:
        self._notes: list[str] = []
        self._notes_dropped = 0
        self._oversize_omissions: list[dict[str, Any]] = []
        self._sdk_messages_observed = 0
        self._unknown_messages_observed = 0
        self._terminal_messages_observed = 0
        self._contradictory_terminals_observed = 0
        self._tool_use_blocks_observed = 0
        self._tool_result_blocks_observed = 0
        self._failed_field_reads = 0
        self._non_string_errors_omitted = 0
        self._scans_truncated = 0
        self._query_entered = False
        self._terminals: list[dict[str, Any]] = []
        self._end_state: str | None = None
        self._exception: BaseException | None = None

        self._run_id = self._identity(run_id)
        self._book = self._identity(book)
        self._role = self._identity(role)
        if book is not None and self._book is None:
            self._note_limit("caller_book_absent_or_malformed_stays_null")
        if role is not None and self._role is None:
            self._note_limit("caller_role_absent_or_malformed_stays_null")
        self._candidate_ordinal = _strict_int(candidate_ordinal)
        if self._candidate_ordinal is not None and self._candidate_ordinal < 0:
            self._candidate_ordinal = None
        if self._candidate_ordinal is None:
            self._note_limit("candidate_ordinal_not_strict_int_stays_null")
        self._sdk_version = (self._bounded_text(sdk_version, limit=IDENTITY_LIMIT, field="sdk_version")
                             if sdk_version is not None else None)
        self._cli_version = (self._bounded_text(cli_version, limit=IDENTITY_LIMIT, field="cli_version")
                             if cli_version is not None else None)

    # -- helpers ----------------------------------------------------------

    def _identity(self, value: Any) -> str | None:
        if value is None:
            return None
        text = self._bounded_text(value, limit=IDENTITY_LIMIT, field="caller_identity")
        return text if text and text.strip() else None

    def _note_limit(self, note: str) -> None:
        # Internal qualification tags are typed constants, deliberately NOT
        # passed through the redactor: its token-shape rule would erase any
        # snake_case tag of 32+ characters.  They are only slice-bounded.
        text = note[:NOTE_LIMIT]
        if not text or text in self._notes:
            return
        if len(self._notes) >= MAX_NOTES:
            self._notes_dropped += 1
            return
        self._notes.append(text)

    def _record_oversize(self, field: str, raw_length: int) -> None:
        if len(self._oversize_omissions) < MAX_NOTES:
            self._oversize_omissions.append(
                {"field": field, "raw_length": raw_length, "reason": "oversize_omitted_not_truncated"}
            )
        self._note_limit("oversize_text_omitted")

    def _bounded_text(self, value: Any, *, limit: int, field: str) -> str | None:
        """Omit malformed/oversize text, then sanitize the full retained input."""
        if type(value) is not str:
            self._note_limit("non_string_field_omitted:" + field)
            return None
        if len(value) > OVERSIZE_TEXT_LIMIT:
            self._record_oversize(field, len(value))
            return None
        try:
            value.encode("utf-8")
        except UnicodeError:
            self._note_limit("invalid_unicode_omitted:" + field)
            return None
        text = _sanitize(value, limit)
        if text is None:
            self._note_limit("redaction_unavailable_text_omitted")
        return text

    def _read(self, message: Any, name: str) -> tuple[Any, bool]:
        value, failed = _read_field(message, name)
        if failed:
            self._failed_field_reads += 1
            self._note_limit("field_read_failed:" + name)
        return value, failed

    # -- observation ------------------------------------------------------

    def mark_query_entered(self) -> None:
        """Record entry into the SDK query iteration.

        This observes the caller entering iteration only; it is NOT proof that
        a provider request started and never proof of any execution effect.
        """
        self._query_entered = True

    def observe_message(self, message: object) -> None:
        """Best-effort observation of one SDK message (or dict fixture).

        Never raises on ordinary malformed properties, never serializes an
        arbitrary object and never mutates ``message``.
        """
        if message is None:
            self._note_limit("none_message_ignored")
            return
        try:
            self._observe(message)
        except Exception as exc:  # observational safety net; never propagate
            self._failed_field_reads += 1
            self._note_limit("message_observation_degraded:" + _bounded_classname(exc))

    def _observe(self, message: Any) -> None:
        kind = self._classify(message)
        self._sdk_messages_observed += 1
        if kind == "unknown":
            self._unknown_messages_observed += 1
        elif kind == "terminal":
            self._terminal_messages_observed += 1
            snapshot = self._snapshot_terminal(message, self._terminal_messages_observed)
            if snapshot["contradictory_success_with_is_error"]:
                self._contradictory_terminals_observed += 1
            if len(self._terminals) < 2:
                self._terminals.append(snapshot)
            else:
                self._terminals[-1] = snapshot
        elif kind == "tool_use":
            self._tool_use_blocks_observed += 1
        elif kind == "tool_result":
            self._tool_result_blocks_observed += 1
        elif kind in ("user_message", "assistant_message"):
            tool_use, tool_result, truncated, failed = self._scan_content(message)
            self._tool_use_blocks_observed += tool_use
            self._tool_result_blocks_observed += tool_result
            if truncated:
                self._scans_truncated += 1
            if failed:
                self._note_limit("content_field_read_failed")

    @staticmethod
    def _classify(message: Any) -> str:
        if type(message) is dict:
            kind = dict.get(message, "type")
            if type(kind) is str:
                return _DICT_TYPE_KINDS.get(kind, "unknown")
            return "unknown"
        if isinstance(message, dict):
            return "unknown"
        name = _safe_classname(message)
        if name in _TERMINAL_CLASS_NAMES:
            return "terminal"
        if name in _TOOL_USE_CLASS_NAMES:
            return "tool_use"
        if name in _TOOL_RESULT_CLASS_NAMES:
            return "tool_result"
        if name in _USER_CLASS_NAMES:
            return "user_message"
        if name in _ASSISTANT_CLASS_NAMES:
            return "assistant_message"
        return "unknown"

    def _scan_content(self, message: Any) -> tuple[int, int, bool, bool]:
        """Inspect at most the configured number of already materialized blocks."""
        value, failed = self._read(message, "content")
        if failed or value is _MISSING:
            return 0, 0, False, failed
        if type(value) is not list and type(value) is not tuple:
            # A string user message is valid SDK input but has no tool blocks.
            if type(value) is not str and value is not None:
                self._note_limit("content_shape_not_inspected")
            return 0, 0, False, False
        tool_use = tool_result = 0
        truncated = len(value) > MAX_CONTENT_BLOCKS_SCANNED
        for block in value[:MAX_CONTENT_BLOCKS_SCANNED]:
            kind = self._classify(block)
            if kind == "tool_use":
                tool_use += 1
            elif kind == "tool_result":
                tool_result += 1
        return tool_use, tool_result, truncated, False

    # -- terminal projection ----------------------------------------------

    def _result_text_presence(self, value: Any, *, field: str) -> bool | None:
        if value is None:
            return False
        if type(value) is not str:
            self._note_limit("non_string_field_omitted:" + field)
            return None
        if len(value) > OVERSIZE_TEXT_LIMIT:
            self._record_oversize(field, len(value))
            return None
        try:
            value.encode("utf-8")
        except UnicodeError:
            self._note_limit("invalid_unicode_omitted:" + field)
            return None
        return bool(value.strip())

    def _terminal_details(self, source: Any, *, prefix: str = "") -> dict[str, Any]:
        details: dict[str, Any] = {}
        for name in ("api_error_status", "terminal_reason", "stop_reason"):
            value, failed = self._read(source, name)
            details[name + "_field_present"] = value is not _MISSING
            details[name + "_read_failed"] = failed
            projected: Any = None
            if not failed and value is not _MISSING and value is not None:
                if name == "api_error_status":
                    projected = _strict_int(value)
                    if projected is None:
                        self._note_limit(prefix + name + "_not_strict_int")
                else:
                    projected = self._bounded_text(
                        value, limit=SUBTYPE_LIMIT, field=prefix + name)
            details[name] = projected
        return details

    def _snapshot_terminal(self, message: Any, ordinal: int) -> dict[str, Any]:
        """Project one terminal message into a bounded, typed snapshot.

        Strict ``bool``-or-null ``is_error``, bounded string-or-null ``subtype``,
        explicit field presence, nonempty-text presence (never the successful
        text itself) and short allowlisted ``errors`` strings only.
        """
        details = self._terminal_details(message)
        unreadable: list[str] = []

        is_error_value, failed = self._read(message, "is_error")
        present_is_error = is_error_value is not _MISSING
        if failed:
            unreadable.append("is_error")
        is_error = None if failed or is_error_value is _MISSING else _strict_bool(is_error_value)
        if not present_is_error:
            self._note_limit("terminal_is_error_missing")
        if present_is_error and not failed and is_error is None:
            self._note_limit("is_error_not_strict_bool")

        subtype_value, failed = self._read(message, "subtype")
        present_subtype = subtype_value is not _MISSING
        if failed:
            unreadable.append("subtype")
        subtype = None
        if not present_subtype:
            self._note_limit("terminal_subtype_missing")
        if not failed and subtype_value is not _MISSING:
            subtype = self._bounded_text(subtype_value, limit=SUBTYPE_LIMIT, field="subtype")

        result_value, failed = self._read(message, "result")
        present_result = result_value is not _MISSING
        if failed:
            unreadable.append("result")
        has_nonempty_text: bool | None = None
        if not failed and result_value is not _MISSING:
            has_nonempty_text = self._result_text_presence(
                result_value, field="terminal_result_presence")

        errors: list[str] = []
        errors_omitted = 0
        errors_value, failed = self._read(message, "errors")
        present_errors = errors_value is not _MISSING
        if failed:
            unreadable.append("errors")
        elif errors_value is not _MISSING and errors_value is not None:
            if (type(errors_value) is list or type(errors_value) is tuple):
                for item in errors_value[:MAX_ERRORS]:
                    text = self._bounded_text(item, limit=MAX_ERROR_ITEM_LEN, field="errors")
                    if text is None:
                        errors_omitted += 1
                        if type(item) is not str:
                            self._non_string_errors_omitted += 1
                    else:
                        errors.append(text)
                if len(errors_value) > MAX_ERRORS:
                    errors_omitted += len(errors_value) - MAX_ERRORS
                    self._note_limit("errors_list_bounded")
            else:
                self._note_limit("errors_field_not_a_list")

        subtype_text = subtype or ""
        errorish = is_error is True or subtype_text.lower().startswith(_ERROR_SUBTYPE_PREFIX)
        retained_failure_text: str | None = None
        if errorish and result_value is not _MISSING and type(result_value) is str:
            retained_failure_text = self._bounded_text(
                result_value, limit=TEXT_LIMIT, field="terminal_failure_text"
            )
        contradictory = bool(
            is_error is True
            and subtype_text.lower().startswith(_SUCCESS_SUBTYPE_PREFIXES)
        )
        if contradictory:
            self._note_limit("contradictory_terminal_success_with_is_error")

        return {
            **details,
            "ordinal": ordinal,
            "is_error": is_error,
            "is_error_field_present": present_is_error,
            "subtype": subtype,
            "subtype_field_present": present_subtype,
            "result_field_present": present_result,
            "errors_field_present": present_errors,
            "unreadable_fields": unreadable,
            "has_nonempty_text": has_nonempty_text,
            "successful_text_retained": False,
            "errors": errors,
            "errors_omitted": errors_omitted,
            "retained_failure_text": retained_failure_text,
            "failure_text_retained": retained_failure_text is not None,
            "failure_text_omitted": bool(errorish and retained_failure_text is None),
            "contradictory_success_with_is_error": contradictory,
        }

    # -- exception projection ---------------------------------------------

    def _project_exception(self, exception: BaseException | None) -> dict[str, Any]:
        """Read SDK ResultError.data through a closed field allowlist.

        A structured exception stays separate from observed terminal messages.
        Raw dictionaries, causes, exception groups and other payload fields are
        never serialized or traversed.
        """
        projection: dict[str, Any] = {
            "observed": exception is not None,
            "exception_class": None,
            "structured_projection_not_terminal_message": True,
            "field_source": "unavailable",
            "is_error": None, "is_error_field_present": False,
            "subtype": None, "subtype_field_present": False,
            "errors": [], "errors_field_present": False, "errors_omitted": 0,
            "result_field_present": False, "has_nonempty_result_text": None,
            "retained_failure_text": None,
            "contradictory_success_with_is_error": False,
        }
        source: Any = exception
        if exception is not None:
            projection["exception_class"] = _bounded_classname(exception)
            projection["field_source"] = "allowlisted_exception_attributes"
            if _safe_classname(exception) == "ResultError":
                data, failed = self._read(exception, "data")
                if not failed and type(data) is dict:
                    source = data
                    projection["field_source"] = "sdk_result_error_data_allowlist"
                elif data is not _MISSING:
                    self._note_limit("result_error_data_unavailable_attributes_only")
        projection.update(self._terminal_details(source, prefix="exception_"))
        if exception is None:
            return projection

        is_error_value, failed = self._read(source, "is_error")
        projection["is_error_field_present"] = is_error_value is not _MISSING
        if not failed and is_error_value is not _MISSING:
            projection["is_error"] = _strict_bool(is_error_value)
            if projection["is_error"] is None:
                self._note_limit("exception_is_error_not_strict_bool")

        subtype_value, failed = self._read(source, "subtype")
        projection["subtype_field_present"] = subtype_value is not _MISSING
        if not failed and subtype_value is not _MISSING and subtype_value is not None:
            projection["subtype"] = self._bounded_text(
                subtype_value, limit=SUBTYPE_LIMIT, field="exception_subtype")

        errors_value, failed = self._read(source, "errors")
        projection["errors_field_present"] = errors_value is not _MISSING
        if not failed and errors_value is not _MISSING and errors_value is not None:
            if type(errors_value) is list or type(errors_value) is tuple:
                for item in errors_value[:MAX_ERRORS]:
                    text = self._bounded_text(item, limit=MAX_ERROR_ITEM_LEN, field="exception_errors")
                    if text is None:
                        projection["errors_omitted"] += 1
                        if type(item) is not str:
                            self._non_string_errors_omitted += 1
                    else:
                        projection["errors"].append(text)
                if len(errors_value) > MAX_ERRORS:
                    projection["errors_omitted"] += len(errors_value) - MAX_ERRORS
                    self._note_limit("exception_errors_list_bounded")
            else:
                self._note_limit("exception_errors_field_not_a_list")

        result_value, failed = self._read(source, "result")
        projection["result_field_present"] = result_value is not _MISSING
        if not failed and result_value is not _MISSING:
            projection["has_nonempty_result_text"] = self._result_text_presence(
                result_value, field="exception_result_presence")
        subtype_text = projection["subtype"] or ""
        errorish = projection["is_error"] is True or subtype_text.lower().startswith(_ERROR_SUBTYPE_PREFIX)
        if errorish and type(result_value) is str:
            projection["retained_failure_text"] = self._bounded_text(
                result_value, limit=TEXT_LIMIT, field="exception_failure_text")
        projection["contradictory_success_with_is_error"] = bool(
            projection["is_error"] is True
            and subtype_text.lower().startswith(_SUCCESS_SUBTYPE_PREFIXES))
        if projection["contradictory_success_with_is_error"]:
            self._note_limit("contradictory_exception_success_with_is_error")
        return projection

    # -- rendering ---------------------------------------------------------

    def finish(self, end_state: str, exception: BaseException | None = None) -> dict[str, Any]:
        """Return a fresh projection; the caller owns exception propagation."""
        if type(end_state) is not str or end_state not in VALID_END_STATES:
            raise ValueError("end_state must be one of %r" % (VALID_END_STATES,))
        self._end_state = end_state
        self._exception = exception
        try:
            try:
                return self._build_envelope()
            except Exception as exc:
                return self._degenerate_envelope(end_state, exc)
        finally:
            # Do not retain a provider exception's traceback after projection.
            self._exception = None

    def _build_envelope(self) -> dict[str, Any]:
        # Complete field reads before snapshotting read/omission counters.
        exception_projection = self._project_exception(self._exception)
        exit_projection = self._exit_section(exception_projection)
        dependencies = self._dependencies()
        terminals = self._terminals_section()
        envelope: dict[str, Any] = {
            "schema": ENVELOPE_SCHEMA,
            "identity": {
                "run_id": self._run_id, "book": self._book, "role": self._role,
                "candidate_ordinal": self._candidate_ordinal,
            },
            "dependencies": dependencies,
            "observation": self._observation_section(),
            "terminals": terminals,
            "exception": exception_projection,
            "exit": exit_projection,
            "qualifications": self._qualifications(terminals),
            "limits": {},
        }
        return self._apply_json_cap(envelope)

    def _dependencies(self) -> dict[str, Any]:
        def declared(value: str | None) -> dict[str, Any]:
            text = value if value and value.strip() else None
            return {"declared_value": text, "status": "declared_only" if text else "unavailable"}

        return {
            "sdk_package_version": declared(self._sdk_version),
            "bundled_cli_version": declared(self._cli_version),
            "redaction_sanitizer": REDACTION_SANITIZER,
            "redaction_projection_status": (
                "degraded" if "redaction_unavailable_text_omitted" in self._notes
                else "limited_to_retained_fields"),
            "declaration_note": "versions_are_caller_declared_inputs_never_executed_version_proof",
        }

    def _observation_section(self) -> dict[str, Any]:
        return {
            "sdk_messages_observed": self._sdk_messages_observed,
            "terminal_messages_observed": self._terminal_messages_observed,
            "contradictory_terminals_observed": self._contradictory_terminals_observed,
            "tool_use_blocks_observed": self._tool_use_blocks_observed,
            "tool_result_blocks_observed": self._tool_result_blocks_observed,
            "unknown_messages_observed": self._unknown_messages_observed,
            "query_entered_observed": self._query_entered,
            "query_entry_is_not_provider_start_proof": True,
            "failed_field_reads": self._failed_field_reads,
            "content_scans_truncated": self._scans_truncated,
            "non_string_errors_omitted": self._non_string_errors_omitted,
            "oversize_omissions": copy.deepcopy(self._oversize_omissions[:MAX_NOTES]),
            "observation_limits": list(_OBSERVATION_LIMITS),
        }

    def _terminals_section(self) -> dict[str, Any]:
        count = self._terminal_messages_observed
        first = copy.deepcopy(self._terminals[0]) if self._terminals else None
        last = copy.deepcopy(self._terminals[-1]) if self._terminals else None
        return {
            "count": count,
            "omitted_middle_count": max(0, count - 2),
            "first": first, "last": last,
            "terminal_presence": "absent" if count == 0 else "single" if count == 1 else "multiple",
            "successful_result_text_retained": False,
        }

    def _exit_section(self, exception_projection: dict[str, Any]) -> dict[str, Any]:
        exit_code: int | None = None
        if self._exception is not None:
            value, failed = self._read(self._exception, "exit_code")
            if not failed and value is not _MISSING:
                exit_code = _strict_exit_code(value)
                if exit_code is None and value is not None:
                    self._note_limit("exit_code_not_strict_signed_int")
        exception_text: str | None = None
        omitted_reason: str | None = None
        text_source: str | None = None
        if isinstance(self._exception, BaseException):
            # Use the built-in descriptor directly, without invoking a foreign
            # __str__, __repr__, args property or formatting an arbitrary item.
            try:
                args = BaseException.args.__get__(self._exception, BaseException)
            except Exception:
                self._failed_field_reads += 1
                omitted_reason = "exception_arguments_unreadable"
            else:
                if type(args) is tuple and args and type(args[0]) is str:
                    text_source = "first_stored_string_argument"
                    exception_text = self._bounded_text(
                        args[0], limit=EXCEPTION_TEXT_LIMIT, field="exception_text")
                    if exception_text is None:
                        omitted_reason = "argument_omitted_by_text_contract"
                    if len(args) > 1:
                        self._note_limit("additional_exception_arguments_not_inspected")
                else:
                    omitted_reason = "no_stored_string_argument"
        elif self._exception is not None:
            omitted_reason = "not_a_base_exception"
            self._note_limit("non_exception_input_not_formatted")
        return {
            "end_state": self._end_state,
            "exception_class": exception_projection["exception_class"],
            "exit_code": exit_code,
            "exception_text": exception_text,
            "exception_text_source": text_source,
            "exception_text_omitted_reason": omitted_reason,
        }

    def _qualifications(self, terminals: dict[str, Any]) -> dict[str, Any]:
        notes: list[str] = [
            "observational_only_no_retry_classification",
            "accepted_submission_outside_collector_authority",
            "effect_reconciliation_not_performed",
            "exception_causes_and_groups_not_traversed",
        ]
        if not self._query_entered:
            notes.append("finish_before_query_entry_observed")
        if self._sdk_messages_observed == 0:
            notes.append("zero_messages_observed_does_not_imply_safe_retry")
        if self._end_state in ("raised", "interrupted"):
            notes.append("abnormal_end_state_stream_partial_even_if_terminal_seen")
        if self._end_state == "exhausted" and terminals["count"] == 0:
            notes.append("exhausted_without_terminal_incomplete")
        if terminals["count"] > 1:
            notes.append("multiple_terminals_observed")
        if self._contradictory_terminals_observed:
            notes.append("contradictory_terminal_success_with_is_error")
        notes.extend(self._notes)
        unique = _dedupe_notes(notes)
        return {
            "effect_reconciliation": "not_performed",
            "completeness": self._completeness(terminals),
            "terminal_presence": terminals["terminal_presence"],
            "no_invocation_wrapper": True,
            "cancellation_propagation": "caller_owned_not_proven_by_collector",
            "no_ok_error_text_verdict_fields": True,
            "notes": unique[:MAX_NOTES],
            "notes_dropped": self._notes_dropped + max(0, len(unique) - MAX_NOTES),
        }

    def _completeness(self, terminals: dict[str, Any]) -> str:
        if self._end_state != "exhausted":
            return "partial_abnormal_end_state"
        if terminals["count"] == 0:
            return "incomplete_exhausted_without_terminal"
        benign_notes = {
            "contradictory_terminal_success_with_is_error",
            "contradictory_exception_success_with_is_error",
        }
        if (not self._query_entered or self._failed_field_reads or self._scans_truncated
                or self._non_string_errors_omitted or self._notes_dropped
                or any(note not in benign_notes for note in self._notes)):
            return "partial_observation_limits"
        return "complete_limited_to_observed_sdk_messages"

    def _degenerate_envelope(self, end_state: str, exc: Exception) -> dict[str, Any]:
        reason = _bounded_classname(exc)
        return {
            "schema": ENVELOPE_SCHEMA,
            "identity": {
                "run_id": self._run_id,
                "book": self._book,
                "role": self._role,
                "candidate_ordinal": self._candidate_ordinal,
            },
            "observation": {
                "sdk_messages_observed": self._sdk_messages_observed,
                "terminal_messages_observed": self._terminal_messages_observed,
                "tool_use_blocks_observed": self._tool_use_blocks_observed,
                "tool_result_blocks_observed": self._tool_result_blocks_observed,
                "query_entered_observed": self._query_entered,
                "query_entry_is_not_provider_start_proof": True,
            },
            "terminals": {
                "count": self._terminal_messages_observed,
                "first": None,
                "last": None,
                "snapshots_omitted_count": min(self._terminal_messages_observed, 2),
                "snapshots_omitted_reason": "projection_degraded",
                "omitted_middle_count": max(0, self._terminal_messages_observed - 2),
            },
            "exit": {
                "end_state": end_state,
                "exception_class": _bounded_classname(self._exception) if self._exception is not None else None,
                "projection_error_class": reason,
            },
            "qualifications": {
                "effect_reconciliation": "not_performed",
                "completeness": "degraded_projection_failure",
                "notes": ["projection_degraded:" + reason],
            },
            "limits": {
                "serialized_json_cap_bytes": JSON_CAP_BYTES,
                "json_cap_applied": True,
                "cap_reductions_applied": ["degenerate_projection_fallback"],
            },
        }

    # -- serialized size cap ----------------------------------------------

    def _apply_json_cap(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Enforce a fixed serialized UTF-8 JSON budget with visible reductions.

        Reductions are applied to a deep copy, ordered so that typed counters,
        identity flags and qualification markers survive longest; each dropped
        detail leaves a count or an explicit reason behind.
        """
        envelope = copy.deepcopy(envelope)
        limits = envelope.setdefault("limits", {})
        limits["serialized_json_cap_bytes"] = JSON_CAP_BYTES
        limits["json_cap_applied"] = False
        limits["cap_reductions_applied"] = []
        reductions = (
            ("drop_retained_text", _reduce_retained_text),
            ("drop_error_strings", _reduce_error_strings),
            ("drop_terminal_snapshots", _reduce_terminal_snapshots),
            ("drop_notes_and_omissions", _reduce_notes_and_omissions),
        )
        for name, reducer in reductions:
            if _json_bytes(envelope) <= JSON_CAP_BYTES:
                break
            reducer(envelope)
            limits["json_cap_applied"] = True
            envelope["qualifications"]["completeness"] = "partial_json_cap"
            limits["cap_reductions_applied"].append(name)
        if _json_bytes(envelope) <= JSON_CAP_BYTES:
            return envelope
        minimal = self._degenerate_envelope(self._end_state or "exhausted", RuntimeError("json_cap_fallback"))
        minimal["limits"]["cap_reductions_applied"] = ["minimal_envelope_fallback"]
        minimal["terminals"]["snapshots_omitted_reason"] = "json_cap"
        minimal["exit"]["projection_error_class"] = None
        minimal["qualifications"]["completeness"] = "partial_json_cap"
        minimal["qualifications"]["notes"] = ["diagnostic_details_omitted_for_json_cap"]
        return minimal


def _json_bytes(envelope: dict[str, Any]) -> int:
    try:
        rendered = json.dumps(
            envelope, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
        return len(rendered.encode("utf-8"))
    except Exception:
        return JSON_CAP_BYTES + 1


def _dedupe_notes(notes: list[str]) -> list[str]:
    seen: list[str] = []
    for note in notes:
        text = note[:NOTE_LIMIT]
        if text and text not in seen:
            seen.append(text)
    return seen


def _reduce_retained_text(envelope: dict[str, Any]) -> None:
    for key in ("first", "last"):
        snapshot = envelope.get("terminals", {}).get(key)
        if isinstance(snapshot, dict) and snapshot.get("retained_failure_text"):
            snapshot["retained_failure_text"] = None
            snapshot["failure_text_retained"] = False
            snapshot["failure_text_omitted"] = True
            snapshot["retained_failure_text_omitted_reason"] = "json_cap"
    exception = envelope.get("exception")
    if isinstance(exception, dict) and exception.get("retained_failure_text"):
        exception["retained_failure_text"] = None
        exception["retained_failure_text_omitted_reason"] = "json_cap"
    exit_section = envelope.get("exit")
    if isinstance(exit_section, dict) and exit_section.get("exception_text"):
        exit_section["exception_text"] = None
        exit_section["exception_text_omitted_reason"] = "json_cap"


def _reduce_error_strings(envelope: dict[str, Any]) -> None:
    for key in ("first", "last"):
        snapshot = envelope.get("terminals", {}).get(key)
        if isinstance(snapshot, dict) and snapshot.get("errors"):
            snapshot["errors_omitted"] = int(snapshot.get("errors_omitted", 0)) + len(snapshot["errors"])
            snapshot["errors"] = []
            snapshot["errors_omitted_reason"] = "json_cap"
    exception = envelope.get("exception")
    if isinstance(exception, dict) and exception.get("errors"):
        exception["errors_omitted"] = int(exception.get("errors_omitted", 0)) + len(exception["errors"])
        exception["errors"] = []
        exception["errors_omitted_reason"] = "json_cap"


def _reduce_terminal_snapshots(envelope: dict[str, Any]) -> None:
    terminals = envelope.get("terminals", {})
    for key in ("first", "last"):
        if terminals.get(key) is not None:
            terminals[key] = {"omitted_reason": "json_cap"}
            terminals["snapshots_omitted_reason"] = "json_cap"


def _reduce_notes_and_omissions(envelope: dict[str, Any]) -> None:
    qualifications = envelope.get("qualifications", {})
    if qualifications.get("notes"):
        qualifications["notes_dropped"] = int(qualifications.get("notes_dropped", 0)) + len(
            qualifications["notes"]
        )
        qualifications["notes"] = []
        qualifications["notes_omitted_reason"] = "json_cap"
    observation = envelope.get("observation", {})
    if observation.get("oversize_omissions"):
        observation["oversize_omissions_count"] = len(observation["oversize_omissions"])
        observation["oversize_omissions"] = []
        observation["oversize_omissions_omitted_reason"] = "json_cap"
    if observation.get("observation_limits"):
        observation["observation_limits_omitted_reason"] = "json_cap"
        observation["observation_limits"] = []
