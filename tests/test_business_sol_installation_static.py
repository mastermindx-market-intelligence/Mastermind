from __future__ import annotations

import ast
from pathlib import Path

from integrations.business_sol_installation import ERROR_CODES, GENERATED_FILE

ROOT = Path(__file__).resolve().parents[1]
BINDINGS = ROOT / "integrations/business_sol_installation/bindings.py"
CLI = ROOT / "scripts/mastermind_business_installation.py"
RUNBOOK = ROOT / "docs/runbooks/business-sol-installation-enrollment.md"
PLAN = ROOT / "docs/superpowers/plans/2026-08-31-business-sol-installation-enrollment.md"

EXPECTED_PATHS = {
    "integrations/business_sol_installation/__init__.py",
    "integrations/business_sol_installation/bindings.py",
    "scripts/mastermind_business_installation.py",
    "tests/test_business_sol_installation.py",
    "tests/test_business_sol_installation_adversarial.py",
    "tests/test_business_sol_installation_static.py",
    "docs/runbooks/business-sol-installation-enrollment.md",
    "docs/superpowers/plans/2026-08-31-business-sol-installation-enrollment.md",
}

FORBIDDEN_IMPORT_ROOTS = {
    "requests",
    "httpx",
    "urllib",
    "socket",
    "subprocess",
    "selenium",
    "playwright",
    "mcp",
    "control_plane",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "integrations.executive_mcp",
    "integrations.mastermind_secretary_mcp",
    "integrations.mastermind_executive_app",
)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_exact_u1_source_inventory_exists() -> None:
    assert {path for path in EXPECTED_PATHS if not (ROOT / path).is_file()} == set()
    plugin_root = ROOT / "plugins"
    if plugin_root.exists():
        assert not list(plugin_root.rglob(GENERATED_FILE))


def test_compiler_and_cli_do_not_import_network_browser_or_runtime_owners() -> None:
    for path in (BINDINGS, CLI):
        imports = imported_modules(path)
        assert not {name for name in imports if name.split(".", 1)[0] in FORBIDDEN_IMPORT_ROOTS}
        assert not {name for name in imports if name.startswith(FORBIDDEN_IMPORT_PREFIXES)}


def test_contract_has_fixed_error_vocabulary_and_no_secret_payload_error() -> None:
    assert {
        "SECRET_SHAPED_INPUT",
        "PREFLIGHT_HELD",
        "OUTPUT_SYMLINK_REFUSED",
        "STAGE_EFFECT_UNKNOWN",
        "ROLLBACK_EFFECT_UNKNOWN",
    }.issubset(ERROR_CODES)
    source = BINDINGS.read_text(encoding="utf-8")
    assert "raise InstallationContractError(" in source
    assert "raise RuntimeError(" not in source
    assert "raise ValueError(" not in source


def test_docs_freeze_private_artifact_and_real_ceremony_boundaries() -> None:
    combined = RUNBOOK.read_text(encoding="utf-8") + "\n" + PLAN.read_text(encoding="utf-8")
    for marker in (
        "Mastermind-private",
        "native app-reference format",
        "PREFLIGHT_HELD",
        "Secure MCP Tunnel",
        "source proof",
        "app publication",
        "endpoint reachability",
        "OAuth",
        "user installation",
        "successful read",
        "write admission",
        "production acceptance",
        "rollback",
        "Mastermind Steward",
        "Mastermind Executive",
    ):
        assert marker in combined


def test_no_live_workspace_identity_is_committed_in_u1_source() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (BINDINGS, CLI, RUNBOOK, PLAN)
    )
    assert "Plugin_773910451848819182e7291ad2431390" not in combined
    assert "plugin_asdk_app_6a967e92f93081919fa9bc55b7df839e" not in combined
    # Secret-prefix strings may appear only in the input-refusal regex; no concrete
    # credential-shaped value or private-key body may be committed.
    assert "xoxb-live-credential" not in combined
    assert "github_pat_live_credential" not in combined
    assert "-----BEGIN PRIVATE KEY-----" not in combined
