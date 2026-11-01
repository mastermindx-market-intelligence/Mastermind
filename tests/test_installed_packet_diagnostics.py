"""Bounded diagnostics projection for installed packet refusals.

Exercises ``installed_packet_error_diagnostic`` only: exact recognition of
refusal messages this module actually authors, adversarial redaction of
hostile text, immediate-cause classification, and fail-closed behavior for
malformed or foreign errors.  Every case builds synthetic exceptions
locally; no collector, runner, live host, network or runtime fixture is
involved and no production read path is exercised.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from integrations.executive_mcp import installed as installed_module
from integrations.executive_mcp.installed import (
    installed_packet_error_diagnostic,
)
from integrations.executive_mcp.schemas import ERROR_CODES, GatewayError


class QuietBase(Exception):
    """An exception whose text is pure canary; the helper must not read it."""

    def __str__(self):
        return CANARY

    def __repr__(self):
        return CANARY


DIAGNOSTIC_KEYS = frozenset({
    "error_code",
    "stage",
    "category",
    "cause_class",
})

#: The complete finite stage vocabulary the projection may return.
EXPECTED_STAGES = frozenset({
    "SOURCE",
    "MACRO_PLAN",
    "MATERIALIZATION",
    "INNER_PACKET",
    "PACKET_BINDING",
    "POST_SEAL",
    "UNKNOWN",
})

#: The complete finite category vocabulary: authored refusal tails for the
#: templated families and the authored text for the exact refusals, plus the
#: fail-closed ``UNCLASSIFIED`` value.
EXPECTED_CATEGORIES = frozenset({
    "repository topology is unsafe",
    "observation failed",
    "HEAD is unavailable",
    "HEAD changed",
    "repository objects are incomplete",
    "worktree path set differs",
    "worktree bytes differ",
    "worktree observation failed",
    "admitted worktree omits read bytes",
    "admitted worktree is incomplete",
    "admitted worktree differs",
    "symlinks are unsupported",
    "tree is malformed",
    "tree is unsupported",
    "checkout is not clean",
    "content scope is invalid",
    "identity is ambiguous",
    "generation seal is unavailable",
    "generation seal failed",
    "exceeded its cumulative deadline",
    "installed Macro repository topology is unsafe",
    "installed Macro materialization plan is unavailable",
    "installed Macro path-list frontmatter is unsupported",
    "installed Macro materialization SHA differs",
    "installed Macro materialization failed",
    "installed Macro verified snapshot is unavailable",
    "installed boot-packet collector failed",
    "installed boot-packet collector emitted invalid JSON",
    "installed boot-packet collector emitted the wrong schema",
    "installed boot-packet collector exceeded its cumulative deadline",
    "installed Context record unavailable",
    "installed boot-packet roots changed",
    "installed boot-packet roots differ",
    "installed boot-packet SHA binding differs",
    "installed Macro source SHA changed",
    "installed Mastermind source SHA changed",
    "installed source changed during boot-packet read",
    "installed materialized Macro changed during boot-packet read",
    "installed snapshot seal is unavailable",
    "installed repository topology is unsafe",
    "UNCLASSIFIED",
})

#: The complete finite immediate-cause class vocabulary.
EXPECTED_CAUSE_CLASSES = frozenset({
    "NONE",
    "GATEWAY_ERROR",
    "PERMISSION_ERROR",
    "TIMEOUT_ERROR",
    "OS_ERROR",
    "VALUE_ERROR",
    "TYPE_ERROR",
    "OTHER",
})

#: Marker used to prove hostile text never reaches the projection output.
CANARY = "c4nary-SECRET-/etc/passwd-9f2e"

#: Positive recognition cases: (authored refusal message, expected stage,
#: expected category, typed error code carried by the raised GatewayError).
POSITIVE_CASES = (
    ("installed Mastermind source repository topology is unsafe",
     "SOURCE", "repository topology is unsafe", "grounding_changed"),
    ("installed Macro source worktree bytes differ",
     "SOURCE", "worktree bytes differ", "grounding_changed"),
    ("installed materialized Macro source HEAD is unavailable",
     "SOURCE", "HEAD is unavailable", "backend_unavailable"),
    ("installed Macro source generation seal failed",
     "SOURCE", "generation seal failed", "internal_error"),
    ("installed Mastermind source checkout is not clean",
     "SOURCE", "checkout is not clean", "backend_refused"),
    ("installed materialized Macro source repository objects "
     "are incomplete",
     "SOURCE", "repository objects are incomplete", "not_found"),
    ("installed Macro source symlinks are unsupported",
     "SOURCE", "symlinks are unsupported", "invalid_input"),
    ("installed Macro repository topology is unsafe",
     "SOURCE", "installed Macro repository topology is unsafe",
     "backend_unavailable"),
    ("installed repository topology is unsafe",
     "SOURCE", "installed repository topology is unsafe",
     "backend_unavailable"),
    ("installed Macro materialization plan is unavailable",
     "MACRO_PLAN", "installed Macro materialization plan is unavailable",
     "not_found"),
    ("installed Macro path-list frontmatter is unsupported",
     "MACRO_PLAN", "installed Macro path-list frontmatter is unsupported",
     "invalid_input"),
    ("installed Macro materialization SHA differs",
     "MATERIALIZATION", "installed Macro materialization SHA differs",
     "grounding_changed"),
    ("installed Macro materialization failed",
     "MATERIALIZATION", "installed Macro materialization failed",
     "backend_unavailable"),
    ("installed Macro verified snapshot is unavailable",
     "MACRO_PLAN", "installed Macro verified snapshot is unavailable",
     "not_found"),
    ("installed boot-packet collector failed",
     "INNER_PACKET", "installed boot-packet collector failed",
     "backend_unavailable"),
    ("installed boot-packet collector emitted invalid JSON",
     "INNER_PACKET", "installed boot-packet collector emitted invalid JSON",
     "internal_error"),
    ("installed boot-packet collector emitted the wrong schema",
     "INNER_PACKET",
     "installed boot-packet collector emitted the wrong schema",
     "internal_error"),
    ("installed boot-packet collector exceeded its cumulative deadline",
     "UNKNOWN",
     "installed boot-packet collector exceeded its cumulative deadline",
     "timeout"),
    ("installed Context record unavailable",
     "INNER_PACKET", "installed Context record unavailable", "not_found"),
    ("installed boot-packet SHA binding differs",
     "PACKET_BINDING", "installed boot-packet SHA binding differs",
     "grounding_changed"),
    ("installed boot-packet roots differ",
     "PACKET_BINDING", "installed boot-packet roots differ",
     "grounding_changed"),
    ("installed boot-packet roots changed",
     "PACKET_BINDING", "installed boot-packet roots changed",
     "grounding_changed"),
    ("installed Macro source SHA changed",
     "SOURCE", "installed Macro source SHA changed",
     "grounding_changed"),
    ("installed Mastermind source SHA changed",
     "SOURCE", "installed Mastermind source SHA changed",
     "grounding_changed"),
    ("installed source changed during boot-packet read",
     "POST_SEAL", "installed source changed during boot-packet read",
     "grounding_changed"),
    ("installed materialized Macro changed during boot-packet read",
     "POST_SEAL",
     "installed materialized Macro changed during boot-packet read",
     "grounding_changed"),
    ("installed snapshot seal is unavailable",
     "SOURCE", "installed snapshot seal is unavailable",
     "backend_unavailable"),
)

#: Adversarial or unsupported inputs that must stay unrecognized:
#: (message, description).  None of these texts is echoed back.
UNRECOGNIZED_CASES = (
    ("installed Macro source SHA changed\n" + CANARY, "newline suffix"),
    (" " + CANARY + " installed Macro source SHA changed",
     "secret prefix"),
    ("installed Macro source SHA changed " + CANARY, "secret suffix"),
    ("installed macro source sha changed", "case change"),
    ("installed Macro source SHA", "truncated message"),
    ("installed Macro source SHA changedCANCAN", "glued suffix"),
    ("the collector reported: installed Macro source SHA changed",
     "substring only"),
    ("installed Foreign source repository topology is unsafe",
     "foreign label"),
    ("installed Mastermind source worktree bytes differ, " + CANARY,
     "appended detail"),
    ("installed boot-packet timeout is invalid", "unmapped refusal"),
    ("read metadata exceeds the ingress byte limit", "ingress refusal"),
    ("read response exceeds the ingress byte limit", "ingress refusal"),
    ("installed reader is read-only", "read composition refusal"),
    ("", "empty message"),
)


def _assert_finite(diagnostic) -> None:
    """Every projection must carry exactly the four bounded fields."""
    assert set(diagnostic.keys()) == DIAGNOSTIC_KEYS
    assert diagnostic["error_code"] in ERROR_CODES
    assert diagnostic["stage"] in EXPECTED_STAGES
    assert diagnostic["category"] in EXPECTED_CATEGORIES
    assert diagnostic["cause_class"] in EXPECTED_CAUSE_CLASSES


@pytest.mark.parametrize(
    ["message", "stage", "category", "code"],
    [list(case) for case in POSITIVE_CASES],
)
def test_source_authored_refusal_is_recognized(
    message, stage, category, code
):
    error = GatewayError(code, message)
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["error_code"] == code
    assert diagnostic["stage"] == stage
    assert diagnostic["category"] == category
    assert diagnostic["cause_class"] == "NONE"


def test_positive_cases_cover_every_broad_stage():
    covered = {case[1] for case in POSITIVE_CASES}
    assert covered == EXPECTED_STAGES


@pytest.mark.parametrize(
    ["message", "description"],
    [list(case) for case in UNRECOGNIZED_CASES],
)
def test_adversarial_text_stays_unrecognized(message, description):
    error = GatewayError("internal_error", message)
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["stage"] == "UNKNOWN"
    assert diagnostic["category"] == "UNCLASSIFIED"
    assert CANARY not in json.dumps(diagnostic)


def test_non_gateway_error_fails_closed_without_message_inspection():
    error = ValueError("installed boot-packet roots differ")
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["error_code"] == "internal_error"
    assert diagnostic["stage"] == "UNKNOWN"
    assert diagnostic["category"] == "UNCLASSIFIED"
    assert diagnostic["cause_class"] == "NONE"


def test_poisoned_text_never_reaches_output():
    calls = []

    class _Poisoned(GatewayError):
        def __str__(self):
            calls.append("str")
            return CANARY

        def __repr__(self):
            calls.append("repr")
            return CANARY

    error = _Poisoned("internal_error", CANARY)
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["stage"] == "UNKNOWN"
    assert diagnostic["category"] == "UNCLASSIFIED"
    assert calls == []
    assert CANARY not in json.dumps(diagnostic)


def test_poisoned_args_and_attributes_stay_out_of_output():
    class _HostileArgs(Exception):
        def __init__(self):
            super().__init__(CANARY)
            self.filenames = CANARY
            self.stderr = CANARY

        @property
        def message(self):
            raise AssertionError("message must not be coerced")

    error = _HostileArgs()
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["stage"] == "UNKNOWN"
    assert CANARY not in json.dumps(diagnostic)


@pytest.mark.parametrize(
    ["cause", "expected"],
    [
        (None, "NONE"),
        (GatewayError("timeout", CANARY), "GATEWAY_ERROR"),
        (PermissionError(CANARY), "PERMISSION_ERROR"),
        (TimeoutError(CANARY), "TIMEOUT_ERROR"),
        (OSError(CANARY), "OS_ERROR"),
        (ValueError(CANARY), "VALUE_ERROR"),
        (TypeError(CANARY), "TYPE_ERROR"),
        (RuntimeError(CANARY), "OTHER"),
    ],
)
def test_immediate_cause_is_classified_finitely(cause, expected):
    error = GatewayError("timeout", "installed boot-packet roots differ")
    error.__cause__ = cause
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["cause_class"] == expected
    assert diagnostic["stage"] == "PACKET_BINDING"
    assert CANARY not in json.dumps(diagnostic)


def test_non_exception_cause_value_fails_closed_to_other():
    # ``__cause__`` assignment rejects non-exceptions, so garbage causes are
    # reached only through an overriding property; the projection must still
    # classify them finitely without echoing the value.
    class _GarbageCause(Exception):
        @property
        def __cause__(self):
            return CANARY

    error = GatewayError("timeout", "installed boot-packet roots differ")
    error.__class__ = _GarbageCause
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["cause_class"] == "NONE"
    assert diagnostic["stage"] == "UNKNOWN"
    assert CANARY not in json.dumps(diagnostic)


def test_unknown_cause_class_name_is_not_echoed():
    class _Zeta(QuietBase):
        pass

    error = GatewayError("timeout", "installed boot-packet roots differ")
    error.__cause__ = _Zeta()
    diagnostic = installed_packet_error_diagnostic(error)
    assert diagnostic["cause_class"] == "OTHER"
    _assert_finite(diagnostic)


def test_deep_and_cyclic_cause_chains_do_not_recurse():
    outer = GatewayError("timeout", "installed boot-packet roots differ")
    middle = GatewayError("backend_unavailable", CANARY)
    inner = GatewayError("backend_refused", CANARY)
    middle.__cause__ = inner
    outer.__cause__ = middle
    inner.__cause__ = outer  # cycle
    diagnostic = installed_packet_error_diagnostic(outer)
    _assert_finite(diagnostic)
    assert diagnostic["cause_class"] == "GATEWAY_ERROR"
    assert CANARY not in json.dumps(diagnostic)


@pytest.mark.parametrize(
    "tampered_code",
    ["not_a_code", "", 123, None, ("timeout",)],
)
def test_tampered_error_code_fails_closed(tampered_code):
    error = GatewayError("timeout", "installed boot-packet roots differ")
    error.code = tampered_code
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["error_code"] == "internal_error"
    assert diagnostic["stage"] == "PACKET_BINDING"


def test_tampered_message_attribute_fails_closed():
    error = GatewayError("timeout", "installed boot-packet roots differ")
    error.message = 12345
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    # Positional args are not a diagnostic input.
    assert diagnostic["stage"] == "UNKNOWN"


def test_garbage_inputs_fail_closed_without_raising():
    for garbage in (None, 42, object(), "installed boot-packet roots differ"):
        diagnostic = installed_packet_error_diagnostic(garbage)
        _assert_finite(diagnostic)
        assert diagnostic["error_code"] == "internal_error"
        assert diagnostic["stage"] == "UNKNOWN"
        assert diagnostic["category"] == "UNCLASSIFIED"
        assert diagnostic["cause_class"] == "NONE"


def test_raising_cause_property_does_not_break_projection():
    class _Hostile(Exception):
        @property
        def __cause__(self):
            raise RuntimeError(CANARY)

    error = GatewayError("timeout", "installed boot-packet roots differ")
    error.__class__ = _Hostile
    diagnostic = installed_packet_error_diagnostic(error)
    _assert_finite(diagnostic)
    assert diagnostic["cause_class"] == "NONE"
    assert diagnostic["stage"] == "UNKNOWN"
    assert CANARY not in json.dumps(diagnostic)


def test_error_object_is_left_unchanged():
    cause = OSError(CANARY)
    error = GatewayError("timeout", "installed boot-packet roots differ")
    error.__cause__ = cause
    before = (
        error.code, error.message, error.args, error.__cause__,
        error.__suppress_context__, error.__traceback__,
    )
    installed_packet_error_diagnostic(error)
    after = (
        error.code, error.message, error.args, error.__cause__,
        error.__suppress_context__, error.__traceback__,
    )
    assert before == after
    assert error.args is before[2]
    assert error.__cause__ is cause


def test_projection_is_fresh_per_call_and_bounded():
    first = installed_packet_error_diagnostic(
        GatewayError("timeout", "installed boot-packet roots differ")
    )
    second = installed_packet_error_diagnostic(
        GatewayError("timeout", "installed boot-packet roots differ")
    )
    assert first == second
    assert first is not second
    serialized = json.dumps(first)
    _assert_finite(first)
    assert len(serialized) <= 512
    assert CANARY not in serialized


def test_error_codes_vocabulary_is_unchanged():
    assert ERROR_CODES == (
        "invalid_input",
        "grounding_unavailable",
        "grounding_changed",
        "identity_unverified",
        "backend_unavailable",
        "backend_refused",
        "authority_refused",
        "not_found",
        "output_too_large",
        "timeout",
        "production_write_disabled",
        "internal_error",
    )


def test_recognition_table_is_traceable_to_authored_text():
    module = installed_module
    table = module._INSTALLED_DIAGNOSTIC_TABLE
    labels = module._INSTALLED_DIAGNOSTIC_LABELS
    tails = module._INSTALLED_DIAGNOSTIC_TAIL_STAGES
    authored_exact = set(module._INSTALLED_DIAGNOSTIC_EXACT_STAGES)
    assert len(table) <= len(labels) * len(tails) + len(authored_exact)
    for message, (stage, category) in table.items():
        assert stage in EXPECTED_STAGES
        assert category in EXPECTED_CATEGORIES
        if message in authored_exact:
            assert category == message
            continue
        recognized = False
        for label in labels:
            prefix = "installed " + label + " "
            if message.startswith(prefix) and message[len(prefix):] in tails:
                assert category == message[len(prefix):]
                recognized = True
        assert recognized, message

    # Bind recognition to actual GatewayError call expressions, rather than
    # merely checking the diagnostic table against its own constants.
    source = ast.parse(Path(module.__file__).read_text())
    authored = set()
    for node in ast.walk(source):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "GatewayError" and len(node.args) > 1):
            continue
        message = node.args[1]
        if isinstance(message, ast.Constant) and type(message.value) is str:
            authored.add(message.value)
        elif isinstance(message, ast.JoinedStr) and all(
            isinstance(part, ast.Constant) and type(part.value) is str
            or isinstance(part, ast.FormattedValue)
            and isinstance(part.value, ast.Name) and part.value.id == "label"
            for part in message.values
        ):
            for label in labels:
                authored.add("".join(
                    part.value if isinstance(part, ast.Constant) else label
                    for part in message.values
                ))
    assert set(table) <= authored


def test_str_subclass_cannot_smuggle_arbitrary_code():
    class Poison(str):
        def __eq__(self, other):
            return True

    error = GatewayError("backend_unavailable", "installed boot-packet roots differ")
    error.code = Poison(CANARY)
    diagnostic = installed_packet_error_diagnostic(error)
    assert diagnostic["error_code"] == "internal_error"
    assert CANARY not in json.dumps(diagnostic)


def test_str_subclass_message_never_runs_hash_or_equality():
    calls = []

    class Poison(str):
        def __hash__(self):
            calls.append("hash")
            raise RuntimeError(CANARY)

    error = GatewayError("backend_unavailable", "installed boot-packet roots differ")
    error.message = Poison("installed boot-packet roots differ")
    diagnostic = installed_packet_error_diagnostic(error)
    assert diagnostic["stage"] == "UNKNOWN"
    assert diagnostic["category"] == "UNCLASSIFIED"
    assert calls == []


def test_missing_message_does_not_fall_back_to_args():
    error = GatewayError("backend_unavailable", "installed boot-packet roots differ")
    del error.message
    assert error.args == ("installed boot-packet roots differ",)
    diagnostic = installed_packet_error_diagnostic(error)
    assert diagnostic["stage"] == "UNKNOWN"
    assert diagnostic["category"] == "UNCLASSIFIED"


@pytest.mark.parametrize("message,stage", [
    ("installed Macro source SHA changed", "SOURCE"),
    ("installed Mastermind source SHA changed", "SOURCE"),
    ("installed snapshot seal is unavailable", "SOURCE"),
    ("installed boot-packet collector exceeded its cumulative deadline", "UNKNOWN"),
    ("installed Macro verified snapshot is unavailable", "MACRO_PLAN"),
])
def test_shared_or_early_refusals_do_not_fabricate_later_stage(message, stage):
    diagnostic = installed_packet_error_diagnostic(GatewayError("backend_unavailable", message))
    assert diagnostic["stage"] == stage


def test_foreign_exception_attributes_are_not_inspected():
    calls = []

    class Poison(Exception):
        def __getattribute__(self, name):
            if name in {"message", "args", "code", "__cause__"}:
                calls.append(name)
                raise RuntimeError(CANARY)
            return super().__getattribute__(name)

    diagnostic = installed_packet_error_diagnostic(Poison())
    assert diagnostic["stage"] == "UNKNOWN"
    assert diagnostic["error_code"] == "internal_error"
    assert calls == []
