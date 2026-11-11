"""Current application executor + fixed Git advice; disposable Git/pipe fixtures only."""
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

import pytest

from ops.native_fabric.provider_plans import compose
import test_current116_maintenance_guard_composition as cohort
import test_fabric_clean_linked_donor_20261017 as donor

current_source = cohort.current_source
repository = donor.repository
SETTINGS = "_SPARSE_GIT_SETTINGS"


@pytest.fixture(scope="module")
def executor_pair(current_source, tmp_path_factory):
    output = tmp_path_factory.mktemp("current116-sparse") / "source"
    compose.compose(current_source, output, profile_name=cohort.PROFILE)
    before = (current_source / "ext/remote_sub_exec.py").read_bytes()
    after = (output / "ext/remote_sub_exec.py").read_bytes()
    assert hashlib.sha256(before).hexdigest() == "bb0369140835dacf1bd08aef6fe96878c5088a8109580fd006436e53d05801ea"
    assert hashlib.sha256(after).hexdigest() == "e13c81475023fdd1e79fdbed87f5e7e5ac4356da345d07c725b36d2e92298f83"
    return before, after


def projection(raw):
    """Same accepted sparse-helper extraction, using the actual current executor bytes."""
    nodes = []
    for node in ast.parse(raw).body:
        if isinstance(node, ast.ClassDef) and node.name == "SparseWorkspaceRefused":
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and (node.name.startswith("_sparse_") or
                node.name in {"_qualify_sparse_donor", "_clean_linked_sparse_donor", "_new_macro_workspace"}):
            nodes.append(node)
        elif isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and
                t.id.startswith(("_MACRO_", "_SPARSE_")) for t in node.targets):
            nodes.append(node)
    namespace = dict(Path=Path, os=os, re=re, stat=stat, subprocess=subprocess,
        selectors=selectors, sys=sys, hashlib=hashlib, json=json, time=time,
        LaneRuntimeError=type("LaneRuntimeError", (RuntimeError,), {}),
        OwnedProcessStartError=type("OwnedProcessStartError", (RuntimeError,), {}))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "actual_current_executor_sparse_projection", "exec"), namespace)
    return namespace


@pytest.fixture
def module(executor_pair):
    return projection(executor_pair[1])


def test_only_exact_advice_constant_changes_and_all_current_application_code_survives(executor_pair):
    old, new = map(ast.parse, executor_pair)
    def setting(tree):
        return next(n for n in tree.body if isinstance(n, ast.Assign) and
            any(isinstance(t, ast.Name) and t.id == SETTINGS for t in n.targets))
    a, b = setting(old), setting(new)
    assert ast.literal_eval(b.value) == ast.literal_eval(a.value) + (("advice.sparseIndexExpanded", "false"),)
    old.body.remove(a); new.body.remove(b)
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)
    defs = {n.name for n in new.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    assert {"ApplicationContext", "_application_owner", "_execute_application", "main"} <= defs


def test_actual_preimage_refuses_expansion_advice_and_fixed_settings_prevent_it(repository, executor_pair, monkeypatch):
    f = repository
    before_config = (f.original / ".git/config").read_bytes()
    seen = []
    class GitObservation:
        def __init__(self, argv, **kwargs):
            seen.append((argv, kwargs["env"]))
            warning = b"" if "advice.sparseIndexExpanded=false" in argv else b"hint: The sparse index is expanding to a full index\n"
            pipes = [os.pipe(), os.pipe()]
            if warning: os.write(pipes[1][1], warning)
            for _, writer in pipes: os.close(writer)
            self.stdout, self.stderr = [os.fdopen(reader, "rb") for reader, _ in pipes]
        def wait(self, timeout): return 0
        def poll(self): return 0
    monkeypatch.setattr(subprocess, "Popen", GitObservation)
    old = projection(executor_pair[0])
    with pytest.raises(old["SparseWorkspaceRefused"], match="GIT_OBSERVATION_UNQUALIFIED"):
        old["_sparse_git"](f.alternate, f.original / ".git", "status", "--porcelain=v1")
    assert f.module["_sparse_git"](f.alternate, f.original / ".git", "status", "--porcelain=v1") == b""
    assert seen[1][0].count("advice.sparseIndexExpanded=false") == 1
    assert (f.original / ".git/config").read_bytes() == before_config
    assert f.calls == []  # No workspace mint, provider or activation.


def test_real_git_and_helper_environment_receive_only_fixed_command_setting(repository, monkeypatch):
    f = repository; before = (f.original / ".git/config").read_bytes(); calls = []
    real = subprocess.Popen
    def observe(argv, **kwargs):
        calls.append((argv, kwargs)); return real(argv, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", observe)
    result = f.module["_sparse_git"](f.alternate, f.original / ".git",
        "ls-files", "-v", "--stage", "-z", "--", "scripts/worktree_sparse.py")
    assert b"scripts/worktree_sparse.py" in result and len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[0] == "/usr/bin/git" and argv.count("advice.sparseIndexExpanded=false") == 1
    env = f.module["_sparse_git_env"]({"GIT_CONFIG_COUNT": "99", "GIT_CONFIG_KEY_0": "include.path",
        "GIT_CONFIG_VALUE_0": "/inert/foreign", "GIT_DIR": "/inert/foreign", "GIT_ADVICE": "0"})
    settings = f.module[SETTINGS]
    assert [(env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"])
            for i in range(int(env["GIT_CONFIG_COUNT"]))] == list(settings)
    assert "GIT_ADVICE" not in env and "GIT_DIR" not in env
    assert all(kwargs["env"][k] == v for k, v in env.items())
    assert (f.original / ".git/config").read_bytes() == before and f.calls == []


@pytest.mark.parametrize("rc,stderr", [(0,b"unrelated warning\n"),(0,b"hint: The sparse index is expanding to a full index\n"),(0,b"\x00"),(1,b"")])
def test_nonempty_stderr_and_nonzero_exit_remain_refused(repository, monkeypatch, rc, stderr):
    f = repository
    class Observation:
        def __init__(self, *args, **kwargs):
            pipes = [os.pipe(), os.pipe()]
            if stderr: os.write(pipes[1][1], stderr)
            for _, writer in pipes: os.close(writer)
            self.stdout, self.stderr = [os.fdopen(reader,"rb") for reader,_ in pipes]
        def wait(self, timeout): return rc
        def poll(self): return rc
    monkeypatch.setattr(subprocess,"Popen",Observation)
    with pytest.raises(f.module["SparseWorkspaceRefused"],match="GIT_OBSERVATION_UNQUALIFIED") as error:
        f.module["_sparse_git"](f.alternate,f.original/".git","status","--porcelain=v1")
    assert error.value.effect_unknown is False and f.calls == []


def test_post_observation_config_identity_drift_still_refuses(repository, monkeypatch):
    f = repository
    class Observation:
        def __init__(self,*args,**kwargs):
            pipes = [os.pipe(),os.pipe()]
            for _, writer in pipes: os.close(writer)
            self.stdout,self.stderr=[os.fdopen(reader,"rb") for reader,_ in pipes]
            with (f.original/".git/config").open("a") as stream:stream.write("\n# fixture drift\n")
        def wait(self,timeout):return 0
        def poll(self):return 0
    monkeypatch.setattr(subprocess,"Popen",Observation)
    with pytest.raises(f.module["SparseWorkspaceRefused"],match="GIT_OBSERVATION_UNQUALIFIED"):
        f.module["_sparse_git"](f.alternate,f.original/".git","status","--porcelain=v1")
    assert f.calls == []
