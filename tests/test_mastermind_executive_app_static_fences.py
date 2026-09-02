"""BSC-E1 durable static fences for the authenticated Executive app.

These tests inspect source-level ownership and authority boundaries that runtime
behavior alone cannot prove. They intentionally avoid current-branch or
merge-base diffs: a repository-global protected test must remain valid on every
unrelated future pull request while still killing an app-side authority bypass.
"""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess

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


def _imported_module_names(path: Path) -> set[str]:
    """Return every dotted module imported at any nesting level."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
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
    actual_app_source = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_PACKAGE.glob("*.py")
        if path.is_file()
    }
    assert actual_app_source == EXPECTED_APP_SOURCE_SURFACE
    for relative in EXPECTED_SUPPORT_PATHS:
        assert (REPO_ROOT / relative).is_file(), relative


def test_static_fences_do_not_depend_on_git_history_or_current_pr_diff() -> None:
    imported = _imported_module_names(Path(__file__))
    assert imported.isdisjoint({"subprocess", "git", "pygit2"})


# ---------------------------------------------------------------------------
# RED-first discriminators for the composable PR-local ratchet repair.
# These intentionally describe the desired API before its implementation.
# ---------------------------------------------------------------------------


def _required_callable(name: str):
    value = globals().get(name)
    assert callable(value), f"missing required static-fence helper: {name}"
    return value


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

    python_source_surface = _required_callable("_python_source_surface")
    surface = python_source_surface(package, root=tmp_path)

    assert surface == {
        "integrations/mastermind_executive_app/__init__.py",
        "integrations/mastermind_executive_app/subpackage/hidden_ingress.py",
    }


def _unexpected_paths(changed: set[str]):
    classifier = _required_callable("_bsc_e1_unexpected_paths")
    return classifier(changed)


def test_bsc_e1_delta_empty_is_not_applicable() -> None:
    assert _unexpected_paths(set()) is None


def test_bsc_e1_delta_foreign_only_c1_shape_is_not_applicable() -> None:
    assert _unexpected_paths(
        {
            "control_plane/chairman_control_room.py",
            "control_plane/executive_placement_selection.py",
            "scripts/chairman_control_room.py",
            "tests/test_chairman_control_room.py",
            "tests/test_executive_placement_selection.py",
        }
    ) is None


def test_bsc_e1_delta_allowed_subset_applies_and_passes() -> None:
    assert _unexpected_paths(
        {
            "integrations/mastermind_executive_app/app.py",
            "tests/test_mastermind_executive_app_static_fences.py",
            "control_plane/ceo_request.py",
        }
    ) == set()


def test_bsc_e1_delta_owned_plus_foreign_refuses_foreign_path() -> None:
    assert _unexpected_paths(
        {
            "integrations/mastermind_executive_app/app.py",
            "docs/unrelated_foreign.md",
        }
    ) == {"docs/unrelated_foreign.md"}


def test_bsc_e1_delta_owned_plus_executive_service_refuses_service() -> None:
    assert _unexpected_paths(
        {
            "integrations/mastermind_executive_app/app.py",
            "control_plane/executive_service.py",
        }
    ) == {"control_plane/executive_service.py"}


def test_bsc_e1_delta_new_unratcheted_app_module_is_refused() -> None:
    path = "integrations/mastermind_executive_app/hidden_ingress.py"
    assert _unexpected_paths({path}) == {path}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=30,
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

    compute = _required_callable("compute_pr_diff_paths")

    assert compute(repo, head="HEAD", upstream="origin/master") == {
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

    compute = _required_callable("compute_pr_diff_paths")
    changed = compute(repo, head=head, upstream="origin/master")

    assert changed == {"integrations/mastermind_executive_app/app.py"}
    assert "docs/base_movement.md" not in changed
