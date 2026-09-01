from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "integrations" / "mastermind_steward_app"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_projection_is_sdk_network_persistence_and_control_plane_free():
    imports = _imports(PACKAGE / "projection.py")
    forbidden = (
        "mcp",
        "starlette",
        "fastapi",
        "uvicorn",
        "httpx",
        "jwt",
        "sqlite3",
        "psycopg",
        "subprocess",
        "socket",
        "control_plane",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imports
        for prefix in forbidden
    )


def test_only_server_and_app_import_mcp_sdk():
    offenders = []
    for path in PACKAGE.glob("*.py"):
        imports = _imports(path)
        if any(name == "mcp" or name.startswith("mcp.") for name in imports):
            if path.name not in {"server.py", "app.py"}:
                offenders.append(path.name)
    assert offenders == []


def test_package_has_no_state_store_or_write_adapter():
    forbidden_tokens = (
        "sqlite3",
        "create_job(",
        "submit_intent(",
        "write_text(",
        "write_bytes(",
        "open(\"w",
        "open('w",
        "psycopg",
        "runtime.at(",
    )
    offenders = []
    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden_tokens:
            if token in text:
                offenders.append((path.name, token))
    assert offenders == []


def test_authenticated_http_stack_has_one_dispatch_and_a1_owns_challenges():
    text = (PACKAGE / "app.py").read_text(encoding="utf-8")

    assert "RequireAuthMiddleware" not in text
    assert "mcp_auth_error_result" in text
    assert "www_authenticate" in text
    assert "BearerAuthBackend" in text
    assert "AuthContextMiddleware" in text
    assert text.count("StreamableHTTPSessionManager(") == 1
    assert text.count("manager.handle_request") == 1
    assert "Mount(" not in text
    assert "RedirectResponse" not in text

    # Starlette evaluates user middleware outermost-first in declaration order:
    # transport refusal must happen before bearer verification.
    transport = text.index("Middleware(_StewardTransportGuard")
    authentication = text.index("Middleware(\n            AuthenticationMiddleware")
    auth_context = text.index("Middleware(AuthContextMiddleware")
    assert transport < authentication < auth_context


def test_transport_guard_has_closed_pre_auth_boundary_vocabulary():
    text = (PACKAGE / "app.py").read_text(encoding="utf-8")
    required = (
        "MAX_REQUEST_BODY_BYTES",
        "_StewardTransportGuard",
        "_A1AuthGate",
        "scope.get(\"raw_path\")",
        "scope.get(\"root_path\")",
        "scope.get(\"query_string\")",
        "application/json",
        "authorization",
        "origin",
        "host",
        "421",
        "413",
        "415",
        "insufficient_scope",
    )
    for token in required:
        assert token in text
