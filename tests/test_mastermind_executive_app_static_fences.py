"""BSC-E1 durable source fences and self-scoping pull-request ratchet.

Source-level checks protect the authenticated Executive app's permanent owner
boundaries.  A separate local, read-only Git helper applies the historical
BSC-E1 carrier ceiling only when the current effective delta touches that
program's reserved surface.  Empty and wholly unrelated pull requests remain
not applicable; a BSC-E1 touch re-arms whole-delta allowlist enforcement.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
import subprocess
from typing import Iterable

import pytest

from integrations.executive_mcp import schemas as mcp_schemas

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PACKAGE = REPO_ROOT / "integrations" / "mastermind_executive_app"
APP_PACKAGE_FILES = [
    APP_PACKAGE / "__init__.py",
    APP_PACKAGE / "app.py",
    APP_PACKAGE / "gateway.py",
    APP_PACKAGE / "admission.py",
]
ENTRYPOINT_SCRIPT = REPO_ROOT / "scripts" / "mastermind_executive_app.py"
ALL_OWNED_MODULES = APP_PACKAGE_FILES + [ENTRYPOINT_SCRIPT]
EXPECTED_APP_SOURCE_SURFACE = {
    "integrations/mastermind_executive_app/__init__.py",
    "integrations/mastermind_executive_app/admission.py",
    "integrations/mastermind_executive_app/app.py",
    "integrations/mastermind_executive_app/gateway.py",
}
EXPECTED_SUPPORT_PATHS = {
    "config/business_mcp/executive_policy.example.json",
    "docs/runbooks/mastermind-executive-app.md",
    "scripts/mastermind_executive_app.py",
    "tests/test_mastermind_executive_app_admission.py",
    "tests/test_mastermind_executive_app_asgi.py",
    "tests/test_mastermind_executive_app_static_fences.py",
}
EXPECTED_CONTROL_PLANE_DEPENDENCIES = {
    "control_plane.ceo_boot_packet",
    "control_plane.ceo_request",
    "control_plane.executive_ceo_ingress",
}
BSC_E1_ALLOWED_PATHS = frozenset(
    {
        "config/business_mcp/executive_policy.example.json",
        "control_plane/ceo_request.py",
        "docs/runbooks/mastermind-executive-app.md",
        "integrations/mastermind_executive_app/__init__.py",
        "integrations/mastermind_executive_app/admission.py",
        "integrations/mastermind_executive_app/app.py",
        "integrations/mastermind_executive_app/gateway.py",
        "scripts/mastermind_executive_app.py",
        "tests/test_mastermind_executive_app_admission.py",
        "tests/test_mastermind_executive_app_asgi.py",
        "tests/test_mastermind_executive_app_static_fences.py",
    }
)
# Prefixes are intentionally wider than the allowlist. A new app/control/test/
# script/config/runbook path must trigger the ratchet and then be refused until
# a separately reviewed source-law change ratchets it in.
BSC_E1_TRIGGER_PREFIXES = (
    "config/business_mcp/executive_policy",
    "control_plane/ceo_request",
    "docs/runbooks/mastermind-executive-app",
    "integrations/mastermind_executive_app",
    "scripts/mastermind_executive_app",
    "tests/test_mastermind_executive_app",
)
LOCAL_READ_ONLY_GIT_COMMANDS = frozenset(
    {"diff", "merge-base", "rev-list", "rev-parse", "show"}
)


class StaticFenceGitError(RuntimeError):
    """A local Git read could not establish an unambiguous effective delta."""


def _imported_module_names(path: Path) -> set[str]:
    """Return imported modules, including full ``from x import y`` candidates."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )
    return names


def _control_plane_dependencies(path: Path) -> set[str]:
    """Normalize the control-plane modules imported by one owned source file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "control_plane" or alias.name.startswith("control_plane."):
                    names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "control_plane":
                names.update(
                    f"control_plane.{alias.name}"
                    for alias in node.names
                    if alias.name != "*"
                )
            elif node.module.startswith("control_plane."):
                names.add(node.module)
    return names


def _python_source_surface(package: Path, *, root: Path) -> set[str]:
    """Return every Python source path below ``package`` relative to ``root``."""

    return {
        path.relative_to(root).as_posix()
        for path in package.rglob("*.py")
        if path.is_file()
    }


def _bsc_e1_unexpected_paths(changed: Iterable[str]) -> set[str] | None:
    """Return widened paths, or ``None`` when the BSC-E1 ratchet is inapplicable."""

    normalized = {Path(path).as_posix().removeprefix("./") for path in changed}
    applies = any(
        path.startswith(prefix)
        for path in normalized
        for prefix in BSC_E1_TRIGGER_PREFIXES
    )
    if not applies:
        return None
    return normalized - BSC_E1_ALLOWED_PATHS


def _git_read(
    repo: Path,
    command: str,
    *args: str,
    accepted_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    """Run one allowlisted local Git read; never fetch or mutate repository state."""

    if command not in LOCAL_READ_ONLY_GIT_COMMANDS:
        raise StaticFenceGitError("BSC_E1_GIT_COMMAND_REFUSED")
    try:
        completed = subprocess.run(
            ["git", command, *args],
            cwd=str(repo),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise StaticFenceGitError("BSC_E1_GIT_READ_FAILED") from None
    if completed.returncode not in accepted_codes:
        raise StaticFenceGitError("BSC_E1_GIT_READ_FAILED")
    return completed


def _resolve_commit(repo: Path, revision: str) -> str:
    completed = _git_read(repo, "rev-parse", "--verify", f"{revision}^{{commit}}")
    resolved = completed.stdout.strip()
    if len(resolved) != 40:
        raise StaticFenceGitError("BSC_E1_GIT_IDENTITY_INVALID")
    return resolved


def _head_parents(repo: Path, head_sha: str) -> tuple[str, ...]:
    completed = _git_read(repo, "show", "-s", "--format=%P", head_sha)
    parents = tuple(completed.stdout.strip().split())
    if any(len(parent) != 40 for parent in parents):
        raise StaticFenceGitError("BSC_E1_GIT_IDENTITY_INVALID")
    return parents


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    completed = _git_read(
        repo,
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
        accepted_codes=(0, 1),
    )
    return completed.returncode == 0


def _distance_to_upstream(repo: Path, ancestor: str, upstream_sha: str) -> int:
    completed = _git_read(repo, "rev-list", "--count", f"{ancestor}..{upstream_sha}")
    try:
        distance = int(completed.stdout.strip())
    except ValueError:
        raise StaticFenceGitError("BSC_E1_GIT_IDENTITY_INVALID") from None
    if distance < 0:
        raise StaticFenceGitError("BSC_E1_GIT_IDENTITY_INVALID")
    return distance


def _select_base_parent(
    repo: Path,
    *,
    parents: tuple[str, ...],
    upstream_sha: str,
) -> str:
    """Select the unique parent nearest to and ancestral to resolved upstream."""

    exact = [parent for parent in parents if parent == upstream_sha]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise StaticFenceGitError("BSC_E1_BASE_PARENT_AMBIGUOUS")

    candidates = [
        parent for parent in parents if _is_ancestor(repo, parent, upstream_sha)
    ]
    if not candidates:
        raise StaticFenceGitError("BSC_E1_BASE_PARENT_UNRESOLVED")

    distance_by_parent = {
        parent: _distance_to_upstream(repo, parent, upstream_sha)
        for parent in candidates
    }
    nearest = min(distance_by_parent.values())
    winners = [
        parent for parent, distance in distance_by_parent.items() if distance == nearest
    ]
    if len(winners) != 1:
        raise StaticFenceGitError("BSC_E1_BASE_PARENT_AMBIGUOUS")
    return winners[0]


def compute_pr_diff_paths(
    repo: Path,
    *,
    head: str = "HEAD",
    upstream: str = "origin/master",
) -> set[str]:
    """Compute the feature-side effective delta from local immutable Git facts."""

    head_sha = _resolve_commit(repo, head)
    upstream_sha = _resolve_commit(repo, upstream)
    parents = _head_parents(repo, head_sha)

    if len(parents) > 1:
        base_sha = _select_base_parent(
            repo,
            parents=parents,
            upstream_sha=upstream_sha,
        )
    else:
        completed = _git_read(repo, "merge-base", upstream_sha, head_sha)
        base_sha = completed.stdout.strip()
        if len(base_sha) != 40:
            raise StaticFenceGitError("BSC_E1_BASE_PARENT_UNRESOLVED")

    completed = _git_read(
        repo,
        "diff",
        "--name-only",
        "--diff-filter=ACDMRTUXB",
        base_sha,
        head_sha,
        "--",
    )
    return {line for line in completed.stdout.splitlines() if line}


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_imports_executive_service(path: Path) -> None:
    imported = _imported_module_names(path)
    forbidden = {
        name
        for name in imported
        if name == "control_plane.executive_service"
        or name.startswith("control_plane.executive_service.")
    }
    assert not forbidden, f"{path.name} imports forbidden module(s): {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_imports_mcp_sdk(path: Path) -> None:
    imported = _imported_module_names(path)
    forbidden = {name for name in imported if name == "mcp" or name.startswith("mcp.")}
    assert not forbidden, f"{path.name} imports the MCP SDK: {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_imports_executive_mcp_server_module(path: Path) -> None:
    imported = _imported_module_names(path)
    assert "integrations.executive_mcp.server" not in imported


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_imports_ceo_intent_module_directly(path: Path) -> None:
    imported = _imported_module_names(path)
    forbidden = {
        name
        for name in imported
        if name == "control_plane.ceo_intent"
        or name.startswith("control_plane.ceo_intent.")
    }
    assert not forbidden, f"{path.name} imports CEO intent directly: {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_references_send_control_request(path: Path) -> None:
    assert "send_control_request" not in path.read_text(encoding="utf-8"), path.name


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_calls_submit_intent_by_name(path: Path) -> None:
    assert "submit_intent(" not in path.read_text(encoding="utf-8"), path.name


@pytest.mark.parametrize("path", APP_PACKAGE_FILES, ids=lambda path: path.name)
def test_app_package_never_imports_subprocess_or_uses_dynamic_execution(path: Path) -> None:
    imported = _imported_module_names(path)
    assert "subprocess" not in imported, path.name
    source = path.read_text(encoding="utf-8")
    assert "os.system(" not in source, path.name
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("eval", "exec"), f"{path.name} calls {node.func.id}()"


def test_admission_never_widens_the_five_tool_privileged_field_list() -> None:
    spec = mcp_schemas.tool_spec(mcp_schemas.MODIFYING_TOOL)
    properties = set(spec.input_schema.get("properties", {}))
    forbidden = {
        "actor",
        "authority_level",
        "requested_authorities",
        "branch",
        "worktree",
        "grounding",
        "request_ref",
        "intent_id",
        "job_id",
        "status",
        "dispatched",
        "schema",
        "provider",
        "account",
        "session",
    }
    assert not (properties & forbidden), properties & forbidden
    assert spec.input_schema.get("additionalProperties") is False


def test_schema_digest_unchanged() -> None:
    assert mcp_schemas.schema_snapshot_sha256() == (
        "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    )


def test_general_executive_service_has_no_app_back_dependency() -> None:
    service = REPO_ROOT / "control_plane" / "executive_service.py"
    imported = _imported_module_names(service)
    assert all(
        not name.startswith("integrations.mastermind_executive_app")
        for name in imported
    )
    assert "mastermind_executive_app" not in service.read_text(encoding="utf-8")


def test_app_control_plane_dependencies_are_closed_to_existing_owners() -> None:
    actual: set[str] = set()
    for path in APP_PACKAGE_FILES:
        actual.update(_control_plane_dependencies(path))
    assert actual == EXPECTED_CONTROL_PLANE_DEPENDENCIES
    assert not _control_plane_dependencies(ENTRYPOINT_SCRIPT)


def test_bsc_e1_artifact_surface_is_present_and_package_is_closed() -> None:
    actual_app_source = _python_source_surface(APP_PACKAGE, root=REPO_ROOT)
    assert actual_app_source == EXPECTED_APP_SOURCE_SURFACE
    for relative in EXPECTED_SUPPORT_PATHS:
        assert (REPO_ROOT / relative).is_file(), relative


def test_static_fence_git_reader_is_local_read_only_and_pr_identity_agnostic() -> None:
    assert LOCAL_READ_ONLY_GIT_COMMANDS == {
        "diff",
        "merge-base",
        "rev-list",
        "rev-parse",
        "show",
    }
    with pytest.raises(StaticFenceGitError, match="BSC_E1_GIT_COMMAND_REFUSED"):
        _git_read(REPO_ROOT, "fetch")
    helper_source = inspect.getsource(compute_pr_diff_paths) + inspect.getsource(
        _select_base_parent
    )
    assert "pull/" not in helper_source
    assert "#372" not in helper_source


def test_current_effective_delta_respects_bsc_e1_owner_surface() -> None:
    changed = compute_pr_diff_paths(REPO_ROOT)
    unexpected = _bsc_e1_unexpected_paths(changed)
    if unexpected is None:
        return
    assert unexpected == set(), (
        "BSC-E1 effective delta escaped its closed owner surface: "
        f"{sorted(unexpected)}"
    )


def test_import_from_member_is_normalized_to_full_forbidden_module(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "from integrations.executive_mcp import server\n",
        encoding="utf-8",
    )
    imported = _imported_module_names(candidate)
    assert "integrations.executive_mcp.server" in imported


def test_python_source_surface_is_recursive(tmp_path: Path) -> None:
    package = tmp_path / "integrations" / "mastermind_executive_app"
    nested = package / "subpackage"
    nested.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (nested / "hidden_ingress.py").write_text("x = 1\n", encoding="utf-8")
    surface = _python_source_surface(package, root=tmp_path)
    assert surface == {
        "integrations/mastermind_executive_app/__init__.py",
        "integrations/mastermind_executive_app/subpackage/hidden_ingress.py",
    }


def test_bsc_e1_delta_empty_is_not_applicable() -> None:
    assert _bsc_e1_unexpected_paths(set()) is None


def test_bsc_e1_delta_foreign_only_c1_shape_is_not_applicable() -> None:
    assert _bsc_e1_unexpected_paths(
        {
            "control_plane/chairman_control_room.py",
            "control_plane/executive_placement_selection.py",
            "scripts/chairman_control_room.py",
            "tests/test_chairman_control_room.py",
            "tests/test_executive_placement_selection.py",
        }
    ) is None


def test_bsc_e1_delta_allowed_subset_applies_and_passes() -> None:
    assert _bsc_e1_unexpected_paths(
        {
            "integrations/mastermind_executive_app/app.py",
            "tests/test_mastermind_executive_app_static_fences.py",
            "control_plane/ceo_request.py",
        }
    ) == set()


def test_bsc_e1_delta_owned_plus_foreign_refuses_foreign_path() -> None:
    assert _bsc_e1_unexpected_paths(
        {
            "integrations/mastermind_executive_app/app.py",
            "docs/unrelated_foreign.md",
        }
    ) == {"docs/unrelated_foreign.md"}


def test_bsc_e1_delta_owned_plus_executive_service_refuses_service() -> None:
    assert _bsc_e1_unexpected_paths(
        {
            "integrations/mastermind_executive_app/app.py",
            "control_plane/executive_service.py",
        }
    ) == {"control_plane/executive_service.py"}


@pytest.mark.parametrize(
    "path",
    [
        "integrations/mastermind_executive_app/hidden_ingress.py",
        "integrations/mastermind_executive_app/subpackage/hidden_ingress.py",
        "tests/test_mastermind_executive_app_hidden.py",
        "scripts/mastermind_executive_app_hidden.py",
        "config/business_mcp/executive_policy.hidden.json",
        "docs/runbooks/mastermind-executive-app-hidden.md",
        "control_plane/ceo_request_hidden.py",
    ],
)
def test_bsc_e1_delta_new_reserved_surface_path_is_refused(path: str) -> None:
    assert _bsc_e1_unexpected_paths({path}) == {path}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _git_init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    result = _git(repo, "init", "-q", "-b", "master")
    assert result.returncode == 0, result.stderr
    assert _git(repo, "config", "user.email", "test@example.invalid").returncode == 0
    assert _git(repo, "config", "user.name", "BSC-E1 Fence Test").returncode == 0


def _git_commit_file(repo: Path, relative: str, content: str, message: str) -> str:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    assert _git(repo, "add", relative).returncode == 0
    result = _git(repo, "commit", "-q", "-m", message)
    assert result.returncode == 0, result.stderr
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _commit_tree(repo: Path, tree: str, parents: tuple[str, ...], message: str) -> str:
    args: list[str] = ["commit-tree", tree]
    for parent in parents:
        args.extend(["-p", parent])
    args.extend(["-m", message])
    result = _git(repo, *args)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_compute_pr_diff_paths_linear_branch_returns_only_feature_delta(tmp_path: Path) -> None:
    repo = tmp_path / "linear"
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base")
    assert _git(repo, "update-ref", "refs/remotes/origin/master", "master").returncode == 0
    assert _git(repo, "checkout", "-q", "-b", "feature").returncode == 0
    _git_commit_file(
        repo,
        "integrations/mastermind_executive_app/app.py",
        "x = 1\n",
        "feature",
    )
    assert compute_pr_diff_paths(repo, head="HEAD", upstream="origin/master") == {
        "integrations/mastermind_executive_app/app.py"
    }


@pytest.mark.parametrize("orientation", ["base_first", "feature_first"])
def test_compute_pr_diff_paths_identifies_base_parent_in_both_merge_orientations(
    tmp_path: Path,
    orientation: str,
) -> None:
    repo = tmp_path / orientation
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base")
    assert _git(repo, "checkout", "-q", "-b", "feature").returncode == 0
    _git_commit_file(
        repo,
        "integrations/mastermind_executive_app/app.py",
        "x = 1\n",
        "feature",
    )
    assert _git(repo, "checkout", "-q", "master").returncode == 0
    _git_commit_file(repo, "docs/base_movement.md", "base moved\n", "base movement")
    assert _git(repo, "update-ref", "refs/remotes/origin/master", "master").returncode == 0
    if orientation == "base_first":
        result = _git(repo, "merge", "--no-ff", "-q", "-m", "hosted merge", "feature")
    else:
        assert _git(repo, "checkout", "-q", "feature").returncode == 0
        result = _git(repo, "merge", "--no-ff", "-q", "-m", "history join", "master")
    assert result.returncode == 0, result.stderr
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    changed = compute_pr_diff_paths(repo, head=head, upstream="origin/master")
    assert changed == {"integrations/mastermind_executive_app/app.py"}
    assert "docs/base_movement.md" not in changed


def test_compute_pr_diff_paths_fails_when_no_parent_is_base_side(tmp_path: Path) -> None:
    repo = tmp_path / "unresolved"
    _git_init(repo)
    root = _git_commit_file(repo, "README.md", "root\n", "root")
    assert _git(repo, "checkout", "-q", "-b", "upstream", root).returncode == 0
    _git_commit_file(repo, "docs/upstream.md", "upstream\n", "upstream")
    assert _git(repo, "update-ref", "refs/remotes/origin/master", "upstream").returncode == 0
    assert _git(repo, "checkout", "-q", "-b", "left", root).returncode == 0
    left = _git_commit_file(repo, "left.txt", "left\n", "left")
    assert _git(repo, "checkout", "-q", "-b", "right", root).returncode == 0
    right = _git_commit_file(repo, "right.txt", "right\n", "right")
    tree = _git(repo, "rev-parse", f"{right}^{{tree}}").stdout.strip()
    head = _commit_tree(repo, tree, (left, right), "unresolved merge")
    with pytest.raises(StaticFenceGitError, match="BSC_E1_BASE_PARENT_UNRESOLVED"):
        compute_pr_diff_paths(repo, head=head, upstream="origin/master")


def test_compute_pr_diff_paths_fails_when_base_parent_is_ambiguous(tmp_path: Path) -> None:
    repo = tmp_path / "ambiguous"
    _git_init(repo)
    root = _git_commit_file(repo, "README.md", "root\n", "root")
    assert _git(repo, "checkout", "-q", "-b", "left", root).returncode == 0
    left = _git_commit_file(repo, "left.txt", "left\n", "left")
    assert _git(repo, "checkout", "-q", "-b", "right", root).returncode == 0
    right = _git_commit_file(repo, "right.txt", "right\n", "right")
    upstream_tree = _git(repo, "rev-parse", f"{right}^{{tree}}").stdout.strip()
    upstream = _commit_tree(repo, upstream_tree, (left, right), "upstream merge")
    assert _git(repo, "update-ref", "refs/remotes/origin/master", upstream).returncode == 0
    head = _commit_tree(repo, upstream_tree, (left, right), "ambiguous merge")
    with pytest.raises(StaticFenceGitError, match="BSC_E1_BASE_PARENT_AMBIGUOUS"):
        compute_pr_diff_paths(repo, head=head, upstream="origin/master")
