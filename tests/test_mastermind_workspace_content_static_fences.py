from __future__ import annotations

import ast
from pathlib import Path

from integrations.mastermind_steward_app.server import REQUIRED_SCOPE
from integrations.mastermind_workspace_content.business import CONTENT_SCOPE

ROOT = Path(__file__).parents[1] / "integrations" / "mastermind_workspace_content"


def test_package_has_no_process_network_or_filesystem_runtime_imports() -> None:
    forbidden = {"os", "pathlib", "socket", "subprocess", "urllib.request"}
    observed: set[str] = set()
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                observed.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                observed.add(node.module)
    assert not (observed & forbidden)


def test_workspace_content_scope_is_not_steward_grounding_scope() -> None:
    assert CONTENT_SCOPE == "mastermind.workspace.content.read"
    assert CONTENT_SCOPE != REQUIRED_SCOPE


def test_package_contains_no_second_lifecycle_or_provider_adapter() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.glob("*.py"))
    for forbidden in (
        "create_subprocess",
        "Popen(",
        "sqlite3",
        "WebSocket",
        "start_provider",
        "resume_provider",
    ):
        assert forbidden not in text


def test_package_init_does_not_eagerly_import_optional_auth_or_web_dependencies() -> None:
    tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in tree.body)
