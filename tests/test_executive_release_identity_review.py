"""The root factory exception is exact-source and never a general UID allowlist."""
from pathlib import Path

import pytest

from tests.executive_identity_review import mask_reviewed_identity_literals, reviewed_literal_spans
from tests.executive_release_identity_review import REVIEWED_PATH, REVIEWED_LITERAL_COUNT
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff

SOURCE = (Path(__file__).parents[1] / REVIEWED_PATH).read_text()


def scan(source, path=REVIEWED_PATH):
    lines = source.splitlines()
    diff = (f'--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n'
            + '\n'.join('+' + line for line in lines) + '\n')
    return _scan_added_identity_diff(diff, source_postimages={path: source})


def test_exact_three_reviewed_constants_and_no_other_bytes_are_hidden():
    spans = reviewed_literal_spans(REVIEWED_PATH, SOURCE)
    assert len(spans) == REVIEWED_LITERAL_COUNT == 3
    masked = mask_reviewed_identity_literals(REVIEWED_PATH, SOURCE)
    assert len(masked) == len(SOURCE)
    allowed = {(line, column) for line, start, end, _ in spans for column in range(start, end)}
    for line, (before, after) in enumerate(zip(SOURCE.splitlines(), masked.splitlines()), 1):
        for column, (a, b) in enumerate(zip(before, after)):
            assert a == b or (line, column) in allowed
    assert scan(SOURCE) == []


@pytest.mark.parametrize('index', range(3))
def test_changed_reviewed_literal_is_not_exempt(index):
    line, start, end, _ = reviewed_literal_spans(REVIEWED_PATH, SOURCE)[index]
    lines = SOURCE.splitlines(keepends=True)
    lines[line-1] = lines[line-1][:start] + '777' + lines[line-1][end:]
    changed = ''.join(lines)
    assert (line, start, end, 'int') not in reviewed_literal_spans(REVIEWED_PATH, changed)
    assert mask_reviewed_identity_literals(REVIEWED_PATH, changed).splitlines()[line-1][start:start+3] == '777'
    assert scan(changed)


@pytest.mark.parametrize('extra', ['\nNEW_CONTROL_UID = 459\n',
    '\ndef new_peer():\n    peer_uid = 777\n    return peer_uid\n',
    '\nSHADOW_ACCOUNT = "_mastermind_shadow"\n'])
def test_additional_identity_outside_reviewed_anchors_is_visible(extra):
    assert scan(SOURCE + extra)


def test_wrong_path_and_changed_anchor_context_remove_exemption():
    assert reviewed_literal_spans('control_plane/other_factory.py', SOURCE) == ()
    assert scan(SOURCE, 'control_plane/other_factory.py')
    changed = SOURCE.replace('control["control_uid"] != 450', 'control["control_uid"] == 450')
    assert changed != SOURCE
    assert len(reviewed_literal_spans(REVIEWED_PATH, changed)) < 3
    assert scan(changed)


def test_duplicate_reviewed_anchor_does_not_inherit_exemption():
    changed = SOURCE + '\ndef _resident(config, reader, now):\n    control_uid = 450\n'
    assert len(reviewed_literal_spans(REVIEWED_PATH, changed)) < 3
    assert scan(changed)
