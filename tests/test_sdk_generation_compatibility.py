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
