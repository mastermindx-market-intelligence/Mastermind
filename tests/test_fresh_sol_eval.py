"""Deterministic fake-backend/falsifier coverage for the fresh-Sol F0 harness.

No provider credentials, no live provider calls.  Every App Server interaction
here goes through an injected in-process fake client -- see ``_FakeEvalClient``
below -- so these tests never spawn ``scripts.ohf.fake_app_server`` as a
subprocess.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ohf.fresh_sol_eval import (
    MAS136_ARMS,
    MAS136_SCENARIOS,
    FreshSolEvalError,
    SkillpackArm,
    materialize_skillpack,
    parse_protocol,
    build_eval_agents_md,
)


# ---------------------------------------------------------------------------
# Task 1, Step 1: RED contract tests for immutable arm identity.
# ---------------------------------------------------------------------------


def test_mas136_arm_identity_is_frozen():
    assert MAS136_ARMS["control-1.0.0"].commit_sha == "51f9942733b86e550bb9169d2a43462bd28e774f"
    assert MAS136_ARMS["control-1.0.0"].skillpack_version == "1.0.0"
    assert MAS136_ARMS["amended-1.1.0"].commit_sha == "8209e1f31da15f8effc23a9899a5c5a02d30cab4"
    assert MAS136_ARMS["amended-1.1.0"].skillpack_version == "1.1.0"
    assert MAS136_SCENARIOS == ("S2", "S6", "S7", "S8")


# ---------------------------------------------------------------------------
# Task 1, Step 3: RED tests proving source bytes come from immutable Git
# objects, not the working tree.
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def skillpack_git_repo(tmp_path: Path) -> dict[str, object]:
    """A tiny two-commit Git repo shaped like the real Skillpack tree."""

    repo = tmp_path / "skillpack_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "ohf1@example.invalid")
    _git(repo, "config", "user.name", "ohf1 fixture")

    index_v1 = (
        "---\n"
        "schema: mastermind.sol_skillpack.v1\n"
        "skillpack_version: 1.0.0\n"
        "minimum_bootstrap_major: 1\n"
        "skill: index\n"
        "---\n\n# index v1\n"
    )
    sibling_v1 = "# sibling v1\ncontrol content\n"
    _write(repo / "docs/sol_skills/INDEX.md", index_v1)
    _write(repo / "docs/sol_skills/SIBLING.md", sibling_v1)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "control commit")
    control_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    index_v2 = (
        "---\n"
        "schema: mastermind.sol_skillpack.v1\n"
        "skillpack_version: 1.1.0\n"
        "minimum_bootstrap_major: 1\n"
        "skill: index\n"
        "---\n\n# index v2\n"
    )
    sibling_v2 = "# sibling v2\namended content\n"
    _write(repo / "docs/sol_skills/INDEX.md", index_v2)
    _write(repo / "docs/sol_skills/SIBLING.md", sibling_v2)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "amended commit")
    amended_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    # Dirty the working tree after both commits exist -- materialize_skillpack
    # must never read this.
    _write(repo / "docs/sol_skills/INDEX.md", "DIRTY WORKING TREE COPY -- MUST NOT BE READ\n")
    _write(repo / "docs/sol_skills/SIBLING.md", "DIRTY WORKING TREE COPY -- MUST NOT BE READ\n")

    return {"repo": repo, "control_sha": control_sha, "amended_sha": amended_sha}


def test_materialize_skillpack_reads_committed_bytes_not_dirty_worktree(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-control", skillpack_git_repo["control_sha"], "1.0.0")
    bundle = materialize_skillpack(repo, arm)
    paths = [source.path for source in bundle.sources]
    assert paths == sorted(paths)
    assert paths == ["docs/sol_skills/INDEX.md", "docs/sol_skills/SIBLING.md"]
    for source in bundle.sources:
        assert b"DIRTY WORKING TREE COPY" not in source.content
        assert len(source.blob_sha) == 40
    sibling = next(s for s in bundle.sources if s.path.endswith("SIBLING.md"))
    assert b"control content" in sibling.content
    assert isinstance(bundle.context_sha256, str) and len(bundle.context_sha256) == 64


def test_materialize_skillpack_aggregate_digest_is_stable(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-control", skillpack_git_repo["control_sha"], "1.0.0")
    first = materialize_skillpack(repo, arm)
    second = materialize_skillpack(repo, arm)
    assert first.context_sha256 == second.context_sha256


def test_materialize_skillpack_unknown_commit_refuses(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-bad", "0" * 40, "1.0.0")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "SOURCE_COMMIT_UNAVAILABLE"


def test_materialize_skillpack_missing_index_refuses(tmp_path: Path):
    repo = tmp_path / "no_index_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "ohf1@example.invalid")
    _git(repo, "config", "user.name", "ohf1 fixture")
    _write(repo / "docs/sol_skills/OTHER.md", "# not an index\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "no index")
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    arm = SkillpackArm("fixture-no-index", sha, "1.0.0")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "PROCEDURE_SOURCE_UNAVAILABLE"


def test_materialize_skillpack_wrong_version_refuses(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-wrong-version", skillpack_git_repo["control_sha"], "9.9.9")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "SKILLPACK_IDENTITY_MISMATCH"


def test_materialize_skillpack_wrong_schema_refuses(tmp_path: Path):
    repo = tmp_path / "wrong_schema_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "ohf1@example.invalid")
    _git(repo, "config", "user.name", "ohf1 fixture")
    _write(
        repo / "docs/sol_skills/INDEX.md",
        "---\nschema: not.the.right.schema\nskillpack_version: 1.0.0\n"
        "minimum_bootstrap_major: 1\n---\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "wrong schema")
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    arm = SkillpackArm("fixture-wrong-schema", sha, "1.0.0")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "SKILLPACK_IDENTITY_MISMATCH"


# ---------------------------------------------------------------------------
# Task 1, Step 5: RED protocol-parser tests with exact S2/S6/S7/S8 extraction.
# ---------------------------------------------------------------------------


def _protocol_text(*, duplicate_preamble: bool = False, missing_pass_requires: bool = False) -> str:
    preamble = (
        "## Shared scenario preamble\n\n"
        "> PREAMBLE LINE\n\n"
    )
    body = preamble
    if duplicate_preamble:
        body += preamble
    for scenario_id, label, rule in (
        ("S2", "repaired-then-stale organizational state", "S2 RULE"),
        ("S6", "second scenario label", "S6 RULE"),
        ("S7", "third scenario label", "S7 RULE"),
        ("S8", "fourth scenario label", "S8 RULE"),
    ):
        body += f"## {scenario_id} — {label}\n\n> {scenario_id} BODY\n\n"
        if not (missing_pass_requires and scenario_id == "S2"):
            body += f"PASS requires: {rule}\n\n"
    return body


def test_parse_protocol_extracts_all_required_scenarios(tmp_path: Path):
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(_protocol_text(), encoding="utf-8")
    packets = parse_protocol(path)
    assert set(packets) == {"S2", "S6", "S7", "S8"}
    s2 = packets["S2"]
    assert s2.scenario_id == "S2"
    assert "PREAMBLE LINE" in s2.prompt
    assert "S2 BODY" in s2.prompt
    assert "PASS requires" not in s2.prompt
    assert s2.pass_requires == "S2 RULE"


def test_parse_protocol_duplicate_preamble_refuses(tmp_path: Path):
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(_protocol_text(duplicate_preamble=True), encoding="utf-8")
    with pytest.raises(FreshSolEvalError) as excinfo:
        parse_protocol(path)
    assert excinfo.value.code == "PROTOCOL_INVALID"


def test_parse_protocol_missing_scenario_refuses(tmp_path: Path):
    text = _protocol_text()
    text = text.replace(
        "## S8 — fourth scenario label\n\n> S8 BODY\n\nPASS requires: S8 RULE\n\n", ""
    )
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(FreshSolEvalError) as excinfo:
        parse_protocol(path)
    assert excinfo.value.code == "PROTOCOL_INVALID"


def test_parse_protocol_missing_pass_requires_refuses(tmp_path: Path):
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(_protocol_text(missing_pass_requires=True), encoding="utf-8")
    with pytest.raises(FreshSolEvalError) as excinfo:
        parse_protocol(path)
    assert excinfo.value.code == "PROTOCOL_INVALID"


def test_parse_protocol_never_falls_back_to_hardcoded_text(tmp_path: Path):
    """A protocol whose scenario body text is unusual must still be used verbatim."""
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    text = _protocol_text().replace("S2 BODY", "UNUSUAL UNIQUE MARKER 42")
    path.write_text(text, encoding="utf-8")
    packets = parse_protocol(path)
    assert "UNUSUAL UNIQUE MARKER 42" in packets["S2"].prompt


# ---------------------------------------------------------------------------
# build_eval_agents_md
# ---------------------------------------------------------------------------


def test_build_eval_agents_md_is_arm_neutral_wrapper_plus_sources(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    control_arm = SkillpackArm("control-1.0.0", skillpack_git_repo["control_sha"], "1.0.0")
    amended_arm = SkillpackArm("amended-1.1.0", skillpack_git_repo["amended_sha"], "1.1.0")
    control_bundle = materialize_skillpack(repo, control_arm)
    amended_bundle = materialize_skillpack(repo, amended_arm)
    control_md = build_eval_agents_md(control_bundle)
    amended_md = build_eval_agents_md(amended_bundle)
    assert isinstance(control_md, bytes)
    # The wrapper preamble (everything before the first source marker) must be
    # byte-identical between arms and must not name arm identity or grading.
    control_wrapper = control_md.split(b"----- BEGIN ", 1)[0]
    amended_wrapper = amended_md.split(b"----- BEGIN ", 1)[0]
    assert control_wrapper == amended_wrapper
    for banned in (b"Continuation Delta", b"control-1.0.0", b"amended-1.1.0", b"PASS requires"):
        assert banned not in control_wrapper
        assert banned not in amended_wrapper
    assert b"control content" in control_md
    assert b"amended content" in amended_md

