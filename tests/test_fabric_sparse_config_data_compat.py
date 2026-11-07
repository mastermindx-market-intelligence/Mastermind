"""Qualify the current executor's narrow, data-only Git configuration delta.

All Git objects and worktrees are disposable fixtures. The existing donor
fixture stubs only the owned-process runner; parser, qualification and Git
observations stay real. No provider, remote transport or live donor is used.
"""
from pathlib import Path
import subprocess

import pytest

import test_fabric_clean_linked_donor_20261017 as donor_contract
import test_fabric_native_security_composition_20261018 as composition


applied = composition.applied
module = donor_contract.module
repository = donor_contract.repository

HTTP_KEYS = ("postBuffer", "lowSpeedLimit", "lowSpeedTime")
DATA_CONFIG = (
    "[extensions]\npartialClone = origin\n"
    "[http]\npostBuffer = 2147483647\nlowSpeedLimit = 0\nlowSpeedTime = 60\n"
)


def _no_process(*args, **kwargs):
    pytest.fail("a configuration-only operation launched a subprocess")


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    # The production reader confines donors to the actual owner's home. Keep
    # that check real, using the same disposable-home seam as the donor cases.
    home = tmp_path.resolve(strict=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home / "config"


@pytest.mark.parametrize("key", HTTP_KEYS)
@pytest.mark.parametrize("value", ["0", "1", "60", "2147483647"])
def test_canonical_http_numbers_are_inert_data(module, config_path, monkeypatch, key, value):
    path = config_path
    content = f"[http]\n\t{key} = \t{value} \t\n".encode()
    path.write_bytes(content)
    monkeypatch.setattr(subprocess, "Popen", _no_process)
    parsed, identity = module["_sparse_config"](path)
    assert parsed == {"http." + key.lower(): value}
    assert identity is not None and path.read_bytes() == content


@pytest.mark.parametrize("key", HTTP_KEYS)
@pytest.mark.parametrize("value", [
    "-1", "+1", "00", "01", "1k", "1K", "1.0", "1e3",
    "2147483648", "9999999999", "10000000000", "１", "١",
    "1 0", "1\t0", '"1"', "1 # comment", "1 ; comment", "1\\\n0",
])
def test_noncanonical_http_numbers_refuse_before_any_process(module, config_path, monkeypatch, key, value):
    path = config_path
    content = f"[http]\n{key} = {value}\n".encode()
    path.write_bytes(content)
    monkeypatch.setattr(subprocess, "Popen", _no_process)
    with pytest.raises(module["SparseWorkspaceRefused"], match="GIT_CONFIG_UNQUALIFIED") as raised:
        module["_sparse_config"](path)
    assert not raised.value.effect_unknown and path.read_bytes() == content


@pytest.mark.parametrize("promisor", [None, "true", "false"])
def test_partial_clone_origin_does_not_require_a_promisor_flag(module, config_path, monkeypatch, promisor):
    content = '[extensions]\npartialClone = origin\n[remote "origin"]\n'
    content += "url = https://example.invalid/inert.git\npartialCloneFilter = blob:none\n"
    if promisor is not None:
        content += f"promisor = {promisor}\n"
    path = config_path
    path.write_text(content)
    monkeypatch.setattr(subprocess, "Popen", _no_process)
    parsed, _ = module["_sparse_config"](path)
    assert parsed["extensions.partialclone"] == "origin"
    assert parsed.get("remote.origin.promisor") == promisor
    assert path.read_text() == content


@pytest.mark.parametrize("value", ["Origin", "ORIGIN", "upstream", "origin/other", "origin other", '"origin"'])
def test_partial_clone_remote_name_is_literal(module, config_path, monkeypatch, value):
    path = config_path
    path.write_text(f"[extensions]\npartialClone = {value}\n")
    monkeypatch.setattr(subprocess, "Popen", _no_process)
    with pytest.raises(module["SparseWorkspaceRefused"], match="GIT_CONFIG_UNQUALIFIED"):
        module["_sparse_config"](path)


@pytest.mark.parametrize("content", [
    "[http]\npostBuffer = 1\npostbuffer = 1\n",
    "[extensions]\npartialClone = origin\npartialclone = origin\n",
    '[http "https://example.invalid"]\npostBuffer = 1\n',
    '[http "example.invalid"]\nlowSpeedTime = 1\n',
    "[http]\nsslVerify = true\n", "[http]\nproxy = origin\n",
    "[extensions]\npartialClone = origin # comment\n",
    "[http]\npostBuffer =\n", "[http]\npostBuffer = 1\x00\n",
])
def test_ambiguous_scoped_and_unknown_config_stays_closed(module, config_path, monkeypatch, content):
    path = config_path
    path.write_text(content)
    monkeypatch.setattr(subprocess, "Popen", _no_process)
    with pytest.raises(module["SparseWorkspaceRefused"], match="GIT_CONFIG_UNQUALIFIED"):
        module["_sparse_config"](path)
    assert path.read_text() == content


@pytest.mark.parametrize("scope", ["common", "worktree"])
@pytest.mark.parametrize("content", [
    "[extensions]\npartialClone = Origin\n",
    "[http]\npostBuffer = 2147483648\n",
    '[http "example.invalid"]\nlowSpeedTime = 1\n',
])
def test_new_settings_refuse_before_controller_git_in_both_config_owners(repository, monkeypatch, scope, content):
    f = repository
    gitdir = Path(donor_contract._git(f.alternate, "rev-parse", "--absolute-git-dir"))
    path = f.original / ".git/config" if scope == "common" else gitdir / "config.worktree"
    original = path.read_bytes()
    path.write_bytes(original + content.encode())
    monkeypatch.setattr(subprocess, "Popen", _no_process)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="GIT_CONFIG_UNQUALIFIED") as raised:
        f.invoke()
    assert not raised.value.effect_unknown and f.calls == []
    assert path.read_bytes() == original + content.encode()


@pytest.mark.parametrize("donor_kind", ["primary", "linked"])
def test_actual_mint_accepts_data_settings_with_every_transport_disabled(repository, monkeypatch, donor_kind):
    f = repository
    donor = f.alternate
    if donor_kind == "primary":
        donor = f.original
        (donor / "preserve.txt").write_text("keep\n")
        (donor / "scripts/worktree_sparse.py").write_bytes(f.reviewed)
        donor_contract._git(donor, "add", "scripts/worktree_sparse.py")
        donor_contract._git(donor, "commit", "-qm", "reviewed primary data fixture")
        donor_contract._git(donor, "sparse-checkout", "set", "--cone", ".claude", ".codex", "config", "scripts", "docs")
    common = f.original / ".git/config"
    common.write_bytes(common.read_bytes() + DATA_CONFIG.encode())
    original_config = common.read_bytes()
    gitdir = Path(donor_contract._git(donor, "rev-parse", "--absolute-git-dir"))
    worktree = gitdir / "config.worktree"
    worktree.write_bytes(worktree.read_bytes() + b"[http]\nlowSpeedTime = 120\n")
    original_worktree = worktree.read_bytes()
    _, effective, _ = f.module["_sparse_git_context"](donor, f.original / ".git")
    assert effective["http.lowspeedtime"] == "120"
    assert "remote.origin.promisor" not in effective
    real = subprocess.Popen
    observations = []

    def observed(command, *args, **kwargs):
        if "--no-optional-locks" in command:
            observations.append((command, kwargs["env"]))
        return real(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", observed)
    target = Path(f.invoke())
    assert target.is_dir() and len(f.calls) == 1
    assert f.calls[0][1]["cwd"] == str(donor)
    assert observations
    for command, _ in observations:
        assert command[0] == "/usr/bin/git"
        assert "core.hooksPath=/dev/null" in command and "core.fsmonitor=false" in command
    for env in [env for _, env in observations] + [f.calls[0][1]["env"]]:
        assert env["GIT_ALLOW_PROTOCOL"] == "" and env["GIT_NO_LAZY_FETCH"] == "1"
        settings = {env["GIT_CONFIG_KEY_" + str(i)]: env["GIT_CONFIG_VALUE_" + str(i)]
                    for i in range(int(env["GIT_CONFIG_COUNT"]))}
        assert settings["protocol.allow"] == "never"
        assert settings["core.hooksPath"] == "/dev/null" and settings["core.fsmonitor"] == "false"
    assert common.read_bytes() == original_config and worktree.read_bytes() == original_worktree


def test_valid_data_does_not_repair_or_admit_a_missing_sparse_cone(repository):
    f = repository
    common = f.original / ".git/config"
    common.write_bytes(common.read_bytes() + DATA_CONFIG.encode())
    # Isolate the missing cone flag from Git sparse-index/cone consistency.
    # Expand the disposable fixture index while its cone is still valid.
    donor_contract._git(f.alternate, "sparse-checkout", "reapply", "--no-sparse-index")
    donor_contract._git(f.alternate, "config", "--worktree", "--unset", "core.sparseCheckoutCone")
    gitdir = Path(donor_contract._git(f.alternate, "rev-parse", "--absolute-git-dir"))
    path = gitdir / "config.worktree"
    before = path.read_bytes()
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="DONOR_PROFILE_UNQUALIFIED") as raised:
        f.invoke()
    assert not raised.value.effect_unknown and f.calls == []
    assert path.read_bytes() == before


def test_valid_data_does_not_broaden_the_fixed_linked_donor_profile(repository):
    f = repository
    common = f.original / ".git/config"
    common.write_bytes(common.read_bytes() + DATA_CONFIG.encode())
    donor_contract._git(f.alternate, "sparse-checkout", "set", "--cone", ".claude", ".codex", "config", "scripts", "docs")
    gitdir = Path(donor_contract._git(f.alternate, "rev-parse", "--absolute-git-dir"))
    rules = gitdir / "info/sparse-checkout"
    before = rules.read_bytes()
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="DONOR_PROFILE_UNQUALIFIED"):
        f.invoke()
    assert f.calls == [] and rules.read_bytes() == before
