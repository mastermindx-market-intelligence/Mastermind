"""BSC-E1 static fences — the invariants a runtime test cannot see.

These tests inspect SOURCE, not behavior: the app package must never import
the general Executive control socket module, the MCP SDK, or call the
in-process mutation sink, no matter how its runtime behavior is composed.
They also pin the exact protected BSC-E1 release payload.  Release-scope
assertions are evaluated against the immutable protected release commit and
its exact parent; they never reinterpret whichever unrelated pull request is
currently running the repository suite as the historical BSC-E1 carrier.
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

BSC_E1_RELEASE_BASE = "162af533a4bcf380125895d225b6962987c3c582"
BSC_E1_RELEASE_COMMIT = "24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8"
BSC_E1_ADDED_PATHS = frozenset(
    {
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
)
BSC_E1_CHANGED_PATHS = BSC_E1_ADDED_PATHS | {
    "control_plane/ceo_request.py"
}


def _imported_module_names(path: Path) -> set[str]:
    """Every dotted module name this file imports, via ``import`` or
    ``from ... import``, at ANY nesting (module-level or inside a
    function) -- so a lazily-imported forbidden dependency cannot hide."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_imports_executive_service(path: Path):
    """OUT OF SCOPE law: the general Executive control socket module is
    never imported by this app -- there is no in-process/general-socket
    admission path to accidentally wire up."""

    imported = _imported_module_names(path)
    forbidden = {
        module
        for module in imported
        if module == "control_plane.executive_service"
        or module.startswith("control_plane.executive_service.")
    }
    assert not forbidden, f"{path.name} imports forbidden module(s): {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_imports_mcp_sdk(path: Path):
    """The MCP SDK stays isolated to integrations/executive_mcp/server.py
    and integrations/business_mcp_auth/mcp_adapter.py (neither of which this
    app imports) -- this app is a plain HTTP edge, never an MCP transport
    process, and never needs the SDK at all."""

    imported = _imported_module_names(path)
    forbidden = {module for module in imported if module == "mcp" or module.startswith("mcp.")}
    assert not forbidden, f"{path.name} imports the MCP SDK: {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_imports_executive_mcp_server_module(path: Path):
    """Only the read-composition surface (adapter/schemas) is reused; the
    MCP-SDK-importing server.py module is never pulled in transitively by
    name here (it would be a clear signal this app tried to BE an MCP
    transport rather than a plain authenticated HTTP edge)."""

    imported = _imported_module_names(path)
    forbidden = {module for module in imported if module == "integrations.executive_mcp.server"}
    assert not forbidden, f"{path.name} imports {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_imports_ceo_intent_module_directly(path: Path):
    """``control_plane.ceo_intent`` (the one v1 mutation-authority sink) is
    never imported by this app at all -- the only legal way this app can
    have any admission effect is a bounded frame sent over the dedicated
    CeoIngress socket, never an in-process call into that sink."""

    imported = _imported_module_names(path)
    forbidden = {
        module
        for module in imported
        if module == "control_plane.ceo_intent"
        or module.startswith("control_plane.ceo_intent.")
    }
    assert not forbidden, f"{path.name} imports control_plane.ceo_intent directly: {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_references_send_control_request(path: Path):
    """``send_control_request`` is the general Executive control socket
    transport used by ``integrations.executive_mcp.adapter``'s OWN
    ``submit_ceo_intent`` path -- this app must never reference it by name,
    directly or via a rebinding alias."""

    source = path.read_text(encoding="utf-8")
    assert "send_control_request" not in source, path.name


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_calls_submit_intent_by_name(path: Path):
    """``.submit_intent(`` (the one v1 mutation sink's call site) never
    appears in this app's source -- reinforces the import-level fence above
    against a hypothetical ``from control_plane import ceo_intent as x``
    aliasing trick, which the import check alone would still catch, but this
    is a second, independent, name-based fence."""

    source = path.read_text(encoding="utf-8")
    assert "submit_intent(" not in source, path.name


@pytest.mark.parametrize("path", APP_PACKAGE_FILES, ids=lambda p: p.name)
def test_app_package_never_imports_subprocess_or_uses_dynamic_execution(path: Path):
    """The app package (excluding the CLI entrypoint script, which is
    permitted ordinary process bootstrap) never shells out and never
    dynamically executes code -- its only I/O is HTTP-in, one AF_UNIX
    socket, and read-only git plumbing via ceo_boot_packet."""

    imported = _imported_module_names(path)
    assert "subprocess" not in imported, path.name
    source = path.read_text(encoding="utf-8")
    assert "os.system(" not in source, path.name
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("eval", "exec"), f"{path.name} calls {node.func.id}()"


def test_admission_never_widens_the_five_tool_privileged_field_list():
    """Every name the FROZEN SPEC lists as caller-unsuppliable is either
    outside the reused five-tool JSON schema's ``properties`` (structurally
    impossible) or explicitly enforced -- this pins the CURRENT schema's
    property set so a future schema change that silently added one of these
    names would fail this test rather than fail silently."""

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


# --------------------------------------------------------------------------

# Immutable BSC-E1 release pins
# ---------------------------------------------------------------------------


def test_schema_digest_unchanged():
    """The Executive MCP tool/schema surface remains byte-identical to the
    frozen literal named in the BSC-E1 source law."""

    assert mcp_schemas.schema_snapshot_sha256() == (
        "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    )


def _git_stdout(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _require_bsc_e1_release_history() -> None:
    for commit in (BSC_E1_RELEASE_BASE, BSC_E1_RELEASE_COMMIT):
        probe = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "cat-file",
                "-e",
                f"{commit}^{{commit}}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert probe.returncode == 0, (
            "immutable BSC-E1 release history is unavailable: " + commit
        )
    assert _git_stdout("rev-parse", f"{BSC_E1_RELEASE_COMMIT}^") == BSC_E1_RELEASE_BASE


def _bsc_e1_release_paths(
    *,
    diff_filter: str | None = None,
    pathspec: tuple[str, ...] = (),
) -> set[str]:
    """Read only the immutable protected BSC-E1 release delta.

    This deliberately never consults ``HEAD``, a moving branch, or the merge
    base of whichever later pull request happens to run the repository suite.
    """

    _require_bsc_e1_release_history()
    args = ["diff", "--name-only"]
    if diff_filter is not None:
        args.append(f"--diff-filter={diff_filter}")
    args.extend((BSC_E1_RELEASE_BASE, BSC_E1_RELEASE_COMMIT))
    if pathspec:
        args.extend(("--", *pathspec))
    return {
        line.strip()
        for line in _git_stdout(*args).splitlines()
        if line.strip()
    }


def test_bsc_e1_scope_fence_is_bound_to_the_protected_release_commit():
    _require_bsc_e1_release_history()


def test_bsc_e1_release_did_not_modify_executive_service():
    assert _bsc_e1_release_paths(
        pathspec=("control_plane/executive_service.py",)
    ) == set()


def test_bsc_e1_release_ceo_request_is_the_only_control_plane_delta():
    assert _bsc_e1_release_paths(pathspec=("control_plane/",)) == {
        "control_plane/ceo_request.py"
    }


def test_bsc_e1_release_added_and_changed_paths_are_exact():
    assert _bsc_e1_release_paths(diff_filter="A") == set(BSC_E1_ADDED_PATHS)
    assert _bsc_e1_release_paths() == set(BSC_E1_CHANGED_PATHS)
