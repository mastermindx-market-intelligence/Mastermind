"""Exact reviewed private-directory modes; source drift stays visible to D8."""
from pathlib import Path
import difflib
import pytest
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff

ROOT = Path(__file__).parents[1]
PATHS = ['integrations/session_bridge/artifact_tool_framing/artifact_production.base.py', 'integrations/session_bridge/artifact_tool_framing/artifact_production.py']


def scan(path, source, *, include_postimage=True):
    diff = "diff --git a/" + path + " b/" + path + "\n"
    diff += "".join(difflib.unified_diff([], source.splitlines(keepends=True),
                                      fromfile="/dev/null", tofile="b/" + path))
    return _scan_added_identity_diff(diff, source_postimages={path: source} if include_postimage else {})


@pytest.mark.parametrize("path", PATHS)
def test_exact_private_mode_source_and_diff(path):
    source = (ROOT / path).read_text()
    spans = reviewed_literal_spans(path, source)
    assert len(spans) == 3
    for line, start, end, kind in spans:
        assert source.splitlines()[line - 1][start:end] == "0o700"
        assert kind == "int"
    assert scan(path, source) == []


@pytest.mark.parametrize("path", PATHS)
def test_private_mode_drift_and_wrong_path_are_not_qualified(path):
    source = (ROOT / path).read_text()
    for drift in [source + "\n# changed source\n", source.replace("0o700", "0o755", 1),
                  source + next(line for line in source.splitlines(keepends=True) if "0o700" in line)]:
        assert reviewed_literal_spans(path, drift) == ()
    wrong = "integrations/session_bridge/unreviewed.py"
    assert reviewed_literal_spans(wrong, source) == ()
    assert "0o700" in scan(wrong, source)


@pytest.mark.parametrize("path", PATHS)
def test_private_mode_review_cannot_hide_new_identity(path):
    source = (ROOT / path).read_text()
    if path.endswith(".patch"):
        source += "\ndiff --git a/injected.py b/injected.py\n--- /dev/null\n+++ b/injected.py\n@@ -0,0 +1 @@\n+worker_uid = 501\n"
    else:
        source += "\nworker_uid = 501\n"
    assert reviewed_literal_spans(path, source) == ()
    assert "501" in scan(path, source)


@pytest.mark.parametrize("path", PATHS)
def test_private_mode_diff_without_bound_postimage_stays_guarded(path):
    source = (ROOT / path).read_text()
    assert "0o700" in scan(path, source, include_postimage=False)
