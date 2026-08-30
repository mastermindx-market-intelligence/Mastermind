from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PURE_MODULES = (
    "integrations/business_mcp_auth/__init__.py",
    "integrations/business_mcp_auth/contracts.py",
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


def test_control_plane_does_not_import_business_auth() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "control_plane").glob("*.py")):
        if "business_mcp_auth" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_pure_package_imports_when_edge_dependencies_are_blocked() -> None:
    script = r'''
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
'''
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
