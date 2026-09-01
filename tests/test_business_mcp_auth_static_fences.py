from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "integrations" / "business_mcp_auth"
JWT_EDGE = "integrations/business_mcp_auth/jwt_verifier.py"
MCP_EDGE = "integrations/business_mcp_auth/mcp_adapter.py"
INTEGRATION_PROOF = "tests/test_business_mcp_auth_integration.py"
PURE_MODULES = (
    "integrations/business_mcp_auth/__init__.py",
    "integrations/business_mcp_auth/contracts.py",
    "integrations/business_mcp_auth/metadata.py",
    "integrations/business_mcp_auth/claims.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_business_auth_dependencies_are_security_pinned() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"mcp==1.28.1"' in text
    assert '"mcp==1.28.0"' not in text
    assert '"PyJWT[crypto]==2.13.0"' in text
    assert "business-mcp = [" in text


def test_security_dependencies_are_not_base_runtime_dependencies() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    base, optional = text.split("[project.optional-dependencies]", 1)
    assert "mcp==" not in base
    assert "PyJWT" not in base
    assert '"mcp==1.28.1"' in optional
    assert '"PyJWT[crypto]==2.13.0"' in optional


def test_pure_auth_modules_do_not_import_edge_or_control_plane_packages() -> None:
    for relative in PURE_MODULES:
        imports = _imports(ROOT / relative)
        assert not any(name == "jwt" or name.startswith("jwt.") for name in imports)
        assert not any(name == "mcp" or name.startswith("mcp.") for name in imports)
        assert not any(name == "httpx" or name.startswith("httpx.") for name in imports)
        assert not any(
            name == "control_plane" or name.startswith("control_plane.")
            for name in imports
        )


def test_jwt_verifier_is_the_only_pyjwt_importer_in_the_package() -> None:
    importers: list[str] = []
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        imports = _imports(path)
        if any(name == "jwt" or name.startswith("jwt.") for name in imports):
            importers.append(path.relative_to(ROOT).as_posix())
    assert importers == [JWT_EDGE]


def test_mcp_adapter_is_the_only_mcp_importer_in_the_package() -> None:
    importers: list[str] = []
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        imports = _imports(path)
        if any(name == "mcp" or name.startswith("mcp.") for name in imports):
            importers.append(path.relative_to(ROOT).as_posix())
    assert importers == [MCP_EDGE]


def test_jwt_verifier_has_a_closed_edge_dependency_surface() -> None:
    path = ROOT / JWT_EDGE
    imports = _imports(path)
    forbidden_prefixes = (
        "mcp",
        "httpx",
        "control_plane",
        "subprocess",
        "sqlite3",
        "pathlib",
        "socket",
        "requests",
        "urllib.request",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imports
        for prefix in forbidden_prefixes
    )

    source = path.read_text(encoding="utf-8")
    assert "PyJWKClient" not in source
    assert "MAX_TOKEN_BYTES = 16 * 1024" in source
    assert 'algorithm="RS256"' in source
    assert 'algorithms=["RS256"]' in source
    assert '"verify_signature": True' in source
    assert '"verify_exp": False' in source
    assert '"verify_nbf": False' in source
    assert '"verify_iat": False' in source
    assert '"verify_aud": False' in source
    assert '"verify_iss": False' in source
    for forbidden in (
        "open(",
        "write_text",
        "write_bytes",
        "sqlite",
        "create_task(",
        "urlopen(",
        "subprocess.",
        "socket.",
    ):
        assert forbidden not in source


def test_mcp_adapter_has_a_closed_sdk_only_edge_surface() -> None:
    path = ROOT / MCP_EDGE
    imports = _imports(path)
    assert "mcp.server.auth.provider" in imports
    forbidden_prefixes = (
        "jwt",
        "httpx",
        "control_plane",
        "subprocess",
        "sqlite3",
        "pathlib",
        "socket",
        "requests",
        "urllib.request",
        "fastapi",
        "starlette",
        "uvicorn",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imports
        for prefix in forbidden_prefixes
    )

    source = path.read_text(encoding="utf-8")
    assert "from mcp.server.auth.provider import AccessToken, TokenVerifier" in source
    for forbidden in (
        "Server(",
        "FastMCP",
        "list_tools",
        "call_tool",
        "Starlette",
        "Route(",
        "uvicorn",
        "open(",
        "write_text",
        "write_bytes",
        "sqlite",
        "create_task(",
        "urlopen(",
        "subprocess.",
        "socket.",
    ):
        assert forbidden not in source


def test_control_plane_does_not_import_business_auth() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "control_plane").glob("*.py")):
        if "business_mcp_auth" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_pure_package_imports_when_edge_dependencies_are_blocked() -> None:
    script = r"""
import importlib.abc
import sys

class BlockEdges(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "mcp" or fullname.startswith("mcp."):
            raise ImportError("mcp blocked")
        if fullname == "jwt" or fullname.startswith("jwt."):
            raise ImportError("jwt blocked")
        if fullname == "httpx" or fullname.startswith("httpx."):
            raise ImportError("httpx blocked")
        return None

sys.meta_path.insert(0, BlockEdges())
from integrations.business_mcp_auth import ResourcePolicy, load_resource_policy
assert ResourcePolicy is not None
assert load_resource_policy is not None
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_business_auth_pure_package_contains_no_io_or_persistence_imports() -> None:
    forbidden = {
        "asyncio",
        "http",
        "http.server",
        "pathlib",
        "socket",
        "sqlite3",
        "subprocess",
        "urllib.request",
    }
    for relative in PURE_MODULES:
        imports = _imports(ROOT / relative)
        assert imports.isdisjoint(forbidden), (relative, imports & forbidden)


def test_metadata_and_claims_sources_contain_no_runtime_or_storage_actions() -> None:
    forbidden_tokens = (
        "open(",
        "write_text",
        "write_bytes",
        "sqlite",
        "requests.",
        "httpx.",
        "urlopen(",
        "subprocess.",
        "socket.",
        "create_task(",
    )
    for relative in (
        "integrations/business_mcp_auth/metadata.py",
        "integrations/business_mcp_auth/claims.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden_tokens), relative


def test_integration_proof_has_no_runtime_server_or_backend_dependency() -> None:
    path = ROOT / INTEGRATION_PROOF
    imports = _imports(path)
    forbidden_prefixes = (
        "app",
        "bot",
        "brain",
        "bridge",
        "control_plane",
        "fastapi",
        "starlette",
        "uvicorn",
        "subprocess",
        "sqlite3",
        "socket",
        "requests",
        "urllib.request",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imports
        for prefix in forbidden_prefixes
    )

    source = path.read_text(encoding="utf-8")
    for forbidden in (
        "FastMCP",
        "Server(",
        "Route(",
        "call_tool",
        "list_tools",
        "RuntimeBinding",
        "ExecutiveJob",
    ):
        assert forbidden not in source


def test_business_auth_tests_contain_no_serialized_credentials() -> None:
    markers = (
        "BEGIN " + "PRIVATE KEY",
        "xoxb" + "-",
        "ghp" + "_",
        "sk" + "-",
        "client_" + "secret=",
        "access_" + "token=",
        "refresh_" + "token=",
    )
    this_file = Path(__file__).resolve()
    for path in sorted((ROOT / "tests").glob("test_business_mcp_auth_*.py")):
        if path.resolve() == this_file:
            continue
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in markers), path
