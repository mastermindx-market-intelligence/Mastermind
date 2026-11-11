"""Tests for the fail-closed H1 JUnit positive proof gate.

``tests/h1_ci_fixture`` is not a package, so the helper is loaded by absolute
repo-relative path via :mod:`importlib.util`. The expected testcase identity
and the fixed output messages are frozen here on purpose (duplicating the
helper constants) so drift fails loudly; nothing is learned from any report.
The tests are self-contained: they run only on temp files and never touch a
real H1 fixture, container, network, or the repository's own reports.
"""

import contextlib
import importlib.util
import pathlib
import subprocess
import sys

_HELPER_PATH = pathlib.Path(__file__).resolve().parent / "h1_ci_fixture" / "require_positive.py"
_MODULE_NAME = "h1_ci_fixture_require_positive_standalone"

_SPEC = importlib.util.spec_from_file_location(_MODULE_NAME, _HELPER_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - collection guard
    raise ImportError("cannot locate tests/h1_ci_fixture/require_positive.py")
HELPER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(HELPER)

# Frozen contract, restated here so accidental helper drift fails.
EXPECTED_CLASSNAME = "tests.test_paid_initializer"
EXPECTED_NAME = "test_actual_nested_initializer_private_package_context_and_wire"
EXPECTED_REJECT_MESSAGE = (
    "h1 positive gate: rejected - JUnit report is not a valid "
    "single-passed positive proof for the required H1 testcase"
)
EXPECTED_ACCEPT_MESSAGE = "h1 positive gate: accepted - exactly one passed proof testcase"
EXPECTED_MAX_BYTES = 65536


def _case(classname=EXPECTED_CLASSNAME, name=EXPECTED_NAME, body=None):
    if body is None:
        return (
            f'<testcase classname="{classname}" name="{name}"'
            ' time="0.004" file="tests/test_paid_initializer.py" line="17"/>'
        )
    return f'<testcase classname="{classname}" name="{name}" time="0.004">{body}</testcase>'


def _suite(cases, attrs=None):
    if attrs is None:
        attrs = (
            'name="pytest" errors="0" failures="0" skipped="0" tests="1"'
            ' time="0.012" timestamp="2026-10-31T00:00:00.000000" hostname="runner"'
        )
    return f"<testsuite {attrs}>{cases}</testsuite>"


def _document(inner=""):
    return ('<?xml version="1.0" encoding="utf-8"?>' + inner).encode("utf-8")


def _valid_report():
    return _document(f"<testsuites>{_suite(_case())}</testsuites>")


@contextlib.contextmanager
def expect_rejection():
    """Assert ``validate_report`` raises ValueError with the fixed message."""
    try:
        yield
    except ValueError as error:
        assert str(error) == EXPECTED_REJECT_MESSAGE, (
            "rejection must carry the single fixed nonsecret message, "
            f"got: {str(error)!r}"
        )
        return
    raise AssertionError("validate_report accepted an invalid report")


def _run_cli(*arguments):
    return subprocess.run(
        [sys.executable, str(_HELPER_PATH), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_frozen_constants_match_contract():
    assert HELPER.EXPECTED_CLASSNAME == EXPECTED_CLASSNAME
    assert HELPER.EXPECTED_NAME == EXPECTED_NAME
    assert HELPER.MAX_REPORT_BYTES == EXPECTED_MAX_BYTES
    assert HELPER.REJECT_MESSAGE == EXPECTED_REJECT_MESSAGE
    assert HELPER.ACCEPT_MESSAGE == EXPECTED_ACCEPT_MESSAGE


def test_valid_pytest_xunit2_report_passes(tmp_path):
    raw = _valid_report()
    assert b'tests="1"' in raw and b'skipped="0"' in raw
    path = tmp_path / "h1-positive.xml"
    path.write_bytes(raw)
    assert HELPER.validate_report(path.read_bytes()) is None


def test_report_at_exact_size_limit_is_accepted():
    template = _document(
        '<testsuites><testsuite name="@PAD@" errors="0" failures="0"'
        ' skipped="0" tests="1">' + _case() + "</testsuite></testsuites>"
    ).decode("utf-8")
    pad = EXPECTED_MAX_BYTES - (len(template) - len("@PAD@"))
    assert pad > 0
    exact = template.replace("@PAD@", "a" * pad).encode("utf-8")
    assert len(exact) == EXPECTED_MAX_BYTES
    assert HELPER.validate_report(exact) is None


def test_oversize_report_rejected_before_identity_checks():
    filler = "a" * (EXPECTED_MAX_BYTES + 1024)
    raw = _document(
        f'<testsuites><testsuite name="{filler}" errors="0" failures="0"'
        ' skipped="0" tests="1">' + _case() + "</testsuite></testsuites>"
    )
    assert len(raw) > EXPECTED_MAX_BYTES
    with expect_rejection():
        HELPER.validate_report(raw)


def test_non_bytes_argument_rejected():
    with expect_rejection():
        HELPER.validate_report("<testsuites/>")


def test_skipped_node_rejected():
    raw = _document(f"<testsuites>{_suite(_case(body='<skipped type=\"pytest.skip\" message=\"docker image unavailable\"/>'))}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_failure_node_rejected():
    raw = _document(f"<testsuites>{_suite(_case(body='<failure message=\"assert 1 == 2\">CLASSIFIED-PRIVATE-TRACE</failure>'))}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_error_node_rejected():
    raw = _document(f"<testsuites>{_suite(_case(body='<error message=\"collection error\"/>'))}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_duplicate_testcase_node_rejected():
    raw = _document(f"<testsuites>{_suite(_case() + _case())}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_two_self_consistent_testcases_rejected():
    attrs = 'name="pytest" errors="0" failures="0" skipped="0" tests="2"'
    raw = _document(f"<testsuites>{_suite(_case() + _case(), attrs=attrs)}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_second_testsuite_rejected():
    suite = _suite(_case())
    raw = _document(f"<testsuites>{suite}{suite}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_missing_testcase_rejected():
    raw = _document(f"<testsuites>{_suite('')}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_missing_testsuite_rejected():
    raw = _document("<testsuites></testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_wrong_root_tag_rejected():
    raw = _document(_suite(_case()))
    with expect_rejection():
        HELPER.validate_report(raw)


def test_wrong_classname_rejected():
    raw = _document(f"<testsuites>{_suite(_case(classname='tests.test_other'))}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_wrong_name_rejected():
    raw = _document(f"<testsuites>{_suite(_case(name='test_something_else'))}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_missing_suite_counter_rejected():
    attrs = 'name="pytest" errors="0" failures="0" tests="1"'
    raw = _document(f"<testsuites>{_suite(_case(), attrs=attrs)}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_noncanonical_counter_rejected():
    attrs = 'name="pytest" errors="0" failures="0" skipped="00" tests="01"'
    raw = _document(f"<testsuites>{_suite(_case(), attrs=attrs)}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_lying_counter_rejected():
    # Canonical counters that under-report two executed testcases.
    raw = _document(f"<testsuites>{_suite(_case() + _case())}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_extra_element_under_suite_rejected():
    raw = _document(
        '<testsuites><testsuite name="pytest" errors="0" failures="0"'
        ' skipped="0" tests="1">' + _case() + "<properties/></testsuite></testsuites>"
    )
    with expect_rejection():
        HELPER.validate_report(raw)


def test_nested_elements_under_testcase_rejected():
    raw = _document(
        f"<testsuites>{_suite(_case(body='<props><p/></props>'))}</testsuites>"
    )
    with expect_rejection():
        HELPER.validate_report(raw)


def test_malformed_xml_rejected():
    raw = _valid_report()[:-25]
    with expect_rejection():
        HELPER.validate_report(raw)


def test_unclosed_tag_rejected():
    raw = _document("<testsuites><testsuite tests=\"1\" errors=\"0\" failures=\"0\" skipped=\"0\">")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_empty_report_rejected():
    with expect_rejection():
        HELPER.validate_report(b"")


def test_text_only_report_rejected():
    with expect_rejection():
        HELPER.validate_report(b"all tests passed, nothing to see")


def test_doctype_declaration_rejected():
    raw = b"<!DOCTYPE testsuites><testsuites></testsuites>"
    with expect_rejection():
        HELPER.validate_report(raw)


def test_external_doctype_declaration_rejected():
    raw = (
        '<!DOCTYPE testsuites SYSTEM "http://127.0.0.1:9/evil.dtd">'
        "<testsuites></testsuites>"
    ).encode("utf-8")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_internal_entity_declaration_rejected():
    raw = (
        "<!DOCTYPE testsuites [<!ENTITY identity \"tests.test_paid_initializer\">]>"
        "<testsuites><testsuite tests=\"1\" errors=\"0\" failures=\"0\" skipped=\"0\">"
        '<testcase classname="&identity;" name="' + EXPECTED_NAME + '"/>'
        "</testsuite></testsuites>"
    ).encode("utf-8")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_undefined_entity_reference_rejected():
    raw = _document(f"<testsuites>{_suite(_case(classname='tests&nope;'))}</testsuites>")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_non_utf8_report_rejected():
    raw = b'<?xml version="1.0" encoding="utf-8"?><testsuites>\xff\xfe</testsuites>'
    with expect_rejection():
        HELPER.validate_report(raw)


def test_utf16_report_rejected():
    raw = '<?xml version="1.0" encoding="utf-16"?><testsuites/>'.encode("utf-16")
    with expect_rejection():
        HELPER.validate_report(raw)


def test_rejection_message_never_renders_report_content(tmp_path):
    secret = "CLASSIFIED-PRIVATE-H1-DETAIL"
    raw = _document(
        f"<testsuites>{_suite(_case(classname=secret))}</testsuites>"
    )
    path = tmp_path / "h1-private-report.xml"
    path.write_bytes(raw)
    with expect_rejection():
        HELPER.validate_report(path.read_bytes())


def test_cli_accepts_valid_report(tmp_path):
    path = tmp_path / "h1-positive.xml"
    path.write_bytes(_valid_report())
    proc = _run_cli(str(path))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == EXPECTED_ACCEPT_MESSAGE + "\n"
    assert proc.stderr == ""


def test_cli_rejects_skipped_report_with_fixed_output(tmp_path):
    raw = _document(
        f"<testsuites>{_suite(_case(body='<skipped message=\"env unavailable\"/>'))}</testsuites>"
    )
    path = tmp_path / "h1-skipped.xml"
    path.write_bytes(raw)
    proc = _run_cli(str(path))
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == EXPECTED_REJECT_MESSAGE + "\n"


def test_cli_invalid_report_never_renders_private_content_or_path(tmp_path):
    secret = "CLASSIFIED-PRIVATE-H1-DETAIL"
    raw = _document(
        "<testsuites><testsuite name=\"pytest\" errors=\"0\" failures=\"0\""
        " skipped=\"0\" tests=\"1\"><testcase classname=\"" + secret + "\""
        " name=\"" + EXPECTED_NAME + "\"><failure message=\"boom " + secret + "\"/>"
        "</testcase></testsuite></testsuites>"
    )
    path = tmp_path / "h1-private-junit.xml"
    path.write_bytes(raw)
    proc = _run_cli(str(path))
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == EXPECTED_REJECT_MESSAGE + "\n"
    assert secret not in proc.stderr
    assert str(path) not in proc.stderr
    assert str(tmp_path) not in proc.stderr


def test_cli_missing_file_fixed_output_without_path_echo(tmp_path):
    proc = _run_cli(str(tmp_path / "does-not-exist.xml"))
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == EXPECTED_REJECT_MESSAGE + "\n"
    assert str(tmp_path) not in proc.stderr


def test_cli_directory_argument_fixed_output(tmp_path):
    proc = _run_cli(str(tmp_path))
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == EXPECTED_REJECT_MESSAGE + "\n"


def test_cli_oversize_report_fixed_output(tmp_path):
    filler = "a" * (EXPECTED_MAX_BYTES + 1024)
    raw = _document(
        f'<testsuites><testsuite name="{filler}" errors="0" failures="0"'
        ' skipped="0" tests="1">' + _case() + "</testsuite></testsuites>"
    )
    path = tmp_path / "h1-oversize.xml"
    path.write_bytes(raw)
    proc = _run_cli(str(path))
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == EXPECTED_REJECT_MESSAGE + "\n"


def test_cli_usage_error_fixed_output():
    for arguments in ([], ["a", "b"]):
        proc = _run_cli(*arguments)
        assert proc.returncode == 1
        assert proc.stdout == ""
        assert proc.stderr == EXPECTED_REJECT_MESSAGE + "\n"
