"""Frozen-source CCR review pins preserve D7/D8 refusal on any drift.

These fixtures exercise source-only guards. No service, peer or provider runs.
"""
from pathlib import Path

import pytest

from tests.executive_identity_review import (
    mask_reviewed_identity_literals, reviewed_literal_spans,
)

ROOT = Path(__file__).resolve().parents[1]
ACTION_PATH = "control_plane/workspace_control_room_actions.py"
HTTP_PATH = "integrations/mastermind_workspace_app/app.py"
EXPECTED = {
    ACTION_PATH: ((135, 58, 61, "int"),),
    HTTP_PATH: (
        (758, 71, 74, "int"), (769, 71, 74, "int"),
        (777, 71, 74, "int"), (783, 79, 82, "int"),
        (792, 71, 74, "int"), (802, 71, 74, "int"),
        (807, 76, 79, "int"), (813, 71, 74, "int"),
    ),
}


@pytest.mark.parametrize("path", EXPECTED)
def test_exact_nine_response_literals_only_are_qualified(path):
    source = (ROOT / path).read_text()
    spans = reviewed_literal_spans(path, source)
    assert spans == EXPECTED[path]
    masked = mask_reviewed_identity_literals(path, source)
    expected = source.splitlines(keepends=True)
    for line, start, end, kind in reversed(spans):
        assert kind == "int"
        expected[line - 1] = (
            expected[line - 1][:start] + "0" + " " * (end - start - 1)
            + expected[line - 1][end:]
        )
    assert masked == "".join(expected)
    assert len(masked) == len(source)
    assert reviewed_literal_spans("foreign/" + path, source) == ()
    assert mask_reviewed_identity_literals("foreign/" + path, source) == source


@pytest.mark.parametrize("before,after", [
    ("wire.action_result(", "foreign.action_result("),
    ("status=409", "worker_uid=409"),
    ("status=409", "status=410"),
    ("status=409", "status=0o631"),
])
def test_action_callee_keyword_literal_or_spelling_drift_refuses(before, after):
    source = (ROOT / ACTION_PATH).read_text()
    changed = source.replace(before, after, 1)
    assert changed != source
    assert reviewed_literal_spans(ACTION_PATH, changed) == ()
    assert mask_reviewed_identity_literals(ACTION_PATH, changed) == changed


@pytest.mark.parametrize("before,after", [
    ("_action_refusal(operation,", "_foreign_refusal(operation,"),
    ('code="invalid_input", status=400', 'code="invalid_input", peer_uid=400'),
    ('code="invalid_input", status=400', 'code="invalid_input", status=401'),
    ('code="invalid_input", status=400', 'code="invalid_input", status=0o620'),
])
def test_http_callee_keyword_literal_or_spelling_drift_refuses(before, after):
    source = (ROOT / HTTP_PATH).read_text()
    changed = source.replace(before, after, 1)
    assert changed != source
    assert reviewed_literal_spans(HTTP_PATH, changed) == ()
    assert mask_reviewed_identity_literals(HTTP_PATH, changed) == changed


@pytest.mark.parametrize("path", EXPECTED)
@pytest.mark.parametrize("suffix", [
    "\nworker_uid = 451\n", '\nworker_user = "_mastermind_unreviewed"\n',
    "\n# unrelated source movement still needs review\n",
])
def test_adjacent_identity_and_unrelated_drift_remain_completely_visible(path, suffix):
    changed = (ROOT / path).read_text() + suffix
    assert reviewed_literal_spans(path, changed) == ()
    assert mask_reviewed_identity_literals(path, changed) == changed


@pytest.mark.parametrize("path", EXPECTED)
def test_duplicated_reviewed_source_site_is_not_adopted(path):
    source = (ROOT / path).read_text()
    line = EXPECTED[path][0][0]
    changed = source + "\n" + source.splitlines()[line - 1] + "\n"
    assert reviewed_literal_spans(path, changed) == ()
    assert mask_reviewed_identity_literals(path, changed) == changed
