"""Exact observer identity review; no file-wide exemption or runtime pins."""
import ast
from pathlib import Path
import pytest
from tests.executive_identity_review import (
    mask_reviewed_identity_literals, reviewed_literal_spans, _anchor_name,
)
from tests.executive_release_observation_identity_review import (
    REVIEWED_PATH, REVIEWED_LITERAL_COUNT, REVIEWED_ANCHORS,
)
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff

SOURCE = (Path(__file__).parents[1] / REVIEWED_PATH).read_text()


def scan(source, path=REVIEWED_PATH):
    lines = source.splitlines(keepends=True)
    diff = f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n" + ''.join('+' + line for line in lines)
    return _scan_added_identity_diff(diff, source_postimages={path: source})


def test_exact_thirty_tokens_and_only_those_bytes_are_reviewed():
    spans = reviewed_literal_spans(REVIEWED_PATH, SOURCE)
    assert len(spans) == REVIEWED_LITERAL_COUNT == 30
    masked = mask_reviewed_identity_literals(REVIEWED_PATH, SOURCE)
    assert len(masked) == len(SOURCE)
    allowed = {(line, col) for line, start, end, _ in spans for col in range(start, end)}
    for line, (old, new) in enumerate(zip(SOURCE.splitlines(), masked.splitlines()), 1):
        assert len(old) == len(new)
        for col, (a, b) in enumerate(zip(old, new)):
            assert a == b or (line, col) in allowed
    assert scan(SOURCE) == []


@pytest.mark.parametrize('index', range(30))
def test_every_changed_identity_token_remains_unmasked(index):
    row = reviewed_literal_spans(REVIEWED_PATH, SOURCE)[index]
    line, start, end, kind = row
    replacement = '"_mastermind_shadow"' if kind == 'str' else '777'
    lines = SOURCE.splitlines(keepends=True)
    lines[line-1] = lines[line-1][:start] + replacement + lines[line-1][end:]
    changed = ''.join(lines)
    assert not any(a == line and b == start for a,b,_,_ in reviewed_literal_spans(REVIEWED_PATH, changed))
    assert mask_reviewed_identity_literals(REVIEWED_PATH, changed).splitlines()[line-1][start:start+len(replacement)] == replacement


@pytest.mark.parametrize('anchor', tuple(REVIEWED_ANCHORS))
def test_duplicate_owning_anchor_never_inherits_review(anchor):
    original = next(n for n in ast.parse(SOURCE).body if _anchor_name(n) == anchor)
    changed = SOURCE + '\n' + ast.get_source_segment(SOURCE, original) + '\n'
    spans = reviewed_literal_spans(REVIEWED_PATH, changed)
    assert not any(original.lineno <= line <= original.end_lineno for line,_,_,_ in spans)


@pytest.mark.parametrize('anchor', tuple(REVIEWED_ANCHORS))
def test_changed_nonliteral_owning_context_removes_review(anchor):
    original = next(n for n in ast.parse(SOURCE).body if _anchor_name(n) == anchor)
    text = ast.get_source_segment(SOURCE, original)
    if isinstance(original, ast.FunctionDef):
        changed_text = text.replace('):', ', unexpected=None):', 1)
    else:
        changed_text = text.replace(anchor+' =', anchor+' : object =', 1)
    assert changed_text != text
    changed = SOURCE.replace(text, changed_text, 1)
    ast.parse(changed)
    assert not any(original.lineno <= line <= original.end_lineno for line,_,_,_ in reviewed_literal_spans(REVIEWED_PATH, changed))


@pytest.mark.parametrize('extra', ['\nNEW_CONTROL_UID = 459\n', '\nSHADOW_ACCOUNT = "_mastermind_shadow"\n'])
def test_added_identity_outside_pins_is_visible_to_generic_scanner(extra):
    assert scan(SOURCE + extra)


def test_wrong_path_is_not_reviewed_or_masked():
    path = 'control_plane/unreviewed.py'
    assert reviewed_literal_spans(path, SOURCE) == ()
    assert mask_reviewed_identity_literals(path, SOURCE) == SOURCE
    assert scan(SOURCE, path)
