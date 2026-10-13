"""The reviewed archive path bound never exempts runtime identities."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.executive_identity_review import reviewed_literal_spans, mask_reviewed_identity_literals
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff

REVIEWED_PATH = "integrations/research_read_mcp/release_identity.py"
SOURCE = (Path(__file__).parents[1] / REVIEWED_PATH).read_text(encoding="utf-8")


def _diff(source, path=REVIEWED_PATH):
    lines = source.splitlines()
    return (f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "\n".join("+" + line for line in lines) + "\n")


def _scan(source, path=REVIEWED_PATH):
    return _scan_added_identity_diff(_diff(source, path), source_postimages={path: source})


def test_only_the_reviewed_path_bound_token_is_neutralized():
    spans = reviewed_literal_spans(REVIEWED_PATH, SOURCE)
    assert len(spans) == 1
    line, start, end, kind = spans[0]
    assert kind == "int" and SOURCE.splitlines()[line - 1][start:end] == "500"
    masked = mask_reviewed_identity_literals(REVIEWED_PATH, SOURCE)
    assert len(masked) == len(SOURCE)
    allowed = {(line, column) for column in range(start, end)}
    for number, (before, after) in enumerate(zip(SOURCE.splitlines(), masked.splitlines()), 1):
        for column, (original, replacement) in enumerate(zip(before, after)):
            assert original == replacement or (number, column) in allowed
    assert _scan(SOURCE) == []


@pytest.mark.parametrize("uid", [500, 459])
def test_unreviewed_identity_outside_anchor_stays_guarded(uid):
    assert _scan(SOURCE + f"\nnew_uid = {uid}\n") == [str(uid)]


@pytest.mark.parametrize("spelling", ["501", "0x1f4"])
def test_changed_bound_or_spelling_has_no_review(spelling):
    changed = SOURCE.replace("len(value) > 500", f"len(value) > {spelling}")
    assert changed != SOURCE
    assert reviewed_literal_spans(REVIEWED_PATH, changed) == ()
    assert _scan(changed) == [spelling]


def test_new_identity_inside_function_invalidates_its_review():
    changed = SOURCE.replace("def _safe_path(value):\n", "def _safe_path(value):\n    new_uid = 459\n")
    assert reviewed_literal_spans(REVIEWED_PATH, changed) == ()
    assert _scan(changed) == ["459", "500"]


def test_duplicate_function_does_not_mask_either_bound():
    node = next(node for node in ast.parse(SOURCE).body
                if isinstance(node, ast.FunctionDef) and node.name == "_safe_path")
    block = "".join(SOURCE.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    changed = SOURCE + "\n" + block
    assert reviewed_literal_spans(REVIEWED_PATH, changed) == ()
    assert _scan(changed) == ["500", "500"]


def test_review_never_transfers_to_another_file():
    other = "integrations/research_read_mcp/other_identity.py"
    assert reviewed_literal_spans(other, SOURCE) == ()
    assert _scan(SOURCE, other) == ["500"]


def test_missing_postimage_keeps_the_bound_visible():
    assert _scan_added_identity_diff(_diff(SOURCE)) == ["500"]
