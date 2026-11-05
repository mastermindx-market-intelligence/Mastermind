"""Exact reviewed direct-native sites suppress only their own literal tokens.

Causal repro: the CI identity guard flags the fixed 0o700 sealed-boundary
mode comparison in ``validate_terminal`` and the fixed 503 unknown-receipt
status in ``dispatch_direct_correction`` until these exact reviewed pins
qualify; every drift below returns both tokens to the generic guard.
"""
import ast
import hashlib
from pathlib import Path

import pytest

from tests.executive_direct_native_identity_review import REVIEWED_ANCHORS_BY_PATH
from tests.executive_identity_review import (
    mask_reviewed_identity_literals, reviewed_literal_spans,
)
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff
from tests.test_executive_identity_review import _replace_span

ROOT = Path(__file__).resolve().parents[1]
CORRECTION_PATH = "control_plane/direct_native_correction.py"
NATIVE_PATH = "integrations/mastermind_executive_app/direct_native.py"
CORRECTION_SOURCE = (ROOT / CORRECTION_PATH).read_text(encoding="utf-8")
NATIVE_SOURCE = (ROOT / NATIVE_PATH).read_text(encoding="utf-8")
CORRECTION_SHA = "e1ca2333e98ed5931cb01f8cbd3770b0240a18c7bdee358b2baea3efd88ed678"
NATIVE_SHA = "f1b433eaeeb7e80743aefbf7e956d579033ba4cb743227952f26030c065969e0"
CORRECTION_SITE = (88, 30, 35, "int")
NATIVE_SITE = (126, 129, 132, "int")
# The exact CI additions over the reviewed postimage: the correction() client
# method at lines 31-37 and dispatch_direct_correction at lines 106-135.
NATIVE_DIFF = (
    f"--- a/{NATIVE_PATH}\n+++ b/{NATIVE_PATH}\n"
    "@@ -30,0 +31,7 @@\n"
    + "".join("+" + line for line in NATIVE_SOURCE.splitlines(keepends=True)[30:37])
    + "@@ -98,0 +106,30 @@\n"
    + "".join("+" + line for line in NATIVE_SOURCE.splitlines(keepends=True)[105:135])
)


def _diff(source, path):
    lines = source.splitlines()
    return (f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "\n".join("+" + line for line in lines) + "\n")


def _scan(source, path):
    return _scan_added_identity_diff(_diff(source, path), source_postimages={path: source})


@pytest.mark.parametrize("path,source,sha,site,flagged", [
    (CORRECTION_PATH, CORRECTION_SOURCE, CORRECTION_SHA, CORRECTION_SITE, "0o700"),
    (NATIVE_PATH, NATIVE_SOURCE, NATIVE_SHA, NATIVE_SITE, "503"),
])
def test_exact_reviewed_postimage_suppresses_only_its_own_site(path, source, sha, site, flagged):
    assert hashlib.sha256(source.encode()).hexdigest() == sha
    assert reviewed_literal_spans(path, source) == (site,)
    assert source.splitlines()[site[0] - 1][site[1]:site[2]] == flagged
    masked = mask_reviewed_identity_literals(path, source)
    assert len(masked) == len(source)
    ast.parse(masked)
    allowed = {(site[0], col) for col in range(site[1], site[2])}
    for line, (before, after) in enumerate(zip(source.splitlines(), masked.splitlines()), 1):
        for col, (old, new) in enumerate(zip(before, after)):
            assert old == new or (line, col) in allowed
    assert masked.splitlines()[site[0] - 1][site[1]:site[2]] == "0" + " " * (site[2] - site[1] - 1)
    assert _scan(source, path) == []


def test_exact_ci_additions_pass_only_with_the_exact_postimage():
    assert _scan_added_identity_diff(
        NATIVE_DIFF, source_postimages={NATIVE_PATH: NATIVE_SOURCE}) == []
    # The same additions without the qualifying postimage stay flagged.
    assert _scan_added_identity_diff(NATIVE_DIFF)
    assert _scan_added_identity_diff(_diff(CORRECTION_SOURCE, CORRECTION_PATH))


def test_changed_whole_source_voids_the_pin():
    for path, source in ((CORRECTION_PATH, CORRECTION_SOURCE), (NATIVE_PATH, NATIVE_SOURCE)):
        changed = source + "\n# unrelated source drift\n"
        assert reviewed_literal_spans(path, changed) == ()
        assert mask_reviewed_identity_literals(path, changed) == changed
        assert _scan(changed, path)


@pytest.mark.parametrize("path,source,site,replacement", [
    (CORRECTION_PATH, CORRECTION_SOURCE, CORRECTION_SITE, "0o711"),
    (NATIVE_PATH, NATIVE_SOURCE, NATIVE_SITE, "502"),
])
def test_site_value_drift_restores_the_generic_guard(path, source, site, replacement):
    changed = _replace_span(source, site, replacement)
    assert changed != source
    assert reviewed_literal_spans(path, changed) == ()
    assert _scan(changed, path)


def test_ast_drift_inside_the_anchor_voids_its_pin():
    lines = CORRECTION_SOURCE.splitlines(keepends=True)
    lines.insert(24, "    added_uid = 459\n")
    changed = "".join(lines)
    assert reviewed_literal_spans(CORRECTION_PATH, changed) == ()
    assert "459" in _scan(changed, CORRECTION_PATH)


@pytest.mark.parametrize("path,source,anchor", [
    (CORRECTION_PATH, CORRECTION_SOURCE, "def validate_terminal"),
    (NATIVE_PATH, NATIVE_SOURCE, "async def dispatch_direct_correction"),
])
def test_duplicate_anchor_cannot_reuse_the_pin(path, source, anchor):
    # Both reviewed anchors are the final top-level definitions of their file.
    start = source.index(anchor)
    changed = source + "\n\n" + source[start:]
    assert reviewed_literal_spans(path, changed) == ()
    assert _scan(changed, path)


@pytest.mark.parametrize("path,source,suffix,literal", [
    (CORRECTION_PATH, CORRECTION_SOURCE, "\nadded_mode = 0o700\n", "0o700"),
    (NATIVE_PATH, NATIVE_SOURCE, "\npeer_uid = 503\n", "503"),
    (NATIVE_PATH, NATIVE_SOURCE, '\nworker_user = "_mastermind_unreviewed"\n', "_mastermind_unreviewed"),
])
def test_adjacent_unreviewed_literals_stay_flagged(path, source, suffix, literal):
    changed = source + suffix
    assert literal in _scan(changed, path)


def test_pins_do_not_transfer_to_another_path_or_the_sibling_source():
    assert reviewed_literal_spans("control_plane/other_correction.py", CORRECTION_SOURCE) == ()
    assert _scan(CORRECTION_SOURCE, "control_plane/other_correction.py")
    assert reviewed_literal_spans(CORRECTION_PATH, NATIVE_SOURCE) == ()
    assert reviewed_literal_spans(NATIVE_PATH, CORRECTION_SOURCE) == ()


@pytest.mark.parametrize("path,source", [
    (CORRECTION_PATH, CORRECTION_SOURCE), (NATIVE_PATH, NATIVE_SOURCE),
])
def test_syntax_error_source_never_qualifies(path, source):
    bad = source + "\n(\n"
    assert reviewed_literal_spans(path, bad) == ()
    assert mask_reviewed_identity_literals(path, bad) == bad


@pytest.mark.parametrize("separator", list("\v\f\x1c\x1d\x1e\u2028\u2029"))
def test_non_python_line_separators_refuse_all_projection(separator):
    for path, source, marker in (
        (CORRECTION_PATH, CORRECTION_SOURCE, "def validate_terminal("),
        (NATIVE_PATH, NATIVE_SOURCE, "async def dispatch_direct_correction("),
    ):
        changed = source.replace(marker, f"{marker}  # note{separator}", 1)
        assert reviewed_literal_spans(path, changed) == ()
        assert mask_reviewed_identity_literals(path, changed) == changed
