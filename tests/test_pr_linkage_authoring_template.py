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
    assert "MAS28-V1-CONTRACT-SHA256: e78cbf00a952f7283a7e0f1e83eb4070c9049c1a445c9a035f9da8652dc6838c" in lines
    assert "MAS28-V1-RULESET-SHA256: 41d5634a6ca6d4bbd993e728b73d839260452b24c891e556c59da52a184a1859" in lines


def test_only_lowercase_default_template_is_tracked():
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", ".github"], cwd=_ROOT, text=True
    ).splitlines()

    assert ".github/pull_request_template.md" in tracked
    assert ".github/PULL_REQUEST_TEMPLATE.md" not in tracked
