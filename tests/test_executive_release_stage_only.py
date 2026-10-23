"""Exercise the real shell staging path with inert OS-ownership collaborators.

Git archives, source admission, asset capture/import and release seals are real.
Only root ownership/native ACLs are simulated in temporary directories; no service,
production directory, secret, journal or selection is accessed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from test_os_release_assets import bundle, source  # reuse real asset fixtures

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "ops/executive_os/install.sh"
TEXT = INSTALL.read_text()


def section(name):
    return TEXT.split(f"# --- BEGIN {name} ---\n", 1)[1].split(f"# --- END {name} ---", 1)[0]


def snapshot(path):
    return {str(p.relative_to(path)): (p.lstat().st_ino, p.lstat().st_mode,
            os.readlink(p) if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest())
            for p in path.rglob("*") if not p.is_dir() or p.is_symlink()}


@pytest.fixture
def stage(tmp_path, bundle, source):
    mod, assets, sha, tree = bundle
    repo = source[0]
    # The fixture's actual Git archive carries the real reviewed release
    # surface and the actual native closure records the unchanged archived
    # builder materializes inside the release; only root ownership/ACLs stay
    # simulated, and runtime caches/generated stages are never copied.
    for name in ("autonomy-control.sh", "autonomy_control.py", "credential_rotation_interlock.py"):
        p = repo / "ops/executive_os" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / "ops/executive_os" / name).read_bytes())
        if name.endswith(".sh"):
            p.chmod(0o755)
    shutil.copytree(ROOT / "ops/native_fabric/quota_continuity",
                    repo / "ops/native_fabric/quota_continuity",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                  "native-code-stage", ".DS_Store"))
    provenance = json.loads((ROOT / "ops/native_fabric/quota_continuity/candidate/"
                              "paid_pyyaml_provenance.json").read_bytes())
    lock = repo / provenance["lock_path"]
    lock.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / provenance["lock_path"], lock)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c",
                    "user.email=t@example.invalid", "commit", "-qm", "surface"], check=True)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], text=True).strip()
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/master", sha], check=True)
    # Rebuild only the fixture bundle after its real source identity changes.
    out = tmp_path / "final-bundle"
    mod.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client-id",
                output=out, build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"))
    digest = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=repo).digest
    library = tmp_path / "Library"
    system = library / "Application Support/MastermindExecutive"
    (system / "releases").mkdir(parents=True)
    for p in (library, library / "Application Support", system, system / "releases"):
        p.chmod(0o755)
    protected = tmp_path / "untouched"
    protected.mkdir()
    for name in ("selected", "config", "receipt", "transaction", "services"):
        (protected / name).write_text(f"original {name}")
    runner = tmp_path / "os-python"
    runner.write_text(f'''#!{sys.executable}
import os, sys, runpy, subprocess, stat
from pathlib import Path
sys.path.insert(0, {str(ROOT)!r})
args=sys.argv[1:]
while args and args[0] in ("-I", "-S", "-B"): args.pop(0)
if args[0] == "-":
    raise SystemExit(subprocess.call([sys.executable, "-I", "-S", "-B", *args]))
name=Path(args[0]).name
command=args[1] if len(args)>1 else ""
with open(os.environ["CALLS"], "a") as f: f.write(name+":"+command+"\\n")
if os.environ.get("FAIL") == name+":"+command: raise SystemExit(65)
from ops.executive_os import os_release_assets as a, release_manifest as r
# Inert trusted OS collaborators only; all byte/provenance/seal logic is real.
a._require_root=lambda: None
a.require_sealed_path=lambda *args, **kwargs: None
r._has_acl=lambda *args: False
def owned(info, *, label):
    assert info.st_uid == os.getuid() and not stat.S_IMODE(info.st_mode)&0o022
r._validate_owned_info=owned
sys.argv=args
if name == "os_release_assets.py": raise SystemExit(a.main() or 0)
if name == "release_manifest.py": raise SystemExit(r.main())
runpy.run_path(args[0], run_name="__main__")
''')
    runner.chmod(0o755)
    statshim = tmp_path / "stat"
    statshim.write_text(f'''#!{sys.executable}
import os,sys,stat
p=sys.argv[-1]
owner=os.environ.get("BAD_OWNER", "0:0")
if p.endswith("Application Support") and os.environ.get("ADMIN") == "1": owner="0:80"
print(owner+":"+oct(stat.S_IMODE(os.lstat(p).st_mode))[2:])
''')
    statshim.chmod(0o755)
    chown = tmp_path / "chown"
    chown.write_text('#!/bin/bash\nprintf "chown\\n" >> "$CALLS"\n[ "${FAIL:-}" != chown ]\n')
    chown.chmod(0o755)
    env = {**os.environ, "SYSTEM_ROOT": str(system), "RELEASE_ROOT": str(system / "releases" / sha),
           "SOURCE_REPO": str(repo), "EXPECTED_SHA": sha, "TREE_SHA": tree,
           "SCRIPT_DIR": str(ROOT / "ops/executive_os"), "PYTHON_BINARY": str(runner),
           "OS_WEB_ASSETS": str(out), "OS_WEB_ASSETS_DIGEST": digest,
           "STAGE_RELEASE_ONLY": "1", "ALLOW_FROZEN_ACCEPTED_ANCESTOR": "0",
           "ARM_PRIVILEGED_BROKER": "0", "CONTROL_CONFIG_SOURCE": "", "PROTECTED_MASTER_SHA": "",
           "CALLS": str(tmp_path / "calls"), "FAIL": ""}
    shared = section("shared sealed release staging").replace("/Library", str(library))
    shared = shared.replace("/usr/bin/stat", shlex.quote(str(statshim))).replace("/usr/sbin/chown", shlex.quote(str(chown)))
    rename = TEXT.split("rename_codex_path_exclusive() {",1)[1].split("\npublish_codex_path_exclusive()",1)[0]
    program = ("set -euo pipefail\numask 077\n" + section("release staging option guard")
               + "validate_release_staging_options || exit 65\n"
               + TEXT[TEXT.index('SOURCE_POLICY="$SCRIPT_DIR/'):TEXT.index('\nSYSTEM_ROOT="/Library')]
               + "\n" + TEXT[TEXT.index("# Optional build artifact is qualified"):TEXT.index('CONTROL_CONFIG="$SYSTEM_ROOT/config/control.json"')]
               + "\nrequire_native_no_acl() { [ \"${BAD_ACL:-}\" != \"$2\" ]; }\n"
               + "rename_codex_path_exclusive() {" + rename + shared)
    def run(*, extra="", ordinary=False, **updates):
        current = {**env, **updates}
        if ordinary:
            current["STAGE_RELEASE_ONLY"] = "0"
        script = program + extra + ("\nstage_sealed_release || exit 65\n" if ordinary else section("stage-only dispatch"))
        return subprocess.run(["/bin/bash", "-c", script], env=current, capture_output=True, text=True)
    return {"run": run, "env": env, "system": system, "protected": protected,
            "release": Path(env["RELEASE_ROOT"]), "stage": system / "releases" / f".stage.{sha}",
            "before": snapshot(protected), "repo": repo, "calls": tmp_path / "calls"}


def unchanged(s):
    assert snapshot(s["protected"]) == s["before"]


# Archive fault injection: deterministic loss of the fixture's ENTIRE disposable
# object store through one atomic rename to a fixed, first-checked-absent
# sibling inside .git. The former rm of the loose fan-out path assumed loose
# storage; a packed store archives fine without that file, so the rm itself
# failed with ENOENT. Inserted as `extra`, this runs after the real
# source-policy read and before the stage-only dispatch performs the shared
# actual git archive of "$EXPECTED_SHA".
ARCHIVE_FAULT = (
    'archive_fault_lost="$SOURCE_REPO/.git/objects.archive-fault-lost"\n'
    'if [ -e "$archive_fault_lost" ]; then\n'
    '  echo "archive fault sibling already exists: $archive_fault_lost" >&2\n'
    '  exit 65\n'
    'fi\n'
    'mv "$SOURCE_REPO/.git/objects" "$archive_fault_lost"\n'
    'if [ -e "$SOURCE_REPO/.git/objects" ]; then\n'
    '  echo "fixture object store survived the archive fault" >&2\n'
    '  exit 65\n'
    'fi\n'
)


def test_cli_recognizes_mode_before_preserving_nonroot_denial():
    if os.getuid() == 0:
        pytest.skip("this test specifically observes an unprivileged invocation")
    result = subprocess.run(["bash", str(INSTALL), "--stage-release-only"], capture_output=True, text=True)
    assert result.returncode == 77 and "must run as root" in result.stderr


def test_real_stage_seal_and_existing_destination_are_read_only(stage):
    r = stage["run"](ADMIN="1")
    assert r.returncode == 0, r.stderr
    value = json.loads(r.stdout)
    assert value["staged_unselected"] and not any(v for k,v in value.items() if k.endswith("_changed"))
    assert (stage["release"] / ".executive-release-manifest.json").is_file()
    assert not stage["stage"].exists()
    before = snapshot(stage["release"])
    stage["calls"].write_text("")
    again = stage["run"]()
    assert again.returncode == 0, again.stderr
    assert snapshot(stage["release"]) == before
    calls = stage["calls"].read_text()
    assert "create" not in calls and "import" not in calls and "chown" not in calls
    unchanged(stage)


@pytest.mark.parametrize("updates", [
    {"OS_WEB_ASSETS": ""}, {"ALLOW_FROZEN_ACCEPTED_ANCESTOR": "1"},
    {"ARM_PRIVILEGED_BROKER": "1"}, {"CONTROL_CONFIG_SOURCE": "/not-read"},
    {"EXPECTED_SHA": "f"*40}, {"BAD_OWNER": "501:20"},
    {"OS_WEB_ASSETS": "/nonexistent-stage-bundle"},
])
def test_preflight_refuses_before_staging(stage, updates):
    r = stage["run"](**updates)
    assert r.returncode == 65, r.stderr
    assert not stage["stage"].exists() and not stage["release"].exists()
    unchanged(stage)


@pytest.mark.parametrize("damage", ["dirty", "stale", "missing", "acl", "mode", "symlink"])
def test_source_and_ancestry_guards(stage, damage):
    updates = {}
    if damage == "dirty": (stage["repo"] / "untracked").write_text("dirty")
    if damage == "stale":
        subprocess.run(["git", "-C", str(stage["repo"]), "update-ref", "-d", "refs/remotes/origin/master"], check=True)
    if damage == "missing": updates["SOURCE_REPO"] = "/nonexistent-stage-source"
    if damage == "acl": updates["BAD_ACL"] = str(stage["system"] / "releases")
    if damage == "mode": (stage["system"] / "releases").chmod(0o777)
    if damage == "symlink":
        (stage["system"] / "releases").rename(stage["system"] / "saved")
        (stage["system"] / "releases").symlink_to("saved")
    r = stage["run"](**updates)
    assert r.returncode == 65, r.stderr
    assert not stage["release"].exists()
    unchanged(stage)


@pytest.mark.parametrize("target,kind", [("stage","dir"),("stage","symlink"),("release","dir"),
                                         ("release","symlink"),("release","file")])
def test_occupied_destination_never_adopted_or_overwritten(stage, target, kind):
    p = stage[target]
    if kind == "dir": p.mkdir(); (p / "sentinel").write_text("original")
    elif kind == "symlink": p.symlink_to("missing")
    else: p.write_text("original")
    before = (p.lstat().st_ino, p.lstat().st_mode)
    r = stage["run"]()
    assert r.returncode == 65, r.stderr
    assert before == (p.lstat().st_ino, p.lstat().st_mode)
    unchanged(stage)


@pytest.mark.parametrize("failure", ["chown", "os_release_assets.py:import", "release_manifest.py:create",
                                      "release_manifest.py:verify", "rename", "race", "archive"])
def test_failure_retains_stage_without_other_effects(stage, failure):
    extra = ""
    if failure == "rename": extra = 'rename_codex_path_exclusive() { return 65; }\n'
    if failure == "race":
        original = TEXT.split('rename_codex_path_exclusive() {', 1)[1].split('\npublish_codex_path_exclusive()', 1)[0]
        extra = ('real_rename() {' + original +
                 'rename_codex_path_exclusive() { mkdir "$2"; echo concurrent > "$2/other"; real_rename "$1" "$2"; }\n')
    if failure == "archive":
        # A valid admitted tree can still fail archive (e.g. I/O). Lose the
        # whole disposable object store *after* the actual policy read, before
        # shared archive, whatever object layout the fixture repo has.
        extra = ARCHIVE_FAULT
    r = stage["run"](extra=extra, FAIL=failure)
    assert r.returncode == 65, r.stderr
    assert stage["stage"].is_dir()
    if failure == "race":
        assert (stage["release"] / "other").read_text().strip() == "concurrent"
        assert not (stage["release"] / stage["stage"].name).exists()
    else: assert not stage["release"].exists()
    unchanged(stage)


def test_packed_source_still_fails_archive_and_retains_stage(stage):
    # CI fixture repos can hold packed objects: Git reads the same commit
    # without any loose file, which is why removing the loose fan-out path
    # could not fault the archive. Prove the packed layout, exercise the same
    # archive fault, and require the same stage retention with no other
    # effects.
    repo = stage["repo"]
    sha = stage["env"]["EXPECTED_SHA"]
    subprocess.run(["git", "-C", str(repo), "repack", "-ad"], check=True)
    assert not (repo / ".git/objects" / sha[:2] / sha[2:]).exists()
    assert list((repo / ".git/objects/pack").glob("*.pack"))
    subprocess.run(["git", "-C", str(repo), "cat-file", "-e", sha], check=True)
    r = stage["run"](extra=ARCHIVE_FAULT)
    assert r.returncode == 65, r.stderr
    assert stage["stage"].is_dir()
    assert not stage["release"].exists()
    unchanged(stage)


def test_changed_existing_assets_or_seal_never_repaired(stage):
    assert stage["run"]().returncode == 0
    p = stage["release"] / "app/mastermind_os/dist/assets/index-a.js"
    p.chmod(0o644); p.write_text("changed")
    before = snapshot(stage["release"])
    assert stage["run"]().returncode == 65
    assert snapshot(stage["release"]) == before
    unchanged(stage)


def test_ordinary_path_reuses_shared_stage(stage):
    r = stage["run"](ordinary=True)
    assert r.returncode == 0, r.stderr
    assert (stage["release"] / ".executive-release-manifest.json").exists()
    unchanged(stage)


def test_dispatch_precedes_all_installed_mutations_and_keeps_preflight():
    start = TEXT.index("# --- BEGIN stage-only dispatch ---")
    end = TEXT.index("# --- END stage-only dispatch ---")
    assert TEXT.index('"$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/install_source_policy.py"') < start
    assert TEXT.index('OS_WEB_ASSETS_DIGEST="$(') < start
    assert TEXT.index('require_native_no_acl one "$AUTH_PATH"') < start
    assert end < TEXT.index("\nprepare_codex_code_mode_host ||") < TEXT.index("trap leave_installed_services_stopped EXIT")
    dispatch = TEXT[start:end]
    assert "exit 0" in dispatch and "stage_sealed_release || exit 65" in dispatch
    shared = section("shared sealed release staging")
    assert all(word not in shared for word in ("launchctl", "rm -", "CONTROL_CONFIG", "RUNTIME_ROOT"))
    assert TEXT.count('archive --format=tar "$EXPECTED_SHA"') == 1
