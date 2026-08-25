"""RED-first grounding mutations for the Continuation Delta commission contract.

These tests isolate identity seams that must fail closed before a continuation
handoff may be emitted:

1. the pickup SHA the commission says it derives from must match the carrier head
   it says it just observed;
2. the Skillpack identity must be an exact immutable commit SHA;
3. the organizational program/workstream and repository identity must not be blank;
4. a continuation carrier must identify its type, branch, and PR number when applicable.

Earlier subsets of this file were observed RED before their corresponding
repairs. New mutation assertions must likewise fail before implementation; do
not weaken them to make the linter pass.
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
    assert manifest["identity"]["carrier"]["pickup_sha"] == manifest["sources"]["github"]["carrier_head_sha"]
    manifest["sources"]["github"]["carrier_head_sha"] = "f" * 40

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


@pytest.mark.parametrize("bad_owner", [None, "", "   "])
def test_program_or_workstream_identity_must_not_be_blank(tmp_path, bad_owner):
    """An omitted owner must not turn self-deferral into an apparently independent WS."""
    manifest = _base()
    if bad_owner is None:
        manifest["identity"].pop("program_or_workstream", None)
    else:
        manifest["identity"]["program_or_workstream"] = bad_owner

    findings = _lint(tmp_path, manifest)

    assert "MALFORMED_MANIFEST" in _hard(findings)


@pytest.mark.parametrize("bad_repository", [None, "", "repo-without-owner"])
def test_repository_identity_requires_owner_repo_shape(tmp_path, bad_repository):
    """A continuation must identify the repository whose carrier SHA is being grounded."""
    manifest = _base()
    if bad_repository is None:
        manifest["identity"].pop("repository", None)
    else:
        manifest["identity"]["repository"] = bad_repository

    findings = _lint(tmp_path, manifest)

    assert "MALFORMED_MANIFEST" in _hard(findings)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_type",
        "missing_branch",
        "missing_pr_id",
        "bad_pr_id",
    ],
)
def test_continuation_carrier_requires_exact_transport_identity(tmp_path, mutation):
    """A pickup SHA without the carrier it belongs to is not a bound continuation."""
    manifest = _base()
    carrier = manifest["identity"]["carrier"]
    if mutation == "missing_type":
        carrier.pop("type", None)
    elif mutation == "missing_branch":
        carrier.pop("branch", None)
    elif mutation == "missing_pr_id":
        carrier.pop("id", None)
    elif mutation == "bad_pr_id":
        carrier["id"] = 0

    findings = _lint(tmp_path, manifest)

    assert "UNBOUND_CONTINUATION" in _hard(findings)
