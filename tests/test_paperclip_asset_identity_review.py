"""The asset-page row bounds do not exempt identities or source drift."""
import hashlib
from pathlib import Path

import pytest

from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import _d8_frozen_source_diff, _scan_added_identity_diff

PATH = "ops/paperclip_fleet/archive_assets.py"
SHA = "f96b00c2c238139c67f7be03f79d698c3f0d4f3d7f055e1a20661600c07b57af"
ROOT = Path(__file__).resolve().parents[1]


def source():
    return (ROOT / PATH).read_text()


def scan(text, path=PATH, postimage=True):
    return _scan_added_identity_diff(_d8_frozen_source_diff(path, text),
        source_postimages={path: text} if postimage else None)


def test_exact_asset_source_reviews_only_page_row_bounds():
    text = source()
    assert hashlib.sha256(text.encode()).hexdigest() == SHA
    assert reviewed_literal_spans(PATH, text) == (
        (459, 53, 56, "int"), (460, 182, 185, "int"), (461, 48, 51, "int"))
    assert scan(text) == []


@pytest.mark.parametrize("path,postimage", [
    (PATH, False), ("ops/paperclip_fleet/unreviewed_assets.py", True)])
def test_missing_postimage_or_wrong_path_restores_findings(path, postimage):
    assert scan(source(), path, postimage) == ["500", "500"]


@pytest.mark.parametrize("suffix,expected", [
    ("\npeer_uid = 501\n", ["500", "500", "501"]),
    ("\n# unrelated drift\n", ["500", "500"]),
])
def test_added_identity_and_unrelated_changes_are_not_reviewed(suffix, expected):
    assert scan(source() + suffix) == expected


def test_page_bound_change_is_not_reviewed():
    changed = source().replace("len(records)), 500)", "len(records)), 501)")
    assert reviewed_literal_spans(PATH, changed) == ()
    assert scan(changed) == ["501", "500"]


def test_removed_review_restores_original_guard(monkeypatch):
    monkeypatch.delitem(REVIEWED_FILES, PATH)
    assert scan(source()) == ["500", "500"]
