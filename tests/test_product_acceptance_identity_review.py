"""A reviewed string bound must not hide an actual identity or source drift."""
from pathlib import Path

import pytest

from tests.executive_identity_review import reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff


PATH = "app/mastermind_os/src/product-acceptance/owner-observation.ts"
SOURCE = (Path(__file__).parents[1] / PATH).read_text()


def diff(source, path=PATH):
    lines = source.splitlines()
    return (f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "\n".join("+" + line for line in lines) + "\n")


def scan(source, path=PATH):
    return _scan_added_identity_diff(diff(source, path), source_postimages={path: source})


def test_exact_reviewed_principal_scope_length_bound_qualifies():
    assert scan(SOURCE) == []
    assert reviewed_literal_spans(PATH, SOURCE) == ((34, 132, 135, "int"),)


@pytest.mark.parametrize("changed", [
    SOURCE.replace(".length > 512", ".length > 513"),
    SOURCE.replace(".length > 512", " > 512"),
    SOURCE.replace(".length > 512", ".length > 0x200"),
    SOURCE + "\nconst peer_uid = 459;\n",
    SOURCE.replace("value.principalScope.length > 512", "value.principalScope.length > 512 || peer_uid === 459"),
    SOURCE + SOURCE,
])
def test_changed_or_extended_source_restores_generic_guard(changed):
    assert reviewed_literal_spans(PATH, changed) == ()
    assert scan(changed)


def test_review_is_bound_to_exact_path_and_complete_postimage():
    assert scan(SOURCE, "app/mastermind_os/src/unreviewed-owner-observation.ts")
    assert _scan_added_identity_diff(diff(SOURCE))
    with pytest.raises(AssertionError, match="diff/postimage line mismatch"):
        _scan_added_identity_diff(diff(SOURCE), source_postimages={PATH: "// shifted\n" + SOURCE})
