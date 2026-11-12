"""Capacity freshness uses accepted contract constants, not identity exemptions."""
import ast
from pathlib import Path

import pytest

from common import workspace_capacity_fabric_contract as wire
from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import _d8_frozen_source_diff, _scan_added_identity_diff

PATH = "control_plane/workspace_capacity_fabric.py"
SOURCE = (Path(__file__).resolve().parents[1] / PATH).read_text()
REFERENCES = ("wire.MAX_PREVIEW_LIFETIME_SECONDS", "wire.MAX_CONSUMER_RECEIPT_SECONDS")


def scan(source, path=PATH):
    return _scan_added_identity_diff(_d8_frozen_source_diff(path, source),
                                    source_postimages={path: source})


def test_capacity_freshness_uses_contract_constants_without_identity_exemptions():
    assert wire.MAX_PREVIEW_LIFETIME_SECONDS == 900
    assert wire.MAX_CONSUMER_RECEIPT_SECONDS == 900
    tree = ast.parse(SOURCE)
    for reference in REFERENCES:
        _, attribute = reference.split(".")
        uses = [node for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr == attribute
                and isinstance(node.value, ast.Name) and node.value.id == "wire"]
        assert len(uses) == 1
        assert any(isinstance(node, ast.Compare) and uses[0] in node.comparators
                   for node in ast.walk(tree))
    assert PATH not in REVIEWED_FILES
    assert reviewed_literal_spans(PATH, SOURCE) == ()
    assert scan(SOURCE) == []


@pytest.mark.parametrize("reference", REFERENCES)
@pytest.mark.parametrize("literal", ["901", "0x384", "9_00"])
def test_inline_duration_or_identity_remains_under_source_scrutiny(reference, literal):
    assert SOURCE.count(reference) == 1
    changed = SOURCE.replace(reference, literal, 1)
    assert reviewed_literal_spans(PATH, changed) == ()
    assert literal in scan(changed)


def test_changed_source_or_foreign_path_cannot_inherit_a_removed_exemption():
    changed = SOURCE + "\n"
    assert reviewed_literal_spans(PATH, changed) == ()
    assert scan(changed) == []
    foreign = "control_plane/copied_workspace_capacity_fabric.py"
    assert reviewed_literal_spans(foreign, SOURCE) == ()
    for path in (PATH, foreign):
        injected = SOURCE + "\npeer_uid = 471\n"
        assert reviewed_literal_spans(path, injected) == ()
        assert "471" in scan(injected, path)


def test_adjacent_identity_remains_visible():
    changed = SOURCE + "\npeer_uid = 471\n"
    assert reviewed_literal_spans(PATH, changed) == ()
    assert "471" in scan(changed)
