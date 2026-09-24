"""Regression coverage for the MAS-28 V1 GitHub PR authoring surface."""
from __future__ import annotations

import subprocess
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE = _ROOT / ".github" / "pull_request_template.md"
_STRICT_HEADER = (
    "Workstream: REQUIRED",
    "Linear: REQUIRED",
    "Portfolio-Mode: REQUIRED",
    "Wave: REQUIRED",
    "Authority: REQUIRED",
    "Completion: REQUIRED",
)


def test_default_template_has_exact_mas28_v1_header_and_digests():
    lines = _TEMPLATE.read_text(encoding="utf-8").splitlines()

    assert tuple(lines[:6]) == _STRICT_HEADER
    assert "MAS28-V1-CONTRACT-SHA256: 9c57ad499fa34ee32f0ffeb9f2f5928f0515dba1609f984e5a20ce6576e7f75e" in lines
    assert "MAS28-V1-RULESET-SHA256: 2e97ad7acd0aec77ef18dbd76a1b3f2bbf8b7d4585e938498615de1917aa71aa" in lines


def test_only_lowercase_default_template_is_tracked():
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", ".github"], cwd=_ROOT, text=True
    ).splitlines()

    assert ".github/pull_request_template.md" in tracked
    assert ".github/PULL_REQUEST_TEMPLATE.md" not in tracked
