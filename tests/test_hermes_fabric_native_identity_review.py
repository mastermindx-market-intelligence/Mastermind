"""D8 finite, source-bound review for Hermes Fabric escalation length limits."""
from pathlib import Path

from tests.executive_identity_review import reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff

ROOT = Path(__file__).resolve().parents[1]
PATH = "integrations/hermes_attended_fabric/native.py"
# Pin moved 2026-11-10: master #2365 (`6696153d3`) expanded MANUAL_POOLS above both
# reviewed `500` operands without moving this pin (master is red here); the
# tokens are byte-identical at their new rows (same registry move as
# tests/executive_fabric_release_identity_review.py, merge MERGE_MASTER_20261109).
EXPECTED = ((57, 65, 68, "int"), (280, 60, 63, "int"))


def _source():
    return (ROOT / PATH).read_text(encoding="utf-8")


def _added_diff(source: str) -> str:
    lines = source.splitlines(keepends=True)
    return (
        f"diff --git a/{PATH} b/{PATH}\n"
        f"new file mode 100644\n--- /dev/null\n+++ b/{PATH}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        + "".join("+" + line for line in lines)
    )


def test_exact_source_reviews_only_two_reason_limit_tokens():
    source = _source()
    assert reviewed_literal_spans(PATH, source) == EXPECTED
    assert _scan_added_identity_diff(
        _added_diff(source), source_postimages={PATH: source}
    ) == []


def test_modified_source_or_limit_cannot_inherit_review():
    source = _source()
    for changed in (
        source + "\n# drift\n",
        source.replace('"maxLength": 500', '"maxLength": 501', 1),
        source.replace('len(reason) > 500', 'len(reason) > 501', 1),
        source + "\nnew_peer_uid = 501\n",
    ):
        assert changed != source
        assert reviewed_literal_spans(PATH, changed) == ()
        assert _scan_added_identity_diff(
            _added_diff(changed), source_postimages={PATH: changed}
        ), "changed or identity-bearing source must remain guarded"
