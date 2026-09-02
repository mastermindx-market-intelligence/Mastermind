"""BSC-E1 static fences — the invariants a runtime test cannot see.

These tests inspect SOURCE, not behavior: the app package must never import
the general Executive control socket module, the MCP SDK, or call the
in-process mutation sink, no matter how its runtime behavior is composed.
They also preserve the original BSC-E1 "did this PR touch something it must
not have" assertions. Those three branch-delta assertions apply only while
the computed merge base predates the Executive app release. Once the app is
already protected in the merge base, applying PR #363's fixed 11-path delta
to an unrelated later PR would be false; the historical assertions skip,
while every enduring source, AST, import and schema fence remains active.
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
_BSC_E1_RELEASE_SENTINEL = "integrations/mastermind_executive_app/app.py"


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
    forbidden = {m for m in imported if m == "control_plane.executive_service" or m.startswith("control_plane.executive_service.")}
    assert not forbidden, f"{path.name} imports forbidden module(s): {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_imports_mcp_sdk(path: Path):
    """The MCP SDK stays isolated to integrations/executive_mcp/server.py
    and integrations/business_mcp_auth/mcp_adapter.py (neither of which this
    app imports) -- this app is a plain HTTP edge, never an MCP transport
    process, and never needs the SDK at all."""

    imported = _imported_module_names(path)
    forbidden = {m for m in imported if m == "mcp" or m.startswith("mcp.")}
    assert not forbidden, f"{path.name} imports the MCP SDK: {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_imports_executive_mcp_server_module(path: Path):
    """Only the read-composition surface (adapter/schemas) is reused; the
    MCP-SDK-importing server.py module is never pulled in transitively by
    name here (it would be a clear signal this app tried to BE an MCP
    transport rather than a plain authenticated HTTP edge)."""

    imported = _imported_module_names(path)
    forbidden = {m for m in imported if m == "integrations.executive_mcp.server"}
    assert not forbidden, f"{path.name} imports {forbidden}"


@pytest.mark.parametrize("path", ALL_OWNED_MODULES, ids=lambda p: p.name)
def test_never_imports_ceo_intent_module_directly(path: Path):
    """``control_plane.ceo_intent`` (the one v1 mutation-authority sink) is
    never imported by this app at all -- the only legal way this app can
    have any admission effect is a bounded frame sent over the dedicated
    CeoIngress socket, never an in-process call into that sink."""

    imported = _imported_module_names(path)
    forbidden = {m for m in imported if m == "control_plane.ceo_intent" or m.startswith("control_plane.ceo_intent.")}
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


# ---------------------------------------------------------------------------
# Enduring schema pin plus historical BSC-E1 commission-scope evidence
# ---------------------------------------------------------------------------


def test_schema_digest_unchanged():
    """The Executive MCP tool/schema surface is byte-identical to the frozen
    literal named in the FROZEN SPEC."""

    assert mcp_schemas.schema_snapshot_sha256() == (
        "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    )


def _rev_parse_quiet(ref: str) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", "--quiet", ref],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return probe.returncode == 0


def _merge_base_with_master() -> str:
    """Resolve the candidate branch's base commit against ``master``.

    CI checks out pull-request merge refs with ``fetch-depth: 0``, so
    ``origin/master`` is normally available. A local development checkout
    gets one existing last-resort fetch before failing closed.
    """

    for ref in ("origin/master", "master"):
        if _rev_parse_quiet(ref):
            result = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "merge-base", ref, "HEAD"],
                check=True, stdout=subprocess.PIPE, text=True,
            )
            return result.stdout.strip()

    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "fetch", "--quiet", "origin", "master"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if _rev_parse_quiet("origin/master"):
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "merge-base", "origin/master", "HEAD"],
            check=True, stdout=subprocess.PIPE, text=True,
        )
        return result.stdout.strip()
    raise RuntimeError("cannot resolve a merge-base against master")


def _skip_historical_bsc_e1_scope_if_released(base: str) -> None:
    """Deactivate PR #363's branch-delta assertions after its release.

    The three callers below prove the original BSC-E1 commission's exact
    candidate delta. They remain discriminating when the merge base predates
    BSC-E1. Once the released app sentinel already exists at ``base``, that
    historical delta belongs to the base rather than the current PR, so
    evaluating it against ``base..HEAD`` would reject every unrelated change.
    A missing/unresolvable sentinel does not skip and therefore fails closed
    through the original assertions.
    """

    if _rev_parse_quiet(f"{base}:{_BSC_E1_RELEASE_SENTINEL}"):
        pytest.skip(
            "historical BSC-E1 PR-scope assertion: Executive app is already "
            "released in the merge base"
        )


def test_executive_service_file_has_zero_diff_against_base():
    """For an unreleased BSC-E1 candidate, executive_service.py is unchanged."""

    base = _merge_base_with_master()
    _skip_historical_bsc_e1_scope_if_released(base)
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--stat", base, "HEAD", "--", "control_plane/executive_service.py"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert result.stdout.strip() == ""


def test_ceo_request_change_is_the_only_control_plane_diff():
    """For an unreleased BSC-E1 candidate, ceo_request.py is its sole control-plane diff."""

    base = _merge_base_with_master()
    _skip_historical_bsc_e1_scope_if_released(base)
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", base, "HEAD", "--", "control_plane/"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    assert changed == ["control_plane/ceo_request.py"], changed


def test_ten_ceiling_paths_are_exactly_the_new_files_this_pr_adds():
    """For an unreleased BSC-E1 candidate, enforce its exact 11-path ceiling."""

    base = _merge_base_with_master()
    _skip_historical_bsc_e1_scope_if_released(base)
    added = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", "--diff-filter=A", base, "HEAD"],
        check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.splitlines()
    everything = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", base, "HEAD"],
        check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.splitlines()

    added_paths = {line.strip() for line in added if line.strip()}
    all_changed_paths = {line.strip() for line in everything if line.strip()}

    ten_ceiling_paths = {
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
    eleven_authorized_paths = ten_ceiling_paths | {"control_plane/ceo_request.py"}

    assert added_paths == ten_ceiling_paths, added_paths
    assert all_changed_paths == eleven_authorized_paths, all_changed_paths
