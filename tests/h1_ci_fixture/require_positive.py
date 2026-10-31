#!/usr/bin/env python3
"""Fail-closed JUnit positive proof gate for the mandatory H1 Linux fixture.

A green ``pytest`` exit code does not prove the required private-package test
actually ran: a single skipped node also exits 0. This gate reads the private
fixture JUnit XML report and accepts it only when the document itself proves
exactly one executed-and-passed testcase:

- exactly one ``testsuites`` root element,
- exactly one ``testsuite`` directly under it, carrying the canonical
  counters ``tests="1" errors="0" failures="0" skipped="0"``,
- exactly one ``testcase`` directly under that suite whose ``classname`` and
  ``name`` equal the frozen expected identity below,
- no ``skipped``, ``failure`` or ``error`` node and no other element anywhere
  in the document,
- suite attributes such as ``name``/``time``/``timestamp``/``hostname`` and
  testcase attributes such as ``time``/``file``/``line`` are treated as inert
  metadata; none of them is ever rendered.

The parser is stdlib ``xml.parsers.expat`` configured fail-closed: bounded
read of at most 65536 bytes, UTF-8 decoding required, DTD and entity
declarations refused outright, parameter entities never parsed, external
entity resolution never attempted, undefined entity references rejected by
expat. Every rejection raises (library use) or prints (CLI use) one fixed,
nonsecret message; report content, paths and tracebacks are never rendered.

Test-only artifact: production code must not import this module.
"""

import os
import re
import stat
import sys
import xml.parsers.expat as expat

# Hard input bound: the private report is tiny; anything larger is refused
# before it is ever parsed.
MAX_REPORT_BYTES = 65536

# Frozen expected testcase identity. These literals are the contract; they
# are never learned from a report.
EXPECTED_CLASSNAME = "tests.test_paid_initializer"
EXPECTED_NAME = "test_actual_nested_initializer_private_package_context_and_wire"

# Canonical suite counters: exactly one executed testcase, nothing else.
EXPECTED_SUITE_COUNTERS = (
    ("tests", "1"),
    ("errors", "0"),
    ("failures", "0"),
    ("skipped", "0"),
)

# The only two output lines. No report content, path, node text or traceback
# is ever appended to them.
REJECT_MESSAGE = (
    "h1 positive gate: rejected - JUnit report is not a valid "
    "single-passed positive proof for the required H1 testcase"
)
ACCEPT_MESSAGE = "h1 positive gate: accepted - exactly one passed proof testcase"

_ALLOWED_ROOT_TAG = "testsuites"
_ALLOWED_SUITE_TAG = "testsuite"
_ALLOWED_CASE_TAG = "testcase"
_FORBIDDEN_TAGS = frozenset(("skipped", "failure", "error"))
# Depth + tag of the only accepted element shape; with exactly these three
# records, real parentage is forced to testsuites > testsuite > testcase.
_EXPECTED_SHAPE = (
    (0, _ALLOWED_ROOT_TAG),
    (1, _ALLOWED_SUITE_TAG),
    (2, _ALLOWED_CASE_TAG),
)

# DTD-ish markup refused by text scan before parsing; the expat handlers
# refuse it independently, this scan is defense in depth.
_DTD_MARKERS = ("<!doctype", "<!entity", "<!element", "<!attlist", "<!notation")
# Only the five predefined general entities and numeric character references
# may be referenced; anything else would require a refused declaration.
_ENTITY_REFERENCE = re.compile(
    r"&(#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z_][A-Za-z0-9.:_-]*);"
)
_PREDEFINED_ENTITIES = frozenset(("amp", "lt", "gt", "apos", "quot"))


def _reject() -> None:
    """Raise the fixed rejection; it never carries dynamic content."""
    raise ValueError(REJECT_MESSAGE)


def _refuse_declaration(*_unused) -> None:
    """Expat callback refusing any DTD/entity declaration or external ref."""
    _reject()


def _scan_text(text: str) -> None:
    """Refuse DTD-ish markup and non-predefined entity references."""
    lowered = text.lower()
    for marker in _DTD_MARKERS:
        if marker in lowered:
            _reject()
    for match in _ENTITY_REFERENCE.finditer(text):
        name = match.group(1)
        if not name.startswith("#") and name not in _PREDEFINED_ENTITIES:
            _reject()


class _ElementRecorder:
    """Collects (depth, tag, attributes) for every element in the document.

    Comments, processing instructions and character data never reach this
    recorder: expat routes them to inert no-op handlers instead.
    """

    def __init__(self) -> None:
        self.records = []
        self._open_tags = []

    def start_element(self, tag, attributes) -> None:
        self.records.append((len(self._open_tags), tag, dict(attributes)))
        self._open_tags.append(tag)

    def end_element(self, _tag) -> None:
        self._open_tags.pop()


def _build_parser(recorder):
    """Return an expat parser hardened against DTD/entity exfiltration."""
    parser = expat.ParserCreate()
    # Parameter entities are never parsed and external entities are never
    # resolved, so no network or filesystem access can be triggered.
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartDoctypeDeclHandler = _refuse_declaration
    parser.EntityDeclHandler = _refuse_declaration
    parser.UnparsedEntityDeclHandler = _refuse_declaration
    parser.ExternalEntityRefHandler = _refuse_declaration
    parser.CommentHandler = lambda *_: None
    parser.ProcessingInstructionHandler = lambda *_: None
    parser.CharacterDataHandler = lambda *_: None
    parser.StartElementHandler = recorder.start_element
    parser.EndElementHandler = recorder.end_element
    return parser


def _parse_report(data: bytes):
    """Parse ``data`` and return element records, or raise the rejection."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _reject()
    _scan_text(text)
    recorder = _ElementRecorder()
    parser = _build_parser(recorder)
    try:
        parser.Parse(data, True)
    except expat.error:
        _reject()
    return recorder.records


def _check_structure(records) -> None:
    """Accept only testsuites > testsuite > testcase with the right attrs."""
    if len(records) != 3:
        _reject()
    for record, expected in zip(records, _EXPECTED_SHAPE):
        depth, tag, _attributes = record
        if (depth, tag) != expected:
            _reject()
    suite_attributes = records[1][2]
    for attribute, expected_value in EXPECTED_SUITE_COUNTERS:
        if suite_attributes.get(attribute) != expected_value:
            _reject()
    case_attributes = records[2][2]
    if case_attributes.get("classname") != EXPECTED_CLASSNAME:
        _reject()
    if case_attributes.get("name") != EXPECTED_NAME:
        _reject()
    # The tag whitelist above already excludes these; kept explicit so the
    # "no skip/failure/error anywhere" guarantee survives future refactors.
    for _depth, tag, _attributes in records:
        if tag in _FORBIDDEN_TAGS:
            _reject()


def validate_report(raw: bytes) -> None:
    """Validate ``raw`` as the positive JUnit proof, or raise ``ValueError``.

    Raises ``ValueError`` carrying exactly :data:`REJECT_MESSAGE` for every
    invalid input (oversize, undecodable, malformed, DTD/entity declarations,
    wrong shape, wrong counters, wrong testcase identity, skip/failure/error
    nodes); returns ``None`` only for the single accepted shape.
    """
    if isinstance(raw, str) or not isinstance(raw, (bytes, bytearray, memoryview)):
        _reject()
    if len(raw) > MAX_REPORT_BYTES:
        _reject()
    try:
        records = _parse_report(bytes(raw))
    except ValueError:
        raise
    except Exception:
        _reject()
    _check_structure(records)


def _read_bounded(path: str) -> bytes:
    """Read at most MAX_REPORT_BYTES + 1 bytes from a regular file."""
    descriptor = os.open(path, os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            _reject()
        return handle.read(MAX_REPORT_BYTES + 1)


def _emit_rejection() -> None:
    sys.stderr.write(REJECT_MESSAGE + "\n")


def main(argv=None) -> int:
    """CLI: exit 0 only when the report proves the required passed testcase."""
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
