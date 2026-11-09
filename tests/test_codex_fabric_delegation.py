"""Codex's incumbent M2 Fabric skill installation and admitted operator path.

No provider calls, no broker/host grants, no agents started. Tests target only
the additive entrypoint and the existing native instruction model.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ops.executive_os import provider_orchestrator_policy as policy

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = "skills/mastermind-fabric-delegate/SKILL.md"
USER_SKILL = ".codex/skills/mastermind-fabric-delegate/SKILL.md"
DOC = ".codex/AGENTS.md"


def _legacy_skill() -> bytes:
    """Exact 2026-10-22 M2 prior skill; no duplicate independent source file."""
    skill = (ROOT / SKILL_PATH).read_bytes()
    marker = b"\n## Codex operator discovery: launch -> child -> original parent\n"
    assert skill.count(marker) == 1
    return skill.split(marker, 1)[0]


def _protected_pre_recovery_codex_skill() -> bytes:
    """Remove only this addition before deriving genuine historical prefixes."""
    current = (ROOT / SKILL_PATH).read_bytes()
    marker = b"\n## Review failure recovery without replay\n"
    next_heading = b"\n## Independent PR review: one portable source contract\n"
    assert current.count(marker) == current.count(next_heading) == 1
    prefix, rest = current.split(marker, 1)
    _, suffix = rest.split(next_heading, 1)
    return prefix + next_heading + suffix


def _home(tmp_path: Path, *, with_pointer: bool) -> tuple[Path, bytes, bytes, bytes]:
    home = tmp_path / "home"
    (home / ".codex/skills/mastermind-fabric-delegate").mkdir(parents=True)
    legacy = _legacy_skill()
    (home / USER_SKILL).write_bytes(legacy)
    doc = (b"# Existing Codex global instructions\nPreserve my account.\n"
           + (b"Read ~/.codex/skills/mastermind-fabric-delegate/SKILL.md\n" if with_pointer else b""))
    (home / DOC).write_bytes(doc)
    config = (b'model = "gpt-6.1-sol"\n\n[agents]\n'
              b'enabled = true\nmax_depth = 1\nmax_concurrent_threads_per_session = 32\n'
              b'\n[features.multi_agent_v2]\nenabled = true\n'
              b'max_concurrent_threads_per_session = 33\n'
              b'disable_direct_message = false\n')
    (home / ".codex/config.toml").write_bytes(config)
    hooks = b'{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"command":"my-guard"}]}]}}\n'
    (home / ".codex/hooks.json").write_bytes(hooks)
    return home, doc, config, hooks


def test_codex_source_pin_and_existing_legacy_digest() -> None:
    new = (ROOT / SKILL_PATH).read_bytes()
    git_blob = hashlib.sha1(b"blob " + str(len(new)).encode() + b"\0" + new).hexdigest()
    assert git_blob == policy.CODEX_FABRIC_SKILL_BLOB_SHA
    assert policy._canonical_codex_fabric_skill() == new
    assert 0 < len(new) <= 24576
    assert hashlib.sha256(_legacy_skill()).hexdigest() == policy.CODEX_FABRIC_LEGACY_SHA256
    s = new.decode()
    for token in ("fabric_operator_scope", "fabric_child_request",
                  "fabric_child_result", "fabric_child_acknowledge",
                  "mastermind.fabric_operator_child_request.v1",
                  "CODEX_THREAD_ID", "fabric_task.py", "Grok 4.7",
                  "C0_MECHANICAL", "C1_ROUTINE_BOUNDED"):
        assert token in s



def test_reviewed_prior_codex_guide_migrates_without_sandbox_or_config_override(
    tmp_path: Path,
) -> None:
    current = (ROOT / SKILL_PATH).read_bytes()
    fence = b"\n## Codex native session and sandbox boundary (mandatory before new Fabric requests)\n"
    assert current.count(fence) == 1
    prior = current.split(fence, 1)[0] + b"\n"
    blob = hashlib.sha1(b"blob " + str(len(prior)).encode() + b"\0" + prior).hexdigest()
    assert blob == policy.CODEX_FABRIC_PRIOR_BLOB_SHA
    home, doc, config, hooks = _home(tmp_path, with_pointer=True)
    (home / USER_SKILL).write_bytes(prior)
    assert policy.verify_codex_fabric_entrypoint(home)["state"] == "DRIFT"
    installed = policy.apply_codex_fabric_entrypoint(home)
    assert installed["state"] == "READY"
    assert installed["native_capacity_modified"] is False
    assert installed["provider_settings_modified"] is False
    assert installed["runtime_admission_proven"] is False
    assert (home / USER_SKILL).read_bytes() == current
    assert (home / DOC).read_bytes() == doc
    assert (home / ".codex/config.toml").read_bytes() == config
    assert (home / ".codex/hooks.json").read_bytes() == hooks
    assert policy.apply_codex_fabric_entrypoint(home)["state"] == "READY"


def test_codex_native_denial_procedure_preserves_identity_and_single_carrier() -> None:
    skill = (ROOT / SKILL_PATH).read_text()
    assert "FABRIC_ADAPTER_SANDBOX_DENIED" in skill
    for phrase in (
        "PermissionError: [Errno 1] Operation not",
        "permitted",
        "CODEX_THREAD_ID",
        "status",
        "NOT_FOUND",
        "no recorded Fabric submission",
        "Do not retry",
        "do not",
        "not",
        "before any request",
    ):
        assert phrase in skill
    assert "workspace-write" in skill
    assert "Do not" in skill and "extend writable" in skill
    assert "An unauthenticated" in skill

def test_codex_m2_upgrade_preserves_native_32_and_mcp_and_user_instructions(tmp_path: Path) -> None:
    home, doc, config, hooks = _home(tmp_path, with_pointer=True)
    assert policy.verify_codex_fabric_entrypoint(home)["state"] == "DRIFT"
    result = policy.apply_codex_fabric_entrypoint(home)
    assert result["state"] == "READY"
    assert result["session_loading_proven"] is False
    assert result["runtime_admission_proven"] is False
    assert result["native_capacity_modified"] is False
    assert result["provider_settings_modified"] is False
    assert (home / USER_SKILL).read_bytes() == policy._canonical_codex_fabric_skill()
    assert (home / DOC).read_bytes() == doc
    assert (home / ".codex/config.toml").read_bytes() == config
    assert (home / ".codex/hooks.json").read_bytes() == hooks
    assert not (home / ".claude").exists()
    assert policy.apply_codex_fabric_entrypoint(home)["state"] == "READY"
    assert (home / DOC).read_bytes() == doc
    assert (home / ".codex/config.toml").read_bytes() == config
    old_backup = home / ".codex/skills/mastermind-fabric-delegate/SKILL.md.mastermind-orchestrator-backup"
    assert old_backup.read_bytes() == _legacy_skill()


def test_new_home_installs_single_pointer_without_provider_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = policy.apply_codex_fabric_entrypoint(home)
    assert result["state"] == "READY"
    doc = (home / DOC).read_text()
    assert doc.count(policy.CODEX_FABRIC_ENTRY_BEGIN) == doc.count(policy.CODEX_FABRIC_ENTRY_END) == 1
    assert "~/.codex/skills/mastermind-fabric-delegate/SKILL.md" in doc
    assert (home / USER_SKILL).is_file()
    assert not (home / ".codex/config.toml").exists()
    assert not (home / ".codex/hooks.json").exists()
    assert policy.apply_codex_fabric_entrypoint(home)["state"] == "READY"


def test_unknown_installed_skill_refused_before_any_change(tmp_path: Path) -> None:
    home, doc, config, hooks = _home(tmp_path, with_pointer=False)
    skill = home / USER_SKILL
    skill.write_bytes(b"Unreviewed local replacement\n")
    existing = skill.read_bytes()
    with pytest.raises(policy.OrchestratorPolicyError, match="installed Skill changed"):
        policy.apply_codex_fabric_entrypoint(home)
    assert skill.read_bytes() == existing
    assert (home / DOC).read_bytes() == doc
    assert (home / ".codex/config.toml").read_bytes() == config
    assert (home / ".codex/hooks.json").read_bytes() == hooks


def test_new_macro_cwd_guide_upgrades_exact_current_skill_only(tmp_path: Path) -> None:
    current = (ROOT / SKILL_PATH).read_bytes()
    section = b"\n## New Macro sparse-worktree requests\n"
    assert current.count(section) == 1
    prior, guidance = _protected_pre_recovery_codex_skill().split(section, 1)
    prior_blob = hashlib.sha1(b"blob " + str(len(prior)).encode() + b"\0" + prior).hexdigest()
    assert prior_blob == "1ae788e373c93546ac4990e7ab48c1fa539561e9"
    assert b"--cwd '~'" in prior
    assert b'--new-macro-worktree "$MACRO_COMMIT_SHA40" --cwd \'~/lanes/repos/macro\'' in guidance
    home, doc, config, hooks = _home(tmp_path, with_pointer=True)
    (home / USER_SKILL).write_bytes(prior)
    result = policy.apply_codex_fabric_entrypoint(home)
    assert result["state"] == "READY"
    assert (home / USER_SKILL).read_bytes() == current
    assert (home / DOC).read_bytes() == doc
    assert (home / ".codex/config.toml").read_bytes() == config
    assert (home / ".codex/hooks.json").read_bytes() == hooks
    assert not (home / ".claude").exists()
    assert policy.apply_codex_fabric_entrypoint(home)["state"] == "READY"


def test_malformed_codex_pointer_refused_before_install(tmp_path: Path) -> None:
    home, _, config, hooks = _home(tmp_path, with_pointer=False)
    doc = home / DOC
    bad = (policy.CODEX_FABRIC_ENTRY_BEGIN + "\n" + policy.CODEX_FABRIC_ENTRY_BEGIN).encode()
    doc.write_bytes(bad)
    with pytest.raises(policy.OrchestratorPolicyError, match="markers ambiguous"):
        policy.apply_codex_fabric_entrypoint(home)
    assert (home / USER_SKILL).read_bytes() == _legacy_skill()
    assert doc.read_bytes() == bad
    assert (home / ".codex/config.toml").read_bytes() == config
    assert (home / ".codex/hooks.json").read_bytes() == hooks


def test_skill_drift_detected_without_mutation(tmp_path: Path) -> None:
    home, *_ = _home(tmp_path, with_pointer=True)
    assert policy.apply_codex_fabric_entrypoint(home)["state"] == "READY"
    skill = home / USER_SKILL
    skill.write_bytes(skill.read_bytes() + b"\nUnreviewed extra action\n")
    observed = policy.verify_codex_fabric_entrypoint(home)
    assert observed["state"] == "DRIFT"
    assert "codex_fabric_skill.digest" in observed["issues"]


def test_bounded_operator_source_keeps_plain_leaf_denied() -> None:
    from ops.native_fabric.quota_continuity.candidate import fabric_operator_client as client
    assert "fabric_operator_scope" in client.OPERATOR_INSTRUCTIONS
    assert "fabric_child_request" in client.OPERATOR_INSTRUCTIONS
    assert "fabric_child_acknowledge" in client.OPERATOR_INSTRUCTIONS
    assert "C0_MECHANICAL" in client.OPERATOR_INSTRUCTIONS
    without_capability = client.load_operator_environment(
        {"FABRIC_OPERATOR_CAPABILITY": "untrusted", "POOL_TASK_CLASS": "mechanical"},
        "ordinary-leaf", "grok", "grok-4.6", b"packet",
    )
    assert "FABRIC_OPERATOR_CAPABILITY" not in without_capability
    with pytest.raises(ValueError, match="operator_capsule_scope"):
        client.load_operator_environment(
            {"FABRIC_OPERATOR_CAPSULE": "lanes/tmp/run1.operator-cap.json",
             "POOL_TASK_CLASS": "domain_orchestration"},
            "run1", "codex-native", "gpt-6-sol", b"packet",
        )


@pytest.mark.parametrize("preimage, expected_blob", [
    ("pre_review", "b2a24eaada6c2996513eed32ea6a8fa283175015"),
    ("pre_recovery", "21480522be625525f1569fbc0b1dec09d0f06160"),
])
def test_previous_current_codex_skill_is_exact_upgrade_preimage(
    tmp_path: Path, preimage: str, expected_blob: str,
) -> None:
    """Genuine protected guides must upgrade without manufacturing historical hashes."""
    current = (ROOT / SKILL_PATH).read_bytes()
    marker = b"\n## Independent PR review: one portable source contract\n"
    assert current.count(marker) == 1
    protected = _protected_pre_recovery_codex_skill()
    former = protected.split(marker, 1)[0] if preimage == "pre_review" else protected
    blob = hashlib.sha1(b"blob " + str(len(former)).encode("ascii") + b"\0" + former).hexdigest()
    assert blob == expected_blob
    home, doc, config, hooks = _home(tmp_path, with_pointer=True)
    (home / USER_SKILL).write_bytes(former)
    assert policy.verify_codex_fabric_entrypoint(home)["state"] == "DRIFT"
    result = policy.apply_codex_fabric_entrypoint(home)
    assert result["state"] == "READY"
    assert result["native_capacity_modified"] is False
    assert result["provider_settings_modified"] is False
    assert (home / USER_SKILL).read_bytes() == current
    assert (home / DOC).read_bytes() == doc
    assert (home / ".codex/config.toml").read_bytes() == config
    assert (home / ".codex/hooks.json").read_bytes() == hooks
