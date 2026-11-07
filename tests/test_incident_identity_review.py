"""Exact dormant-source literals never authorize an altered identity path."""
from pathlib import Path

import pytest

from tests.executive_identity_review import reviewed_literal_spans, mask_reviewed_identity_literals
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff

ROOT = Path(__file__).parents[1]
CASES = (
    ("control_plane/executive_incident_release_observation.py", 1),
    ("control_plane/executive_incident_forward_host.py", 1),
    ("control_plane/executive_incident_origin.py", 6),
    ("control_plane/executive_recovery_namespace.py", 3),
    ("ops/executive_os/provider_incident_forward.py", 1),
)


def _diff(path, source):
    lines = source.splitlines()
    return (f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "\n".join("+" + line for line in lines) + "\n")


def _scan(path, source, *, postimage=True):
    return _scan_added_identity_diff(
        _diff(path, source), source_postimages={path: source} if postimage else None,
    )


@pytest.mark.parametrize("path,count", CASES)
def test_exact_sources_mask_only_the_qualified_tokens(path, count):
    source = (ROOT / path).read_text()
    spans = reviewed_literal_spans(path, source)
    assert len(spans) == count
    masked = mask_reviewed_identity_literals(path, source)
    allowed = {(line, col) for line, start, end, _kind in spans for col in range(start, end)}
    assert len(masked) == len(source)
    for line, (before, after) in enumerate(zip(source.splitlines(), masked.splitlines()), 1):
        for col, (left, right) in enumerate(zip(before, after)):
            assert left == right or (line, col) in allowed
    assert _scan(path, source) == []


@pytest.mark.parametrize("path,count", CASES)
def test_each_token_mutation_and_duplicate_restores_the_generic_guard(path, count):
    source = (ROOT / path).read_text()
    spans = reviewed_literal_spans(path, source)
    assert len(spans) == count
    for line, start, end, _kind in spans:
        lines = source.splitlines(keepends=True)
        lines[line - 1] = lines[line - 1][:start] + "459" + lines[line - 1][end:]
        changed = "".join(lines)
        assert reviewed_literal_spans(path, changed) == ()
        assert _scan(path, changed)
    changed = source + "\n" + source
    assert reviewed_literal_spans(path, changed) == ()
    assert _scan(path, changed)


@pytest.mark.parametrize("path,_count", CASES)
@pytest.mark.parametrize("suffix", ["\nnew_uid = 450\n", "\nnew_uid = 459\n", "\n# source drift\n"])
def test_added_source_is_never_covered_by_the_frozen_file_pin(path, _count, suffix):
    changed = (ROOT / path).read_text() + suffix
    assert reviewed_literal_spans(path, changed) == ()
    assert _scan(path, changed)


@pytest.mark.parametrize("path,_count", CASES)
def test_wrong_path_and_missing_or_shifted_postimage_cannot_qualify(path, _count):
    source = (ROOT / path).read_text()
    foreign = "control_plane/unreviewed_incident_identity.py"
    assert reviewed_literal_spans(foreign, source) == ()
    assert _scan(foreign, source)
    assert _scan(path, source, postimage=False)
    with pytest.raises(AssertionError, match="diff/postimage line mismatch"):
        _scan_added_identity_diff(_diff(path, source), source_postimages={path: "# shifted\n" + source})
