"""Behavioral checks for complete, no-clobber attended coordinator delivery."""
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/codex_fabric"


def module():
    name = "ops.codex_fabric.orchestrator_bundle"
    assert importlib.util.find_spec(name) is not None, "orchestrator bundle implementation is absent"
    return importlib.import_module(name)


def home(tmp_path):
    result = tmp_path / "codex"
    result.mkdir()
    return result


def install(mod, target, **kwargs):
    before = mod.inspect_bundle(target, **kwargs)
    return mod.install_bundle(target, expected_bundle_digest=before["bundle_digest"], **kwargs)


def source_copy(tmp_path):
    dest = tmp_path / "source"
    dest.mkdir()
    (dest / "agents").mkdir()
    for rel in module().BUNDLE_PATHS:
        shutil.copyfile(SOURCE / rel, dest / rel)
    return dest


def test_source_has_both_coordinators_with_bounded_nonrecursive_roles(tmp_path):
    mod = module()
    result = mod.inspect_bundle(home(tmp_path))
    assert set(result["files"]) == {
        "mastermind-orchestrators.config.toml",
        "agents/l2-sol-ceo.toml", "agents/l2-astra-ceo.toml",
    }
    profile = tomllib.loads((SOURCE / "mastermind-orchestrators.config.toml").read_text())
    assert profile["model"] == "gpt-6-astra"
    assert profile["sandbox_mode"] == "read-only"
    assert profile["agents"]["max_concurrent_threads_per_session"] == 1
    assert profile["agents"]["enabled"] is True
    assert "principal, not the default worker" in profile["developer_instructions"]
    for role, model in (("sol", "gpt-5.6-sol"), ("astra", "gpt-6-astra")):
        value = tomllib.loads((SOURCE / f"agents/l2-{role}-ceo.toml").read_text())
        assert value["name"] == f"l2_{role}_ceo"
        assert value["model"] == model
        assert value["agents"]["enabled"] is False
        assert value["sandbox_mode"] == "read-only"


def test_inspect_does_not_write_or_claim_execution(tmp_path):
    result = module().inspect_bundle(home(tmp_path))
    assert result["state"] == "READY_TO_INSTALL"
    assert result["execution_authorized"] is False
    assert len(result["missing"]) == 3
    assert list((tmp_path / "codex").iterdir()) == []


def test_install_complete_and_repeat_is_noop_preserving_global_settings(tmp_path):
    mod = module(); target = home(tmp_path)
    (target / "config.toml").write_text('model = "unchanged"')
    (target / "mastermind-astra.config.toml").write_text("# incumbent")
    (target / "agents").mkdir()
    (target / "agents/unrelated.toml").write_text("# unrelated")
    result = install(mod, target)
    assert result["state"] == "INSTALLED"
    assert result["execution_authorized"] is False
    assert len(result["created"]) == 3
    mtimes = {rel: (target / rel).stat().st_mtime_ns for rel in mod.BUNDLE_PATHS}
    repeated = install(mod, target)
    assert repeated["created"] == []
    assert mtimes == {rel: (target / rel).stat().st_mtime_ns for rel in mod.BUNDLE_PATHS}
    assert (target / "config.toml").read_text() == 'model = "unchanged"'
    assert (target / "mastermind-astra.config.toml").read_text() == "# incumbent"
    assert (target / "agents/unrelated.toml").read_text() == "# unrelated"


def test_late_conflict_refuses_before_any_other_write(tmp_path):
    mod = module(); target = home(tmp_path)
    (target / "mastermind-orchestrators.config.toml").write_text("# different")
    with pytest.raises(mod.BundleError) as exc:
        install(mod, target)
    assert exc.value.code == "DESTINATION_CONFLICT"
    assert not (target / "agents").exists()
    assert (target / "mastermind-orchestrators.config.toml").read_text() == "# different"


def test_source_digest_changed_after_inspection_refuses_before_writes(tmp_path):
    mod = module(); target = home(tmp_path); src = source_copy(tmp_path)
    digest = mod.inspect_bundle(target, source_root=src)["bundle_digest"]
    file = src / "agents/l2-astra-ceo.toml"
    file.write_text(file.read_text() + "\n# revised reviewed source\n")
    with pytest.raises(mod.BundleError) as exc:
        mod.install_bundle(target, source_root=src, expected_bundle_digest=digest)
    assert exc.value.code == "SOURCE_MOVED"
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("relative", ["agents", "agents/l2-sol-ceo.toml", "mastermind-orchestrators.config.toml"])
def test_destination_symlinks_refuse_without_following(tmp_path, relative):
    mod = module(); target = home(tmp_path); outside = tmp_path / "outside"
    outside.mkdir()
    link = target / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    destination = outside if relative == "agents" else outside / "sentinel"
    if relative != "agents":
        destination.write_text("do not touch")
    link.symlink_to(destination)
    with pytest.raises(mod.BundleError):
        install(mod, target)
    assert link.is_symlink()
    if relative != "agents": assert destination.read_text() == "do not touch"


def test_symlink_home_refuses(tmp_path):
    mod = module(); real = home(tmp_path); alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(mod.BundleError): mod.inspect_bundle(alias)
    assert list(real.iterdir()) == []


def test_symlink_ancestor_refuses(tmp_path):
    mod = module(); real = home(tmp_path); (real / "nested").mkdir()
    alias = tmp_path / "alias"; alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(mod.BundleError): mod.inspect_bundle(alias / "nested")


@pytest.mark.parametrize("relative", ["agents/l2-sol-ceo.toml", "agents/l2-astra-ceo.toml"])
def test_missing_source_role_refuses_without_destination_writes(tmp_path, relative):
    mod = module(); target = home(tmp_path); src = source_copy(tmp_path)
    (src / relative).unlink()
    with pytest.raises(mod.BundleError): mod.inspect_bundle(target, source_root=src)
    assert list(target.iterdir()) == []


def test_source_symlink_refuses(tmp_path):
    mod = module(); target = home(tmp_path); src = source_copy(tmp_path)
    role = src / "agents/l2-astra-ceo.toml"; original = role.read_bytes(); role.unlink()
    outside = tmp_path / "outside.toml"; outside.write_bytes(original); role.symlink_to(outside)
    with pytest.raises(mod.BundleError): mod.inspect_bundle(target, source_root=src)


@pytest.mark.parametrize("replacement", [
    ('enabled = false', 'enabled = true'),
    ('model = "gpt-6-astra"', 'model = "other"'),
    ('sandbox_mode = "read-only"', 'sandbox_mode = "workspace-write"'),
    ('name = "l2_astra_ceo"', 'name = "worker"'),
])
def test_invalid_coordinator_contract_refuses(tmp_path, replacement):
    mod = module(); target = home(tmp_path); src = source_copy(tmp_path)
    role = src / "agents/l2-astra-ceo.toml"
    role.write_text(role.read_text().replace(*replacement))
    with pytest.raises(mod.BundleError) as exc: mod.inspect_bundle(target, source_root=src)
    assert exc.value.code == "SOURCE_CONTRACT_INVALID"


def test_parent_permission_expansion_refuses(tmp_path):
    mod = module(); target = home(tmp_path); src = source_copy(tmp_path)
    profile = src / "mastermind-orchestrators.config.toml"
    profile.write_text(profile.read_text().replace('sandbox_mode = "read-only"', 'sandbox_mode = "danger-full-access"'))
    with pytest.raises(mod.BundleError): mod.inspect_bundle(target, source_root=src)


def test_malformed_source_is_bounded_error_not_content_echo(tmp_path):
    mod = module(); target = home(tmp_path); src = source_copy(tmp_path)
    (src / "agents/l2-astra-ceo.toml").write_text('SENTINEL_SECRET = "unterminated')
    with pytest.raises(mod.BundleError) as exc: mod.inspect_bundle(target, source_root=src)
    assert "SENTINEL_SECRET" not in str(exc.value)


def test_existing_partial_install_is_recognized_without_overwrite(tmp_path):
    mod = module(); target = home(tmp_path); (target / "agents").mkdir()
    rel = "agents/l2-sol-ceo.toml"; original = (SOURCE / rel).read_bytes()
    (target / rel).write_bytes(original); initial = (target / rel).stat().st_mtime_ns
    result = install(mod, target)
    assert rel not in result["created"]
    assert len(result["created"]) == 2
    assert (target / rel).stat().st_mtime_ns == initial


def test_publication_failure_preserves_receipts_and_does_not_enable_parent(tmp_path, monkeypatch):
    mod = module(); target = home(tmp_path); publish = mod._publish_new
    calls = []
    def fail_second(directory_fd, name, content):
        calls.append(name)
        if len(calls) == 2: raise OSError("simulated filesystem failure")
        return publish(directory_fd, name, content)
    monkeypatch.setattr(mod, "_publish_new", fail_second)
    with pytest.raises(mod.BundleError) as exc: install(mod, target)
    assert exc.value.code == "PARTIAL_INSTALL"
    assert exc.value.created == ("agents/l2-sol-ceo.toml",)
    assert not (target / "mastermind-orchestrators.config.toml").exists()
    assert (target / "agents/l2-sol-ceo.toml").read_bytes() == (SOURCE / "agents/l2-sol-ceo.toml").read_bytes()


def test_profile_published_last(tmp_path, monkeypatch):
    mod = module(); target = home(tmp_path); original = mod._publish_new; calls = []
    def record(fd, name, content):
        calls.append(name); return original(fd, name, content)
    monkeypatch.setattr(mod, "_publish_new", record)
    install(mod, target)
    assert calls == ["l2-sol-ceo.toml", "l2-astra-ceo.toml", "mastermind-orchestrators.config.toml"]


def test_inspection_never_executes_provider_or_credential_commands(tmp_path, monkeypatch):
    mod = module(); target = home(tmp_path)
    def forbidden(*args, **kwargs): raise AssertionError("unexpected subprocess")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert install(mod, target)["state"] == "INSTALLED"


def test_cli_defaults_to_inspection_and_requires_digest_for_install(tmp_path):
    module(); target = home(tmp_path)
    cmd = [sys.executable, "-m", "ops.codex_fabric.orchestrator_bundle", "--codex-home", str(target)]
    read = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert read.returncode == 0
    assert json.loads(read.stdout)["state"] == "READY_TO_INSTALL"
    assert list(target.iterdir()) == []
    refused = subprocess.run(cmd + ["--install"], cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert refused.returncode != 0
    assert list(target.iterdir()) == []


def test_contract_validation_survives_python_optimized_mode(tmp_path):
    mod = module(); target = home(tmp_path); src = source_copy(tmp_path)
    role = src / "agents/l2-astra-ceo.toml"
    role.write_text(role.read_text().replace("enabled = false", "enabled = true"))
    code = (
        "from pathlib import Path; "
        "from ops.codex_fabric.orchestrator_bundle import inspect_bundle; "
        f"inspect_bundle(Path({str(target)!r}), source_root=Path({str(src)!r}))"
    )
    result = subprocess.run([sys.executable, "-O", "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0, "optimized Python bypassed the role safety contract"
    assert "SOURCE_CONTRACT_INVALID" in result.stderr


@pytest.mark.parametrize("moved_part", ["home", "agents"])
def test_directory_rebinding_stops_before_next_publication(tmp_path, monkeypatch, moved_part):
    mod = module(); target = home(tmp_path); original = mod._publish_new; calls = []
    def rebind_after_first(fd, name, content):
        original(fd, name, content); calls.append(name)
        if len(calls) == 1:
            source = target if moved_part == "home" else target / "agents"
            source.rename(tmp_path / "moved")
            source.mkdir()
    monkeypatch.setattr(mod, "_publish_new", rebind_after_first)
    with pytest.raises(mod.BundleError) as exc:
        install(mod, target)
    assert exc.value.code == "INSTALL_EFFECT_UNKNOWN"
    assert exc.value.created == ("agents/l2-sol-ceo.toml",)
    assert calls == ["l2-sol-ceo.toml"]
    assert not (target / "mastermind-orchestrators.config.toml").exists()


def test_effective_overrides_pin_parent_contract_and_role_locations(tmp_path):
    mod = module(); target = home(tmp_path); result = install(mod, target)
    assert hasattr(mod, "configuration_overrides"), "effective invocation compiler is absent"
    overrides = mod.configuration_overrides(target, expected_bundle_digest=result["bundle_digest"])
    parsed = {}
    for value in overrides:
        key, raw = value.split("=", 1)
        parsed[key] = tomllib.loads("value=" + raw)["value"]
    assert parsed["model"] == "gpt-6-astra"
    assert parsed["sandbox_mode"] == "read-only"
    assert parsed["approval_policy"] == "never"
    assert parsed["agents.enabled"] is True
    assert parsed["agents.max_concurrent_threads_per_session"] == 1
    assert parsed["agents.default_subagent_model"] == "gpt-5.6-sol"
    for role in ("sol", "astra"):
        assert parsed[f"agents.l2_{role}_ceo.config_file"] == str(target / f"agents/l2-{role}-ceo.toml")
    assert result["role_selection_proven"] is False
    assert result["child_enforcement_proven"] is False


def test_effective_overrides_refuse_incomplete_or_changed_installation(tmp_path):
    mod = module(); target = home(tmp_path)
    assert hasattr(mod, "configuration_overrides"), "effective invocation compiler is absent"
    receipt = mod.inspect_bundle(target)
    with pytest.raises(mod.BundleError):
        mod.configuration_overrides(target, expected_bundle_digest=receipt["bundle_digest"])
    install(mod, target)
    (target / "agents/l2-astra-ceo.toml").write_text("# changed after installation")
    with pytest.raises(mod.BundleError):
        mod.configuration_overrides(target, expected_bundle_digest=receipt["bundle_digest"])


def test_effective_overrides_refuse_mismatched_source_digest(tmp_path):
    mod = module(); target = home(tmp_path); install(mod, target)
    assert hasattr(mod, "configuration_overrides"), "effective invocation compiler is absent"
    with pytest.raises(mod.BundleError) as exc:
        mod.configuration_overrides(target, expected_bundle_digest="0" * 64)
    assert exc.value.code == "SOURCE_MOVED"


def test_child_disable_requires_boolean_false_not_integer_zero(tmp_path):
    mod = module(); target = home(tmp_path); src = source_copy(tmp_path)
    role = src / "agents/l2-astra-ceo.toml"
    role.write_text(role.read_text().replace("enabled = false", "enabled = 0"))
    with pytest.raises(mod.BundleError) as exc:
        mod.inspect_bundle(target, source_root=src)
    assert exc.value.code == "SOURCE_CONTRACT_INVALID"


def test_cli_can_emit_verified_overrides_without_launch(tmp_path):
    mod = module(); target = home(tmp_path); receipt = install(mod, target)
    cmd = [sys.executable, "-m", "ops.codex_fabric.orchestrator_bundle",
           "--codex-home", str(target), "--configuration-overrides",
           "--expected-bundle-digest", receipt["bundle_digest"]]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution_authorized"] is False
    assert "agents.max_concurrent_threads_per_session=1" in payload["configuration_overrides"]
    assert payload["model_turn_started"] is False


def test_cli_overrides_requires_inspected_digest(tmp_path):
    module(); target = home(tmp_path)
    cmd = [sys.executable, "-m", "ops.codex_fabric.orchestrator_bundle",
           "--codex-home", str(target), "--configuration-overrides"]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "--expected-bundle-digest" in result.stderr
    assert list(target.iterdir()) == []
