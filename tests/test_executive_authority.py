"""Focused authority-policy tests for the Executive OS Phase 1B worker path."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from control_plane.executive_authority import (
    PHASE1B_ALLOWED,
    PHASE1B_REQUIRED_DENIES,
    AuthorityDenied,
    AuthorityPolicyError,
    ExecutiveAuthorityPolicy,
)


_ROOT = Path(__file__).resolve().parent.parent
_POLICY_PATH = _ROOT / "config" / "authority_map.yml"
_EXPECTED_ALLOWED = frozenset({"READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"})
_EXPECTED_REQUIRED_DENIES = frozenset(
    {
        "OPEN_PR",
        "MERGE",
        "DEPLOY",
        "SERVICE_CONTROL",
        "CAPITAL_EXECUTION",
        "BILLING",
        "CREDENTIAL_ADMIN",
    }
)


def _canonical_section() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "allowed_capabilities": sorted(_EXPECTED_ALLOWED),
        "denied_capabilities": sorted(_EXPECTED_REQUIRED_DENIES),
        "scope_requirements": {
            "WRITE_BRANCH": "assigned_workspace_and_declared_paths",
            "RUN_TESTS": "declared_argv_commands",
        },
    }


def _write_document(tmp_path: Path, document: Any) -> Path:
    path = tmp_path / "authority_map.yml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _write_section(tmp_path: Path, section: dict[str, Any] | None = None) -> Path:
    return _write_document(
        tmp_path,
        {"executive_worker_policy": copy.deepcopy(section or _canonical_section())},
    )


def test_checked_in_policy_has_exact_phase1b_allow_set_and_mandatory_denies():
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    assert PHASE1B_ALLOWED == _EXPECTED_ALLOWED
    assert policy.allowed == _EXPECTED_ALLOWED
    assert PHASE1B_REQUIRED_DENIES == _EXPECTED_REQUIRED_DENIES
    assert _EXPECTED_REQUIRED_DENIES.issubset(policy.denied)
    assert policy.allowed.isdisjoint(policy.denied)


def test_policy_hash_is_sha256_of_exact_reviewed_bytes_and_flows_to_decision():
    raw = _POLICY_PATH.read_bytes()
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    expected_hash = hashlib.sha256(raw).hexdigest()
    assert policy.sha256 == expected_hash
    assert len(policy.sha256) == 64
    assert policy.schema_version == 1

    decision = policy.authorize("READ")
    assert decision.policy_sha256 == expected_hash
    assert decision.policy_schema_version == 1


def test_read_authority_succeeds_without_effect_scopes():
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    decision = policy.authorize("read")

    assert decision.to_dict() == {
        "requested": ["READ"],
        "policy_sha256": policy.sha256,
        "policy_schema_version": 1,
        "worktree": None,
        "allowed_write_paths": [],
        "validation_commands": [],
    }


def test_write_branch_requires_absolute_workspace_and_declared_relative_paths(tmp_path):
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)
    workspace = tmp_path / "assigned-worktree"

    decision = policy.authorize(
        ["WRITE_BRANCH", "READ"],
        worktree=workspace,
        allowed_write_paths=[
            "tests/test_executive_authority.py",
            "control_plane/executive_authority.py",
            "tests/test_executive_authority.py",
        ],
    )

    assert decision.requested == ("READ", "WRITE_BRANCH")
    assert decision.worktree == str(workspace.resolve())
    assert decision.allowed_write_paths == (
        "control_plane/executive_authority.py",
        "tests/test_executive_authority.py",
    )
    assert decision.validation_commands == ()


@pytest.mark.parametrize(
    ("worktree", "write_paths", "message"),
    [
        (None, ["tests/test_file.py"], "assigned workspace"),
        (Path("relative/worktree"), ["tests/test_file.py"], "absolute path"),
        (Path("/tmp/assigned-worktree"), [], "declared relative write path"),
    ],
)
def test_write_branch_missing_scope_fails_closed(worktree, write_paths, message):
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    with pytest.raises(AuthorityDenied, match=message):
        policy.authorize(
            "WRITE_BRANCH",
            worktree=worktree,
            allowed_write_paths=write_paths,
        )


@pytest.mark.parametrize(
    "write_path",
    [
        "/absolute/file.py",
        "../outside.py",
        "control_plane/../../outside.py",
        ".",
        "./",
    ],
)
def test_write_branch_rejects_unsafe_declared_paths(tmp_path, write_path):
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    with pytest.raises(AuthorityDenied, match="unsafe assigned write path"):
        policy.authorize(
            "WRITE_BRANCH",
            worktree=tmp_path,
            allowed_write_paths=[write_path],
        )


def test_write_paths_without_write_branch_fail_closed(tmp_path):
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    with pytest.raises(AuthorityDenied, match="require WRITE_BRANCH"):
        policy.authorize(
            "READ",
            worktree=tmp_path,
            allowed_write_paths=["tests/test_file.py"],
        )


def test_run_tests_accepts_only_declared_argv_commands():
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)
    commands = [
        ["python3", "-m", "pytest", "-q", "tests/test_executive_authority.py"],
        ["git", "diff", "--check"],
    ]

    decision = policy.authorize(["RUN_TESTS", "READ"], validation_commands=commands)

    assert decision.requested == ("READ", "RUN_TESTS")
    assert decision.validation_commands == (
        ("python3", "-m", "pytest", "-q", "tests/test_executive_authority.py"),
        ("git", "diff", "--check"),
    )


@pytest.mark.parametrize(
    ("commands", "message"),
    [
        (None, "at least one declared argv command"),
        ([], "at least one declared argv command"),
        (["python3 -m pytest"], "argv lists, never shell strings"),
        ([[]], "only non-empty strings"),
        ([["python3", ""]], "only non-empty strings"),
        ([["python3", 7]], "only non-empty strings"),
    ],
)
def test_run_tests_missing_or_non_argv_scope_fails_closed(commands, message):
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    with pytest.raises(AuthorityDenied, match=message):
        policy.authorize("RUN_TESTS", validation_commands=commands)


def test_validation_commands_without_run_tests_fail_closed():
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    with pytest.raises(AuthorityDenied, match="require RUN_TESTS"):
        policy.authorize("READ", validation_commands=[["python3", "-m", "pytest"]])


@pytest.mark.parametrize("capability", sorted(_EXPECTED_REQUIRED_DENIES))
def test_every_mandatory_denied_capability_is_rejected(capability):
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    with pytest.raises(AuthorityDenied, match="denied Executive worker authorities"):
        policy.authorize(capability)


def test_unknown_and_empty_authority_requests_fail_closed():
    policy = ExecutiveAuthorityPolicy.load(_POLICY_PATH)

    with pytest.raises(AuthorityDenied, match="unknown Executive worker authorities"):
        policy.authorize("INVENT_NEW_AUTHORITY")
    with pytest.raises(AuthorityDenied, match="at least one explicit worker authority"):
        policy.authorize([])


def test_missing_policy_file_fails_closed(tmp_path):
    missing = tmp_path / "missing-authority-map.yml"

    with pytest.raises(AuthorityPolicyError, match="policy is unavailable"):
        ExecutiveAuthorityPolicy.load(missing)


@pytest.mark.parametrize(
    "raw",
    [
        "executive_worker_policy: [unterminated",
        "- executive_worker_policy",
        "flags: {}\n",
    ],
)
def test_malformed_or_missing_policy_mapping_fails_closed(tmp_path, raw):
    path = tmp_path / "authority_map.yml"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(AuthorityPolicyError):
        ExecutiveAuthorityPolicy.load(path)


def test_missing_required_policy_field_fails_closed(tmp_path):
    section = _canonical_section()
    del section["scope_requirements"]

    with pytest.raises(AuthorityPolicyError, match="invalid executive_worker_policy shape"):
        ExecutiveAuthorityPolicy.load(_write_section(tmp_path, section))


@pytest.mark.parametrize("schema_version", [0, 2, "future"])
def test_schema_version_drift_fails_closed(tmp_path, schema_version):
    section = _canonical_section()
    section["schema_version"] = schema_version

    with pytest.raises(AuthorityPolicyError):
        ExecutiveAuthorityPolicy.load(_write_section(tmp_path, section))


@pytest.mark.parametrize("change", ["remove", "expand"])
def test_allowed_capability_drift_fails_closed(tmp_path, change):
    section = _canonical_section()
    if change == "remove":
        section["allowed_capabilities"].remove("RESEARCH")
    else:
        section["allowed_capabilities"].append("OPEN_PR")

    with pytest.raises(AuthorityPolicyError, match="allow-list drifted"):
        ExecutiveAuthorityPolicy.load(_write_section(tmp_path, section))


def test_missing_mandatory_deny_fails_closed(tmp_path):
    section = _canonical_section()
    section["denied_capabilities"].remove("DEPLOY")

    with pytest.raises(AuthorityPolicyError, match="missing mandatory denies.*DEPLOY"):
        ExecutiveAuthorityPolicy.load(_write_section(tmp_path, section))


def test_allowed_and_denied_overlap_fails_closed(tmp_path):
    section = _canonical_section()
    section["denied_capabilities"].append("READ")

    with pytest.raises(AuthorityPolicyError, match="both allow and deny"):
        ExecutiveAuthorityPolicy.load(_write_section(tmp_path, section))


@pytest.mark.parametrize(
    ("capability", "scope", "message"),
    [
        ("WRITE_BRANCH", "repository_wide", "workspace and path scoped"),
        ("RUN_TESTS", "shell_commands", "declared argv commands"),
    ],
)
def test_scope_requirement_drift_fails_closed(tmp_path, capability, scope, message):
    section = _canonical_section()
    section["scope_requirements"][capability] = scope

    with pytest.raises(AuthorityPolicyError, match=message):
        ExecutiveAuthorityPolicy.load(_write_section(tmp_path, section))
