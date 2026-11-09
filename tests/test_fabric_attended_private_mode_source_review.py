"""Review exact source-pinned private modes without changing installed artifacts."""
from pathlib import Path
import hashlib

import pytest

from tests.executive_identity_review import (
    REVIEWED_PRIVATE_MODE_SOURCES, mask_reviewed_identity_literals,
    reviewed_literal_spans,
)

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("path, count", [
    ("integrations/session_bridge/artifact_manifest_framing/artifact_production.base.py", 3),
    ("integrations/session_bridge/artifact_manifest_framing/artifact_production.py", 3),
    ("integrations/session_bridge/bound_launch_capture/lane_runtime.py.patch", 1),
])
def test_exact_reviewed_private_dir_mode_is_only_exception(path, count):
    source = (ROOT / path).read_text(encoding="utf-8")
    binding = REVIEWED_PRIVATE_MODE_SOURCES[path]
    assert hashlib.sha256(source.encode()).hexdigest() == binding["sha256"]
    spans = reviewed_literal_spans(path, source)
    assert len(spans) == count
    lines = source.splitlines()
    for line, start, end, kind in spans:
        assert kind == "int"
        assert lines[line - 1][start:end] == "0o700"
    masked = mask_reviewed_identity_literals(path, source)
    assert masked.count("0o700") == source.count("0o700") - count


@pytest.mark.parametrize("path", list(REVIEWED_PRIVATE_MODE_SOURCES))
def test_mode_review_fails_closed_for_changed_source_or_other_path(path):
    source = (ROOT / path).read_text(encoding="utf-8")
    assert reviewed_literal_spans(path, source + "\n# unexpected new source") == ()
    assert reviewed_literal_spans(path, source.replace("0o700", "0o755", 1)) == ()
    assert reviewed_literal_spans("integrations/session_bridge/foreign.py", source) == ()
