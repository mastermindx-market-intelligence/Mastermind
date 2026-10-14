"""Fixed finite identity review never relaxes the generic D8 source guard."""
from pathlib import Path

import pytest

from tests.executive_identity_review import reviewed_literal_spans
from tests.test_executive_a2_identity_review import scan

STAGE = 'ops/executive_os/attended_control_staging.py'
REGISTER = 'control_plane/fabric_attended_registration.py'


@pytest.mark.parametrize('path,count', [(STAGE, 7), (REGISTER, 1)])
def test_exact_review_preserves_scan_of_other_identity(path, count):
    text = (Path(__file__).parents[1]/path).read_text()
    assert len(reviewed_literal_spans(path, text)) == count
    assert scan(text, path) == []
    assert scan(text+'\nnew_peer_uid = 471\n', path) == ['471']
    assert reviewed_literal_spans('ops/executive_os/foreign.py', text) == ()


@pytest.mark.parametrize('path,before,after', [
    (STAGE, '!= 470', '!= 471'),
    (STAGE, "'_mastermind_minimax'", "'_mastermind_other'"),
    (STAGE, 'identity.pw_uid !=', 'identity.pw_uid =='),
    (STAGE, "'finite principal is not quiescent'", "'changed semantics'"),
    (REGISTER, "'_mastermind_minimax'", "'_mastermind_other'"),
    (REGISTER, "label = 'mastermind-minimax'", "label = 'another-account'"),
    (REGISTER, '    guard()\n    if existing', '    if existing'),
])
def test_semantic_or_identity_drift_exposes_entire_anchor(path, before, after):
    text = (Path(__file__).parents[1]/path).read_text()
    assert before in text
    changed = text.replace(before, after)
    assert reviewed_literal_spans(path, changed) == ()
    assert scan(changed, path)


def test_exact_lifecycle_identity_pins_require_entire_reviewed_source():
    path = 'ops/executive_os/finite_service_lifecycle.py'
    text = (Path(__file__).parents[1]/path).read_text()
    spans = reviewed_literal_spans(path, text)
    assert len(spans) == 37
    assert scan(text, path) == []
    assert reviewed_literal_spans('ops/executive_os/foreign.py', text) == ()
    for line, start, end, kind in spans:
        lines = text.splitlines(keepends=True)
        replacement = '471' if kind == 'int' else '"_mastermind_other"'
        lines[line - 1] = lines[line - 1][:start] + replacement + lines[line - 1][end:]
        changed = ''.join(lines)
        assert reviewed_literal_spans(path, changed) == ()
        assert scan(changed, path)
    for suffix in ('\nnew_peer_uid = 471\n', '\n# source drift\n'):
        assert reviewed_literal_spans(path, text + suffix) == ()
        assert scan(text + suffix, path)
