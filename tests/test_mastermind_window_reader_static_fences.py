from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_control_plane_does_not_reference_window_reader() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "control_plane").glob("*.py")):
        if "mastermind_window_reader" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


# Exact importer -> module exceptions. Each entry is a single importer path mapped to the
# only Reader modules that importer may name; there is no package-wide or wildcard allowance.
EXTERNAL_IMPORTER_EXCEPTIONS: dict[str, frozenset[str]] = {
    "integrations/mastermind_steward_app/installed.py": frozenset(
        {
            "integrations.mastermind_window_reader.production_binding",
            "integrations.mastermind_window_reader.owner_read_resource",
        }
    ),
    "integrations/mastermind_steward_app/live_window.py": frozenset(
        {"integrations.mastermind_window_reader.owner_read_resource"}
    ),
    "tests/test_mastermind_steward_app_live_window.py": frozenset(
        {"integrations.mastermind_window_reader.owner_read_resource"}
    ),
    "tests/test_steward_installed_content.py": frozenset(
        {"integrations.mastermind_window_reader.owner_read_resource"}
    ),
}


def test_window_reader_modules_have_only_package_and_test_importers() -> None:
    modules = {
        "integrations.mastermind_window_reader.live_window_read",
        "integrations.mastermind_window_reader.production_binding",
        "integrations.mastermind_window_reader.owner_read_resource",
    }
    offenders: list[str] = []
    candidate_paths = [path for path in ROOT.rglob("*.py") if path != Path(__file__)]
    allowed_roots = (
        ROOT / "integrations" / "mastermind_window_reader",
        ROOT / "tests" / "mastermind_window_reader",
    )
    for path in candidate_paths:
        imported_modules = sorted(modules.intersection(_imports(path)))
        if not imported_modules:
            continue
        if any(path.is_relative_to(root) for root in allowed_roots):
            continue
        relative = path.relative_to(ROOT).as_posix()
        permitted = EXTERNAL_IMPORTER_EXCEPTIONS.get(relative, frozenset())
        for name in imported_modules:
            if name not in permitted:
                offenders.append(f"{relative} -> {name}")
    assert sorted(offenders) == []


def test_window_reader_package_never_imports_steward_app() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "integrations" / "mastermind_window_reader").glob("*.py")):
        if "integrations.mastermind_steward_app" in _imports(path):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
