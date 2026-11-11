#!/usr/bin/env python3
"""Fail-closed JUnit all-passed gate for the 23 provider-entry module cases.

A green ``pytest`` exit code does not prove the mandatory provider-entry
Linux module cases actually ran and passed: a single skipped node also
exits 0. This gate reads the private fixture JUnit XML report and accepts
it only when the document itself proves that all 23 frozen cases were
executed and passed:

- exactly one ``testsuites`` root element with exactly one ``testsuite``
  directly under it, carrying the canonical counters ``tests="23"
  errors="0" failures="0" skipped="0"``,
- exactly 23 ``testcase`` elements directly under that suite, each with
  ``classname="tests.test_paid_provider_entry_linux"`` and a ``name`` from
  the frozen inventory below; the executed name set must equal the frozen
  set exactly, so missing, duplicated, replaced or extra names are refused,
  while the document order is never consulted,
- no ``skipped``, ``failure`` or ``error`` node and no unrecognized element
  anywhere in the document, at any depth,
- the only optional extra structure is the real ``pytest``
  ``record_property`` shape: at most one ``properties`` element directly
  under a testcase, holding only ``property`` elements whose ``name``
  attributes come from the fixed two-name allowlist and stay unique inside
  their block. Property ``value`` attributes and every other metadata
  attribute are inert: they are never rendered and never consulted as
  authority. No ``properties`` element is accepted under the root or the
  suite, and no ``testcase`` is accepted hidden inside metadata.

The accepted single-node helper is materialized beside this file as
``require_positive.py`` and is loaded through :mod:`importlib.util` from
that fixed sibling path, so the gate also runs under ``python -I``. Its
bounded reader (at most 65536 bytes of a regular file) and its fail-closed
``expat`` configuration (UTF-8 required, DTD and entity declarations
refused outright, parameter entities never parsed, external entity
resolution never attempted) are reused unchanged.

Every rejection raises (library use) or prints (CLI use) one fixed,
nonsecret message; report content, paths, parameters and tracebacks are
never rendered.

Test-only artifact: production code must not import this module.
"""

import importlib.util
import os
import sys

# Fixed sibling path of the accepted single-node helper. It is loaded by
# absolute file location instead of a plain ``import`` so ``python -I``
# (script directory absent from ``sys.path``) still finds it.
_HELPER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "require_positive.py"
)


def _load_accepted_helper():
    """Load the accepted helper module, or return ``None`` on any failure."""
    try:
        spec = importlib.util.spec_from_file_location(
            "_h1_require_positive_accepted", _HELPER_PATH
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


_HELPER = _load_accepted_helper()

# Hard input bound, reused unchanged from the accepted helper.
MAX_REPORT_BYTES = _HELPER.MAX_REPORT_BYTES if _HELPER is not None else 65536

# Frozen expected testcase inventory. These literals are the contract; they
# are never learned from a report.
EXPECTED_CLASSNAME = "tests.test_paid_provider_entry_linux"
EXPECTED_NAMES = (
    "test_actual_compiled_c_executor_model_and_original_result[None]",
    "test_actual_compiled_c_executor_model_and_original_result[source-drift]",
    "test_actual_compiled_c_executor_model_and_original_result[expired]",
    "test_actual_compiled_c_executor_model_and_original_result[lost-response]",
    "test_actual_compiled_c_executor_model_and_original_result[truncated-response]",
    "test_compiled_fixture_data_assembles_against_real_wire_and_compilers",
    "test_retained_output_canary_discriminator_uses_owned_fixed_leaves[lane]",
    "test_retained_output_canary_discriminator_uses_owned_fixed_leaves[stdout]",
    "test_retained_output_canary_discriminator_uses_owned_fixed_leaves[stderr]",
    "test_retained_output_canary_discriminator_uses_owned_fixed_leaves[receipt]",
    "test_retained_output_canary_discriminator_uses_owned_fixed_leaves[intent]",
    "test_retained_output_symlink_and_original_namespace_swap_refuse",
    "test_unknown_process_settlement_preserves_disposable_namespace",
    "test_executor_timeout_terminates_only_same_identity_once_and_consumes",
    "test_truncated_http_fixture_announces_full_body_then_closes",
    "test_model_cleanup_requires_exact_original_terminal_before_removal[None]",
    "test_model_cleanup_requires_exact_original_terminal_before_removal[missing]",
    "test_model_cleanup_requires_exact_original_terminal_before_removal[partial]",
    "test_model_cleanup_requires_exact_original_terminal_before_removal[wrong-parent]",
    "test_model_cleanup_requires_exact_original_terminal_before_removal[wrong-pid]",
    "test_model_cleanup_requires_exact_original_terminal_before_removal[unproved]",
    "test_model_cleanup_requires_exact_original_terminal_before_removal[live-model]",
    "test_executor_identity_retains_actual_popen_pid_and_start_scope",
)
EXPECTED_NAME_SET = frozenset(EXPECTED_NAMES)
EXPECTED_CASE_COUNT = len(EXPECTED_NAMES)

# Canonical suite counters: 23 executed testcases, nothing else.
EXPECTED_SUITE_COUNTERS = (
    ("tests", "23"),
    ("errors", "0"),
    ("failures", "0"),
    ("skipped", "0"),
)

# The only property names ``pytest.record_property`` may contribute.
EXPECTED_PROPERTY_NAMES = frozenset(
    ("actual_executor_command_utf8_nul", "actual_executor_identity")
)

# The only two output lines. No report content, path, node text or traceback
# is ever appended to them.
REJECT_MESSAGE = (
    "h1 provider module gate: rejected - JUnit report is not a valid "
    "all-passed proof for the 23 required provider-entry testcases"
)
ACCEPT_MESSAGE = (
    "h1 provider module gate: accepted - all 23 provider-entry testcases passed"
)

_ROOT_TAG = "testsuites"
_SUITE_TAG = "testsuite"
_CASE_TAG = "testcase"
_PROPERTIES_TAG = "properties"
_PROPERTY_TAG = "property"
# The tag whitelist in _check_structure already excludes these; kept explicit
# so the "no skip/failure/error anywhere" guarantee survives refactors.
_FORBIDDEN_TAGS = frozenset(("skipped", "failure", "error"))


def _reject() -> None:
    """Raise the fixed rejection; it never carries dynamic content."""
    raise ValueError(REJECT_MESSAGE)


def _check_structure(records) -> None:
    """Accept only the 23-case all-passed document shape, or raise."""
    if not records:
        _reject()
    if records[0][0] != 0 or records[0][1] != _ROOT_TAG:
        _reject()
    # Exactly one testsuite directly under the root, with canonical counters.
    suite_records = [record for record in records if record[0] == 1]
    if len(suite_records) != 1 or suite_records[0][1] != _SUITE_TAG:
        _reject()
    suite_attributes = suite_records[0][2]
    for attribute, expected_value in EXPECTED_SUITE_COUNTERS:
        if suite_attributes.get(attribute) != expected_value:
            _reject()
    # Walk every element record against the whitelist, reconstructing real
    # parentage from the recorder's depth values.
    stack = []  # (depth, tag) of every currently open element
    case_names = []  # testcase name attributes in document order
    last_case_index = None  # index of the last depth-2 testcase record
    cases_with_properties = set()  # indexes of cases owning one properties
    current_property_names = set()  # names inside the open properties block
    for index, record in enumerate(records):
        depth, tag, attributes = record
        while len(stack) > depth:
            stack.pop()
        if len(stack) != depth:
            _reject()
        parent_tag = stack[-1][1] if stack else None
        if depth == 0:
            if tag != _ROOT_TAG:
                _reject()
        elif depth == 1:
            if parent_tag != _ROOT_TAG or tag != _SUITE_TAG:
                _reject()
        elif depth == 2:
            if parent_tag != _SUITE_TAG or tag != _CASE_TAG:
                _reject()
            if attributes.get("classname") != EXPECTED_CLASSNAME:
                _reject()
            name = attributes.get("name")
            if name not in EXPECTED_NAME_SET:
                _reject()
            case_names.append(name)
            last_case_index = index
        elif depth == 3:
            # Only the record_property shape lives here: one properties
            # block per testcase, nothing else, nothing deeper.
            if parent_tag != _CASE_TAG or tag != _PROPERTIES_TAG:
                _reject()
            if (
                last_case_index is None
                or last_case_index in cases_with_properties
            ):
                _reject()
            cases_with_properties.add(last_case_index)
            current_property_names = set()
        elif depth == 4:
            if parent_tag != _PROPERTIES_TAG or tag != _PROPERTY_TAG:
                _reject()
            name = attributes.get("name")
            if name not in EXPECTED_PROPERTY_NAMES:
                _reject()
            if name in current_property_names:
                _reject()
            current_property_names.add(name)
        else:
            _reject()
        if tag in _FORBIDDEN_TAGS:
            _reject()
        stack.append((depth, tag))
    # The executed inventory must equal the frozen set exactly; order is
    # never consulted and duplicates collapse in the set comparison.
    if len(case_names) != EXPECTED_CASE_COUNT:
        _reject()
    if len(set(case_names)) != len(case_names):
        _reject()
    if set(case_names) != EXPECTED_NAME_SET:
        _reject()


def validate_report(raw: bytes) -> None:
    """Validate ``raw`` as the all-23-passed JUnit proof, or raise ValueError.

    Raises ``ValueError`` carrying exactly :data:`REJECT_MESSAGE` for every
    invalid input (missing helper, wrong type, oversize, undecodable,
    malformed, DTD/entity declarations, wrong shape, wrong counters, wrong,
    duplicated or extra testcase names, skip/failure/error nodes, unexpected
    properties structure); returns ``None`` only for the accepted shape.
    """
    if _HELPER is None:
        _reject()
    if isinstance(raw, str) or not isinstance(raw, (bytes, bytearray, memoryview)):
        _reject()
    if len(raw) > MAX_REPORT_BYTES:
        _reject()
    try:
        records = _HELPER._parse_report(bytes(raw))
    except ValueError:
        _reject()
    except Exception:
        _reject()
    _check_structure(records)


def _read_bounded(path: str) -> bytes:
    """Bounded read of a regular file, delegated to the accepted helper."""
    if _HELPER is None:
        _reject()
    return _HELPER._read_bounded(path)


def _emit_rejection() -> None:
    sys.stderr.write(REJECT_MESSAGE + "\n")


def main(argv=None) -> int:
    """CLI: exit 0 only when the report proves all 23 cases passed."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        _emit_rejection()
        return 1
    try:
        validate_report(_read_bounded(arguments[0]))
    except Exception:
        # One fixed, nonsecret failure line: no errno text, path or traceback.
        _emit_rejection()
        return 1
    sys.stdout.write(ACCEPT_MESSAGE + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
