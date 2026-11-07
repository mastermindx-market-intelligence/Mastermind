"""Real SDK generation contracts with a closed synthetic transport and unchanged Bot controls."""
from __future__ import annotations
import asyncio
import copy
import dataclasses
import importlib
import importlib.metadata
import json
import sys

import pytest
import claude_agent_sdk as sdk
from claude_agent_sdk import _errors
from claude_agent_sdk._internal.message_parser import parse_message
from claude_agent_sdk._internal.transport import Transport

from test_sdk_diagnostic_bridge import Harness, CANDIDATES

SDK_VERSION = importlib.metadata.version("claude-agent-sdk")
CLI_MODULE = importlib.import_module("claude_agent_sdk._cli_version")
CLI_VERSION = CLI_MODULE.__cli_version__
REAL_METADATA_VERSION = importlib.metadata.version
RESULT_ERROR = getattr(_errors, "ResultError", None)


def terminal(**changes):
    value = {
        "type": "result", "subtype": "success", "duration_ms": 1,
        "duration_api_ms": 1, "is_error": False, "num_turns": 1,
        "session_id": "fixture-sdk-generation", "result": "fixture answer",
        "errors": [], "total_cost_usd": 0.25,
        "usage": {"input_tokens": 11, "output_tokens": 7},
        "api_error_status": None, "terminal_reason": None, "stop_reason": "end_turn",
    }
    value.update(changes)
    return value


def plan(case):
    if case == "success":
        return [terminal()], False
    if case == "contradictory_clean_eof":
        return [terminal(is_error=True, result="fixture failure detail",
                         api_error_status=503, terminal_reason="api_error", stop_reason="error")], False
    if case == "terminal_then_exit":
        return [terminal(is_error=True, result="fixture failure detail",
                         api_error_status=503, terminal_reason="api_error", stop_reason="error")], True
    if case == "quota_text_only":
        return [terminal(is_error=True, result="API Error: quota exceeded (429 rate limit)",
                         api_error_status=429, terminal_reason="api_error", stop_reason="error")], True
    if case == "process_exit_before_terminal":
        return [], True
    if case == "malformed_result":
        return [{"type": "result", "subtype": "success"}], False
    raise AssertionError(case)


class ClosedTransport(Transport):
    """Only a recorded initialize/user handshake; no subprocess, network or SDK fallback."""
    def __init__(self, frames, trailing_exit):
        self.frames = copy.deepcopy(frames)
        self.trailing_exit = trailing_exit
        self.queue = asyncio.Queue()
        self.connected = 0
        self.closed = 0
        self.input_ends = 0
        self.write_types = []
        self.request_ids = []
        self.responses = []
        self.user_count = 0

    async def connect(self):
        self.connected += 1
        assert self.connected == 1

    async def write(self, data):
        for line in data.splitlines():
            message = json.loads(line)
            self.write_types.append(message["type"])
            if message["type"] == "control_request":
                assert message["request"]["subtype"] == "initialize"
                request_id = message["request_id"]
                assert type(request_id) is str and request_id
                self.request_ids.append(request_id)
                response = {"type": "control_response", "response": {
                    "subtype": "success", "request_id": request_id,
                    "response": {"capabilities": {}, "commands": [], "models": []},
                }}
                self.responses.append(copy.deepcopy(response))
                await self.queue.put(response)
            else:
                assert message["type"] == "user"
                assert message["message"] == {"role": "user", "content": "fixture prompt"}
                self.user_count += 1
                assert self.user_count == 1 and len(self.request_ids) == 1
                for frame in self.frames:
                    await self.queue.put(copy.deepcopy(frame))
                if self.trailing_exit:
                    await self.queue.put(_errors.ProcessError("fixture CLI exit", exit_code=1))
                else:
                    await self.queue.put(None)

    async def read_messages(self):
        while True:
            item = await self.queue.get()
            if item is None:
                return
            if isinstance(item, BaseException):
                raise item
            yield item

    async def close(self):
        self.closed += 1
        await self.queue.put(None)

    def is_ready(self):
        return bool(self.connected and not self.closed)

    async def end_input(self):
        self.input_ends += 1


class ActualGenerationHarness(Harness):
    def __init__(self, monkeypatch, case):
        self.actual_sdk_query = sdk.query
        self.case = case
        self.transports = []
        self.actual_options = []
        self.sdk_messages = []
        self.sdk_exceptions = []
        super().__init__(monkeypatch)
        # The inherited harness deliberately uses SimpleNamespace and declared
        # fixture versions. Restore the actual package's constructor/metadata.
        monkeypatch.setattr(self.cb, "_Options", sdk.ClaudeAgentOptions)
        monkeypatch.setattr(importlib.metadata, "version", REAL_METADATA_VERSION)
        monkeypatch.setitem(sys.modules, "claude_agent_sdk._cli_version", CLI_MODULE)

    async def query(self, *, prompt, options):
        assert type(options) is sdk.ClaudeAgentOptions
        assert options.permission_mode == "dontAsk"
        assert options.setting_sources == ["project"]
        assert options.allowed_tools == [] and options.add_dirs == []
        assert options.cwd == "/fixture/workspace" and options.model == "fixture-model"
        assert options.can_use_tool is None and options.session_store is None
        assert prompt == "fixture prompt"
        index = len(self.providers)
        assert index < 2, "Only the controlled original candidate and one success control exist"
        captured = dict(vars(options))
        # This actual SDK default is an IO stream, not serializable fixture data.
        # Assert its identity before replacing only its recorded representation.
        declared_stream = sdk.ClaudeAgentOptions.__dataclass_fields__["debug_stderr"].default
        assert captured["debug_stderr"] is declared_stream
        captured["debug_stderr"] = {"sdk_declared_default_identity_preserved": True}
        self.providers.append(("sdk", prompt, copy.deepcopy(captured)))
        self.timeline.append(("sdk", options.env["FIXTURE_CANDIDATE"]))
        self.actual_options.append(options)
        frames, trailing_exit = plan(self.case if index == 0 else "success")
        transport = ClosedTransport(frames, trailing_exit)
        self.transports.append(transport)
        try:
            async with asyncio.timeout(3):
                async for message in self.actual_sdk_query(prompt=prompt, options=options, transport=transport):
                    self.sdk_messages.append({
                        "class": type(message).__name__,
                        "fields": dataclasses.asdict(message) if dataclasses.is_dataclass(message) else None,
                    })
                    yield message
        except Exception as exc:
            self.sdk_exceptions.append({
                "class": type(exc).__name__, "repr": repr(exc),
                "exit_code": getattr(exc, "exit_code", None),
                "has_structured_data": type(getattr(exc, "data", None)) is dict,
            })
            raise

    def transport_summary(self):
        out = []
        for t in self.transports:
            assert t.connected == 1 and t.closed >= 1
            assert t.write_types == ["control_request", "user"]
            assert t.user_count == 1
            assert t.responses[0]["response"]["request_id"] == t.request_ids[0]
            out.append({"connected": t.connected, "closed": t.closed,
                        "write_types": t.write_types, "user_count": t.user_count})
        return out


def test_real_terminal_parser_and_collector_do_not_require_result_error(record_property):
    from brain.sdk_diagnostics import SDKInvocationDiagnostics
    raw = terminal(is_error=True, result="fixture failure detail", errors=["fixture failure"],
                   api_error_status=503, terminal_reason="api_error", stop_reason="error")
    before = copy.deepcopy(raw)
    message = parse_message(raw)
    assert type(message) is sdk.ResultMessage
    message_before = dataclasses.asdict(message)
    collector = SDKInvocationDiagnostics(run_id="fixture-sdk-generation", book="autonomous",
                                        role="deep", candidate_ordinal=0,
                                        sdk_version=SDK_VERSION, cli_version=CLI_VERSION)
    collector.mark_query_entered()
    collector.observe_message(message)
    envelope = collector.finish("exhausted")
    assert raw == before and dataclasses.asdict(message) == message_before
    assert envelope["terminals"]["count"] == 1
    last = envelope["terminals"]["last"]
    assert last["is_error"] is True and last["contradictory_success_with_is_error"] is True
    for name in ["api_error_status", "terminal_reason", "stop_reason"]:
        supported = name in sdk.ResultMessage.__dataclass_fields__
        assert getattr(message, name, None) == (raw[name] if supported else None)
        assert last[name] == (raw[name] if supported else None)
        assert last[name + "_field_present"] is supported
    assert envelope["dependencies"]["sdk_package_version"] == {
        "declared_value": SDK_VERSION, "status": "declared_only",
    }
    record_property("sdk_observation", json.dumps({
        "case": "actual_parser", "sdk": SDK_VERSION, "cli": CLI_VERSION,
        "result_error_type_available": RESULT_ERROR is not None,
        "message_fields": message_before, "diagnostic": envelope,
    }, sort_keys=True))


@pytest.mark.parametrize("case", [
    "success", "contradictory_clean_eof", "terminal_then_exit",
    "quota_text_only", "process_exit_before_terminal", "malformed_result",
])
def test_actual_options_public_query_and_parser_preserve_diagnostic_off_on_controls(monkeypatch, case, record_property):
    observations = []
    captures = []
    for enabled in (False, True):
        with monkeypatch.context() as mp:
            h = ActualGenerationHarness(mp, case)
            if not enabled:
                mp.setattr(h.cb, "_new_sdk_diagnostic", lambda *a: None)
                mp.setattr(h.cb, "_record_sdk_diagnostic", lambda *a: None)
            result = h.run([[]], candidates=CANDIDATES)
            legacy = h.legacy(result)
            transports = h.transport_summary()
            assert all(e["class"] != "TimeoutError" for e in h.sdk_exceptions)
            if case == "success":
                assert result["ok"] is True and result["text"] == "fixture answer"
                assert result.get("error") is None and h.sdk_exceptions == []
            if case == "malformed_result":
                assert result["ok"] is False and len(h.sdk_exceptions) == 1
                assert h.sdk_exceptions[0]["class"] == "MessageParseError"
                assert "Missing required field in result message: 'duration_ms'" in h.sdk_exceptions[0]["repr"]
            observations.append({"legacy": legacy, "transports": transports,
                                 "sdk_messages": h.sdk_messages, "sdk_exceptions": h.sdk_exceptions})
            if enabled:
                diagnostics = [r["provider_diagnostic"] for r in h.diagnostics()]
                assert len(diagnostics) == len(h.transports)
                for ordinal, d in enumerate(diagnostics):
                    assert d["identity"]["candidate_ordinal"] == ordinal
                    assert d["observation"]["query_entered_observed"] is True
                    assert d["dependencies"]["sdk_package_version"] == {
                        "declared_value": SDK_VERSION, "status": "declared_only",
                    }
                    assert d["dependencies"]["bundled_cli_version"] == {
                        "declared_value": CLI_VERSION, "status": "declared_only",
                    }
                first = diagnostics[0]
                if case == "success":
                    assert first["exit"]["end_state"] == "exhausted"
                    assert first["exception"]["observed"] is False
                if case == "malformed_result":
                    assert first["exit"]["end_state"] == "raised"
                    assert first["exception"]["exception_class"] == "MessageParseError"
                terminal_count = 0 if case in {"process_exit_before_terminal", "malformed_result"} else 1
                assert first["terminals"]["count"] == terminal_count
                if case in {"terminal_then_exit", "quota_text_only"}:
                    assert first["exception"]["exception_class"] == ("ResultError" if RESULT_ERROR else "Exception")
                    assert first["exit"]["exit_code"] == (1 if RESULT_ERROR else None)
                    assert first["exception"]["is_error"] == (True if RESULT_ERROR else None)
                if case == "process_exit_before_terminal":
                    assert first["exception"]["exception_class"] == ("ProcessError" if RESULT_ERROR else "Exception")
                    assert first["exit"]["exit_code"] == (1 if RESULT_ERROR else None)
                if case == "contradictory_clean_eof":
                    assert first["terminals"]["last"]["contradictory_success_with_is_error"] is True
                    assert result["ok"] is False and result["error"] == "sdk_terminal_error"
                    assert result["text"] == "fixture failure detail"
                if case == "quota_text_only":
                    assert len(h.providers) == (2 if RESULT_ERROR else 1)
                    assert len(h.cooling) == (1 if RESULT_ERROR else 0)
                else:
                    assert len(h.providers) == 1 and h.cooling == []
                captures.append({
                    "case": case, "sdk": SDK_VERSION, "cli": CLI_VERSION,
                    "result_error_type_available": RESULT_ERROR is not None,
                    "legacy": legacy, "transport": transports,
                    "sdk_messages": h.sdk_messages, "sdk_exceptions": h.sdk_exceptions,
                    "diagnostics": diagnostics,
                })
    assert observations[0] == observations[1]
    assert len(captures) == 1
    record_property("sdk_observation", json.dumps(captures[0], sort_keys=True))


# Local CR-RT-4 / #1714 composition regression proposal.
# This append-only test extension changes no production behavior.
from test_provider_refusal_book_lineage import BookRunHarness, ASOF, submission_args


class _ObservedAuthFailureTransport(ClosedTransport):
    """Observe the existing closed transport without changing its protocol."""

    def __init__(self, frames, trailing_exit):
        super().__init__(frames, trailing_exit)
        self.read_frames = 0
        self.read_process_errors = 0

    async def read_messages(self):
        try:
            async for frame in super().read_messages():
                self.read_frames += 1
                yield frame
        except _errors.ProcessError:
            self.read_process_errors += 1
            raise


class _BookSDKAuthFailureHarness(BookRunHarness):
    """Real book caller and allocator; only SDK transport/market inputs are fake."""

    def __init__(self, monkeypatch, root, *, status, phase, deny_second=False):
        import hashlib
        from brain import provider_waterfall
        from control_plane import run_events

        self.status, self.phase = status, phase
        self.deny_second = deny_second
        self.transports, self.sdk_errors, self.sdk_frames = [], [], []
        self.query_entries, self.accepted_bytes, self.failure_boxes = [], [], []
        self.unexpected_shared_module_calls = []
        self.sdk_exception_objects, self.diagnostic_completions = [], []
        self.guard_calls = 0
        self.bridge_result = None
        self.actual_sdk_query = sdk.query
        self.sha256 = lambda raw: hashlib.sha256(raw).hexdigest()
        super().__init__(monkeypatch, root, "autonomous", seed=False)

        # Caller-owned fixture provisioning; never infer a fresh book from failure.
        self.registry.data_dir(self.book).mkdir(parents=True, exist_ok=False)
        self.pa._save_account({
            "inception_date": ASOF, "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0, "positions": {},
            "spy_shares": None, "spy_inception_price": None,
        }, self.book)
        monkeypatch.setattr(self.module, "_build_prompt", lambda *a, **kw: "fixture prompt")
        monkeypatch.setattr(self.cb, "_Options", sdk.ClaudeAgentOptions)
        monkeypatch.setattr(
            self.cb, "_selected_backend", lambda override=None: override or "waterfall",
        )
        monkeypatch.setattr(self.kr, "all_cooling_info", lambda: {
            "all_cooling": True, "earliest_reset": None,
        })
        actual_event_append = run_events.append
        monkeypatch.setattr(run_events, "append", lambda event, *, root=None:
                            actual_event_append(event, root=root or self.governance))

        def unexpected_shared_modules():
            # The real inner key_rotor classifier produces the cooling marker;
            # the outer OAuth loop short-circuits on that marker. No Macro
            # classifier is substituted. Any unexpected use invalidates proof,
            # even if production's defensive exception handler catches this.
            self.unexpected_shared_module_calls.append(True)
            raise AssertionError("Unexpected Macro dependency in the closed OAuth fixture")

        monkeypatch.setattr(provider_waterfall, "_shared_modules", unexpected_shared_modules)
        monkeypatch.setattr(provider_waterfall, "provider_rungs", lambda _role: [
            {"provider": "oauth", **candidate, "cooling": False} for candidate in CANDIDATES
        ])

        # BookRunHarness forwards the actual caller's original arguments, adding
        # its optional fixture guard. Default None matches this pinned caller;
        # only the separate veto control supplies a callback.
        if deny_second:
            def guard():
                self.guard_calls += 1
                return None if self.guard_calls == 1 else False
            self.guard = guard

        actual_record_diagnostic = self.cb._record_sdk_diagnostic

        def observe_diagnostic_completion(state, run_id, end_state, exception=None):
            self.diagnostic_completions.append({
                "end_state": end_state,
                "exception_class": type(exception).__name__ if exception is not None else None,
                "same_actual_sdk_exception": any(exception is seen for seen in self.sdk_exception_objects),
            })
            return actual_record_diagnostic(state, run_id, end_state, exception)

        monkeypatch.setattr(self.cb, "_record_sdk_diagnostic", observe_diagnostic_completion)
        real_public_forward = self.cb.reason

        async def observe_public_result(prompt, **kwargs):
            result = await real_public_forward(prompt, **kwargs)
            self.bridge_result = copy.deepcopy(result)
            return result

        monkeypatch.setattr(self.cb, "reason", observe_public_result)
        actual_via_sdk = self.cb._via_sdk

        async def observe_failure_box(*args, **kwargs):
            try:
                return await actual_via_sdk(*args, **kwargs)
            finally:
                self.failure_boxes.append(copy.deepcopy(kwargs.get("failure_out")))

        monkeypatch.setattr(self.cb, "_via_sdk", observe_failure_box)

    def submission_observation(self):
        path = self.mcp.submission_path(self.book)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return {"state": "absent", "sha256": None, "bytes": 0}
        return {"state": "present", "sha256": self.sha256(raw), "bytes": len(raw)}

    async def query(self, *, prompt, options):
        assert type(options) is sdk.ClaudeAgentOptions
        assert options.permission_mode == "dontAsk"
        assert options.setting_sources == ["project"]
        assert options.env == {} and prompt == "fixture prompt"
        index = len(self.query_entries)
        self.query_entries.append({
            "ordinal": index, "submission_before_entry": self.submission_observation(),
            "caller_guard_supplied": self.guard is not None,
        })
        self.providers.append(("sdk", prompt, {"ordinal": index}))
        assert index < 2, "The closed fixture permits at most two SDK query entries"

        frames = []
        if index == 0:
            if self.phase == "accepted_submission":
                frames.extend([
                    {"type": "assistant", "message": {
                        "model": "synthetic-model", "content": [{
                            "type": "tool_use", "id": "composition-submit-1",
                            "name": "mcp__desk__submit_book",
                            "input": submission_args(self.book),
                        }],
                    }},
                    {"type": "user", "message": {"role": "user", "content": [{
                        "type": "tool_result", "tool_use_id": "composition-submit-1",
                        "content": "Synthetic local submission handler completed",
                        "is_error": False,
                    }]}},
                ])
            prose = ("API Error: 401 fixture authentication failed" if self.status == 401
                     else "API Error: 429 fixture rate limit")
            frames.append(terminal(
                is_error=True, result=prose, errors=[], api_error_status=self.status,
                terminal_reason="api_error", stop_reason="error",
            ))
        else:
            # No second tool or submission is simulated: entry itself is the
            # disputed replay boundary, not a claim of a duplicate target/fill.
            frames.append(terminal(result="Synthetic second provider completed"))
        transport = _ObservedAuthFailureTransport(frames, trailing_exit=(index == 0))
        self.transports.append(transport)

        try:
            async with asyncio.timeout(3):
                async for message in self.actual_sdk_query(
                    prompt=prompt, options=options, transport=transport,
                ):
                    blocks = getattr(message, "content", []) or []
                    tool_seen = any(
                        type(block).__name__ == "ToolUseBlock"
                        for block in (blocks if isinstance(blocks, list) else [])
                    )
                    self.sdk_frames.append({
                        "query_ordinal": index, "class": type(message).__name__,
                        "tool_use_seen": tool_seen,
                    })
                    yield message
                    # The real bridge has now observed the real SDK ToolUseBlock.
                    # Execute the existing real local handler before the later
                    # ToolResult/terminal/error is delivered to that bridge.
                    if index == 0 and self.phase == "accepted_submission" and tool_seen:
                        response = await self.mcp.submit_book.handler(submission_args(self.book))
                        accepted = self.mcp.read_submission(self.book)
                        assert accepted and len(accepted["holdings"]) == 1
                        assert "SUBMISSION REJECTED" not in json.dumps(response)
                        self.submitted.append(copy.deepcopy(accepted))
                        self.accepted_bytes.append(self.mcp.submission_path(self.book).read_bytes())
        except Exception as exc:
            self.sdk_exception_objects.append(exc)
            data = getattr(exc, "data", None)
            self.sdk_errors.append({
                "class": type(exc).__name__, "is_actual_result_error": isinstance(exc, RESULT_ERROR),
                "status": data.get("api_error_status") if isinstance(data, dict) else None,
                "repr": repr(exc), "query_ordinal": index,
            })
            raise


def _observe_book_sdk_auth_failure(monkeypatch, tmp_path, *, status, phase, deny_second=False):
    """Complete scenario validation before the test's final no-reentry assertion."""
    assert RESULT_ERROR is not None, "This qualification requires an SDK exposing ResultError"
    h = _BookSDKAuthFailureHarness(
        monkeypatch, tmp_path / "private-book", status=status, phase=phase,
        deny_second=deny_second,
    )
    initial = h.submission_observation()
    assert initial["state"] == "absent"
    out = h.module.run_autonomous(asof=ASOF, armed=True, force=True)

    # An unrelated assertion/fixture failure cannot become a policy reproduction.
    assert len(h.calls) == 1
    assert h.unexpected_shared_module_calls == []
    assert "before_provider_start" not in h.calls[0]
    assert len(h.sdk_errors) == 1
    error = h.sdk_errors[0]
    assert error["class"] == "ResultError" and error["is_actual_result_error"]
    assert error["status"] == status and str(status) in error["repr"]
    assert error["query_ordinal"] == 0
    assert h.transports and len(h.providers) == len(h.query_entries) == len(h.transports)
    assert all(t.connected == 1 and t.closed >= 1 for t in h.transports)
    assert all(t.write_types == ["control_request", "user"] and t.user_count == 1
               for t in h.transports)
    assert all(t.read_frames >= 2 for t in h.transports)
    assert h.transports[0].read_process_errors == 1
    assert all(t.read_process_errors == 0 for t in h.transports[1:])
    assert h.query_entries[0]["submission_before_entry"]["state"] == "absent"
    assert h.failure_boxes[0]["tool_activity_observed"] is (phase == "accepted_submission")
    assert len(h.checks) >= len(h.query_entries)
    assert all(check is h.guard for check in h.checks)
    final = h.submission_observation()
    accepted_identity = None
    if phase == "accepted_submission":
        assert len(h.submitted) == len(h.accepted_bytes) == 1
        assert any(frame["tool_use_seen"] for frame in h.sdk_frames)
        assert h.mcp.submission_path(h.book).read_bytes() == h.accepted_bytes[0]
        assert final["sha256"] == h.sha256(h.accepted_bytes[0])
        assert all(entry["submission_before_entry"]["sha256"] == final["sha256"]
                   for entry in h.query_entries[1:])
        row = h.module.load_decisions()[0]
        assert out["decided"] is True and out["target_status"] == "queued"
        assert row["decision_effective"] is True and row["target_status"] == "queued"
        assert row["target_sha256"]
        assert not out["executed"] and not h.pa._load_account(h.book)["positions"]
        accepted_identity = {
            "submission_sha256": final["sha256"], "submission_bytes": final["bytes"],
            "target_sha256": row["target_sha256"], "packet_id": row.get("packet_id"),
            "decision_run_id": row.get("run_id"), "target_status": row["target_status"],
        }
    else:
        assert phase == "pretool_absent"
        assert h.submitted == h.accepted_bytes == []
        assert not any(frame["tool_use_seen"] for frame in h.sdk_frames)
        assert final["state"] == "absent"
        assert all(entry["submission_before_entry"]["state"] == "absent"
                   for entry in h.query_entries)
        assert out["target_status"] == "rejected_no_submission"
    if deny_second:
        assert h.guard is not None and h.guard_calls == 2
        assert len(h.refusals) == 1 and "source admission revoked" in out["brain"]["error"]
    else:
        assert h.guard is None and h.refusals == []

    return {
        "schema": "mastermind.sdk_auth_submission_composition.v1",
        "scenario_complete": True, "fixture_source_base": "c3623f7b9804fee28fa8204775f952fb22fe3d98",
        "sdk_version": SDK_VERSION, "bundled_cli_version": CLI_VERSION,
        "status": status, "phase": phase, "explicit_late_veto_control": deny_second,
        "actual_caller_guard_argument_present": "before_provider_start" in h.calls[0],
        "effective_guard": "supplied_fixture_denial" if deny_second else "caller_default_none",
        "provider_start_check_count": len(h.checks), "guard_call_count": h.guard_calls,
        "refusal_count": len(h.refusals), "query_count": len(h.query_entries),
        "unexpected_shared_module_calls": len(h.unexpected_shared_module_calls),
        "query_entries": h.query_entries, "sdk_errors": h.sdk_errors,
        "transport_activity": [{
            "connected": t.connected, "closed": t.closed, "read_frames": t.read_frames,
            "read_process_errors": t.read_process_errors, "user_count": t.user_count,
        } for t in h.transports],
        "accepted_submission_count": len(h.submitted), "accepted_identity": accepted_identity,
        "initial_submission": initial, "final_submission": final,
        "captured_failure_boxes": h.failure_boxes,
        "candidate_repair": {
            "variant": "exception_replay_repair_candidate_v1",
            "final_bridge_error": (h.bridge_result or {}).get("error"),
            "final_bridge_ok": (h.bridge_result or {}).get("ok"),
            "inner_classifier_call_count": len(h.classifications),
            "inner_cooling_count": len(h.cooling),
            "diagnostic_completions": h.diagnostic_completions,
        },
        "final_provider_attempts": (h.bridge_result or {}).get("provider_attempts"),
        "final_provider_failures": (h.bridge_result or {}).get("provider_failures"),
        "paper_executions": len(out.get("executed") or []),
        "qualification_scope": "real book owner and SDK query over closed synthetic transport; no live provider or duplicate-fill claim",
    }


@pytest.mark.parametrize("phase,status", [
    pytest.param("accepted_submission", 401, id="post-submit-http401"),
    pytest.param("accepted_submission", 429, id="post-submit-http429"),
    pytest.param("pretool_absent", 401, id="pretool-absent-http401"),
    pytest.param("pretool_absent", 429, id="pretool-absent-http429"),
])
def test_actual_book_sdk_auth_failure_respects_submission_replay_boundary(
    monkeypatch, tmp_path, record_property, status, phase,
):
    observation = _observe_book_sdk_auth_failure(
        monkeypatch, tmp_path, status=status, phase=phase,
    )
    record_property("sdk_auth_submission_composition", json.dumps(observation, sort_keys=True))
    if phase == "accepted_submission":
        assert observation["query_count"] == 1, "SDK_POST_TOOL_REENTRY"
        repair = observation["candidate_repair"]
        assert repair["final_bridge_error"] == "sdk_terminal_error"
        assert repair["final_bridge_ok"] is False
        assert repair["inner_classifier_call_count"] == repair["inner_cooling_count"] == 0
        assert len(observation["final_provider_attempts"]) == 1
        assert repair["diagnostic_completions"] == [{
            "end_state": "raised", "exception_class": "ResultError",
            "same_actual_sdk_exception": True,
        }]
    else:
        assert observation["query_count"] == 2, "SDK_PRETOOL_CONTROL_NO_ADVANCE"


def test_actual_book_sdk_auth_failure_honors_supplied_late_veto(
    monkeypatch, tmp_path, record_property,
):
    observation = _observe_book_sdk_auth_failure(
        monkeypatch, tmp_path, status=401, phase="pretool_absent", deny_second=True,
    )
    record_property("sdk_auth_submission_composition", json.dumps(observation, sort_keys=True))
    assert observation["query_count"] == 1, "SDK_LATE_VETO_QUERY_ENTERED"
