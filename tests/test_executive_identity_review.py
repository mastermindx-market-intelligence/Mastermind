"""D8 compatibility accepts only exact independently reviewed literal sites."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.executive_identity_review import (
    REVIEWED_LITERAL_COUNT, REVIEWED_PATH, mask_reviewed_identity_literals,
    reviewed_literal_spans,
)
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff

ROOT = Path(__file__).parents[1]
SOURCE = (ROOT / REVIEWED_PATH).read_text(encoding="utf-8")


def _diff(source, path=REVIEWED_PATH):
    lines = source.splitlines()
    return (f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "\n".join("+" + line for line in lines) + "\n")


def _scan(source, path=REVIEWED_PATH):
    return _scan_added_identity_diff(_diff(source, path), source_postimages={path: source})


def _anchor(name="_CONTROL_SOCKETS"):
    return next(node for node in ast.parse(SOURCE).body
                if isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name)


def _replace_span(source, span, replacement):
    line, start, end, _kind = span
    lines = source.splitlines(keepends=True)
    lines[line - 1] = lines[line - 1][:start] + replacement + lines[line - 1][end:]
    return "".join(lines)


def test_reviewed_topology_has_all_33_exact_literal_sites_and_no_other_masking():
    spans = reviewed_literal_spans(REVIEWED_PATH, SOURCE)
    assert len(spans) == REVIEWED_LITERAL_COUNT == 33
    masked = mask_reviewed_identity_literals(REVIEWED_PATH, SOURCE)
    assert len(masked) == len(SOURCE)
    assert masked.count("\n") == SOURCE.count("\n")
    allowed = {(line, col) for line, start, end, _kind in spans for col in range(start, end)}
    for line, (before, after) in enumerate(zip(SOURCE.splitlines(), masked.splitlines()), 1):
        for col, (old, new) in enumerate(zip(before, after)):
            assert old == new or (line, col) in allowed
    assert _scan(SOURCE) == []


@pytest.mark.parametrize("index", range(33))
def test_every_reviewed_literal_mutation_returns_to_generic_guard(index):
    span = reviewed_literal_spans(REVIEWED_PATH, SOURCE)[index]
    replacement = '"_mastermind_intruder"' if span[3] == "str" else "999"
    changed = _replace_span(SOURCE, span, replacement)
    assert _scan(changed), f"reviewed token {index} drift was suppressed"


@pytest.mark.parametrize("suffix", [
    "\nnew_uid = 459\n", "\nnew_uid = 450\n",
    '\nnew_account = "_mastermind_exec"\n',
    '\nnew_account = "_mastermind_intruder"\n',
    "\nfrom config.service import identity as chosen\nchosen = 459\n",
])
def test_unreviewed_identities_and_aliases_outside_anchors_stay_guarded(suffix):
    assert _scan(SOURCE + suffix)


@pytest.mark.parametrize("uid", [450, 459])
def test_same_line_trailing_identity_is_never_masked(uid):
    anchor = _anchor()
    lines = SOURCE.splitlines(keepends=True)
    lines[anchor.end_lineno - 1] = lines[anchor.end_lineno - 1].rstrip("\n") + f"; extra_uid = {uid}\n"
    changed = "".join(lines)
    assert len(reviewed_literal_spans(REVIEWED_PATH, changed)) == 33
    assert str(uid) in _scan(changed)


def test_literal_added_inside_function_invalidates_only_that_anchor():
    marker = 'def _verify_role_config('
    tree = ast.parse(SOURCE)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_verify_role_config')
    lines = SOURCE.splitlines(keepends=True)
    lines.insert(node.body[0].lineno - 1, '    added_uid = 459\n')
    changed = ''.join(lines)
    assert marker in changed
    assert '459' in _scan(changed)


@pytest.mark.parametrize("change", ["duplicate", "rename", "move", "annotate"])
def test_ambiguous_or_retargeted_anchor_cannot_authorize_literals(change):
    node = _anchor()
    lines = SOURCE.splitlines(keepends=True)
    block = ''.join(lines[node.lineno - 1:node.end_lineno])
    if change == 'duplicate':
        changed = SOURCE + '\n' + block
    elif change == 'rename':
        changed = SOURCE.replace('_CONTROL_SOCKETS =', '_OTHER_SOCKETS =', 1)
    elif change == 'annotate':
        changed = SOURCE.replace('_CONTROL_SOCKETS =', '_CONTROL_SOCKETS: dict =', 1)
    else:
        lines[node.lineno - 1:node.end_lineno] = ['if True:\n'] + ['    ' + line for line in block.splitlines(keepends=True)]
        changed = ''.join(lines)
    assert _scan(changed)


def test_copy_to_another_source_file_has_no_review_exception():
    assert reviewed_literal_spans('control_plane/other_peer.py', SOURCE) == ()
    assert _scan(SOURCE, 'control_plane/other_peer.py')


def test_missing_postimage_cannot_suppress_any_literal():
    assert _scan_added_identity_diff(_diff(SOURCE))


def test_mismatched_postimage_refuses_before_projection_is_used():
    with pytest.raises(AssertionError, match='diff/postimage line mismatch'):
        _scan_added_identity_diff(_diff(SOURCE), source_postimages={REVIEWED_PATH: '# shifted\n' + SOURCE})


def test_syntax_error_never_produces_reviewed_spans():
    bad = SOURCE + '\n(\n'
    assert reviewed_literal_spans(REVIEWED_PATH, bad) == ()
    assert mask_reviewed_identity_literals(REVIEWED_PATH, bad) == bad


@pytest.mark.parametrize("where", ["prefix", "trailing"])
def test_nonascii_inline_content_cannot_shift_approved_token_columns(where):
    node = _anchor()
    lines = SOURCE.splitlines(keepends=True)
    if where == 'prefix':
        lines[node.lineno - 1] = 'label = "é"; ' + lines[node.lineno - 1]
    else:
        lines[node.end_lineno - 1] = lines[node.end_lineno - 1].rstrip('\n') + '; label = "é"; extra_uid = 459\n'
    changed = ''.join(lines)
    assert len(reviewed_literal_spans(REVIEWED_PATH, changed)) < 33
    assert _scan(changed)


def test_equivalent_unreviewed_token_spelling_is_not_silently_approved():
    span = next(span for span in reviewed_literal_spans(REVIEWED_PATH, SOURCE)
                if span[3] == 'int' and SOURCE.splitlines()[span[0]-1][span[1]:span[2]] == '450')
    assert _scan(_replace_span(SOURCE, span, '0x1c2'))


def test_unrelated_ascii_comments_and_whitespace_preserve_approved_ast():
    changed = '# unrelated comment\n\n' + SOURCE.replace('_CONTROL_SOCKETS = {', '_CONTROL_SOCKETS  =  {\n    # spacing only', 1)
    assert len(reviewed_literal_spans(REVIEWED_PATH, changed)) == 33
    assert _scan(changed) == []


@pytest.mark.parametrize("separator", list("\v\f\x1c\x1d\x1e\x85\u2028\u2029"))
@pytest.mark.parametrize("position", ["prefix", "anchor"])
def test_non_python_line_separators_refuse_all_projection(separator, position):
    if position == "prefix":
        changed = f"# prefix{separator}\n" + SOURCE
    else:
        changed = SOURCE.replace("_CONTROL_SOCKETS = {", f"_CONTROL_SOCKETS = {{ # note{separator}", 1)
    assert reviewed_literal_spans(REVIEWED_PATH, changed) == ()
    assert mask_reviewed_identity_literals(REVIEWED_PATH, changed) == changed


@pytest.mark.parametrize("newline", ["\r\n", "\r"])
def test_python_universal_newlines_preserve_exact_tokens(newline):
    changed = SOURCE.replace("\n", newline)
    assert len(reviewed_literal_spans(REVIEWED_PATH, changed)) == 33
    masked = mask_reviewed_identity_literals(REVIEWED_PATH, changed)
    assert len(masked) == len(changed)
    ast.parse(masked)
    assert _scan(changed) == []
