"""Passive SDK diagnostic contracts against the canonical repository redactor."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field

import pytest


ENVELOPE_SCHEMA = "mastermind.bot.sdk_diagnostic.v1"
JSON_CAP_BYTES = 16384


# -- staging fixture -----------------------------------------------------------


@pytest.fixture()
def sdk_diag():
    from brain import sdk_diagnostics
    return sdk_diagnostics


# -- SDK-shaped fixtures (no SDK dependency) -----------------------------------


@dataclass
class ResultMessage:
    subtype: str = "success"
    is_error: bool = False
    result: str = "done"
    errors: list = field(default_factory=list)


@dataclass
class ToolUseBlock:
    id: str = "tu_1"
    name: str = "bash"
    input: dict = field(default_factory=dict)


@dataclass
class ToolResultBlock:
    tool_use_id: str = "tu_1"
    content: object = "ok"
    is_error: bool = False


@dataclass
class TextBlock:
    text: str = "hi"


@dataclass
class UserMessage:
    content: list = field(default_factory=list)


@dataclass
class AssistantMessage:
    content: list = field(default_factory=list)


class StructuredError(Exception):
    def __init__(self, message, *, subtype="error", is_error=True, errors=None, result=""):
        super().__init__(message)
        self.subtype = subtype
        self.is_error = is_error
        self.errors = list(errors or [])
        self.result = result


class CodedExit(Exception):
    def __init__(self, code):
        super().__init__("process exited")
        self.exit_code = code


def raiser(exc):
    def fail(self):
        raise exc

    return fail


# A class named exactly like the real SDK terminal type, whose every allowlisted
# property raises: observation must qualify the failure, never propagate it.
RaisingResultMessage = type(
    "ResultMessage",
    (),
    {
        "is_error": property(raiser(ValueError("refused is_error"))),
        "subtype": property(raiser(RuntimeError("refused subtype"))),
        "result": property(raiser(OSError("refused result"))),
        "errors": property(raiser(KeyError("refused errors"))),
    },
)


def make_collector(sdk_diag, **overrides):
    kwargs = {"run_id": "run-1", "book": "bot.book", "role": "worker", "candidate_ordinal": 7}
    kwargs.update(overrides)
    return sdk_diag.SDKInvocationDiagnostics(**kwargs)


def envelope_json_bytes(envelope):
    return len(
        json.dumps(envelope, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    )


# -- tests ---------------------------------------------------------------------


def test_success_terminal_snapshot_and_completeness(sdk_diag):
    collector = make_collector(sdk_diag, sdk_version="1.2.3", cli_version="4.5.6")
    collector.mark_query_entered()
    collector.observe_message(ResultMessage(subtype="success", is_error=False, result="did the thing"))
    envelope = collector.finish("exhausted")

    assert envelope["schema"] == ENVELOPE_SCHEMA
    assert envelope["identity"] == {
        "run_id": "run-1",
        "book": "bot.book",
        "role": "worker",
        "candidate_ordinal": 7,
    }
    dependencies = envelope["dependencies"]
    assert dependencies["sdk_package_version"] == {"declared_value": "1.2.3", "status": "declared_only"}
    assert dependencies["bundled_cli_version"]["status"] == "declared_only"
    assert "never_executed_version_proof" in dependencies["declaration_note"]

    observation = envelope["observation"]
    assert observation["sdk_messages_observed"] == 1
    assert observation["terminal_messages_observed"] == 1
    assert observation["query_entered_observed"] is True
    assert observation["query_entry_is_not_provider_start_proof"] is True

    terminals = envelope["terminals"]
    assert terminals["count"] == 1
    assert terminals["omitted_middle_count"] == 0
    assert terminals["terminal_presence"] == "single"
    snapshot = terminals["first"]
    assert snapshot["is_error"] is False
    assert snapshot["subtype"] == "success"
    assert snapshot["is_error_field_present"] is True
    assert snapshot["has_nonempty_text"] is True
    assert snapshot["successful_text_retained"] is False
    assert snapshot["retained_failure_text"] is None
    assert terminals["successful_result_text_retained"] is False
    assert "did the thing" not in json.dumps(envelope)

    qualifications = envelope["qualifications"]
    assert qualifications["completeness"] == "complete_limited_to_observed_sdk_messages"
    assert qualifications["effect_reconciliation"] == "not_performed"
    assert envelope["exception"]["observed"] is False
    # No verdict fields of any kind at the top level.
    assert not ({"ok", "error", "text", "result", "retry", "accepted", "verdict"} & set(envelope))
    json.dumps(envelope, allow_nan=False)
    assert envelope_json_bytes(envelope) <= JSON_CAP_BYTES


def test_contradictory_success_subtype_with_is_error_true(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(ResultMessage(subtype="success", is_error=True, result="weird state"))
    envelope = collector.finish("exhausted")

    snapshot = envelope["terminals"]["last"]
    assert snapshot["is_error"] is True
    assert snapshot["subtype"] == "success"
    assert snapshot["contradictory_success_with_is_error"] is True
    assert "contradictory_terminal_success_with_is_error" in envelope["qualifications"]["notes"]
    # Contradiction is reported, never resolved by the collector.
    assert envelope["qualifications"]["effect_reconciliation"] == "not_performed"


def test_old_sdk_generic_exception(sdk_diag):
    collector = make_collector(sdk_diag, run_id=None, book=None, role=None)
    collector.mark_query_entered()
    try:
        raise RuntimeError("provider exploded mid-stream")
    except RuntimeError as exception:
        envelope = collector.finish("raised", exception)

    assert envelope["identity"]["run_id"] is None
    assert envelope["identity"]["book"] is None
    assert envelope["identity"]["role"] is None
    assert envelope["exit"]["end_state"] == "raised"
    assert envelope["exit"]["exception_class"] == "RuntimeError"
    assert "provider exploded mid-stream" in envelope["exit"]["exception_text"]
    assert envelope["exit"]["exit_code"] is None

    projection = envelope["exception"]
    assert projection["observed"] is True
    assert projection["exception_class"] == "RuntimeError"
    assert projection["is_error_field_present"] is False
    assert projection["subtype_field_present"] is False
    assert projection["errors_field_present"] is False
    assert projection["result_field_present"] is False
    assert projection["structured_projection_not_terminal_message"] is True
    # The exception never became an invented terminal message.
    assert envelope["observation"]["terminal_messages_observed"] == 0
    assert envelope["terminals"]["count"] == 0
    assert envelope["qualifications"]["completeness"] == "partial_abnormal_end_state"


def test_structured_error_exception_projected_not_terminal(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    try:
        raise StructuredError(
            "structured failure", subtype="error", is_error=True, errors=["overloaded"], result="bad result text"
        )
    except StructuredError as exception:
        envelope = collector.finish("raised", exception)

    projection = envelope["exception"]
    assert projection["observed"] is True
    assert projection["is_error"] is True
    assert projection["is_error_field_present"] is True
    assert projection["subtype"] == "error"
    assert projection["subtype_field_present"] is True
    assert projection["errors"] == ["overloaded"]
    assert projection["result_field_present"] is True
    assert projection["has_nonempty_result_text"] is True
    assert "bad result text" in projection["retained_failure_text"]
    # Separately projected: terminal counters and snapshots untouched.
    assert envelope["observation"]["terminal_messages_observed"] == 0
    assert envelope["terminals"]["first"] is None
    assert projection["structured_projection_not_terminal_message"] is True
    assert envelope["qualifications"]["completeness"] == "partial_abnormal_end_state"


def test_failure_before_query_entry(sdk_diag):
    collector = make_collector(sdk_diag)
    envelope = collector.finish("raised")

    observation = envelope["observation"]
    assert observation["query_entered_observed"] is False
    assert "finish_before_query_entry_observed" in envelope["qualifications"]["notes"]
    assert observation["sdk_messages_observed"] == 0
    assert envelope["qualifications"]["completeness"] == "partial_abnormal_end_state"


def test_accepted_submission_outside_collector_authority(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(ResultMessage(subtype="success", is_error=False, result="ok"))
    envelope = collector.finish("exhausted")

    notes = envelope["qualifications"]["notes"]
    assert "accepted_submission_outside_collector_authority" in notes
    assert "observational_only_no_retry_classification" in notes
    assert envelope["qualifications"]["effect_reconciliation"] == "not_performed"
    # The collector never rules on acceptance, retries or outcomes.
    assert not ({"ok", "error", "text", "result", "retry", "accepted", "verdict"} & set(envelope))


def test_zero_observed_messages_does_not_imply_safe_retry(sdk_diag):
    collector = make_collector(sdk_diag)
    envelope = collector.finish("exhausted")

    assert envelope["observation"]["sdk_messages_observed"] == 0
    notes = envelope["qualifications"]["notes"]
    assert "zero_messages_observed_does_not_imply_safe_retry" in notes
    assert "counts_never_prove_absence_of_execution_effects" in envelope["observation"]["observation_limits"]
    assert envelope["qualifications"]["effect_reconciliation"] == "not_performed"
    assert envelope["qualifications"]["completeness"] == "incomplete_exhausted_without_terminal"
    assert envelope["terminals"]["terminal_presence"] == "absent"


def test_tool_results_counted_once_across_shapes(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    # A user message carrying a tool-result block plus ordinary text: one count.
    collector.observe_message(UserMessage(content=[ToolResultBlock(content="exit 0"), TextBlock(text="note")]))
    # A top-level tool-result block/message: one count, its text never a second.
    collector.observe_message(ToolResultBlock(content="direct output"))
    # Assistant tool-use block.
    collector.observe_message(AssistantMessage(content=[ToolUseBlock(), TextBlock(text="thinking")]))
    envelope = collector.finish("exhausted")

    observation = envelope["observation"]
    assert observation["sdk_messages_observed"] == 3
    assert observation["tool_result_blocks_observed"] == 2
    assert observation["tool_use_blocks_observed"] == 1
    assert observation["terminal_messages_observed"] == 0


def test_dict_fixture_equivalents_and_unknown_messages(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message({"type": "result", "subtype": "success", "is_error": False, "result": "ok"})
    collector.observe_message({"type": "user", "content": [{"type": "tool_result", "content": "r1"}]})
    collector.observe_message({"type": "assistant", "content": [{"type": "tool_use", "name": "bash"}]})
    collector.observe_message({"type": "system"})
    collector.observe_message({"subtype": "no_type_key"})
    collector.observe_message("plain string that is not a message object")
    envelope = collector.finish("exhausted")

    observation = envelope["observation"]
    assert observation["sdk_messages_observed"] == 6
    assert observation["terminal_messages_observed"] == 1
    assert observation["tool_result_blocks_observed"] == 1
    assert observation["tool_use_blocks_observed"] == 1
    assert observation["unknown_messages_observed"] == 3
    assert envelope["terminals"]["first"]["is_error"] is False


def test_multiple_terminals_first_last_and_omitted_middle(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(ResultMessage(subtype="success", is_error=False, result="first"))
    collector.observe_message(ResultMessage(subtype="error", is_error=True, result="middle boom"))
    collector.observe_message(ResultMessage(subtype="success_max", is_error=False, result="last"))
    envelope = collector.finish("exhausted")

    terminals = envelope["terminals"]
    assert terminals["count"] == 3
    assert terminals["omitted_middle_count"] == 1
    assert terminals["terminal_presence"] == "multiple"
    assert terminals["first"]["ordinal"] == 1
    assert terminals["first"]["subtype"] == "success"
    assert terminals["last"]["ordinal"] == 3
    assert terminals["last"]["subtype"] == "success_max"
    assert terminals["last"]["has_nonempty_text"] is True
    assert "multiple_terminals_observed" in envelope["qualifications"]["notes"]
    # The omitted middle terminal's text stays out entirely.
    assert "middle boom" not in json.dumps(envelope)
    assert envelope["qualifications"]["completeness"] == "complete_limited_to_observed_sdk_messages"


def test_raising_properties_and_malformed_values_qualified(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(RaisingResultMessage())
    collector.observe_message(
        ResultMessage(subtype="error", is_error="yes", result="boom", errors=[1, "real problem"])
    )
    envelope = collector.finish("exhausted")

    terminals = envelope["terminals"]
    assert terminals["count"] == 2
    hostile = terminals["first"]
    assert hostile["is_error"] is None
    assert hostile["subtype"] is None
    assert hostile["has_nonempty_text"] is None
    assert set(hostile["unreadable_fields"]) == {"is_error", "subtype", "result", "errors"}
    assert envelope["observation"]["failed_field_reads"] == 4

    malformed = terminals["last"]
    assert malformed["is_error"] is None
    assert malformed["is_error_field_present"] is True
    assert malformed["subtype"] == "error"
    assert malformed["errors"] == ["real problem"]
    # error-ish terminal: failure text retained, successful text never is
    assert malformed["retained_failure_text"] == "boom"
    assert malformed["failure_text_retained"] is True
    assert envelope["observation"]["non_string_errors_omitted"] == 1
    notes = json.dumps(envelope["qualifications"]["notes"])
    assert "is_error_not_strict_bool" in notes


def test_strict_signed_integer_exit_code(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    try:
        raise CodedExit(7)
    except CodedExit as exception:
        envelope = collector.finish("raised", exception)
    assert envelope["exit"]["exit_code"] == 7

    for bad in ("3", True, float("nan"), float("inf"), 2.5, [1]):
        collector = make_collector(sdk_diag)
        try:
            raise CodedExit(bad)
        except CodedExit as exception:
            envelope = collector.finish("raised", exception)
        assert envelope["exit"]["exit_code"] is None, bad
        assert "exit_code_not_strict_signed_int" in envelope["qualifications"]["notes"]

    collector = make_collector(sdk_diag)
    try:
        raise CodedExit(5.0)
    except CodedExit as exception:
        envelope = collector.finish("raised", exception)
    assert envelope["exit"]["exit_code"] is None


def test_interrupted_stream_stays_partial_even_with_terminal(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(ResultMessage(subtype="success", is_error=False, result="arrived"))
    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt as exception:
        envelope = collector.finish("interrupted", exception)

    assert envelope["exit"]["end_state"] == "interrupted"
    assert envelope["exit"]["exception_class"] == "KeyboardInterrupt"
    assert envelope["exit"]["exit_code"] is None
    assert envelope["terminals"]["count"] == 1
    assert envelope["qualifications"]["completeness"] == "partial_abnormal_end_state"
    assert "abnormal_end_state_stream_partial_even_if_terminal_seen" in envelope["qualifications"]["notes"]
    assert envelope["qualifications"]["cancellation_propagation"] == "caller_owned_not_proven_by_collector"


def test_invalid_end_state_is_a_caller_error(sdk_diag):
    collector = make_collector(sdk_diag)
    with pytest.raises(ValueError):
        collector.finish("completed")
    with pytest.raises(ValueError):
        collector.finish("")
    with pytest.raises(ValueError):
        collector.finish(None)


def test_malformed_identity_qualified_not_coerced(sdk_diag):
    collector = make_collector(sdk_diag, book=42, role=object(), candidate_ordinal=True)
    envelope = collector.finish("exhausted")

    assert envelope["identity"]["book"] is None
    assert envelope["identity"]["role"] is None
    assert envelope["identity"]["candidate_ordinal"] is None
    notes = envelope["qualifications"]["notes"]
    assert "caller_book_absent_or_malformed_stays_null" in notes
    assert "caller_role_absent_or_malformed_stays_null" in notes
    assert "candidate_ordinal_not_strict_int_stays_null" in notes


def test_unavailable_versions_declared_unavailable(sdk_diag):
    collector = make_collector(sdk_diag)
    envelope = collector.finish("exhausted")
    dependencies = envelope["dependencies"]
    assert dependencies["sdk_package_version"] == {"declared_value": None, "status": "unavailable"}
    assert dependencies["bundled_cli_version"] == {"declared_value": None, "status": "unavailable"}


def test_oversize_unicode_text_omitted_and_errors_list_bounded(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    big = "é" * 6000 + "ü" * 2000
    collector.observe_message(ResultMessage(subtype="error", is_error=True, result=big))
    many_errors = [f"problem {i} " + "y" * 140 for i in range(50)]
    collector.observe_message(
        ResultMessage(subtype="error", is_error=True, result="failed", errors=many_errors)
    )
    envelope = collector.finish("exhausted")

    first = envelope["terminals"]["first"]
    assert first["retained_failure_text"] is None
    assert first["failure_text_omitted"] is True
    omissions = envelope["observation"]["oversize_omissions"]
    assert any(
        item["field"] == "terminal_failure_text"
        and item["raw_length"] == len(big)
        and item["reason"] == "oversize_omitted_not_truncated"
        for item in omissions
    )
    assert big not in json.dumps(envelope)

    last = envelope["terminals"]["last"]
    assert len(last["errors"]) == 8
    assert last["errors_omitted"] == 42


def test_environment_secret_redacted_before_bounding(sdk_diag, monkeypatch):
    secret = "sb_secret_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"
    monkeypatch.setenv("BOT_PROVIDER_API_KEY", secret)
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    # Padding sized so a naive pre-redaction cut at the text bound would slice
    # straight through the secret and leave a surviving residue.
    collector.observe_message(
        ResultMessage(subtype="error", is_error=True, result=("x" * 20 + " ") * 9 + secret)
    )
    envelope = collector.finish("exhausted")

    retained = envelope["terminals"]["first"]["retained_failure_text"]
    assert retained.startswith("x")  # padding survived; only the secret was replaced
    rendered = json.dumps(envelope)
    assert secret not in rendered
    assert "sb_secret_" not in rendered
    assert "a1B2c3D4" not in rendered
    assert "<redacted>" in retained


def test_secret_shape_backstop_without_environment_identity(sdk_diag, monkeypatch):
    secret = "sk-ant-" + "Z" * 40
    monkeypatch.setenv("PROVIDER_TOKEN", secret)
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(
        ResultMessage(subtype="error", is_error=True, result="auth failed", errors=[f"token {secret}"])
    )
    envelope = collector.finish("exhausted")
    monkeypatch.delenv("PROVIDER_TOKEN")

    rendered = json.dumps(envelope)
    assert secret not in rendered
    assert "sk-ant-" not in rendered
    assert "<redacted>" in envelope["terminals"]["last"]["errors"][0]
    assert envelope["terminals"]["last"]["retained_failure_text"] == "auth failed"


def test_json_cap_backstop_reductions_and_bounded_by_construction(sdk_diag, monkeypatch):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    for index in range(40):
        collector.observe_message(
            ResultMessage(
                subtype="error",
                is_error=True,
                result=("failure " + "z" * 20 + " ") * 8,
                errors=[(f"e{index} " + "w" * 20 + " ") * 7 for _ in range(8)],
            )
        )

    # Only first/last snapshots are retained, so even a long stream stays well
    # inside the fixed 16384-byte budget with no reduction at all.
    envelope = collector.finish("exhausted")
    assert envelope_json_bytes(envelope) <= JSON_CAP_BYTES
    assert envelope["limits"]["serialized_json_cap_bytes"] == JSON_CAP_BYTES
    assert envelope["limits"]["json_cap_applied"] is False
    assert envelope["terminals"]["count"] == 40
    assert envelope["terminals"]["omitted_middle_count"] == 38

    # The cap is still a real backstop: force a tiny budget and the reduction
    # ladder must fire with visible reasons while typed counters survive.
    monkeypatch.setattr(sdk_diag, "JSON_CAP_BYTES", 2500)
    squeezed = collector.finish("exhausted")
    assert envelope_json_bytes(squeezed) <= 2500
    limits = squeezed["limits"]
    assert limits["serialized_json_cap_bytes"] == 2500
    assert limits["json_cap_applied"] is True
    assert limits["cap_reductions_applied"], limits
    assert squeezed["observation"]["terminal_messages_observed"] == 40
    assert squeezed["terminals"]["count"] == 40
    assert squeezed["identity"]["candidate_ordinal"] == 7
    assert squeezed["qualifications"]["effect_reconciliation"] == "not_performed"
    parsed = json.loads(json.dumps(squeezed, allow_nan=False))
    assert parsed["schema"] == ENVELOPE_SCHEMA


def test_fresh_copies_and_no_mutation_of_returned_or_observed_objects(sdk_diag):
    message = ResultMessage(subtype="error", is_error=True, result="failed badly", errors=["e1"])
    before = dataclasses.asdict(message)
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(message)

    envelope_one = collector.finish("exhausted")
    envelope_two = collector.finish("exhausted")
    assert envelope_one is not envelope_two

    envelope_one["terminals"]["last"]["retained_failure_text"] = "tampered"
    envelope_one["terminals"]["last"]["errors"].append("tampered")
    envelope_one["observation"]["sdk_messages_observed"] = 999
    assert envelope_two["terminals"]["last"]["retained_failure_text"] == "failed badly"
    assert envelope_two["terminals"]["last"]["errors"] == ["e1"]
    assert envelope_two["observation"]["sdk_messages_observed"] == 1
    # first and last snapshots are independent copies within one envelope
    envelope_one["terminals"]["first"]["subtype"] = "mutated"
    assert envelope_two["terminals"]["first"]["subtype"] == "error"

    # The observed SDK object was only ever read.
    assert dataclasses.asdict(message) == before
    envelope_three = collector.finish("exhausted")
    assert envelope_three["observation"]["sdk_messages_observed"] == 1
    assert envelope_three["terminals"]["last"]["retained_failure_text"] == "failed badly"


# Parent adversarial cases: actual SDK shapes, memory bounds and passive capture.

def _result_error_type():
    from claude_agent_sdk import _errors
    result_error = getattr(_errors, "ResultError", None)
    if result_error is None:
        pytest.skip("This SDK has no structured ResultError; real-shape qualification requires 0.2.168.")
    return result_error


def test_parent_real_sdk_error_data_is_retained_without_inventing_terminal(sdk_diag):
    result_error = _result_error_type()
    data = {
        "type": "result", "subtype": "success", "is_error": True,
        "result": "API Error: overloaded", "errors": ["overloaded"],
        "api_error_status": 503, "terminal_reason": "api_error", "stop_reason": "error",
    }
    exc = result_error("CLI reported failure", data=data, exit_code=1)
    assert not hasattr(exc, "is_error")
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    envelope = collector.finish("raised", exc)
    failure = envelope["exception"]
    assert failure["is_error"] is True
    assert failure["contradictory_success_with_is_error"] is True
    assert failure["retained_failure_text"] == "API Error: overloaded"
    assert failure["api_error_status"] == 503
    assert failure["terminal_reason"] == "api_error"
    assert failure["stop_reason"] == "error"
    assert envelope["observation"]["terminal_messages_observed"] == 0
    assert envelope["terminals"]["count"] == 0
    assert envelope["exit"]["exit_code"] == 1
    assert exc.data == data


def test_parent_real_terminal_then_error_does_not_double_count(sdk_diag):
    from claude_agent_sdk import ResultMessage as SDKResultMessage
    result_error = _result_error_type()
    msg = SDKResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=True,
        num_turns=1, session_id="fixture", result="API Error: overloaded",
        api_error_status=503, terminal_reason="api_error", stop_reason="error",
    )
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(msg)
    envelope = collector.finish("raised", result_error(
        "CLI reported failure",
        data={"subtype": "success", "is_error": True, "api_error_status": True,
              "terminal_reason": "api_error", "result": "API Error: overloaded"},
        exit_code=1,
    ))
    assert envelope["terminals"]["count"] == 1
    assert envelope["terminals"]["last"]["api_error_status"] == 503
    assert envelope["terminals"]["last"]["terminal_reason"] == "api_error"
    assert envelope["terminals"]["last"]["stop_reason"] == "error"
    assert envelope["exception"]["api_error_status"] is None  # bool is not an HTTP status
    assert envelope["exception"]["is_error"] is True


def test_parent_terminal_storage_is_bounded_during_the_stream(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    for index in range(150):
        collector.observe_message(ResultMessage(
            subtype="success", is_error=index == 74, result="observed message"))
    assert len(collector._terminals) <= 2  # cap retained state, not merely serialized output
    envelope = collector.finish("exhausted")
    assert envelope["terminals"]["count"] == 150
    assert envelope["terminals"]["first"]["ordinal"] == 1
    assert envelope["terminals"]["last"]["ordinal"] == 150
    assert envelope["terminals"]["omitted_middle_count"] == 148
    assert "contradictory_terminal_success_with_is_error" in envelope["qualifications"]["notes"]


def test_parent_integral_float_exit_is_not_a_typed_integer(sdk_diag):
    collector = make_collector(sdk_diag)
    envelope = collector.finish("raised", CodedExit(5.0))
    assert envelope["exit"]["exit_code"] is None


def test_parent_oversize_integer_cannot_break_json_contract(sdk_diag):
    collector = make_collector(sdk_diag, candidate_ordinal=1 << 20000)
    envelope = collector.finish("exhausted")
    assert envelope_json_bytes(envelope) <= JSON_CAP_BYTES
    assert envelope["identity"]["candidate_ordinal"] is None


def test_parent_surrogate_identity_cannot_break_utf8_contract(sdk_diag):
    collector = make_collector(sdk_diag, run_id="bad" + chr(0xD800))
    envelope = collector.finish("exhausted")
    assert envelope_json_bytes(envelope) <= JSON_CAP_BYTES
    assert envelope["identity"]["run_id"] is None


def test_parent_exception_stringification_is_not_invoked(sdk_diag):
    calls = []

    class GuardedError(Exception):
        def __str__(self):
            calls.append("stringified")
            raise AssertionError("foreign stringification must not run")

    exception = GuardedError("safe stored argument")
    collector = make_collector(sdk_diag)
    envelope = collector.finish("raised", exception)
    assert calls == []
    assert envelope["exit"]["exception_text"] == "safe stored argument"
    assert exception.args == ("safe stored argument",)


def test_parent_exit_read_failures_are_in_observation_counts(sdk_diag):
    class BrokenExit(Exception):
        @property
        def exit_code(self):
            raise ValueError("unreadable exit code")

    collector = make_collector(sdk_diag)
    envelope = collector.finish("raised", BrokenExit("original failure"))
    assert envelope["observation"]["failed_field_reads"] == 1
    assert envelope["exit"]["exit_code"] is None


def test_parent_failed_observation_does_not_report_complete_capture(sdk_diag):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(RaisingResultMessage())
    envelope = collector.finish("exhausted")
    assert envelope["qualifications"]["completeness"].startswith("partial")


def test_parent_cap_reduction_updates_retention_flags(sdk_diag, monkeypatch):
    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(ResultMessage(
        subtype="error", is_error=True, result="provider failure " * 11))
    full = collector.finish("exhausted")
    monkeypatch.setattr(sdk_diag, "JSON_CAP_BYTES", envelope_json_bytes(full) - 32)
    reduced = collector.finish("exhausted")
    terminal = reduced["terminals"]["first"]
    assert terminal["retained_failure_text"] is None
    assert terminal["failure_text_retained"] is False
    assert terminal["failure_text_omitted"] is True


def test_parent_redactor_failure_cannot_escape_constructor(sdk_diag, monkeypatch):
    def broken_redactor(*args, **kwargs):
        raise RuntimeError("redactor unavailable")

    monkeypatch.setattr(sdk_diag, "sanitize_external_text", broken_redactor)
    collector = make_collector(sdk_diag)
    envelope = collector.finish("exhausted")
    assert envelope["identity"]["run_id"] is None
    assert envelope["identity"]["book"] is None
    assert envelope_json_bytes(envelope) <= JSON_CAP_BYTES


def test_parent_dict_subclass_does_not_execute_override(sdk_diag):
    calls = []

    class ForeignDict(dict):
        def get(self, *args, **kwargs):
            calls.append("get")
            return super().get(*args, **kwargs)

    collector = make_collector(sdk_diag)
    collector.mark_query_entered()
    collector.observe_message(ForeignDict(type="result", is_error=False, subtype="success"))
    envelope = collector.finish("exhausted")
    assert calls == []
    assert envelope["observation"]["unknown_messages_observed"] == 1
    assert envelope["terminals"]["count"] == 0
    assert envelope["qualifications"]["completeness"] == "incomplete_exhausted_without_terminal"
