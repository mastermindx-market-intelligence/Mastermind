"""Exact Capacity freshness tokens; no generic duration or identity exemption."""
from pathlib import Path
import hashlib

import pytest

from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import _d8_frozen_source_diff, _scan_added_identity_diff

PATH = "control_plane/workspace_capacity_fabric.py"
SOURCE = (Path(__file__).resolve().parents[1] / PATH).read_text()
SITES = ((234, 66, 69, "int", "900"), (277, 106, 109, "int", "900"))
DIGEST = "f48347aa98d894368e7e175263427c55f79c066cb3c7dfd7f32ea4253db53892"


def scan(source, path=PATH):
    return _scan_added_identity_diff(_d8_frozen_source_diff(path, source),
                                    source_postimages={path: source})


def test_only_exact_capacity_freshness_tokens_are_reviewed():
    assert hashlib.sha256(SOURCE.encode()).hexdigest() == DIGEST
    assert REVIEWED_FILES[PATH] == {"sha256": DIGEST, "sites": SITES}
    assert reviewed_literal_spans(PATH, SOURCE) == tuple(row[:4] for row in SITES)
    assert scan(SOURCE) == []


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("literal", ["901", "0x384", "9_00"])
def test_changed_value_or_spelling_restores_capacity_source_scrutiny(site, literal):
    line, start, end, *_ = site
    lines = SOURCE.splitlines(keepends=True)
    assert lines[line - 1][start:end] == "900"
    lines[line - 1] = lines[line - 1][:start] + literal + lines[line - 1][end:]
    changed = "".join(lines)
    assert reviewed_literal_spans(PATH, changed) == ()
    assert literal in scan(changed)


def test_changed_source_or_foreign_path_cannot_reuse_capacity_review():
    changed = SOURCE + "\n"
    assert reviewed_literal_spans(PATH, changed) == ()
    assert scan(changed) == ["900", "900"]
    foreign = "control_plane/copied_workspace_capacity_fabric.py"
    assert reviewed_literal_spans(foreign, SOURCE) == ()
    assert scan(SOURCE, foreign) == ["900", "900"]


def test_adjacent_identity_remains_visible():
    changed = SOURCE + "\npeer_uid = 471\n"
    assert reviewed_literal_spans(PATH, changed) == ()
    assert "471" in scan(changed)
