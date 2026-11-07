"""Real-Git tests for the installed owner's closed repository selection.

No network request, production checkout, or real host workspace is modified.
The installer checks below call read-only discovery, never host-root acquisition.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/mastermind_workspace.py"
IDENTITIES = {
    "mastermind": ("Mastermind", "master"),
    "macro": ("macro", "main"),
    "terminal": ("mastermind-terminal", "master"),
}


def git(path: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.check_output(["git", "-C", str(path), *args], text=True, env=env).strip()


def repository(parent: Path, alias: str) -> tuple[Path, str]:
    path = parent / alias
    path.mkdir(parents=True)
    name, branch = IDENTITIES[alias]
    git(path, "init", "-q", "-b", branch)
    git(path, "config", "user.name", "Workspace Test")
    git(path, "config", "user.email", "workspace@example.invalid")
    git(path, "remote", "add", "origin", f"https://github.com/mastermindx-market-intelligence/{name}.git")
    (path / "README.md").write_text(alias + "\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "fixture")
    return path, git(path, "rev-parse", "HEAD")


def binding(path: Path) -> dict[str, str]:
    common = Path(git(path, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = path / common
    return {"source_repository": str(path.resolve()), "common_git_dir": str(common.resolve())}


@pytest.fixture
def fleet(tmp_path: Path):
    repos = {alias: repository(tmp_path / "sources", alias) for alias in IDENTITIES}
    config = {"schema": "mastermind.workspace_repositories/v1",
              "repositories": {alias: binding(source) for alias, (source, _) in repos.items()}}
    root = tmp_path / "workspaces"
    env = dict(os.environ)
    env.update(MASTERMIND_SOURCE_REPO=str(repos["mastermind"][0]),
               MASTERMIND_AGENT_WORKSPACE_ROOT=str(root),
               MASTERMIND_WORKSPACE_STORAGE_POLICY="",
               MASTERMIND_WORKSPACE_REPOSITORIES=json.dumps(config))
    return repos, config, root, env


def invoke(env: dict[str, str], *args: str):
    result = subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                            capture_output=True, text=True, timeout=30)
    text = result.stdout or result.stderr
    try:
        body = json.loads(text)
    except ValueError:
        body = {"unparsed": text}
    return result.returncode, body


def acquire(fleet, alias: str, operation: str = "same-operation"):
    repos, _, _, env = fleet
    return invoke(env, "acquire", "--repository", alias, "--operation-id", operation,
                  "--base-sha", repos[alias][1], "--lane", "web")


def test_three_repositories_separate_same_operation_and_reuse_exact_custody(fleet):
    repos, _, root, _ = fleet
    paths = []
    for alias in IDENTITIES:
        code, result = acquire(fleet, alias)
        assert code == 0, result
        assert result["schema_version"] == "mastermind.workspace_cli/v2"
        assert result["repository"] == alias
        receipt = result["receipt"]
        expected = root / "web" / "same-operation" if alias == "mastermind" else root / alias / "web" / "same-operation"
        assert receipt["workspace_path"] == str(expected)
        assert receipt["source_repository"] == str(repos[alias][0])
        assert receipt["branch"] == "sol/web-same-operation"
        assert receipt["head_sha"] == repos[alias][1]
        assert (expected / "README.md").read_text() == alias + "\n"
        assert receipt["reused"] is False
        paths.append(expected)
        code, again = acquire(fleet, alias)
        assert code == 0 and again["effect"] == "NOT_APPLIED"
        assert again["receipt"]["reused"] is True
    assert len(set(paths)) == 3


@pytest.mark.parametrize("alias", IDENTITIES)
def test_selected_release_preserves_dirty_then_releases_unchanged_base(fleet, alias):
    _, _, _, env = fleet
    code, result = acquire(fleet, alias)
    assert code == 0, result
    path = Path(result["receipt"]["workspace_path"])
    (path / "unsaved.txt").write_text("preserve me\n")
    code, result = invoke(env, "release", "--repository", alias, "--operation-id", "same-operation")
    assert code == 0 and result["effect"] == "NOT_APPLIED"
    assert result["receipt"]["state"] == "PRESERVED_DIRTY"
    assert (path / "unsaved.txt").read_text() == "preserve me\n"
    (path / "unsaved.txt").unlink()
    code, result = invoke(env, "release", "--repository", alias, "--operation-id", "same-operation")
    assert code == 0 and result["receipt"]["removed"] is True
    assert not path.exists()


def test_discovery_is_read_only_and_reports_correct_default_branches(fleet):
    repos, _, root, env = fleet
    before = {a: git(p, "worktree", "list", "--porcelain") for a, (p, _) in repos.items()}
    code, result = invoke(env, "repositories")
    assert code == 0, result
    assert result["effect"] == "NOT_APPLIED"
    rows = {row["alias"]: row for row in result["receipt"]["repositories"]}
    assert set(rows) == set(IDENTITIES)
    for alias, (name, branch) in IDENTITIES.items():
        assert rows[alias]["repository_full_name"] == "mastermindx-market-intelligence/" + name
        assert rows[alias]["default_branch"] == branch
        assert rows[alias]["state"] == "READY"
    assert not root.exists()
    assert before == {a: git(p, "worktree", "list", "--porcelain") for a, (p, _) in repos.items()}


@pytest.mark.parametrize("failure", ["unenrolled", "remote", "common", "extra_field", "duplicate", "missing_source"])
def test_invalid_binding_refuses_before_allocation_without_fallback(fleet, failure):
    repos, config, root, env = fleet
    if failure == "unenrolled":
        del config["repositories"]["macro"]
    elif failure == "remote":
        git(repos["macro"][0], "remote", "set-url", "origin", "https://example.invalid/wrong.git")
    elif failure == "common":
        config["repositories"]["macro"]["common_git_dir"] = str(repos["terminal"][0] / ".git")
    elif failure == "extra_field":
        config["repositories"]["macro"]["workspace_root"] = "/unapproved"
    elif failure == "missing_source":
        config["repositories"]["macro"]["source_repository"] += "-missing"
    env["MASTERMIND_WORKSPACE_REPOSITORIES"] = json.dumps(config)
    if failure == "duplicate":
        env["MASTERMIND_WORKSPACE_REPOSITORIES"] = json.dumps(config)[:-1] + ',"repositories":{}}'
    before = {a: git(p, "worktree", "list", "--porcelain") for a, (p, _) in repos.items()}
    code, result = acquire(fleet, "macro")
    assert code == 2, result
    assert result.get("effect") == "NOT_APPLIED", result
    assert "REPOSITORY_" in result.get("error", ""), result
    assert not root.exists()
    assert before == {a: git(p, "worktree", "list", "--porcelain") for a, (p, _) in repos.items()}


def test_unenrolled_discovery_keeps_missing_target_explicit(fleet):
    _, config, root, env = fleet
    del config["repositories"]["terminal"]
    env["MASTERMIND_WORKSPACE_REPOSITORIES"] = json.dumps(config)
    code, result = invoke(env, "repositories")
    assert code == 0, result
    rows = {row["alias"]: row for row in result["receipt"]["repositories"]}
    assert rows["terminal"]["state"] == "NOT_ENROLLED"
    assert rows["mastermind"]["state"] == "READY"
    assert not root.exists()


def test_legacy_default_retains_v1_path_and_source(fleet):
    repos, _, root, env = fleet
    env.pop("MASTERMIND_WORKSPACE_REPOSITORIES")
    code, result = invoke(env, "acquire", "--operation-id", "legacy", "--base-sha", repos["mastermind"][1])
    assert code == 0, result
    assert result["schema_version"] == "mastermind.workspace_cli/v1"
    assert "repository" not in result
    assert result["receipt"]["workspace_path"] == str(root / "web" / "legacy")


@pytest.mark.parametrize("extra", [["--repository", "unknown"], ["--source-repository", "/tmp/unapproved"]])
def test_no_arbitrary_repository_or_source_path_selector(fleet, extra):
    repos, _, root, env = fleet
    code, _ = invoke(env, "acquire", "--operation-id", "invalid", "--base-sha", repos["macro"][1], *extra)
    assert code == 2
    assert not root.exists()


def test_repository_subroot_does_not_change_storage_policy_root(fleet, monkeypatch, capsys):
    repos, _, root, env = fleet
    for name, value in env.items():
        if name.startswith("MASTERMIND_"):
            monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("repository_cli_test", SCRIPT)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    observed = []
    def storage(path):
        observed.append(path)
        return {"admission_allowed": False}
    monkeypatch.setattr(cli, "_storage_status", storage)
    try:
        code = cli.main(["acquire", "--repository", "macro", "--operation-id", "low-space", "--base-sha", repos["macro"][1]])
    except SystemExit as exc:
        pytest.fail(f"closed repository CLI missing: {exc}")
    assert code == 2
    assert observed == [root]
    assert "STORAGE_LOW_SPACE" in capsys.readouterr().err
    assert not root.exists()


def test_selected_repository_uses_its_pinned_sparse_profile(fleet):
    repos, _, _, _ = fleet
    path, _ = repos["macro"]
    for d in ["src", "cache", "config"]:
        (path / d).mkdir()
    (path / "src/code.py").write_text("value = 1\n")
    (path / "cache/large.txt").write_text("excluded\n")
    (path / "config/sparse_worktree.json").write_text(json.dumps({"enabled": True, "exclude_dirs": ["cache"]}))
    git(path, "config", "extensions.worktreeConfig", "true")
    git(path, "add", ".")
    git(path, "commit", "-qm", "sparse fixture")
    repos["macro"] = (path, git(path, "rev-parse", "HEAD"))
    code, result = acquire(fleet, "macro", "sparse")
    assert code == 0, result
    workspace = Path(result["receipt"]["workspace_path"])
    assert (workspace / "src/code.py").is_file()
    assert not (workspace / "cache").exists()
    assert git(workspace, "status", "--porcelain=v1") == ""


def install_fixture(tmp_path: Path, fleet):
    repos, _, _, _ = fleet
    source, _ = repos["mastermind"]
    for relative in ["scripts/install_mastermind_workspace_cli.sh", "scripts/mastermind_workspace.py",
                     "control_plane/executive_workspace.py", "control_plane/__init__.py"]:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (source / "common").mkdir(exist_ok=True)
    for path in (ROOT / "common").glob("*.py"):
        shutil.copy2(path, source / "common" / path.name)
    git(source, "add", ".")
    git(source, "commit", "-qm", "installer fixture")
    home = tmp_path / "home O'Brien $HOME"
    home.mkdir()
    launcher = tmp_path / "bin" / "mmx-workspace"
    payload = tmp_path / "payload"
    env = dict(os.environ)
    env.update(HOME=str(home), MASTERMIND_WORKSPACE_CLI_INSTALL=str(launcher),
               MASTERMIND_WORKSPACE_CLI_PAYLOAD_ROOT=str(payload), MASTERMIND_PYTHON=sys.executable)
    return source, launcher, payload, env


def test_installed_wrapper_pins_repository_map_against_hostile_environment(tmp_path, fleet):
    repos, _, _, _ = fleet
    source, launcher, _, env = install_fixture(tmp_path, fleet)
    run = subprocess.run(["/bin/sh", str(source / "scripts/install_mastermind_workspace_cli.sh"),
                          "--repository-source", "macro=" + str(repos["macro"][0]),
                          "--repository-source", "terminal=" + str(repos["terminal"][0])],
                         env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    hostile = dict(env, MASTERMIND_WORKSPACE_REPOSITORIES='{"schema":"foreign","repositories":{}}',
                   MASTERMIND_SOURCE_REPO="/unapproved", MASTERMIND_AGENT_WORKSPACE_ROOT="/unapproved")
    result = subprocess.run([str(launcher), "repositories"], env=hostile,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    rows = {row["alias"]: row for row in json.loads(result.stdout)["receipt"]["repositories"]}
    for alias in IDENTITIES:
        assert rows[alias]["state"] == "READY"
        assert rows[alias]["source_repository"] == str(repos[alias][0].resolve())
    assert not (Path(env["HOME"]) / "unexpected-substitution").exists()


@pytest.mark.parametrize("case", ["duplicate", "wrong_origin", "unknown_alias"])
def test_installer_refuses_invalid_bindings_before_installing(tmp_path, fleet, case):
    repos, _, _, _ = fleet
    source, launcher, payload, env = install_fixture(tmp_path, fleet)
    registrations = ["macro=" + str(repos["macro"][0])]
    if case == "duplicate":
        registrations *= 2
    elif case == "wrong_origin":
        git(repos["macro"][0], "remote", "set-url", "origin", "https://example.invalid/foreign.git")
    else:
        registrations = ["arbitrary=" + str(repos["macro"][0])]
    argv = ["/bin/sh", str(source / "scripts/install_mastermind_workspace_cli.sh")]
    for value in registrations:
        argv += ["--repository-source", value]
    result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert not launcher.exists()
    assert not payload.exists()


@pytest.mark.parametrize("base", ["0" * 40, "not-a-commit", "HEAD"])
def test_selected_invalid_base_is_rejected_before_any_workspace_directory(fleet, base):
    repos, _, root, env = fleet
    before = git(repos["macro"][0], "worktree", "list", "--porcelain")
    code, result = invoke(env, "acquire", "--repository", "macro", "--operation-id", "bad-base", "--base-sha", base)
    assert code == 2
    assert result["effect"] == "NOT_APPLIED"
    assert not root.exists()
    assert git(repos["macro"][0], "worktree", "list", "--porcelain") == before


def test_changed_binding_during_storage_observation_refuses(fleet, monkeypatch, capsys):
    repos, _, root, env = fleet
    for name, value in env.items():
        if name.startswith("MASTERMIND_"):
            monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("repository_binding_race", SCRIPT)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    def storage(path):
        git(repos["macro"][0], "remote", "set-url", "origin", "https://example.invalid/rebound.git")
        return {"admission_allowed": True}
    monkeypatch.setattr(cli, "_storage_status", storage)
    code = cli.main(["acquire", "--repository", "macro", "--operation-id", "raced", "--base-sha", repos["macro"][1]])
    assert code == 2
    assert "REPOSITORY_REMOTE_MISMATCH" in capsys.readouterr().err
    assert not root.exists()


def test_repository_subroot_symlink_cannot_select_another_workspace(fleet, tmp_path):
    _, _, root, _ = fleet
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root.mkdir()
    (root / "macro").symlink_to(elsewhere, target_is_directory=True)
    code, result = acquire(fleet, "macro")
    assert code == 2 and result["effect"] == "NOT_APPLIED"
    assert not list(elsewhere.iterdir())


def test_multiple_effective_origins_are_not_one_repository_binding(fleet):
    repos, _, root, _ = fleet
    git(repos["macro"][0], "config", "--add", "remote.origin.pushurl", "https://github.com/mastermindx-market-intelligence/macro.git")
    git(repos["macro"][0], "config", "--add", "remote.origin.pushurl", "https://example.invalid/other.git")
    code, result = acquire(fleet, "macro")
    assert code == 2 and "REPOSITORY_REMOTE_MISMATCH" in result["error"]
    assert not root.exists()


def test_reinstall_without_registration_cannot_silently_remove_repository_bindings(tmp_path, fleet):
    repos, _, _, _ = fleet
    source, launcher, _, env = install_fixture(tmp_path, fleet)
    installer = ["/bin/sh", str(source / "scripts/install_mastermind_workspace_cli.sh")]
    first = subprocess.run([*installer, "--repository-source", "macro=" + str(repos["macro"][0]),
                            "--repository-source", "terminal=" + str(repos["terminal"][0])],
                           env=env, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0, first.stderr
    before = launcher.read_bytes()
    second = subprocess.run(installer, env=env, capture_output=True, text=True, timeout=30)
    assert second.returncode == 0, second.stderr
    result = subprocess.run([str(launcher), "repositories"], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    rows = {row["alias"]: row for row in json.loads(result.stdout)["receipt"]["repositories"]}
    assert {alias for alias, row in rows.items() if row["state"] == "READY"} == set(IDENTITIES)
    assert launcher.read_bytes() == before, "same-release reinstall retains exactly the same pinned map"


@pytest.mark.parametrize("fault", ["empty_map", "symlink", "writable"])
def test_reinstall_refuses_untrusted_previous_wrapper_before_overwrite(tmp_path, fleet, fault):
    repos, _, _, _ = fleet
    source, launcher, payload, env = install_fixture(tmp_path, fleet)
    installer = ["/bin/sh", str(source / "scripts/install_mastermind_workspace_cli.sh")]
    first = subprocess.run([*installer, "--repository-source", "macro=" + str(repos["macro"][0])],
                           env=env, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0, first.stderr
    if fault == "empty_map":
        lines = launcher.read_text().splitlines()
        launcher.write_text("\n".join("export MASTERMIND_WORKSPACE_REPOSITORIES=''" if line.startswith("export MASTERMIND_WORKSPACE_REPOSITORIES=") else line for line in lines) + "\n")
    elif fault == "writable":
        launcher.chmod(0o777)
    else:
        retained = launcher.with_name("retained-wrapper")
        launcher.rename(retained)
        launcher.symlink_to(retained)
    before = launcher.read_bytes()
    result = subprocess.run(installer, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0, result.stdout
    assert launcher.read_bytes() == before
    assert launcher.is_symlink() is (fault == "symlink")


def test_exact_registration_status_skips_fleet_worktree_enumeration(fleet, monkeypatch):
    """Publisher's status identifies one locked worktree without scanning peers.

    The release path must continue to use its original complete enumeration.
    """
    from control_plane import executive_workspace as workspace

    repos, _, root, env = fleet
    code, created = acquire(fleet, "macro", "status-fast-fixture")
    assert code == 0, created
    destination = Path(created["receipt"]["workspace_path"])
    source = repos["macro"][0]
    scoped_root = root / "macro"

    def fleet_scan_forbidden(*args, **kwargs):
        raise AssertionError("status must not enumerate other worktrees")

    monkeypatch.setattr(workspace, "_worktree_records", fleet_scan_forbidden)
    status = workspace.inspect_linked_worktree(
        source, scoped_root, destination,
        expected_operation_id="status-fast-fixture",
        status_direct_registration=True,
    )
    assert status.head_sha == repos["macro"][1]
    assert status.branch == "sol/web-status-fast-fixture"
    assert status.dirty is False
    assert status.removed is False
    with pytest.raises(AssertionError, match="must not enumerate"):
        workspace.inspect_linked_worktree(
            source, scoped_root, destination,
            expected_operation_id="status-fast-fixture",
        )


def test_exact_registration_status_refuses_wrong_lock_or_git_backref(fleet):
    """A synthetic or displaced .git file is never an authorized registration."""
    from control_plane import executive_workspace as workspace

    repos, _, root, _ = fleet
    code, created = acquire(fleet, "macro", "status-spoof-guard")
    assert code == 0, created
    destination = Path(created["receipt"]["workspace_path"])
    source = repos["macro"][0]
    scoped_root = root / "macro"
    admin = Path((destination / ".git").read_text().split("gitdir: ", 1)[1].strip())
    lock = admin / "locked"
    backref = admin / "gitdir"

    def must_fail():
        with pytest.raises(workspace.WorkspaceError):
            workspace.inspect_linked_worktree(
                source, scoped_root, destination,
                expected_operation_id="status-spoof-guard",
                status_direct_registration=True,
            )

    original_lock = lock.read_text()
    try:
        lock.write_text(original_lock.replace(
            "operation=status-spoof-guard", "operation=another-operation"
        ))
        must_fail()
    finally:
        lock.write_text(original_lock)

    original_backref = backref.read_text()
    try:
        backref.write_text(str(destination / "not-the-gitfile") + "\n")
        must_fail()
    finally:
        backref.write_text(original_backref)

    # The real registration remains usable; no source or fixture was deleted.
    accepted = workspace.inspect_linked_worktree(
        source, scoped_root, destination,
        expected_operation_id="status-spoof-guard",
        status_direct_registration=True,
    )
    assert accepted.head_sha == repos["macro"][1]


def test_registered_cli_status_preserves_existing_receipt_contract(fleet):
    _, _, _, env = fleet
    code, created = acquire(fleet, "macro", "status-cli-contract")
    assert code == 0, created
    code, observed = invoke(
        env, "status", "--repository", "macro",
        "--operation-id", "status-cli-contract", "--lane", "web",
    )
    assert code == 0, observed
    assert observed["schema_version"] == "mastermind.workspace_cli/v2"
    assert observed["effect"] == "NOT_APPLIED"
    assert observed["repository"] == "macro"
    receipt = observed["receipt"]
    assert receipt["branch"] == "sol/web-status-cli-contract"
    assert receipt["workspace_path"] == created["receipt"]["workspace_path"]
    assert receipt["dirty"] is False and receipt["removed"] is False


# Storage admission belongs to the existing attended workspace route.  A
# verified existing operation workspace may be re-used below the creation
# reserve because re-use allocates nothing, but the enrolled storage policy
# and volume identity are still observed on every acquisition.  The reserve
# itself is never weakened and no new allocation is admitted at low space.


def _load_cli(monkeypatch, env, module_name):
    """Load the installed CLI in-process so synthetic stand-ins are honoured."""
    for name, value in env.items():
        if name.startswith("MASTERMIND_"):
            monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


@pytest.fixture
def enrolled_volume(tmp_path, fleet, monkeypatch):
    """Synthetic enrolled volume: real policy reader, synthetic volume probe.

    No real disk probing and no host volume dependency.  The policy file is a
    synthetic fixture read by the real policy reader; only the volume identity
    and the free-byte observation are stand-ins for the enrolled host volume.
    """
    repos, config, _, _ = fleet
    mount = (tmp_path / "volume").resolve()
    mount.mkdir()
    root = mount / "workspaces"
    policy = tmp_path / "worktree-storage.json"
    data = {
        "version": 1, "mount_point": str(mount), "root": str(root),
        "volume_uuid": "7EE5D196-8BB6-4E6D-B1D7-AFEA5DEB172A", "min_free_bytes": 100,
    }
    policy.write_text(json.dumps(data))
    policy.chmod(0o600)
    env = dict(os.environ)
    env.update(MASTERMIND_SOURCE_REPO=str(repos["mastermind"][0]),
               MASTERMIND_AGENT_WORKSPACE_ROOT=str(root),
               MASTERMIND_WORKSPACE_STORAGE_POLICY=str(policy),
               MASTERMIND_WORKSPACE_REPOSITORIES=json.dumps(config))
    cli = _load_cli(monkeypatch, env, "enrolled_volume_cli_test")
    state = {
        "free": 100,
        "volume": {"Mounted": True, "Writable": True, "MountPoint": str(mount),
                   "VolumeUUID": data["volume_uuid"]},
    }
    monkeypatch.setattr(cli, "_volume_identity", lambda path: dict(state["volume"]))
    monkeypatch.setattr(cli, "_storage_free_bytes", lambda path: state["free"])
    return cli, repos, root, state, policy, data


def test_existing_workspace_reuse_survives_low_storage_without_new_allocation(fleet, monkeypatch, capsys):
    """A verified existing operation workspace is re-used below the reserve.

    The storage observation itself is never skipped: the enrolled host root is
    still checked on the re-use, and a new operation is still refused.
    """
    repos, _, root, env = fleet
    code, created = acquire(fleet, "mastermind", "reuse-low-storage")
    assert code == 0 and created["effect"] == "APPLIED"
    original = Path(created["receipt"]["workspace_path"])
    registered = git(repos["mastermind"][0], "worktree", "list", "--porcelain")
    cli = _load_cli(monkeypatch, env, "reuse_storage_cli_test")
    observed = []

    def storage(path):
        observed.append(path)
        return {"admission_allowed": False}

    monkeypatch.setattr(cli, "_storage_status", storage)
    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "reuse-low-storage", "--base-sha", repos["mastermind"][1]])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["effect"] == "NOT_APPLIED"
    assert payload["receipt"]["reused"] is True
    assert payload["receipt"]["workspace_path"] == str(original)
    # The storage observation is NOT skipped for an existing path.
    assert observed == [root]
    assert git(original, "status", "--porcelain=v1") == ""
    assert git(repos["mastermind"][0], "worktree", "list", "--porcelain") == registered

    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "new-low-storage", "--base-sha", repos["mastermind"][1]])
    payload = json.loads(capsys.readouterr().err)
    assert code == 2 and payload["effect"] == "NOT_APPLIED"
    assert "STORAGE_LOW_SPACE" in payload["error"]
    assert observed == [root, root]
    assert not (root / "web" / "new-low-storage").exists()


def test_verified_existing_workspace_is_reused_below_the_creation_reserve(enrolled_volume, capsys):
    """The real storage reader observes LOW_SPACE and still permits re-use."""
    cli, repos, root, state, _policy, _data = enrolled_volume
    base = repos["mastermind"][1]
    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "reuse-below-reserve", "--base-sha", base])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["effect"] == "APPLIED"
    assert payload["receipt"]["reused"] is False
    original = Path(payload["receipt"]["workspace_path"])

    state["free"] = 99
    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "reuse-below-reserve", "--base-sha", base])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["effect"] == "NOT_APPLIED"
    assert payload["receipt"]["reused"] is True
    assert payload["receipt"]["workspace_path"] == str(original)
    assert payload["receipt"]["base_sha"] == base
    assert git(original, "status", "--porcelain=v1") == ""


def test_new_allocation_remains_blocked_below_the_creation_reserve(enrolled_volume, capsys):
    """The reserve still refuses a new allocation; nothing is allocated."""
    cli, repos, root, state, _policy, _data = enrolled_volume
    base = repos["mastermind"][1]
    state["free"] = 99
    registered = git(repos["mastermind"][0], "worktree", "list", "--porcelain")
    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "new-below-reserve", "--base-sha", base])
    payload = json.loads(capsys.readouterr().err)
    assert code == 2 and payload["effect"] == "NOT_APPLIED"
    assert "STORAGE_LOW_SPACE" in payload["error"]
    assert not (root / "web" / "new-below-reserve").exists()
    assert git(repos["mastermind"][0], "worktree", "list", "--porcelain") == registered
    assert "sol/web-new-below-reserve" not in git(repos["mastermind"][0], "branch", "--list")


@pytest.mark.parametrize("failure,expected", [
    ("identity", "STORAGE_VOLUME_IDENTITY_MISMATCH"),
    ("read_only", "STORAGE_VOLUME_READ_ONLY"),
    ("policy", "STORAGE_POLICY_INVALID"),
])
def test_storage_identity_read_only_and_policy_errors_refuse_even_an_existing_workspace(
    enrolled_volume, capsys, failure, expected,
):
    """A failing storage observation is never skipped for an existing path."""
    cli, repos, root, state, policy, data = enrolled_volume
    base = repos["mastermind"][1]
    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "guarded-reuse", "--base-sha", base])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["effect"] == "APPLIED"
    original = Path(payload["receipt"]["workspace_path"])

    if failure == "identity":
        state["volume"]["VolumeUUID"] = "BDB7D9BA-7145-4115-B6BA-EB9B54896B67"
    elif failure == "read_only":
        state["volume"]["Writable"] = False
    else:
        data["version"] = 2
        policy.write_text(json.dumps(data))

    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "guarded-reuse", "--base-sha", base])
    payload = json.loads(capsys.readouterr().err)
    assert code == 2 and payload["effect"] == "NOT_APPLIED"
    assert expected in payload["error"]
    # The refused re-use left the existing workspace registered and untouched.
    assert original.is_dir()
    assert git(original, "status", "--porcelain=v1") == ""


def test_invalid_or_mismatched_existing_workspace_is_refused_below_the_creation_reserve(
    enrolled_volume, capsys,
):
    """Existing-path reuse still requires a verified managed linked workspace."""
    cli, repos, root, state, _policy, _data = enrolled_volume
    base = repos["mastermind"][1]
    source = repos["mastermind"][0]

    # A directory that is not a managed linked worktree is never re-used.
    decoy = root / "web" / "not-a-workspace"
    decoy.mkdir(parents=True)
    state["free"] = 99
    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "not-a-workspace", "--base-sha", base])
    payload = json.loads(capsys.readouterr().err)
    assert code == 2 and payload["effect"] == "NOT_APPLIED"
    assert "not registered to the source repository" in payload["error"]
    assert list(decoy.iterdir()) == []

    # A workspace bound to another base is not re-used for this operation.
    state["free"] = 100
    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "bound-workspace", "--base-sha", base])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["effect"] == "APPLIED"
    original = Path(payload["receipt"]["workspace_path"])
    (source / "second.txt").write_text("second\n")
    git(source, "add", ".")
    git(source, "commit", "-qm", "second fixture")
    second = git(source, "rev-parse", "HEAD")
    state["free"] = 99
    code = cli.main(["acquire", "--repository", "mastermind", "--lane", "web",
                     "--operation-id", "bound-workspace", "--base-sha", second])
    payload = json.loads(capsys.readouterr().err)
    assert code == 2 and payload["effect"] == "NOT_APPLIED"
    assert "lock identity does not match" in payload["error"]
    assert original.is_dir()
    assert git(original, "status", "--porcelain=v1") == ""
