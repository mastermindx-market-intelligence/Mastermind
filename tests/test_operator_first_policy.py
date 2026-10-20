"""Exercise the exact incumbent installer, not a second deployment implementation.

The inert fixture is pinned #1228 source. A patch candidate is applied only in
pytest's disposable directory; these tests never touch a real provider home.
OPERATOR_FIRST_BASELINE=1 runs the semantic discriminator on the unpatched source.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests/fixtures/operator_first/provider_orchestrator_policy.baseline.txt"
PATCH = ROOT / "patches/operator-first/provider-orchestrator-policy.patch"
ASSETS = ROOT / "skills/mastermind-fabric-orchestration"
BASELINE_SHA = "1db7e21fcbdac041304b27101eb506cc7810340d61330db293f2ad22efc0bfe1"
ROLE_FILES = ("SKILL.md", "references/meta-ceo.md", "references/program-ceo.md",
              "references/operator.md", "references/worker.md", "references/reviewer.md")


def load_installer(tmp_path, *, patched=True):
    source = tmp_path / "source"
    target = source / "ops/executive_os/provider_orchestrator_policy.py"
    target.parent.mkdir(parents=True)
    raw = BASELINE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == BASELINE_SHA
    target.write_bytes(raw)
    if patched and not os.environ.get("OPERATOR_FIRST_BASELINE"):
        subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=source, check=True,
                       capture_output=True)
        subprocess.run(["git", "apply", str(PATCH)], cwd=source, check=True,
                       capture_output=True)
    if ASSETS.exists():
        shutil.copytree(ASSETS, source / "skills/mastermind-fabric-orchestration")
    name = "operator_policy_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    guard = source / "ops/executive_os/provider_orchestrator_guard.py"
    # The installer accepts an explicit guard source. This inert fixture tests
    # distribution/digest preservation, never provider-hook execution.
    guard.write_text("# inert distribution fixture; not a live admission guard\n")
    return module, source, guard


def seed_home(home):
    (home / ".codex").mkdir(parents=True)
    (home / ".claude").mkdir()
    (home / ".codex/AGENTS.md").write_text("Keep my unrelated instructions.\n")
    (home / ".claude/CLAUDE.md").write_text("Keep my unrelated instructions.\n")
    (home / ".codex/config.toml").write_text('model = "keep-selected-model"\n[features]\nkeep = true\n')
    (home / ".claude/settings.json").write_text(json.dumps({"model": "keep-fable",
        "env": {"KEEP_ENV": "yes"}, "permissions": {"deny": ["keep-this"]}}))


def test_incumbent_semantic_discriminator_operator_owns_closure(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    seed_home(home)
    assert m.apply_policy(home, guard_source=guard)["state"] == "READY"
    text = (home / ".claude/CLAUDE.md").read_text()
    assert "GLM/Grok" in text
    assert "operator owns" in text
    assert "adjudication" in text
    assert "Sol is the default day-to-day project executive for decomposition" not in text
    assert "whole completion cycle" in text


@pytest.mark.parametrize("client", [".agents", ".claude"])
@pytest.mark.parametrize("relative", ROLE_FILES)
def test_exact_role_content_is_installed(tmp_path, client, relative):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    m.apply_policy(home, guard_source=guard)
    assert (home / client / "skills/mastermind-fabric-orchestration" / relative).read_bytes() == (ASSETS / relative).read_bytes()


def test_preserves_caps_models_permissions_and_one_managed_block(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    seed_home(home)
    result = m.apply_policy(home, guard_source=guard)
    assert result["state"] == "READY"
    codex = tomllib.loads((home / ".codex/config.toml").read_text())
    claude = json.loads((home / ".claude/settings.json").read_text())
    assert codex["model"] == "keep-selected-model"
    assert codex["features"]["keep"] is True
    assert codex["agents"]["enabled"] is False
    assert codex["agents"]["max_concurrent_threads_per_session"] == 1
    assert claude["model"] == "keep-fable"
    assert claude["permissions"] == {"deny": ["keep-this"]}
    assert claude["env"]["KEEP_ENV"] == "yes"
    assert claude["env"]["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] == "2"
    assert claude["env"]["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] == "1"
    for relative in [".codex/AGENTS.md", ".claude/CLAUDE.md"]:
        text = (home / relative).read_text()
        assert text.count(m.BEGIN) == 1
        assert text.count(m.END) == 1
        assert text.count("Keep my unrelated instructions.") == 1
    assert result["runtime_admission_proven"] is False
    assert result["session_loading_proven"] is False


def test_idempotent_and_preserves_original_backup(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    seed_home(home)
    m.apply_policy(home, guard_source=guard)
    before = {p.relative_to(home): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in home.rglob("*") if p.is_file()}
    assert m.apply_policy(home, guard_source=guard)["state"] == "READY"
    after = {p.relative_to(home): (p.read_bytes(), p.stat().st_mtime_ns)
             for p in home.rglob("*") if p.is_file()}
    assert before == after
    assert (home / (".claude/CLAUDE.md" + m.BACKUP_SUFFIX)).read_text() == "Keep my unrelated instructions.\n"


@pytest.mark.parametrize("mutation", ["missing", "tampered", "symlink", "directory"])
def test_bad_source_role_refuses_before_any_home_mutation(tmp_path, mutation):
    m, source, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    source_role = source / "skills/mastermind-fabric-orchestration/references/operator.md"
    source_role.unlink()
    if mutation == "tampered":
        source_role.write_text("Do everything in the premium parent.\n")
    elif mutation == "symlink":
        source_role.symlink_to(ASSETS / "references/operator.md")
    elif mutation == "directory":
        source_role.mkdir()
    with pytest.raises(m.OrchestratorPolicyError):
        m.apply_policy(home, guard_source=guard)
    assert not home.exists()


@pytest.mark.parametrize("mutation", ["missing", "tampered", "symlink"])
def test_installed_role_drift_is_not_ready(tmp_path, mutation):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    m.apply_policy(home, guard_source=guard)
    role = home / ".agents/skills/mastermind-fabric-orchestration/references/operator.md"
    role.unlink()
    if mutation == "tampered":
        role.write_text("wrong role")
    elif mutation == "symlink":
        role.symlink_to(ASSETS / "references/operator.md")
    result = m.verify_policy(home, guard_source=guard)
    assert result["state"] == "DRIFT"
    assert any("role" in issue for issue in result["issues"])


def test_symlink_destination_refuses_without_changing_peer(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    seed_home(home)
    outsider = tmp_path / "outsider"
    outsider.mkdir()
    (home / ".agents").symlink_to(outsider, target_is_directory=True)
    with pytest.raises(m.OrchestratorPolicyError):
        m.apply_policy(home, guard_source=guard)
    assert list(outsider.iterdir()) == []
    assert (home / ".claude/CLAUDE.md").read_text() == "Keep my unrelated instructions.\n"


def test_partial_apply_retains_original_owner_and_reports_drift(tmp_path, monkeypatch):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    original = m._atomic_write
    calls = []
    def fail_on_fourth(path, payload):
        calls.append(path)
        if len(calls) == 4:
            raise m.OrchestratorPolicyError("injected bounded I/O failure")
        return original(path, payload)
    monkeypatch.setattr(m, "_atomic_write", fail_on_fourth)
    with pytest.raises(m.OrchestratorPolicyApplyIncomplete) as raised:
        m.apply_policy(home, guard_source=guard)
    assert raised.value.modified_files
    assert m.verify_policy(home, guard_source=guard)["state"] == "DRIFT"


def test_role_contract_covers_each_graph_and_no_grant_from_topology(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    m.apply_policy(home, guard_source=guard)
    common = (ASSETS / "SKILL.md").read_text()
    for graph in ["CEO -> worker", "CEO -> operator -> workers", "Meta-CEO -> CEO -> operator -> workers", "Meta-CEO -> operator -> workers"]:
        assert graph in common
    operator = (ASSETS / "references/operator.md").read_text()
    assert "adjudication" in operator and "independent" in operator
    assert "raw worker transcripts" in operator
    ceo = (ASSETS / "references/program-ceo.md").read_text()
    assert "adjudication" in ceo and "LOWER_TOTAL_OVERHEAD" in ceo
    for leaf in ["worker", "reviewer"]:
        assert "Do not spawn" in (ASSETS / f"references/{leaf}.md").read_text()
    assert "not authentication" in common
    assert "EFFECT_UNKNOWN" in common


def test_source_fixture_is_not_a_second_installed_implementation(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    result = m.apply_policy(home, guard_source=guard)
    assert all("baseline" not in str(path) for path in result["managed_files"].values())
    assert result["credentials_read"] is False
    assert result["lifecycle_created"] is False


def test_supporting_role_views_are_not_concatenated_into_parent_context(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    m.apply_policy(home, guard_source=guard)
    for parent in [".codex/AGENTS.md", ".claude/CLAUDE.md"]:
        text = (home / parent).read_text()
        for relative in ROLE_FILES[1:]:
            role_body = (ASSETS / relative).read_text().strip()
            assert role_body not in text
        assert "only the role supplied by the accepted assignment" in text
        assert "installed files" in text.lower()


def test_patch_evidence_binds_exact_source_and_no_other_implementation_path(tmp_path):
    m, source, _ = load_installer(tmp_path)
    pins = json.loads((ROOT / "patches/operator-first/source-pins.json").read_text())
    candidate = source / "ops/executive_os/provider_orchestrator_policy.py"
    assert hashlib.sha256(BASELINE.read_bytes()).hexdigest() == pins["before_sha256"]
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == pins["after_sha256"]
    assert hashlib.sha256(PATCH.read_bytes()).hexdigest() == pins["patch_sha256"]
    assert m.ROLE_SHA256 == pins["role_source_sha256"]
    changed = subprocess.run(["git", "apply", "--numstat", str(PATCH)], cwd=source,
                             check=True, text=True, capture_output=True).stdout.splitlines()
    assert len(changed) == 1
    assert changed[0].split("\t")[-1] == pins["path"]
    assert pins["installed"] is False


def test_original_guard_is_first_partial_apply_effect(tmp_path, monkeypatch):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    original = m._atomic_write
    calls = []
    def fail_second(path, payload):
        calls.append(path)
        if len(calls) == 2:
            raise m.OrchestratorPolicyError("injected second effect failure")
        return original(path, payload)
    monkeypatch.setattr(m, "_atomic_write", fail_second)
    with pytest.raises(m.OrchestratorPolicyApplyIncomplete) as raised:
        m.apply_policy(home, guard_source=guard)
    assert raised.value.modified_files == (str(home / ".codex/hooks/mastermind_fabric_routing_guard.py"),)


def test_source_role_ancestor_symlink_refuses_before_write(tmp_path):
    m, source, guard = load_installer(tmp_path)
    root = source / "skills/mastermind-fabric-orchestration"
    refs = root / "references"
    shutil.rmtree(refs)
    refs.symlink_to(ASSETS / "references", target_is_directory=True)
    home = tmp_path / "home"
    with pytest.raises(m.OrchestratorPolicyError):
        m.apply_policy(home, guard_source=guard)
    assert not home.exists()


def test_canonical_delegation_companion_does_not_make_sol_routine_manager():
    text = (ROOT / "docs/sol_skills/WEB_CEO_DELEGATION.md").read_text()
    assert "OPERATOR_OWNED_DELIVERY" in text
    assert "shared principal subscription pool" in text
    assert "ordinary return adjudication" in text
    assert "`SUSTAINED_ORCHESTRATION`: prefer Sol when a mission's dominant need" not in text
    assert "same pinned" in text


def test_canonical_routing_addendum_enrolls_completion_economics():
    text = (ROOT / "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md").read_text()
    assert "## 1B. Operator-first completion economics" in text
    assert "skills/mastermind-fabric-orchestration/SKILL.md" in text
    assert "does not change cognition-route" in text
    assert "direct commissioning owner retains adjudication" in text


def test_principal_role_overlay_does_not_mutate_protected_operator_package():
    """The new role is a separately installed Skill, not old package authority.

    Re-pointing a protected V4 package's Skill bytes at this unmerged role text
    breaks its signed generation and cannot be called source-qualified. The
    accepted incumbent role installer owns future explicit role selection.
    """
    ceo = (ROOT / "plugins/mastermind-sol/skills/mastermind-web-ceo/SKILL.md").read_text()
    operator_path = ROOT / "plugins/mastermind-operator/skills/receive-commission/SKILL.md"
    operator = operator_path.read_bytes()
    assert hashlib.sha256(operator).hexdigest() == (
        "212f5253c812ca47174ca9aac92977d5f649891da28c12b6948c4e0284422c4d"
    )
    assert "skills/mastermind-fabric-orchestration/SKILL.md" in ceo
    assert "same exact commit" in ceo
    assert "only the assigned role" in ceo
    assert "Read `../../references/dialogue-boundary.md`" in operator.decode()
    assert len(ceo.split()) <= 650
    core = (ROOT / "skills/mastermind-fabric-orchestration/SKILL.md").read_text()
    delivery = (ROOT / "skills/mastermind-fabric-orchestration/references/operator.md").read_text()
    assert "ordinary return adjudication" in core
    assert "only the role supplied by the accepted assignment" in core
    assert "not authentication" in core
    assert "missing access is not authority" in delivery
    assert "independent review" in delivery

@pytest.mark.parametrize("key,configured", [
    ("CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS", "12"),
    ("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH", "3"),
])
def test_existing_claude_capacity_not_silently_reduced(tmp_path, key, configured):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    seed_home(home)
    settings_path = home / ".claude/settings.json"
    settings = json.loads(settings_path.read_text())
    settings.setdefault("env", {})[key] = configured
    settings_path.write_text(json.dumps(settings, sort_keys=True))
    existing_doc = (home / ".claude/CLAUDE.md").read_bytes()
    existing_settings = settings_path.read_bytes()
    with pytest.raises(m.OrchestratorPolicyError, match="Claude native limit"):
        m.apply_policy(home, guard_source=guard)
    assert settings_path.read_bytes() == existing_settings
    assert (home / ".claude/CLAUDE.md").read_bytes() == existing_doc
    assert not (home / ".codex/hooks/mastermind_fabric_routing_guard.py").exists()
    assert not (home / ".agents/skills/mastermind-fabric-orchestration").exists()

def test_scoped_claude_profile_no_unrelated_codex(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text('{"model":"preserve","env":{}}\n')
    result = m.apply_provider_policy(home, "claude", guard_source=guard)
    assert result["state"] == "READY" and result["provider_scope"] == "claude"
    assert not (home / ".codex").exists()
    assert not (home / ".agents").exists()
    assert json.loads((home / ".claude/settings.json").read_text())["model"] == "preserve"
    assert all(k.startswith("claude_") for k in result["managed_files"])
    snapshot = {k: Path(v).read_bytes() for k,v in result["managed_files"].items()}
    assert m.apply_provider_policy(home, "claude", guard_source=guard)["state"] == "READY"
    assert snapshot == {k: Path(v).read_bytes() for k,v in result["managed_files"].items()}
    assert (home / ".claude/CLAUDE.md").read_text().count(m.BEGIN) == 1


def test_scoped_codex_ignores_unrelated_claude_cap12(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings = home / ".claude/settings.json"
    orig = b'{"env":{"CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS":"12"}}\n'
    settings.write_bytes(orig)
    result = m.apply_provider_policy(home, "codex", guard_source=guard)
    assert result["state"] == "READY"
    assert settings.read_bytes() == orig
    assert not (home / ".claude/skills/mastermind-fabric-orchestration").exists()
    assert (home / ".agents/skills/mastermind-fabric-orchestration/SKILL.md").exists()
    assert m.verify_provider_policy(home, "codex", guard_source=guard)["state"] == "READY"
    assert m.verify_provider_policy(home, "claude", guard_source=guard)["state"] == "DRIFT"
    assert m.verify_policy(home, guard_source=guard)["state"] == "DRIFT"


@pytest.mark.parametrize("cap,depth", [("12", "1"), ("2", "3"), ("0", None)])
def test_scoped_claude_capacity_refuses_pre_effect(tmp_path, cap, depth):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {"CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": cap}
    if depth:env["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] = depth
    settings = home / ".claude/settings.json"
    settings.write_text(json.dumps({"env":env}))
    before = settings.read_bytes()
    with pytest.raises(m.OrchestratorPolicyError, match="Claude native limit"):
        m.apply_provider_policy(home, "claude", guard_source=guard)
    assert settings.read_bytes() == before
    assert not (home / ".claude/hooks").exists()
    assert not (home / ".claude/skills/mastermind-fabric-orchestration").exists()
    assert not (home / ".codex").exists()


def test_scoped_claude_rejects_symlink_destination_before_write(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (home / ".claude").symlink_to(external, target_is_directory=True)
    with pytest.raises(m.OrchestratorPolicyError):
        m.apply_provider_policy(home, "claude", guard_source=guard)
    assert list(external.iterdir()) == []
    assert not (home / ".codex").exists()


def test_scoped_verifier_rejects_noncommand_guard_mutation(tmp_path):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    m.apply_provider_policy(home, "claude", guard_source=guard)
    path = home / ".claude/settings.json"
    data = json.loads(path.read_text())
    rows = [h for row in data["hooks"]["PreToolUse"] for h in row["hooks"]
            if "mastermind_fabric_routing_guard.py" in h.get("command", "")]
    assert len(rows)==1
    rows[0]["type"]="prompt"
    path.write_text(json.dumps(data))
    result=m.verify_provider_policy(home, "claude", guard_source=guard)
    assert result["state"]=="DRIFT"
    assert "claude_settings.pretool" in result["issues"]


def test_scoped_partial_apply_has_exact_original_carrier_evidence(tmp_path, monkeypatch):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    orig=m._atomic_write
    counter=[0]
    def fail_fourth(path,payload):
        counter[0]+=1
        if counter[0]==4:raise m.OrchestratorPolicyError("injected failure")
        return orig(path,payload)
    monkeypatch.setattr(m, "_atomic_write", fail_fourth)
    with pytest.raises(m.OrchestratorPolicyApplyIncomplete) as exc:
        m.apply_provider_policy(home, "claude", guard_source=guard)
    assert exc.value.modified_files
    assert m.verify_provider_policy(home, "claude", guard_source=guard)["state"]=="DRIFT"
    assert not (home / ".codex").exists()


def test_scoped_cli_defaults_unchanged_both(tmp_path, capsys):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    assert m.main(["apply","--home",str(home),"--guard-source",str(guard),
                   "--provider","claude"]) == 0
    output=json.loads(capsys.readouterr().out)
    assert output["provider_scope"]=="claude"
    assert not (home / ".codex").exists()
    assert m.main(["verify","--home",str(home),"--guard-source",str(guard),
                   "--provider","claude"]) == 0
    assert json.loads(capsys.readouterr().out)["state"]=="READY"
    assert m.main(["verify","--home",str(home),"--guard-source",str(guard)]) == 1
    assert json.loads(capsys.readouterr().out)["state"]=="DRIFT"


def test_scoped_provider_enum_closed(tmp_path):
    m, _, guard = load_installer(tmp_path)
    with pytest.raises(m.OrchestratorPolicyError, match="provider"):
        m.apply_provider_policy(tmp_path/"home", "unknown", guard_source=guard)
    with pytest.raises(m.OrchestratorPolicyError, match="provider"):
        m.verify_provider_policy(tmp_path/"home", "unknown", guard_source=guard)

@pytest.mark.parametrize("provider,unselected", [
    ("claude", ".codex"),
    ("codex", ".claude"),
])
def test_scoped_provider_does_not_read_unrelated_profile(tmp_path, monkeypatch, provider, unselected):
    m, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    peer = home / unselected
    peer.mkdir(parents=True)
    # Invalid peer config would be dangerous to inspect or treat as selected.
    (peer / ("config.toml" if unselected == ".codex" else "settings.json")).write_text(
        "invalid peer content intentionally unreadable by scoped rollout"
    )
    original = m._regular_bytes
    def forbid_peer_reads(path, *args, **kwargs):
        assert not Path(path).is_relative_to(peer), "read from unrelated provider"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(m, "_regular_bytes", forbid_peer_reads)
    ready = m.apply_provider_policy(home, provider, guard_source=guard)
    assert ready["state"] == "READY"
    assert m.verify_provider_policy(home, provider, guard_source=guard)["state"] == "READY"
    assert (peer / ("config.toml" if unselected == ".codex" else "settings.json")).read_text().startswith("invalid peer")
