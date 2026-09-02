from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "integrations" / "mastermind_steward_app"
LAUNCHER = ROOT / "scripts" / "mastermind_steward_app.py"
RUNBOOK = ROOT / "docs" / "runbooks" / "mastermind-steward-app.md"


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


def test_authenticated_app_accepts_only_exact_protected_a1_verifier_type():
    text = (PACKAGE / "app.py").read_text(encoding="utf-8")
    assert (
        "from integrations.business_mcp_auth.mcp_adapter import "
        "MastermindTokenVerifier"
    ) in text
    assert "type(token_verifier) is not MastermindTokenVerifier" in text
    assert "token_verifier: MastermindTokenVerifier" in text
    assert "from mcp.server.auth.provider import TokenVerifier" not in text


def test_authenticated_app_has_no_operator_host_authority_widening_seam():
    text = (PACKAGE / "app.py").read_text(encoding="utf-8")
    assert "extra_allowed_hosts" not in text
    assert "def _allowed_hosts(policy: ResourcePolicy)" in text
    assert "resource_host = urlsplit(policy.resource).netloc" in text


def test_launcher_and_runbook_preserve_policy_resource_host_as_only_public_host():
    launcher = LAUNCHER.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    forbidden = (
        "--extra-allowed-hosts",
        "MASTERMIND_STEWARD_ALLOWED_HOSTS",
        "extra_allowed_hosts=",
    )
    for token in forbidden:
        assert token not in launcher
        assert token not in runbook
    assert "preserve the exact Host authority from `policy.resource`" in runbook


def test_transport_and_auth_gates_share_one_optional_raw_path_normalizer():
    text = (PACKAGE / "app.py").read_text(encoding="utf-8")

    assert "def _canonical_raw_path(scope: Scope) -> bytes:" in text
    assert text.count("_canonical_raw_path(scope)") == 2
    assert 'scope.get("raw_path") != self.resource' not in text

def _load_canonical_raw_path():
    text = (PACKAGE / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(PACKAGE / "app.py"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_canonical_raw_path"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {"Scope": dict}
    exec(compile(ast.fix_missing_locations(module), str(PACKAGE / "app.py"), "exec"), namespace)
    return namespace["_canonical_raw_path"]


def test_canonical_path_requires_exact_decoded_and_raw_asgi_paths():
    normalize = _load_canonical_raw_path()
    canonical = "/mcp/steward/v1"
    raw = canonical.encode("ascii")

    assert normalize({"path": canonical, "raw_path": raw}) == raw
    assert normalize({"path": canonical}) == b""
    assert normalize({"path": canonical, "raw_path": b"/mcp%2Fsteward%2Fv1"}) == b""
    assert normalize({"path": canonical + "/", "raw_path": raw}) == b""

