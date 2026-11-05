"""Apply the shipped patch, then exercise its actual workspace-mint boundary.

Git repositories are disposable fixtures. The owned-process runner is a stub
that creates a real linked sparse Git worktree; it is not a provider, physical
lease, runtime receipt or accepted-worker proof. Config and drift fixtures are
inert. No hook, fsmonitor command or shadow-module payload is executed.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "integrations/fleet/ubuntu_thermal_headroom_20261013/FABRIC_CLEAN_LINKED_DONOR_FALLBACK_20261016.patch"
PREIMAGE = ROOT / "tests/fixtures/fabric_executor_m2_a29798ab.py.txt"
PREIMAGE_SHA256 = "a29798abb84294b1d8a67c53ef2b45137db4517f960598e51c8da21796d6cf61"
PATCH_SHA256 = "dbcc9b8938781cc18f3da0fdfe5bad8ee5693c89873f68260e33a8c44339ce95"
POSTIMAGE_SHA256 = "131f56a4c26915d9e6a5fc6501f930b3aeeb5e4c4501eb730b080e0c6dde5772"


def _blob(body: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()


def _git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "LD_", "DYLD_"))}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                             "-C", str(root), *args], env=env,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, (args, result.stderr[:500])
    return result.stdout.strip()


@pytest.fixture(scope="session")
def applied(tmp_path_factory):
    before = PREIMAGE.read_bytes()
    patch = PATCH.read_bytes()
    assert hashlib.sha256(before).hexdigest() == PREIMAGE_SHA256
    assert hashlib.sha256(patch).hexdigest() == PATCH_SHA256
    assert patch.startswith(b"--- a/remote_sub_exec.py\n+++ b/remote_sub_exec.py\n")
    assert patch.count(b"+++ b/") == 1
    directory = tmp_path_factory.mktemp("applied-fabric-patch")
    target = directory / "remote_sub_exec.py"
    target.write_bytes(before)
    _git(directory, "apply", "--check", str(PATCH))
    _git(directory, "apply", str(PATCH))
    after = target.read_bytes()
    assert hashlib.sha256(after).hexdigest() == POSTIMAGE_SHA256
    assert before[before.index(b"def _execute("):] == after[after.index(b"def _execute("):]
    parsed = ast.parse(after, filename=str(target))
    wanted = []
    for node in parsed.body:
        if isinstance(node, ast.ClassDef) and node.name == "SparseWorkspaceRefused":
            wanted.append(node)
        elif isinstance(node, ast.FunctionDef) and (
                node.name.startswith("_sparse_") or node.name in {
                    "_qualify_sparse_donor", "_clean_linked_sparse_donor", "_new_macro_workspace"}):
            wanted.append(node)
        elif isinstance(node, ast.Assign) and all(
                isinstance(t, ast.Name) and t.id.startswith(("_MACRO_", "_SPARSE_")) for t in node.targets):
            wanted.append(node)
    assert any(isinstance(n, ast.FunctionDef) and n.name == "_new_macro_workspace" for n in wanted)
    return compile(ast.Module(body=wanted, type_ignores=[]), str(target), "exec")


@pytest.fixture
def module(applied):
    namespace = dict(Path=Path, os=os, re=re, stat=stat, subprocess=subprocess,
                     selectors=selectors, sys=sys, hashlib=hashlib, json=json, time=time,
                     LaneRuntimeError=type("LaneRuntimeError", (RuntimeError,), {}),
                     OwnedProcessStartError=type("OwnedProcessStartError", (RuntimeError,), {}))
    exec(applied, namespace)
    return namespace


@pytest.fixture
def repository(tmp_path, monkeypatch, module):
    home = tmp_path.resolve(strict=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    original = home / "lanes/repos/macro"
    original.mkdir(parents=True)
    _git(original, "init", "-q")
    _git(original, "config", "user.name", "Fabric Fixture")
    _git(original, "config", "user.email", "fixture@example.invalid")
    _git(original, "config", "extensions.worktreeConfig", "true")
    old = b"# inert old helper fixture\n"
    reviewed = b"# inert reviewed helper fixture; runner is stubbed\n"
    policy = json.dumps({"enabled": True, "exclude_dirs": ["data", "site", "mockups", "verify_shots"]}).encode() + b"\n"
    for directory in (".claude", ".codex", "scripts", "config", "docs", "data", "site", "mockups", "verify_shots"):
        path = original / directory
        path.mkdir()
        (path / "keep.txt").write_text("tracked fixture\n")
    (original / "scripts/worktree_sparse.py").write_bytes(old)
    (original / "config/sparse_worktree.json").write_bytes(policy)
    (original / "preserve.txt").write_text("keep\n")
    (original / ".gitignore").write_text("scripts/cache.fixture\n")
    _git(original, "add", ".")
    _git(original, "commit", "-qm", "original fixture")
    original_head = _git(original, "rev-parse", "HEAD")
    alternate = original.parent / "macro-fabric-pinned-20261016"
    _git(original, "worktree", "add", "-q", "-b", "reviewed-fixture", str(alternate))
    (alternate / "scripts/worktree_sparse.py").write_bytes(reviewed)
    _git(alternate, "add", "scripts/worktree_sparse.py")
    _git(alternate, "commit", "-qm", "reviewed fixture")
    reviewed_head = _git(alternate, "rev-parse", "HEAD")
    _git(alternate, "sparse-checkout", "set", "--cone", "--sparse-index", ".claude", ".codex", "config", "scripts")
    (original / "preserve.txt").write_text("ORIGINAL UNCOMMITTED WORK\n")
    module.update(_MACRO_PREMERGE_SPARSE_BLOB=_blob(old),
                  _MACRO_FABRIC_SPARSE_BLOB=_blob(reviewed),
                  _MACRO_SPARSE_CONFIG_BLOB=_blob(policy),
                  _MACRO_PINNED_DONOR_COMMIT=reviewed_head)
    key = "fixture-new-mint"
    for name, value in {"FABRIC_NEW_MACRO_COMMIT": reviewed_head,
                        "REMOTE_SUB_RUN_ID": key, "POOL_ORCHESTRATOR_ID": "fixture-root",
                        "POOL_PARENT_RUN_ID": "fixture-parent", "POOL_LEASE_ID": "fixture-lease",
                        "POOL_ACCOUNT": "fixture-account"}.items():
        monkeypatch.setenv(name, value)
    here = home / "lanes/support-releases/fixture/ext"
    (here / "lanes").mkdir(parents=True)
    result = SimpleNamespace(returncode=0, timed_out=False, cleanup_proven=True,
                             stdout_truncated=False, stderr_truncated=False)
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        destination = home / "lanes/wt" / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        _git(original, "worktree", "add", "--no-checkout", "-b", "lane/" + key,
             str(destination), reviewed_head)
        _git(destination, "sparse-checkout", "set", "--cone", ".claude", ".codex", "config", "scripts", "docs")
        _git(destination, "read-tree", "-mu", "HEAD")
        return result

    module["run_owned_process"] = runner
    fixture = SimpleNamespace(home=home, original=original, alternate=alternate,
                              original_head=original_head, head=reviewed_head,
                              old=old, reviewed=reviewed, policy=policy, module=module,
                              key=key, here=here, calls=calls, result=result, runner=runner)
    fixture.invoke = lambda: module["_new_macro_workspace"](
        key, str(original), here, dict(os.environ), SimpleNamespace(nice=10))
    return fixture


def test_production_source_pins(module):
    assert module["_MACRO_PREMERGE_SPARSE_BLOB"] == "296e47bab2d28f9a019e81b5aef76eeea62a6cc3"
    assert module["_MACRO_FABRIC_SPARSE_BLOB"] == "75297acb10d0cef4d01730a59fdcad19c7cfd3e6"
    assert module["_MACRO_SPARSE_CONFIG_BLOB"] == "46b4d13bb5302a68b437a257eebe066d07bdc7ff"
    assert module["_MACRO_PINNED_DONOR_COMMIT"] == "6ee058b0491a3f67e843f25d4379b94e98880e8b"
    assert module["_MACRO_PINNED_DONOR_CONE"] == (".claude", ".codex", "config", "scripts")


@pytest.mark.parametrize("sparse_index", [True, False])
def test_actual_new_workspace_accepts_sparse_donor_and_preserves_original(repository, sparse_index):
    f = repository
    if not sparse_index:
        _git(f.alternate, "sparse-checkout", "reapply", "--no-sparse-index")
    assert "S " in _git(f.alternate, "ls-files", "-v", "--sparse")
    target = Path(f.invoke())
    assert target == f.home / "lanes/wt" / f.key
    assert _git(target, "rev-parse", "HEAD") == f.head
    assert _git(target, "branch", "--show-current") == "lane/" + f.key
    assert _git(target, "status", "--porcelain=v1", "-uall") == ""
    assert (target / "docs/keep.txt").is_file()
    assert not (target / "data/keep.txt").exists()
    assert _git(f.original, "rev-parse", "HEAD") == f.original_head
    assert (f.original / "preserve.txt").read_text() == "ORIGINAL UNCOMMITTED WORK\n"
    assert len(f.calls) == 1
    argv, kw = f.calls[0]
    assert argv == [sys.executable, "-I", str(f.alternate / "scripts/worktree_sparse.py"),
                    "fabric-mint", f.key, f.head]
    assert kw["cwd"] == str(f.alternate)
    assert kw["label"] == f.key + ":workspace-mint"
    assert kw["receipt_path"] == f.here / "lanes" / (f.key + ".workspace-mint.process.jsonl")
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_LEASE_ID", "POOL_ACCOUNT"):
        assert kw["env"][name] == os.environ[name]
    assert kw["env"]["MASTERMIND_FABRIC_SPARSE_NEW"] == "1"
    assert "MASTERMIND_FABRIC_SPARSE_NEW" not in os.environ


@pytest.mark.parametrize("scope", ["common", "worktree"])
@pytest.mark.parametrize("setting", [
    "[core]\nfsmonitor = false\n", "[core]\nhooksPath = /dev/null\n",
    "[core]\npager = false\n", "[core]\neditor = false\n",
    "[core]\nsshCommand = false\n", '[alias]\nfixture = status\n',
    '[protocol "ext"]\nallow = never\n', '[include]\npath = /dev/null\n',
    '[filter "fixture"]\nrequired = false\n', '[core]\nworktree = .\n',
    '[core]\nignoreStat = false\n',
])
def test_untrusted_config_refuses_before_any_controller_git_or_mint(repository, monkeypatch, scope, setting):
    f = repository
    gitdir = Path(_git(f.alternate, "rev-parse", "--absolute-git-dir"))
    path = f.original / ".git/config" if scope == "common" else gitdir / "config.worktree"
    with path.open("a") as stream:
        stream.write("\n" + setting)

    def forbidden(*args, **kwargs):
        pytest.fail("Git executed before local config qualification")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="GIT_CONFIG_UNQUALIFIED") as raised:
        f.invoke()
    assert not raised.value.effect_unknown
    assert f.calls == []


@pytest.mark.parametrize("direct", [False, True])
def test_gitlink_refuses_before_status_or_mint(repository, direct):
    f = repository
    donor = f.alternate
    if direct:
        donor = f.original
        (donor / "preserve.txt").write_text("keep\n")
        (donor / "scripts/worktree_sparse.py").write_bytes(f.reviewed)
        _git(donor, "add", "scripts/worktree_sparse.py")
        _git(donor, "commit", "-qm", "reviewed original fixture")
    name = ".codex/nested-fixture"
    child = donor / name
    child.mkdir()
    _git(child, "init", "-q")
    child_config = (child / ".git/config").read_bytes()
    _git(donor, "update-index", "--add", "--cacheinfo", "160000", f.head, name)
    assert _git(donor, "ls-files", "--stage", "--", name).startswith("160000 ")
    real = f.module["_sparse_git"]

    def observed(root, common, *args, **kwargs):
        if args[0] == "status":
            pytest.fail("Gitlink reached status before child-repository refusal")
        return real(root, common, *args, **kwargs)

    f.module["_sparse_git"] = observed
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="GITLINK_UNQUALIFIED") as raised:
        f.invoke()
    assert not raised.value.effect_unknown
    assert (child / ".git/config").read_bytes() == child_config
    assert f.calls == []


def test_git_environment_is_scrubbed_for_controller_and_actual_mint_boundary(repository, monkeypatch):
    f = repository
    monkeypatch.setenv("GIT_DIR", "/inert/untrusted-fixture")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "99")
    monkeypatch.setenv("GIT_CONFIG_KEY_98", "inert.fixture")
    monkeypatch.setenv("GIT_CONFIG_VALUE_98", "inert")
    monkeypatch.setenv("GIT_SSH_COMMAND", "inert-unused-value")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/inert/untrusted-global")
    original = subprocess.Popen
    observed = []

    def spy(command, *args, **kwargs):
        if "--no-optional-locks" in command:
            observed.append((command, kwargs["env"]))
        return original(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    f.invoke()
    assert observed
    environments = [env for _, env in observed] + [f.calls[0][1]["env"]]
    for command, _ in observed:
        assert command[0] == "/usr/bin/git"
        assert "core.fsmonitor=false" in command and "core.hooksPath=/dev/null" in command
    for env in environments:
        assert "GIT_DIR" not in env and "GIT_SSH_COMMAND" not in env
        assert "GIT_CONFIG_KEY_98" not in env and "GIT_CONFIG_VALUE_98" not in env
        assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
        assert env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert env["GIT_NO_LAZY_FETCH"] == "1"
        assert env["GIT_ALLOW_PROTOCOL"] == ""
        settings = {env["GIT_CONFIG_KEY_" + str(i)]: env["GIT_CONFIG_VALUE_" + str(i)]
                    for i in range(int(env["GIT_CONFIG_COUNT"]))}
        assert settings["core.fsmonitor"] == "false"
        assert settings["core.hooksPath"] == "/dev/null"
        assert settings["protocol.allow"] == "never"
        assert env["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"


@pytest.mark.parametrize("path", ["scripts/worktree_sparse.py", "config/sparse_worktree.json", "preserve.txt", "docs/keep.txt"])
def test_clean_assume_unchanged_flags_refuse_without_executing_a_bypass(repository, path):
    f = repository
    # Only a flag is set on unchanged fixture content. No hidden changed-file
    # reproduction or executable payload is constructed.
    # An omitted child has no individual entry in a compact sparse index;
    # retain a full index for this flag-only fixture and prove the flag exists.
    if path.startswith("docs/"):
        _git(f.alternate, "sparse-checkout", "reapply", "--no-sparse-index")
    _git(f.alternate, "update-index", "--assume-unchanged", "--", path)
    assert _git(f.alternate, "ls-files", "-v", "--", path)[0] in {"h", "s"}
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="(INPUT_INDEX|INDEX_FLAGS)_UNQUALIFIED"):
        f.invoke()
    assert f.calls == []


def test_modified_policy_bytes_refuse_independently_of_git_status(repository):
    f = repository
    (f.alternate / "config/sparse_worktree.json").write_text('{"enabled":false}\n')
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="INPUT_BLOB_MISMATCH"):
        f.invoke()
    assert f.calls == []


def test_policy_index_must_match_independent_head_and_working_pin(repository):
    f = repository
    policy = f.alternate / "config/sparse_worktree.json"
    policy.write_text('{"enabled":false}\n')
    _git(f.alternate, "add", "config/sparse_worktree.json")
    policy.write_bytes(f.policy)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="INPUT_INDEX_UNQUALIFIED"):
        f.invoke()
    assert f.calls == []


@pytest.mark.parametrize("path", ["scripts/worktree_sparse.py", "config/sparse_worktree.json"])
def test_critical_skip_flag_observation_refuses(repository, path):
    f = repository
    real = f.module["_sparse_git"]

    def observed(root, common, *args, **kwargs):
        result = real(root, common, *args, **kwargs)
        if args[:4] == ("ls-files", "-v", "--stage", "-z") and args[-1] == path:
            return b"S" + result[1:]
        return result

    f.module["_sparse_git"] = observed
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="INPUT_INDEX_UNQUALIFIED"):
        f.invoke()
    assert f.calls == []


@pytest.mark.parametrize("name", ["preserve.txt", "scripts/keep.txt", "docs/keep.txt"])
def test_skipped_present_or_required_path_observation_refuses(repository, name):
    f = repository
    real = f.module["_sparse_git"]
    if name.startswith("docs/"):
        # Reach the explicit observed-flag check on every supported Git. Newer
        # Git emits a sparse-index expansion hint when an omitted directory is
        # materialized, which correctly triggers an earlier Git refusal.
        _git(f.alternate, "sparse-checkout", "reapply", "--no-sparse-index")
        (f.alternate / "docs").mkdir()
        (f.alternate / name).write_text("inert present fixture\n")

    def observed(root, common, *args, **kwargs):
        if "--sparse" in args:
            return ("S 100644 " + "0" * 40 + " 0\t" + name + "\0").encode()
        return real(root, common, *args, **kwargs)

    f.module["_sparse_git"] = observed
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="INDEX_FLAGS_UNQUALIFIED"):
        f.invoke()
    assert f.calls == []


def test_dangling_link_is_not_a_verified_sparse_absence(repository):
    f = repository
    (f.alternate / "docs").symlink_to("fixture-nonexistent-directory", target_is_directory=True)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="INDEX_FLAGS_UNQUALIFIED"):
        f.invoke()
    assert f.calls == []


def test_unapproved_donor_cone_refuses_without_resparsifying(repository):
    f = repository
    gitdir = Path(_git(f.alternate, "rev-parse", "--absolute-git-dir"))
    rules = gitdir / "info/sparse-checkout"
    before = rules.read_bytes()
    rules.write_bytes(before + b"/docs/\n")
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="DONOR_PROFILE_UNQUALIFIED"):
        f.invoke()
    assert rules.read_bytes() == before + b"/docs/\n"
    assert f.calls == []


@pytest.mark.parametrize("name", ["untracked.fixture", "scripts/cache.fixture"])
def test_untracked_and_ignored_objects_refuse(repository, name):
    f = repository
    (f.alternate / name).write_text("inert fixture\n")
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="REVIEWED_DONOR_UNQUALIFIED"):
        f.invoke()
    assert f.calls == []


def test_second_helper_pass_rejects_changed_fallback_before_process(repository):
    f = repository
    select = f.module["_clean_linked_sparse_donor"]

    def changed(original):
        selected = select(original)
        (selected / "scripts/worktree_sparse.py").write_text("# different inert fixture\n")
        return selected

    f.module["_clean_linked_sparse_donor"] = changed
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="HELPER_BLOB_MISMATCH"):
        f.invoke()
    assert f.calls == []


def test_prelaunch_helper_change_refuses_before_process(repository):
    f = repository
    qualify = f.module["_qualify_sparse_donor"]
    count = 0

    def changed(*args, **kwargs):
        nonlocal count
        count += 1
        result = qualify(*args, **kwargs)
        if count == 2:
            (f.alternate / "scripts/worktree_sparse.py").write_text("# changed inert fixture\n")
        return result

    f.module["_qualify_sparse_donor"] = changed
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="HELPER_CHANGED"):
        f.invoke()
    assert count == 2 and f.calls == []


@pytest.mark.parametrize("effect_unknown", [False, True])
def test_donor_drift_error_branch_is_reachable_and_preserves_cause(repository, effect_unknown):
    f = repository
    qualify = f.module["_qualify_sparse_donor"]
    count = 0

    def drift(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise f.module["SparseWorkspaceRefused"]("fixture requalification refused", effect_unknown=effect_unknown)
        return qualify(*args, **kwargs)

    f.module["_qualify_sparse_donor"] = drift
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="REVIEWED_DONOR_DRIFT") as raised:
        f.invoke()
    assert str(raised.value.__cause__) == "fixture requalification refused"
    assert raised.value.effect_unknown == effect_unknown and f.calls == []


@pytest.mark.parametrize("change", ["returncode", "timed_out", "cleanup_proven", "stdout_truncated", "stderr_truncated"])
def test_unverified_mint_keeps_uncertain_effect_and_created_fixture(repository, change):
    f = repository
    setattr(f.result, change, 1 if change == "returncode" else change != "cleanup_proven")
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="MINT_UNVERIFIED") as raised:
        f.invoke()
    assert raised.value.effect_unknown
    assert (f.home / "lanes/wt" / f.key).is_dir()
    assert len(f.calls) == 1


@pytest.mark.parametrize("path,reason", [("scripts/worktree_sparse.py", "HELPER"),
                                        ("config/sparse_worktree.json", "POLICY")])
def test_postmint_input_drift_keeps_uncertain_effect(repository, path, reason):
    f = repository

    def changed(*args, **kwargs):
        result = f.runner(*args, **kwargs)
        (f.alternate / path).write_text("inert changed input\n")
        return result

    f.module["run_owned_process"] = changed
    with pytest.raises(f.module["SparseWorkspaceRefused"], match=reason + "_EFFECT_UNKNOWN") as raised:
        f.invoke()
    assert raised.value.effect_unknown
    assert (f.home / "lanes/wt" / f.key).is_dir()


@pytest.mark.parametrize("existing", ["destination", "receipt"])
def test_existing_effect_carrier_is_never_reused(repository, existing):
    f = repository
    path = (f.home / "lanes/wt" / f.key if existing == "destination"
            else f.here / "lanes" / (f.key + ".workspace-mint.process.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("retained fixture bytes\n")
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="(DESTINATION|MINT_RECEIPT)_EXISTS"):
        f.invoke()
    assert path.read_text() == "retained fixture bytes\n"
    assert f.calls == []


def test_no_opt_in_leaves_existing_cwd_untouched(repository, monkeypatch):
    f = repository
    monkeypatch.delenv("FABRIC_NEW_MACRO_COMMIT")
    assert f.invoke() == str(f.original)
    assert f.calls == []


def test_unknown_original_helper_does_not_reroute(repository):
    f = repository
    (f.original / "scripts/worktree_sparse.py").write_text("# unknown inert fixture\n")
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="HELPER_BLOB_MISMATCH"):
        f.invoke()
    assert f.calls == []


def test_reviewed_original_full_donor_uses_same_protected_mint_boundary(repository):
    f = repository
    (f.original / "preserve.txt").write_text("keep\n")
    (f.original / "scripts/worktree_sparse.py").write_bytes(f.reviewed)
    _git(f.original, "add", "scripts/worktree_sparse.py")
    _git(f.original, "commit", "-qm", "reviewed original fixture")
    target = Path(f.invoke())
    assert target.is_dir()
    assert f.calls[0][1]["cwd"] == str(f.original)
    assert f.calls[0][0][1] == "-I"


def test_required_cone_omission_refuses_even_when_file_is_absent(repository):
    f = repository
    (f.alternate / "scripts/keep.txt").unlink()
    real = f.module["_sparse_git"]

    def observed(root, common, *args, **kwargs):
        if "--sparse" in args:
            return ("S 100644 " + "0" * 40 + " 0\tscripts/keep.txt\0").encode()
        return real(root, common, *args, **kwargs)

    f.module["_sparse_git"] = observed
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="INDEX_FLAGS_UNQUALIFIED"):
        f.invoke()
    assert f.calls == []


def test_policy_symlink_refuses_without_following_it(repository):
    f = repository
    policy = f.alternate / "config/sparse_worktree.json"
    policy.unlink()
    policy.symlink_to(f.original / "config/sparse_worktree.json")
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="SOURCE_FILE_UNQUALIFIED"):
        f.invoke()
    assert f.calls == []


def test_group_writable_common_config_refuses_without_repairing_permissions(repository):
    f = repository
    path = f.original / ".git/config"
    path.chmod(0o664)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="SOURCE_FILE_UNQUALIFIED"):
        f.invoke()
    assert stat.S_IMODE(path.stat().st_mode) == 0o664
    assert f.calls == []


def test_git_cleanup_timeout_is_a_typed_uncertain_effect(repository, monkeypatch):
    f = repository

    class UnsettledObservation:
        # Pipe-only fixture: no subprocess is launched. Both bounded reads
        # reach EOF, then wait/cleanup report an unconfirmed process outcome.
        def __init__(self, *args, **kwargs):
            pipes = [os.pipe(), os.pipe()]
            for _, writer in pipes:
                os.close(writer)
            self.stdout, self.stderr = [os.fdopen(reader, "rb") for reader, _ in pipes]

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("fixture Git observation", timeout)

        def poll(self):
            return None

        def kill(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", UnsettledObservation)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="GIT_CLEANUP_UNKNOWN") as raised:
        f.invoke()
    assert raised.value.effect_unknown
    assert isinstance(raised.value.__cause__, subprocess.TimeoutExpired)
    assert f.calls == []


@pytest.mark.parametrize("timed_out", [True, False])
def test_forced_git_abort_keeps_unknown_even_when_direct_pid_cleanup_succeeds(repository, monkeypatch, timed_out):
    f = repository
    observations = []

    class DirectPidObservation:
        # Pipe-only fixture. A successful direct-PID cleanup is intentionally
        # not represented as proof about a possible internal Git child.
        def __init__(self, *args, **kwargs):
            pipes = [os.pipe(), os.pipe()]
            os.write(pipes[1][1], b"inert observation refusal\n")
            for _, writer in pipes:
                os.close(writer)
            self.stdout, self.stderr = [os.fdopen(reader, "rb") for reader, _ in pipes]
            self.killed = False
            self.settled = False
            observations.append(self)

        def wait(self, timeout):
            if timed_out and not self.killed:
                raise subprocess.TimeoutExpired("fixture Git observation", timeout)
            self.settled = True
            return 1

        def poll(self):
            return 1 if self.settled else None

        def kill(self):
            self.killed = True

    monkeypatch.setattr(subprocess, "Popen", DirectPidObservation)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="GIT_OBSERVATION_UNQUALIFIED") as raised:
        f.invoke()
    assert raised.value.effect_unknown is timed_out
    assert len(observations) == 1 and observations[0].settled
    assert observations[0].killed is timed_out
    assert f.calls == []


def test_existing_partial_clone_and_multivalue_fetch_metadata_are_data_only(repository):
    f = repository
    # All fixture objects remain local. No remote or fetch is invoked.
    with (f.original / ".git/config").open("a") as stream:
        stream.write('[remote "origin"]\nurl = https://example.invalid/fixture.git\n'
                     'fetch = +refs/heads/main:refs/remotes/origin/main\n'
                     'fetch = +refs/heads/review:refs/remotes/origin/review\n'
                     'pushurl = https://example.invalid/fixture.git\n'
                     'promisor = true\npartialclonefilter = blob:none\n'
                     '[lfs]\nrepositoryformatversion = 0\n')
    assert Path(f.invoke()).is_dir()
    assert f.calls[0][1]["env"]["GIT_ALLOW_PROTOCOL"] == ""

