"""Persistent BSC-E1 static fences.

Current-tree tests protect the authenticated Executive app's source boundaries.
Historical scope tests inspect the immutable protected BSC-E1 squash commit,
not the merge-base of whichever unrelated pull request happens to run CI.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from integrations.executive_mcp import schemas as mcp_schemas

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PACKAGE_FILES = [
    REPO_ROOT / "integrations" / "mastermind_executive_app" / "__init__.py",
    REPO_ROOT / "integrations" / "mastermind_executive_app" / "app.py",
    REPO_ROOT / "integrations" / "mastermind_executive_app" / "gateway.py",
    REPO_ROOT / "integrations" / "mastermind_executive_app" / "admission.py",
]
ENTRYPOINT_SCRIPT = REPO_ROOT / "scripts" / "mastermind_executive_app.py"
ALL_OWNED_MODULES = APP_PACKAGE_FILES + [ENTRYPOINT_SCRIPT]

BSC_E1_BASE_SHA = "162af533a4bcf380125895d225b6962987c3c582"
BSC_E1_PROTECTED_SHA = "24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8"
TEN_CEILING_PATHS = {
    "integrations/mastermind_executive_app/__init__.py",
    "integrations/mastermind_executive_app/app.py",
    "integrations/mastermind_executive_app/gateway.py",
    "integrations/mastermind_executive_app/admission.py",
    "scripts/mastermind_executive_app.py",
    "config/business_mcp/executive_policy.example.json",
    "tests/test_mastermind_executive_app_asgi.py",
    "tests/test_mastermind_executive_app_admission.py",
    "tests/test_mastermind_executive_app_static_fences.py",
    "docs/runbooks/mastermind-executive-app.md",
}
ELEVEN_AUTHORIZED_PATHS = TEN_CEILING_PATHS | {"control_plane/ceo_request.py"}


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def _require_historical_range() -> None:
    for sha in (BSC_E1_BASE_SHA, BSC_E1_PROTECTED_SHA):
        probe = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{sha}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode != 0:
            raise RuntimeError(
                "BSC-E1 historical scope proof requires a full repository "
                f"history containing {sha}; CI checkout must use fetch-depth: 0"
            )


def _historical_paths(*options: str, pathspec: tuple[str, ...] = ()) -> set[str]:
    _require_historical_range()
    args = [
        "diff",
        "--name-only",
        *options,
        BSC_E1_BASE_SHA,
        BSC_E1_PROTECTED_SHA,
    ]
    if pathspec:
        args.extend(("--", *pathspec))
    output = _git(*args)
    return {line.strip() for line in output.splitlines() if line.strip()}


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_imports_executive_service(path: Path):
    imported = _imported_module_names(path)
    forbidden = {
        module
        for module in imported
        if module == "control_plane.executive_service"
        or module.startswith("control_plane.executive_service.")
    }
    assert not forbidden, f"{path.name} imports forbidden module(s): {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_imports_mcp_sdk(path: Path):
    imported = _imported_module_names(path)
    forbidden = {
        module for module in imported if module == "mcp" or module.startswith("mcp.")
    }
    assert not forbidden, f"{path.name} imports the MCP SDK: {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_imports_executive_mcp_server_module(path: Path):
    imported = _imported_module_names(path)
    assert "integrations.executive_mcp.server" not in imported, path.name


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_imports_ceo_intent_module_directly(path: Path):
    imported = _imported_module_names(path)
    forbidden = {
        module
        for module in imported
        if module == "control_plane.ceo_intent"
        or module.startswith("control_plane.ceo_intent.")
    }
    assert not forbidden, f"{path.name} imports control_plane.ceo_intent: {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_references_send_control_request(path: Path):
    assert "send_control_request" not in path.read_text(encoding="utf-8"), path.name


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda path: path.name)
def test_never_calls_submit_intent_by_name(path: Path):
    assert "submit_intent(" not in path.read_text(encoding="utf-8"), path.name


@pytest.mark.parametrize("path", APP_PACKAGE_FILES, ids=lambda path: path.name)
def test_app_package_never_imports_subprocess_or_uses_dynamic_execution(path: Path):
    imported = _imported_module_names(path)
    assert "subprocess" not in imported, path.name
    source = path.read_text(encoding="utf-8")
    assert "os.system(" not in source, path.name
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"eval", "exec"}, f"{path.name} calls {node.func.id}()"


def test_admission_never_widens_the_five_tool_privileged_field_list():
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


def test_schema_digest_unchanged():
    assert mcp_schemas.schema_snapshot_sha256() == (
        "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    )


def test_historical_scope_range_is_the_protected_bsc_e1_commit():
    _require_historical_range()
    assert _git("rev-parse", f"{BSC_E1_PROTECTED_SHA}^").strip() == BSC_E1_BASE_SHA


def test_executive_service_file_has_zero_diff_in_bsc_e1():
    _require_historical_range()
    output = _git(
        "diff",
        "--stat",
        BSC_E1_BASE_SHA,
        BSC_E1_PROTECTED_SHA,
        "--",
        "control_plane/executive_service.py",
    )
    assert output.strip() == ""


def test_ceo_request_is_the_only_bsc_e1_control_plane_diff():
    assert _historical_paths(pathspec=("control_plane/",)) == {"control_plane/ceo_request.py"}


def test_bsc_e1_added_and_total_path_ceiling_is_immutable():
    assert _historical_paths("--diff-filter=A") == TEN_CEILING_PATHS
    assert _historical_paths() == ELEVEN_AUTHORIZED_PATHS
