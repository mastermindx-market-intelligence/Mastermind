#!/usr/bin/env python3
"""Task-only tests for the 23-case provider-entry JUnit module gate.

Every document exercised here is synthetic JUnit XML built in memory or in
the pytest temporary directory: no real provider-entry fixture test is ever
collected or executed, no production source is read and no network, host or
credential effect exists. The accepted single-node helper is materialized
beside the gate from its frozen bytes; the tests pin those bytes by SHA-256
so the "reuse the accepted helper unchanged" contract stays machine-checked.
"""

import hashlib
import importlib.util
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
# The gate lives beside this test file in the task layout and inside the
# ``h1_ci_fixture`` package directory in the real repository layout.
_GATE_CANDIDATES = (
    os.path.join(_HERE, "require_provider_entry.py"),
    os.path.join(_HERE, "h1_ci_fixture", "require_provider_entry.py"),
)
_GATE_PATH = next(
    (path for path in _GATE_CANDIDATES if os.path.isfile(path)), None
)
if _GATE_PATH is None:
    raise ImportError(
        "require_provider_entry.py not found beside test_h1_provider_module_gate.py"
    )

_GATE_DIR = os.path.dirname(os.path.abspath(_GATE_PATH))
_HELPER_PATH = os.path.join(_GATE_DIR, "require_positive.py")
_HELPER_SHA256 = "4e613519940efb3794432076d1c955ecaa6e209829415744b9c0094b36c26560"


def _load_gate_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = _load_gate_module(_GATE_PATH, "require_provider_entry_under_test")

COMPILED_CASE_PREFIX = "test_actual_compiled_c_executor_model_and_original_result["
COMPILED_CASE_NAMES = tuple(
    name for name in GATE.EXPECTED_NAMES if name.startswith(COMPILED_CASE_PREFIX)
)
assert len(COMPILED_CASE_NAMES) == 5  # the five actual compiled cases
BOTH_PROPERTIES = ("actual_executor_identity", "actual_executor_command_utf8_nul")


# --- synthetic JUnit document builder -------------------------------------


def _escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _document(
    names=None,
    counters=None,
    classname=None,
    properties=None,
    property_value="inert-recorded-value",
    case_body=None,
    suite_children="",
    root_children="",
    suite_attributes="",
    case_attributes="",
):
    """Build a synthetic JUnit document; every argument is an injection point."""
    if names is None:
        names = list(GATE.EXPECTED_NAMES)
    if counters is None:
        counters = {"tests": "23", "errors": "0", "failures": "0", "skipped": "0"}
    if classname is None:
        classname = GATE.EXPECTED_CLASSNAME
    if properties is None:
        properties = {}
    counters_text = "".join(
        ' %s="%s"' % (key, _escape(value)) for key, value in sorted(counters.items())
    )
    case_lines = []
    for name in names:
        inner = "".join(
            '<property name="%s" value="%s" />' % (_escape(item), _escape(property_value))
            for item in properties.get(name, ())
        )
        if inner:
            inner = "<properties>%s</properties>" % inner
        if case_body is not None:
            inner += case_body(name)
        case_lines.append(
            '  <testcase classname="%s" name="%s"%s>%s</testcase>'
            % (_escape(classname), _escape(name), case_attributes, inner)
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        '  <testsuite name="pytest"%s%s>\n'
        "%s%s\n"
        "  </testsuite>%s\n"
        "</testsuites>\n"
    ) % (
        counters_text,
        suite_attributes,
        "\n".join(case_lines),
        suite_children,
        root_children,
    )


def _child_body(target, markup):
    """Case-body hook appending ``markup`` inside one named testcase only."""
    return lambda name: markup if name == target else ""


def _expect_rejection(raw):
    """Every invalid input raises the one fixed, nonsecret ValueError."""
    with pytest.raises(ValueError) as excinfo:
        GATE.validate_report(raw)
    assert excinfo.value.args == (GATE.REJECT_MESSAGE,)


# --- reuse of the accepted helper -----------------------------------------


def test_gate_reuses_accepted_helper_unchanged():
    assert GATE._HELPER is not None
    assert GATE._HELPER_PATH == _HELPER_PATH  # fixed sibling path
    with open(_HELPER_PATH, "rb") as handle:
        assert hashlib.sha256(handle.read()).hexdigest() == _HELPER_SHA256
    assert GATE.MAX_REPORT_BYTES == GATE._HELPER.MAX_REPORT_BYTES == 65536
    assert callable(GATE._HELPER._parse_report)


# --- accepted documents ---------------------------------------------------


def test_validate_report_returns_none_for_valid_23_without_properties():
    assert GATE.validate_report(_document().encode("utf-8")) is None


def test_document_order_is_not_authoritative():
    rotated = list(GATE.EXPECTED_NAMES[11:] + GATE.EXPECTED_NAMES[:11])
    assert rotated != list(GATE.EXPECTED_NAMES)
    assert GATE.validate_report(_document(names=rotated).encode("utf-8")) is None


def test_five_compiled_cases_with_both_properties_are_accepted():
    properties = {name: BOTH_PROPERTIES for name in COMPILED_CASE_NAMES}
    assert GATE.validate_report(_document(properties=properties).encode("utf-8")) is None


def test_properties_on_every_case_are_accepted():
    properties = {name: ("actual_executor_identity",) for name in GATE.EXPECTED_NAMES}
    assert GATE.validate_report(_document(properties=properties).encode("utf-8")) is None


def test_mixed_harmless_property_blocks_are_accepted():
    names = list(GATE.EXPECTED_NAMES)
    properties = {
        names[0]: ("actual_executor_command_utf8_nul",),
        names[22]: BOTH_PROPERTIES,
    }
    assert GATE.validate_report(_document(properties=properties).encode("utf-8")) is None


def test_inert_suite_and_case_metadata_are_accepted():
    raw = _document(
        suite_attributes=' time="1.25" timestamp="2026-10-31T00:00:00" hostname="localhost"',
        case_attributes=' time="0.01" file="tests/test_paid_provider_entry_linux.py" line="12"',
        properties={COMPILED_CASE_NAMES[0]: ("actual_executor_identity",)},
    ).encode("utf-8")
    assert GATE.validate_report(raw) is None


def test_predefined_entity_references_are_accepted():
    raw = _document(case_attributes=' file="a &amp; b &lt; c"').encode("utf-8")
    assert GATE.validate_report(raw) is None


def test_property_values_are_never_authority():
    properties = {COMPILED_CASE_NAMES[2]: BOTH_PROPERTIES}
    raw = _document(
        properties=properties,
        property_value='nul-bytes &amp; "quotes" 999999 ignored',
    ).encode("utf-8")
    assert GATE.validate_report(raw) is None


# --- testcase inventory rejections ----------------------------------------


def test_missing_case_is_rejected():
    _expect_rejection(_document(names=list(GATE.EXPECTED_NAMES)[:-1]).encode("utf-8"))


def test_duplicated_replacement_case_is_rejected():
    names = list(GATE.EXPECTED_NAMES)
    names[7] = names[0]
    _expect_rejection(_document(names=names).encode("utf-8"))


def test_extra_duplicate_case_is_rejected():
    names = list(GATE.EXPECTED_NAMES) + [GATE.EXPECTED_NAMES[3]]
    _expect_rejection(_document(names=names).encode("utf-8"))


def test_replacement_by_other_inventory_name_is_rejected():
    names = list(GATE.EXPECTED_NAMES)
    names[20] = COMPILED_CASE_NAMES[0]
    _expect_rejection(_document(names=names).encode("utf-8"))


def test_extra_unknown_case_is_rejected():
    names = list(GATE.EXPECTED_NAMES) + ["test_case_never_frozen_for_this_gate"]
    _expect_rejection(_document(names=names).encode("utf-8"))


def test_adverse_case_name_is_rejected():
    names = list(GATE.EXPECTED_NAMES)
    names[2] = "Test_Actual_Compiled_C_Executor_Model_And_Original_Result[None]"
    _expect_rejection(_document(names=names).encode("utf-8"))


@pytest.mark.parametrize(
    "classname",
    [
        "tests.test_paid_initializer",
        "Tests.Test_Paid_Provider_Entry_Linux",
        "tests.test_paid_provider_entry_linu",
    ],
)
def test_wrong_classname_is_rejected(classname):
    _expect_rejection(_document(classname=classname).encode("utf-8"))


@pytest.mark.parametrize(
    "counters",
    [
        {"tests": "22", "errors": "0", "failures": "0", "skipped": "0"},
        {"tests": "23", "errors": "1", "failures": "0", "skipped": "0"},
        {"tests": "23", "errors": "0", "failures": "2", "skipped": "0"},
        {"tests": "23", "errors": "0", "failures": "0", "skipped": "1"},
        {"tests": "23", "errors": "0", "failures": "0"},
        {"tests": "023", "errors": "0", "failures": "0", "skipped": "0"},
    ],
)
def test_non_canonical_counters_are_rejected(counters):
    _expect_rejection(_document(counters=counters).encode("utf-8"))


# --- node and structure rejections ----------------------------------------


def test_skipped_node_is_rejected():
    markup = '<skipped type="pytest.skip" message="unexecuted" />'
    target = GATE.EXPECTED_NAMES[0]
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


def test_failure_node_is_rejected():
    markup = '<failure message="assert 1 == 2">traceback text</failure>'
    target = GATE.EXPECTED_NAMES[1]
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


def test_error_node_is_rejected():
    markup = '<error message="boom">setup crashed</error>'
    target = GATE.EXPECTED_NAMES[2]
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


def test_properties_under_suite_are_rejected():
    suite_children = (
        '<properties><property name="actual_executor_identity" value="x" /></properties>'
    )
    _expect_rejection(_document(suite_children=suite_children).encode("utf-8"))


def test_properties_under_root_are_rejected():
    root_children = (
        '<properties><property name="actual_executor_identity" value="x" /></properties>'
    )
    _expect_rejection(_document(root_children=root_children).encode("utf-8"))


def test_fake_testcase_inside_properties_is_rejected():
    target = GATE.EXPECTED_NAMES[5]
    markup = (
        '<properties><property name="actual_executor_identity" value="x" />'
        '<testcase classname="%s" name="hidden-fake-case" /></properties>'
        % _escape(GATE.EXPECTED_CLASSNAME)
    )
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


def test_property_directly_under_testcase_is_rejected():
    markup = '<property name="actual_executor_identity" value="x" />'
    target = GATE.EXPECTED_NAMES[6]
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


def test_second_properties_block_under_one_case_is_rejected():
    target = GATE.EXPECTED_NAMES[7]
    markup = (
        '<properties><property name="actual_executor_identity" value="x" /></properties>'
    )
    raw = _document(
        properties={target: ("actual_executor_command_utf8_nul",)},
        case_body=_child_body(target, markup),
    ).encode("utf-8")
    _expect_rejection(raw)


def test_unrecognized_element_under_testcase_is_rejected():
    markup = "<system-out>ignored</system-out>"
    target = GATE.EXPECTED_NAMES[8]
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


def test_element_deeper_than_property_is_rejected():
    markup = (
        '<properties><property name="actual_executor_identity" value="x">'
        "<deep-nest /></property></properties>"
    )
    target = GATE.EXPECTED_NAMES[9]
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


def test_duplicate_property_name_in_one_block_is_rejected():
    properties = {GATE.EXPECTED_NAMES[10]: ("actual_executor_identity",) * 2}
    _expect_rejection(_document(properties=properties).encode("utf-8"))


@pytest.mark.parametrize(
    "property_name",
    ["actual_executor_command", "os_username", "host", ""],
)
def test_unknown_property_name_is_rejected(property_name):
    markup = '<properties><property name="%s" value="x" /></properties>' % _escape(
        property_name
    )
    target = GATE.EXPECTED_NAMES[11]
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


def test_property_without_name_attribute_is_rejected():
    markup = '<properties><property value="x" /></properties>'
    target = GATE.EXPECTED_NAMES[12]
    _expect_rejection(_document(case_body=_child_body(target, markup)).encode("utf-8"))


# --- parser hardening rejections ------------------------------------------


def test_entity_declaration_is_rejected():
    valid = _document().encode("utf-8")
    assert GATE.validate_report(valid) is None
    doctype = b'<!DOCTYPE testsuites [<!ENTITY packed "payload">]>\n'
    _expect_rejection(doctype + valid)


def test_undefined_entity_reference_is_rejected():
    raw = _document(suite_attributes=' hostname="&outside;"').encode("utf-8")
    _expect_rejection(raw)


def test_malformed_xml_is_rejected():
    raw = _document().encode("utf-8")
    _expect_rejection(raw[:-40])
    _expect_rejection(raw + b"</testsuites>")


def test_empty_input_is_rejected():
    _expect_rejection(b"")


def test_undecodable_bytes_are_rejected():
    _expect_rejection(b"<testsuites>\xff\xfe</testsuites>")


def test_oversize_document_is_rejected():
    valid = _document().encode("utf-8")
    assert len(valid) <= GATE.MAX_REPORT_BYTES
    bloated = b"<!--" + b"a" * (GATE.MAX_REPORT_BYTES + 1) + b"-->" + valid
    _expect_rejection(bloated)


def test_text_input_is_rejected():
    _expect_rejection(_document())


# --- CLI: isolated interpreter, fixed output, no secrets -------------------


def _run_gate_cli(arguments):
    return subprocess.run(
        [sys.executable, "-I", _GATE_PATH, *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_cli_accepts_valid_report(tmp_path):
    path = tmp_path / "provider-entry-report.xml"
    properties = {name: BOTH_PROPERTIES for name in COMPILED_CASE_NAMES}
    path.write_bytes(_document(properties=properties).encode("utf-8"))
    completed = _run_gate_cli([str(path)])
    assert completed.returncode == 0
    assert completed.stdout == (GATE.ACCEPT_MESSAGE + "\n").encode("utf-8")
    assert completed.stderr == b""


def test_cli_rejects_invalid_report_with_fixed_line(tmp_path):
    path = tmp_path / "provider-entry-report.xml"
    counters = {"tests": "22", "errors": "0", "failures": "0", "skipped": "1"}
    path.write_bytes(_document(counters=counters).encode("utf-8"))
    completed = _run_gate_cli([str(path)])
    assert completed.returncode == 1
    assert completed.stderr == (GATE.REJECT_MESSAGE + "\n").encode("utf-8")
    assert completed.stdout == b""


def test_cli_missing_file_is_fixed_rejection(tmp_path):
    missing = tmp_path / "absent-report.xml"
    completed = _run_gate_cli([str(missing)])
    assert completed.returncode == 1
    assert completed.stderr == (GATE.REJECT_MESSAGE + "\n").encode("utf-8")
    assert completed.stdout == b""
    assert b"Traceback" not in completed.stderr
    assert str(missing).encode("utf-8") not in completed.stderr


@pytest.mark.skipif(
    os.geteuid() == 0, reason="unreadable file requires a non-root executor"
)
def test_cli_unreadable_file_is_fixed_rejection(tmp_path):
    path = tmp_path / "unreadable-report.xml"
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o000)
    os.close(descriptor)
    try:
        completed = _run_gate_cli([str(path)])
    finally:
        os.chmod(str(path), 0o600)
    assert completed.returncode == 1
    assert completed.stderr == (GATE.REJECT_MESSAGE + "\n").encode("utf-8")
    assert completed.stdout == b""


def test_cli_directory_argument_is_fixed_rejection(tmp_path):
    completed = _run_gate_cli([str(tmp_path)])
    assert completed.returncode == 1
    assert completed.stderr == (GATE.REJECT_MESSAGE + "\n").encode("utf-8")
    assert completed.stdout == b""


@pytest.mark.parametrize("arguments", ([], ["one", "two"]))
def test_cli_argument_count_is_fixed_rejection(arguments):
    completed = _run_gate_cli(arguments)
    assert completed.returncode == 1
    assert completed.stderr == (GATE.REJECT_MESSAGE + "\n").encode("utf-8")
    assert completed.stdout == b""


def test_cli_never_renders_report_content_or_path(tmp_path):
    path = tmp_path / "poisoned-provider-entry.xml"
    marker = "SECRET-octopus-314159"
    counters = {"tests": "21", "errors": "0", "failures": "0", "skipped": "2"}
    raw = _document(
        counters=counters,
        suite_attributes=' hostname="%s" notes="%s"'
        % (marker, _escape(str(path))),
    ).encode("utf-8")
    path.write_bytes(raw)
    completed = _run_gate_cli([str(path)])
    assert completed.returncode == 1
    rendered = completed.stdout + completed.stderr
    assert rendered == (GATE.REJECT_MESSAGE + "\n").encode("utf-8")
    assert marker.encode("utf-8") not in rendered
    assert str(path).encode("utf-8") not in rendered
    assert b"Traceback" not in rendered


# --- in-process main(): fixed lines only -----------------------------------


def test_main_accepts_valid_report_with_fixed_line(tmp_path, capsys):
    path = tmp_path / "report.xml"
    properties = {COMPILED_CASE_NAMES[0]: ("actual_executor_identity",)}
    path.write_bytes(_document(properties=properties).encode("utf-8"))
    assert GATE.main([str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == GATE.ACCEPT_MESSAGE + "\n"
    assert captured.err == ""


def test_main_rejects_invalid_report_with_fixed_line(tmp_path, capsys):
    path = tmp_path / "report.xml"
    path.write_bytes(_document(names=list(GATE.EXPECTED_NAMES)[:-1]).encode("utf-8"))
    assert GATE.main([str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.err == GATE.REJECT_MESSAGE + "\n"
    assert captured.out == ""
