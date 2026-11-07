"""Fixed Git advice compatibility; no host/provider/configuration mutation."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest
import test_fabric_native_security_composition_20261018 as composed

ROOT = Path(__file__).resolve().parents[1]
PARENT_INVENTORY_SHA256 = "fc3347a3633cd9127e93a77d23e6b60eab4b8dddad632f87dd7dad5a57886dc5"
PARENT_EXECUTOR_BYTES = 61402
ROLLOUT = ROOT / "ops/native_fabric/quota_continuity/rollout"
EXECUTOR = "ops/native_fabric/quota_continuity/candidate/remote_sub_exec.py"
applied = composed.applied
module = composed.module
repository = composed.repository


def builder():
    spec = importlib.util.spec_from_file_location("sparse_advice_cohort", ROLLOUT / "build_review_stage.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_executor_adds_only_the_one_command_scoped_setting(tmp_path):
    # Reconstruct the immutable710 preimage with the appended fixture delta;
    # no unmerged branch or historical Git object is needed in later CI.
    target = tmp_path / "remote_sub_exec.py"
    target.write_bytes((ROOT / EXECUTOR).read_bytes())
    composed.donor_contract._git(tmp_path, "apply", "--reverse", str(composed.SPARSE_INDEX_ADVICE_FORWARD_PATCH))
    assert hashlib.sha256(target.read_bytes()).hexdigest() == composed.PRE_SPARSE_INDEX_ADVICE_COMPOSED_SHA
    old = ast.parse(target.read_bytes())
    new = ast.parse((ROOT / EXECUTOR).read_text())
    def settings(tree):
        return next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "_SPARSE_GIT_SETTINGS" for t in n.targets))
    a, b = settings(old), settings(new)
    assert ast.literal_eval(b.value) == ast.literal_eval(a.value) + (("advice.sparseIndexExpanded", "false"),)
    old.body.remove(a); new.body.remove(b)
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)


def test_real_git_argv_and_sanitized_helper_env_share_exact_setting(repository, monkeypatch):
    f = repository
    config = f.original / ".git/config"
    before = config.read_bytes()
    calls = []
    original = subprocess.Popen
    def observe(argv, **kwargs):
        calls.append((argv, kwargs))
        return original(argv, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", observe)
    output = f.module["_sparse_git"](f.alternate, f.original / ".git",
        "ls-files", "-v", "--stage", "-z", "--", "scripts/worktree_sparse.py")
    assert b"scripts/worktree_sparse.py" in output
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv.count("advice.sparseIndexExpanded=false") == 1
    assert argv[0] == "/usr/bin/git"
    env = f.module["_sparse_git_env"]({"GIT_CONFIG_COUNT": "99", "GIT_CONFIG_KEY_0": "include.path",
        "GIT_CONFIG_VALUE_0": "/inert/foreign", "GIT_DIR": "/inert/foreign", "GIT_ADVICE": "0"})
    settings = f.module["_SPARSE_GIT_SETTINGS"]
    assert int(env["GIT_CONFIG_COUNT"]) == len(settings)
    assert [(env["GIT_CONFIG_KEY_" + str(i)], env["GIT_CONFIG_VALUE_" + str(i)])
            for i in range(len(settings))] == list(settings)
    assert env == kwargs["env"] or all(kwargs["env"][k] == v for k, v in env.items())
    assert "GIT_ADVICE" not in env and "GIT_DIR" not in env
    assert config.read_bytes() == before


@pytest.mark.parametrize("rc,stderr", [(0, b"unrelated warning\n"),
    (0, b"hint: The sparse index is expanding to a full index\n"), (0, b"\x00"), (1, b"")])
def test_other_stderr_or_nonzero_rc_still_refuses(repository, monkeypatch, rc, stderr):
    f = repository
    class Observation:
        def __init__(self, *args, **kwargs):
            pipes = [os.pipe(), os.pipe()]
            if stderr: os.write(pipes[1][1], stderr)
            for _, writer in pipes: os.close(writer)
            self.stdout, self.stderr = [os.fdopen(reader, "rb") for reader, _ in pipes]
        def wait(self, timeout): return rc
        def poll(self): return rc
    monkeypatch.setattr(subprocess, "Popen", Observation)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="GIT_OBSERVATION_UNQUALIFIED") as error:
        f.module["_sparse_git"](f.alternate, f.original / ".git", "status", "--porcelain=v1")
    assert error.value.effect_unknown is False
    assert f.calls == []


def test_post_observation_config_identity_still_refuses(repository, monkeypatch):
    f = repository
    class Observation:
        def __init__(self, *args, **kwargs):
            pipes = [os.pipe(), os.pipe()]
            for _, writer in pipes: os.close(writer)
            self.stdout, self.stderr = [os.fdopen(reader, "rb") for reader, _ in pipes]
            with (f.original / ".git/config").open("a") as stream: stream.write("\n# fixture drift\n")
        def wait(self, timeout): return 0
        def poll(self): return 0
    monkeypatch.setattr(subprocess, "Popen", Observation)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="GIT_OBSERVATION_UNQUALIFIED"):
        f.module["_sparse_git"](f.alternate, f.original / ".git", "status", "--porcelain=v1")
    assert f.calls == []


def test_exact107_current_bytes_and_historical_parent_are_separate():
    b = builder()
    current = json.loads((ROLLOUT / "native-manifest.json").read_bytes())
    parent = b.before_sparse_index_advice(current)
    parent_raw = (json.dumps(parent, sort_keys=True, indent=2) + "\n").encode()
    assert hashlib.sha256(parent_raw).hexdigest() == b.SPARSE_INDEX_ADVICE_PARENT_SHA256
    assert len(parent) == len(current) == 107
    assert {k for k in current if current[k] != parent[k]} == {"ext/remote_sub_exec.py"}
    original = dict(current)
    assert b.before_sparse_index_advice(current) == parent
    assert b.before_sparse_index_advice(parent) == parent
    assert current == original
    capture = {name: current["ext/" + name] for name in b.GO_APPLICATION_DEPENDENCIES}
    b.validate_go_base_manifest(current, capture)
    b.validate_go_base_manifest(parent, capture)
    # Historical H/Q guards are not widened to accept the new source epoch.
    with pytest.raises(ValueError): b.before_qualification_quiescence(current)
    with pytest.raises(ValueError): b.before_host_pull_integrity(current)
    new = json.loads((ROLLOUT / "native-source-inventory.json").read_bytes())
    row = new["files"]["ext/remote_sub_exec.py"]
    assert row["sha256"] == hashlib.sha256((ROOT / EXECUTOR).read_bytes()).hexdigest()
    assert row["bytes"] == len((ROOT / EXECUTOR).read_bytes())
    row["sha256"] = b.SPARSE_INDEX_ADVICE_EXECUTOR_PREIMAGE
    row["bytes"] = PARENT_EXECUTOR_BYTES
    assert hashlib.sha256((json.dumps(new, sort_keys=True, indent=2) + "\n").encode()).hexdigest() == PARENT_INVENTORY_SHA256


@pytest.mark.parametrize("drift", ["extra", "missing", "foreign", "old-broker", "old-host", "executor-byte"])
def test_mixed_or_foreign107_never_reuses_advice_qualification(drift):
    b = builder(); current = json.loads((ROLLOUT / "native-manifest.json").read_bytes())
    if drift == "extra": current["ext/foreign.py"] = "f" * 64
    elif drift == "missing": del current["pool"]
    elif drift == "foreign": current["pool"] = "f" * 64
    elif drift == "old-broker": current["ext/lease_broker.py"] = b.QUALIFICATION_QUIESCENCE_BROKER_PREIMAGE
    elif drift == "old-host": current.update(b.HOST_PULL_INTEGRITY_PREIMAGES)
    else: current["ext/remote_sub_exec.py"] = hashlib.sha256((ROOT / EXECUTOR).read_bytes() + b"\n").hexdigest()
    captured = {name: current["ext/" + name] for name in b.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError): b.validate_go_base_manifest(current, captured)


def test_new_forward_proof_rejects_unrelated_byte_drift(tmp_path, monkeypatch):
    original = Path.read_bytes
    source = ROOT / EXECUTOR
    def drift(path):
        raw = original(path)
        return raw + b"\n# foreign byte\n" if path == source else raw
    monkeypatch.setattr(Path, "read_bytes", drift)
    with pytest.raises(AssertionError): composed._composition(tmp_path)
