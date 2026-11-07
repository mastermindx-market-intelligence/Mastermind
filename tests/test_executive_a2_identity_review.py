"""D8 acknowledgement is exact to one independently reviewed permission read."""
import ast
from pathlib import Path

import pytest

from tests.executive_a2_identity_review import REVIEWED_PATH
from tests.executive_identity_review import mask_reviewed_identity_literals, reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff


def source():
    text = (Path(__file__).parents[1] / REVIEWED_PATH).read_text()
    node = next(n for n in ast.parse(text).body
                if isinstance(n, ast.FunctionDef) and n.name == "w3c_plist_configured")
    return ast.get_source_segment(text, node) + "\n"


def scan(text, path=REVIEWED_PATH):
    lines = text.splitlines()
    diff = (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + line for line in lines))
    return _scan_added_identity_diff(diff, source_postimages={path: text})


def test_only_the_exact_reviewed_permission_constant_is_acknowledged():
    text = source()
    spans = reviewed_literal_spans(REVIEWED_PATH, text)
    assert len(spans) == 1
    line, start, end, kind = spans[0]
    assert text.splitlines()[line - 1][start:end] == "0o644"
    assert kind == "int"
    masked = mask_reviewed_identity_literals(REVIEWED_PATH, text)
    assert "uid=PLIST_UID, gid=PLIST_GID" in masked
    assert scan(text) == []
    assert scan(text + "new_peer_uid = 457\n") == ["457"]


@pytest.mark.parametrize("old,new", [
    ("mode=0o644", "mode=0o666"),
    ("mode=0o644", "mode=420"),
    ("uid=PLIST_UID", "uid=450"),
    ("gid=PLIST_GID", "gid=457"),
    ("w3c_enabled=True", "w3c_enabled=False"),
    ('document["ProgramArguments"]', 'document["OtherArguments"]'),
])
def test_permission_pin_fails_closed_when_any_reviewed_semantics_change(old, new):
    text = source().replace(old, new)
    assert reviewed_literal_spans(REVIEWED_PATH, text) == ()
    assert scan(text)


def test_duplicate_or_foreign_function_cannot_reuse_review_pin():
    text = source()
    assert reviewed_literal_spans(REVIEWED_PATH, text + text) == ()
    assert reviewed_literal_spans("ops/executive_os/other.py", text) == ()
    assert scan(text + text)
    assert scan(text, path="ops/executive_os/other.py")
