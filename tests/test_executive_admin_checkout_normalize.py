from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(root), *args],
        check=check,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(root.parent / "home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
        },
    )


def _repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Executive Test")
    _git(root, "config", "user.email", "executive@example.invalid")
    (root / "payload.txt").write_text("payload\n", encoding="utf-8")
    _git(root, "add", "payload.txt")
    _git(root, "commit", "-q", "-m", "fixture")
    return root, _git(root, "rev-parse", "HEAD").stdout.strip()


def _marker(root: Path, name: str = "pack-" + "a" * 40 + ".promisor", data: bytes = b"") -> Path:
    pack = root / ".git/objects/pack"
    pack.mkdir(parents=True, exist_ok=True)
    marker = pack / name
    marker.write_bytes(data)
    return marker


def test_complete_checkout_normalizes_only_empty_safe_promisor_marker(tmp_path: Path):
    from ops.executive_os.admin_checkout import normalize_admin_checkout

    root, head = _repo(tmp_path)
    marker = _marker(root)
    result = normalize_admin_checkout(root, expected_commit=head)

    assert result["commit"] == head
    assert result["normalized_promisor_markers"] == 1
    assert not marker.exists()
    assert not list((root / ".git/objects/pack").glob("*.promisor"))


def test_complete_checkout_without_marker_is_unchanged(tmp_path: Path):
    from ops.executive_os.admin_checkout import normalize_admin_checkout

    root, head = _repo(tmp_path)
    before = _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    result = normalize_admin_checkout(root, expected_commit=head)
    after = _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout

    assert result["normalized_promisor_markers"] == 0
    assert before == after == ""


def test_missing_reachable_object_refuses_and_preserves_promisor_evidence(tmp_path: Path):
    from ops.executive_os.admin_checkout import AdminCheckoutError, normalize_admin_checkout

    root, head = _repo(tmp_path)
    marker = _marker(root)
    blob = _git(root, "rev-parse", "HEAD:payload.txt").stdout.strip()
    loose = root / ".git/objects" / blob[:2] / blob[2:]
    assert loose.is_file()
    loose.unlink()

    with pytest.raises(AdminCheckoutError, match="reachable object closure is incomplete"):
        normalize_admin_checkout(root, expected_commit=head)
    assert marker.is_file()


@pytest.mark.parametrize("disappear_at", ["initial", "before_unlink"])
def test_normalize_refuses_commit_graph_hidden_missing_parent(
    tmp_path: Path, monkeypatch, disappear_at: str,
):
    from ops.executive_os import admin_checkout

    root, parent = _repo(tmp_path)
    (root / "payload.txt").write_text("second\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "second")
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    _git(root, "commit-graph", "write", "--reachable")
    marker = _marker(root)
    loose = root / ".git/objects" / parent[:2] / parent[2:]
    if disappear_at == "initial":
        loose.unlink()
    else:
        original = admin_checkout._validated_markers

        def remove_parent(*args):
            result = original(*args)
            loose.unlink()
            return result

        monkeypatch.setattr(admin_checkout, "_validated_markers", remove_parent)
    with pytest.raises(admin_checkout.AdminCheckoutError, match="reachable object closure is incomplete"):
        admin_checkout.normalize_admin_checkout(root, expected_commit=head)
    # rev-list can still print the missing parent's SHA from its commit graph.
    assert parent in _git(root, "rev-list", "--objects", "--missing=print", "--no-object-names", head).stdout
    assert marker.is_file() and marker.read_bytes() == b""


def test_normalize_checks_all_enumerated_object_types_twice_without_lazy_fetch(tmp_path: Path, monkeypatch):
    from ops.executive_os import admin_checkout

    root, head = _repo(tmp_path)
    marker = _marker(root)
    expected = set(_git(root, "rev-list", "--objects", "--no-object-names", head).stdout.splitlines())
    original = admin_checkout._run_git
    batches = []

    def observe(checkout, *args, **kwargs):
        if "cat-file" in args:
            batches.append(set(kwargs["input_bytes"].decode("ascii").splitlines()))
            assert admin_checkout._git_env()["GIT_NO_LAZY_FETCH"] == "1"
        return original(checkout, *args, **kwargs)

    monkeypatch.setattr(admin_checkout, "_run_git", observe)
    admin_checkout.normalize_admin_checkout(root, expected_commit=head)
    assert batches == [expected, expected]
    assert not marker.exists()


@pytest.mark.parametrize("case", ["nonempty", "symlink", "hardlink", "writable"])
def test_unsafe_promisor_marker_refuses_without_deleting_evidence(tmp_path: Path, case: str):
    from ops.executive_os.admin_checkout import AdminCheckoutError, normalize_admin_checkout

    root, head = _repo(tmp_path)
    marker = root / ".git/objects/pack" / ("pack-" + "a" * 40 + ".promisor")
    marker.parent.mkdir(parents=True, exist_ok=True)
    if case == "nonempty":
        marker.write_bytes(b"unexpected")
    elif case == "symlink":
        target = root / "marker-target"
        target.write_bytes(b"")
        marker.symlink_to(target)
    elif case == "hardlink":
        marker.write_bytes(b"")
        os.link(marker, root / "marker-hardlink")
    elif case == "writable":
        marker.write_bytes(b"")
        marker.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IWGRP)

    with pytest.raises(AdminCheckoutError, match="promisor marker is unsafe"):
        normalize_admin_checkout(root, expected_commit=head)
    assert marker.exists() or marker.is_symlink()


def test_partial_clone_config_refuses_before_marker_normalization(tmp_path: Path):
    from ops.executive_os.admin_checkout import AdminCheckoutError, normalize_admin_checkout

    root, head = _repo(tmp_path)
    marker = _marker(root)
    _git(root, "config", "remote.origin.promisor", "true")

    with pytest.raises(AdminCheckoutError, match="partial clone configuration remains"):
        normalize_admin_checkout(root, expected_commit=head)
    assert marker.is_file()


def test_normalize_refuses_head_mismatch_and_preserves_markers(tmp_path: Path):
    from ops.executive_os.admin_checkout import AdminCheckoutError, normalize_admin_checkout

    root, _head = _repo(tmp_path)
    marker = _marker(root)
    with pytest.raises(AdminCheckoutError, match="HEAD differs"):
        normalize_admin_checkout(root, expected_commit="0" * 40)
    assert marker.is_file()


def test_normalize_refuses_remaining_remote_and_preserves_markers(tmp_path: Path):
    from ops.executive_os.admin_checkout import AdminCheckoutError, normalize_admin_checkout

    root, head = _repo(tmp_path)
    marker = _marker(root)
    _git(root, "remote", "add", "origin", "https://example.invalid/repo.git")
    with pytest.raises(AdminCheckoutError, match="still has a remote"):
        normalize_admin_checkout(root, expected_commit=head)
    assert marker.is_file()


def test_normalize_refuses_supplied_root_symlink_without_following(tmp_path: Path):
    from ops.executive_os.admin_checkout import AdminCheckoutError, normalize_admin_checkout

    root, head = _repo(tmp_path)
    marker = _marker(root)
    alias = tmp_path / "alias-checkout"
    alias.symlink_to(root)
    with pytest.raises(AdminCheckoutError, match="root is unsafe"):
        normalize_admin_checkout(alias, expected_commit=head)
    assert marker.is_file()
    assert list((root / ".git/objects/pack").glob("*.promisor"))


@pytest.mark.parametrize(
    "marker_path",
    [
        "commondir",
        "shallow",
        "info/grafts",
        "objects/info/alternates",
        "objects/info/http-alternates",
    ],
)
def test_normalize_refuses_shared_object_store_topology_and_preserves_markers(
    tmp_path: Path, marker_path: str,
):
    from ops.executive_os.admin_checkout import AdminCheckoutError, normalize_admin_checkout

    root, head = _repo(tmp_path)
    marker = _marker(root)
    path = root / ".git" / marker_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("foreign\n", encoding="utf-8")
    with pytest.raises(AdminCheckoutError, match="object store is unsafe"):
        normalize_admin_checkout(root, expected_commit=head)
    assert marker.is_file()


def test_normalize_refuses_symlinked_object_store_and_preserves_markers(tmp_path: Path):
    from ops.executive_os.admin_checkout import AdminCheckoutError, normalize_admin_checkout

    root, head = _repo(tmp_path)
    marker = _marker(root)
    objects = root / ".git" / "objects"
    external = tmp_path / "external-objects"
    objects.rename(external)
    objects.symlink_to(external, target_is_directory=True)
    with pytest.raises(AdminCheckoutError, match="object store is unsafe"):
        normalize_admin_checkout(root, expected_commit=head)
    assert (external / "pack" / marker.name).is_file()


def test_installer_style_destination_normalizes_without_mutating_partial_source(
    tmp_path: Path,
):
    """Partial-clone source stays untouched; only the installer destination is
    normalized, then the installed reader accepts that destination.
    """
    from integrations.executive_mcp.installed import _direct_git_directory
    from integrations.executive_mcp.schemas import GatewayError
    from ops.executive_os.admin_checkout import normalize_admin_checkout

    origin, head = _repo(tmp_path)
    partial = tmp_path / "partial-source"
    clone_env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(tmp_path / "home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    subprocess.run(
        [
            "/usr/bin/git", "clone", "--filter=blob:none", "--no-hardlinks",
            str(origin), str(partial),
        ],
        check=True, capture_output=True, env=clone_env,
    )
    lazy_env = dict(clone_env)
    lazy_env["GIT_NO_LAZY_FETCH"] = "0"
    subprocess.run(
        ["/usr/bin/git", "-C", str(partial), "checkout", "--force", "HEAD"],
        check=True, capture_output=True, env=lazy_env,
    )
    source_config = (partial / ".git/config").read_bytes()
    source_markers_before = sorted(
        path.name for path in (partial / ".git/objects/pack").glob("*.promisor")
    )
    assert source_markers_before or _git(
        partial, "config", "--get", "remote.origin.promisor", check=False,
    ).stdout.strip()

    dest = tmp_path / "admin-checkout"
    subprocess.run(
        [
            "/usr/bin/git", "clone", "--no-hardlinks", "--no-checkout",
            str(partial), str(dest),
        ],
        check=True, capture_output=True, env=clone_env,
    )
    _git(dest, "checkout", "--detach", head)
    _git(dest, "remote", "remove", "origin")
    _git(dest, "repack", "-ad")
    _git(dest, "prune", "--expire=now")
    dest_pack = dest / ".git/objects/pack"
    dest_pack.mkdir(parents=True, exist_ok=True)
    if not list(dest_pack.glob("*.promisor")):
        (dest_pack / ("pack-" + "b" * 40 + ".promisor")).write_bytes(b"")
    dest_markers_before = sorted(path.name for path in dest_pack.glob("*.promisor"))
    assert dest_markers_before

    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _direct_git_directory(dest, label="administrative checkout")
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _direct_git_directory(partial, label="partial source")

    result = normalize_admin_checkout(dest, expected_commit=head)
    assert result["commit"] == head
    assert result["normalized_promisor_markers"] == len(dest_markers_before)
    assert not list(dest_pack.glob("*.promisor"))
    assert _direct_git_directory(dest, label="administrative checkout") is not None

    assert (partial / ".git/config").read_bytes() == source_config
    assert sorted(
        path.name for path in (partial / ".git/objects/pack").glob("*.promisor")
    ) == source_markers_before
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _direct_git_directory(partial, label="partial source")
    assert (origin / "payload.txt").read_text(encoding="utf-8") == "payload\n"
