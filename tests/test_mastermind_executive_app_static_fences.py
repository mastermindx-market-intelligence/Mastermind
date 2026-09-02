"""BSC-E1 durable static fences for the authenticated Executive app.

These tests inspect source-level ownership and authority boundaries that runtime
behavior alone cannot prove. They intentionally avoid current-branch or
merge-base diffs: a repository-global protected test must remain valid on every
unrelated future pull request while still killing an app-side authority bypass.
"""
from __future__ import annotations

import ast
from pathlib import Path

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
