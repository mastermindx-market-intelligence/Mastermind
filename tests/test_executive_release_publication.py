"""Exercise the real release-publication shell block without privileged host effects.

Archive, manifest contents, rename and failure ordering are real. The subprocess
wrapper substitutes only root ownership/ACL admission and chown for temp files.
Darwin runs the production exclusive rename syscall under the current user.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "ops/executive_os/install.sh"

WRAPPER = r'''#!/usr/bin/env python3
import importlib.util, json, os, shutil, stat, sys
from pathlib import Path
args = sys.argv[1:]
mode = args.pop(0)
fault = os.environ.get("FAULT", "")
canonical = Path(os.environ["RELEASE_ROOT"])
if mode == "chown":
    sys.exit(0)  # Explicit root-ownership substitute only.
if mode == "python":
    while args and args[0] in ("-I", "-S", "-B"):
        args.pop(0)
    if args[0] != "-":
        operation = args[1]
        root = Path(args[args.index("--root") + 1])
        commit = args[args.index("--commit-sha") + 1]
        tree = args[args.index("--tree-sha") + 1]
        sys.path.insert(0, os.environ["REPO_ROOT"])
        from ops.executive_os import release_manifest as manifest
        def metadata(info, *, label):
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise manifest.ReleaseManifestError("fixture object is writable")
        manifest._validate_owned_info = metadata
        manifest._has_acl = lambda *_: False
        if fault == operation + "-before":
            sys.exit(71)
        getattr(manifest, operation)(root, commit, tree)
        if fault == operation + "-after":
            sys.exit(72)
        sys.exit(0)
    source, destination = map(Path, args[1:3])
else:
    assert mode == "mv"
    source, destination = map(Path, args)
if fault == "publish-before":
    sys.exit(73)
if fault.startswith("race-"):
    if fault == "race-directory":
        destination.mkdir()
        (destination / "foreign").write_text("winner")
    elif fault == "race-file":
        destination.write_text("winner")
    elif fault == "race-symlink":
        destination.symlink_to(destination.parent / "missing-foreign")
    else:
        raise AssertionError(fault)
if mode == "mv":
    shutil.move(str(source), str(destination))  # Original mv nests into a dir.
else:
    sys.argv = ["-", str(source), str(destination)]
    exec(compile(sys.stdin.read(), "<actual-exclusive-rename>", "exec"))
if fault == "publish-after":
    sys.exit(74)
'''


@pytest.fixture
def harness(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.txt").write_text("reviewed release payload\n")
    git_env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    def git(*args):
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(source), *args],
                              env=git_env, capture_output=True, text=True, check=True).stdout.strip()
    git("init", "-q")
    git("add", "payload.txt")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
    sha = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    system = tmp_path / "system"
    (system / "releases").mkdir(parents=True)
    canonical = system / "releases" / sha
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(WRAPPER)
    wrapper.chmod(0o755)
    python_wrapper = tmp_path / "python-fixture"
    python_wrapper.write_text("#!/bin/bash\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(wrapper)) + ' python "$@"\n')
    python_wrapper.chmod(0o755)
    text = INSTALL.read_text()
    helper = text.split("rename_codex_path_exclusive() {", 1)[1].split("publish_codex_path_exclusive() {", 1)[0]
    helper = "rename_codex_path_exclusive() {" + helper
    block = text.split('if [ ! -d "$RELEASE_ROOT" ]; then', 1)[1].split('[ -x "$RELEASE_ROOT/ops/executive_os/autonomy-control.sh" ]', 1)[0]
    block = 'if [ ! -d "$RELEASE_ROOT" ]; then' + block
    fake = shlex.quote(sys.executable) + " " + shlex.quote(str(wrapper))
    block = block.replace("/usr/sbin/chown", fake + " chown").replace("/bin/mv", fake + " mv")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_BINARY": str(python_wrapper),
           "REPO_ROOT": str(ROOT), "SYSTEM_ROOT": str(system), "SOURCE_REPO": str(source),
           "EXPECTED_SHA": sha, "TREE_SHA": tree, "RELEASE_ROOT": str(canonical)}
    # The installer's cleanup only removes its still-owned staging pathname.
    cleanup = """trap 'if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then /bin/rm -rf -- "$STAGING"; fi' EXIT\n"""
    script = 'set -euo pipefail\nSTAGING=""\n' + helper + "\n" + cleanup + block
    def run(fault=""):
        return subprocess.run(["/bin/bash", "-c", script], env={**env, "FAULT": fault},
                              capture_output=True, text=True)
    def verify():
        return subprocess.run([str(python_wrapper), "-I", "-S", "-B", "release_manifest.py", "verify",
                               "--root", str(canonical), "--commit-sha", sha, "--tree-sha", tree],
                              env=env, capture_output=True, text=True)
    return canonical, system / "releases", run, verify


@pytest.mark.parametrize("fault", ["create-before", "create-after", "verify-before", "verify-after", "publish-before"])
def test_prepublication_fault_never_exposes_unsealed_release(harness, fault):
    canonical, releases, run, _ = harness
    result = run(fault)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not canonical.exists()
    assert list(releases.iterdir()) == []


def test_postpublication_interruption_leaves_verified_release(harness):
    canonical, releases, run, verify = harness
    result = run("publish-after")
    assert result.returncode != 0
    assert canonical.is_dir()
    verified = verify()
    assert verified.returncode == 0, verified.stderr
    assert list(releases.iterdir()) == [canonical]
    assert run().returncode == 0


@pytest.mark.parametrize("fault", ["race-directory", "race-file", "race-symlink"])
def test_competing_destination_is_preserved_without_nested_stage(harness, fault):
    canonical, releases, run, _ = harness
    result = run(fault)
    assert result.returncode != 0
    assert list(releases.iterdir()) == [canonical]
    if fault == "race-directory":
        assert list(canonical.iterdir()) == [canonical / "foreign"]
        assert (canonical / "foreign").read_text() == "winner"
    elif fault == "race-file":
        assert canonical.read_text() == "winner"
    else:
        assert canonical.is_symlink()
        assert os.readlink(canonical).endswith("missing-foreign")


def test_existing_unsealed_release_is_not_adopted(harness):
    canonical, releases, run, _ = harness
    canonical.mkdir()
    sentinel = canonical / "foreign"
    sentinel.write_text("existing unsealed material")
    result = run()
    assert result.returncode != 0
    assert sentinel.read_text() == "existing unsealed material"
    assert list(canonical.iterdir()) == [sentinel]
    assert list(releases.iterdir()) == [canonical]


def test_seal_survives_relocation_and_existing_release_is_only_verified(harness):
    canonical, _, run, verify = harness
    result = run()
    assert result.returncode == 0, result.stderr
    seal = canonical / ".executive-release-manifest.json"
    before = (seal.stat().st_ino, seal.read_bytes())
    assert verify().returncode == 0
    assert run().returncode == 0
    assert (seal.stat().st_ino, seal.read_bytes()) == before
    (canonical / "payload.txt").write_text("foreign mutation")
    assert run().returncode != 0
    assert (canonical / "payload.txt").read_text() == "foreign mutation"
