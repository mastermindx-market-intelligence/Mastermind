"""RED-first grounding mutations for the Continuation Delta commission contract.

These tests isolate two identity seams that must fail closed before a continuation
handoff may be emitted:

1. the pickup SHA the commission says it derives from must match the carrier head
   it says it just observed; and
2. the Skillpack identity must be an exact immutable commit SHA.

The first committed version of this file is intentionally RED against the
pre-repair linter. Do not weaken the assertions to make the implementation pass.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from scripts.sol_commission_lint import lint_file

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "sol_commission_delta"


def _extract_yaml(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    inside = False
    buf: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("```yaml"):
            inside = True
            continue
        if inside and line.strip().startswith("```"):
            break
        if inside:
            buf.append(line)
    data = yaml.safe_load("\n".join(buf))
    assert isinstance(data, dict) and data.get("schema") == "mastermind.sol_commission.v1"
    return data


def _base() -> dict:
    return copy.deepcopy(_extract_yaml(FIX / "base_continuation.md"))


def _lint(tmp_path: Path, manifest: dict):
    path = tmp_path / "manifest.yml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return lint_file(path)


def _hard(findings) -> set[str]:
    return {finding.name for finding in findings if finding.severity == "hard"}


def test_continuation_pickup_must_match_observed_carrier_head(tmp_path):
    """A stale pickup cannot coexist with a separately claimed newer carrier head."""
    manifest = _base()
    assert manifest["identity"]["carrier"]["pickup_sha"] != manifest["sources"]["github"]["carrier_head_sha"]

    findings = _lint(tmp_path, manifest)

    assert "CARRIER_HEAD_MISMATCH" in _hard(findings)


@pytest.mark.parametrize(
    "bad_skillpack_sha",
    [None, "abc123", "g" * 40],
)
def test_skillpack_identity_requires_exact_commit_sha(tmp_path, bad_skillpack_sha):
    """Atomic procedure identity must not be absent, short, or non-hex."""
    manifest = _base()
    if bad_skillpack_sha is None:
        manifest["identity"].pop("skillpack_sha", None)
    else:
        manifest["identity"]["skillpack_sha"] = bad_skillpack_sha

    findings = _lint(tmp_path, manifest)

    assert "MALFORMED_MANIFEST" in _hard(findings)
