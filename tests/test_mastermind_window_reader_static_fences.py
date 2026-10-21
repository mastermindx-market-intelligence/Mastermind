from __future__ import annotations

import ast
from pathlib import Path
from textwrap import dedent

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    pending: list[ast.AST] = [tree]
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        # Imports are statements: an expression subtree cannot contain one.
        # Keep every other container (including except handlers and match cases)
        # rather than hardcoding compound-statement names. Full parsing above
        # still rejects malformed or unreadable source, even with no imports.
        pending.extend(
            child for child in ast.iter_child_nodes(node)
            if not isinstance(child, ast.expr)
        )
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


@pytest.mark.parametrize("source", [
    "import alpha, beta as b\nfrom pkg.child import value\n",
    "from . import sibling\nfrom ..parent import value\n",
    "if False:\n    import unreachable\nelse:\n    from fallback import value\n",
    "class C:\n    import class_scope\n    def f(self):\n        import nested\n",
    "for value in []:\n    import loop_body\nelse:\n    import loop_else\n",
    "while False:\n    import while_body\nelse:\n    import while_else\n",
    "with context():\n    from with_body import value\n",
    "async def f():\n    async with context():\n        import async_with\n    async for value in items:\n        import async_for\n    else:\n        import async_else\n",
    "try:\n    import try_body\nexcept Exception:\n    import handler\nelse:\n    import try_else\nfinally:\n    import cleanup\n",
    "try:\n    import grouped_body\nexcept* Exception:\n    import grouped_handler\n",
    "match subject:\n    case 1:\n        import first_case\n    case _:\n        from other_case import value\n",
    "import ｍodule\n",
    "# import comment_only\ntext = 'import string_only'\nf = lambda: __import__('dynamic')\n",
    "@decorator()\ndef f(value: annotation = factory()):\n    import decorated_body\n",
    "type Alias[T] = list[T]\nimport after_type_alias\n",
])
def test_import_scan_matches_full_ast_for_every_statement_container(tmp_path: Path, source: str) -> None:
    source = dedent(source)
    path = tmp_path / "fixture.py"
    path.write_text(source, encoding="utf-8")
    expected: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            expected.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            expected.add(node.module)
    assert _imports(path) == expected


def test_import_scan_does_not_walk_expression_subtrees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "expressions.py"
    path.write_text("payload = [1, {'k': [True, None]}, (lambda x: x)(2)]\nimport actual\n", encoding="utf-8")
    original = ast.iter_child_nodes

    def statement_children(node):
        assert not isinstance(node, ast.expr), "import scan walked an irrelevant expression subtree"
        yield from original(node)

    with monkeypatch.context() as scoped:
        scoped.setattr(ast, "iter_child_nodes", statement_children)
        actual = _imports(path)
    assert actual == {"actual"}


def test_import_scan_still_parses_files_without_imports(tmp_path: Path) -> None:
    path = tmp_path / "invalid.py"
    path.write_text("value = (\n", encoding="utf-8")
    with pytest.raises(SyntaxError):
        _imports(path)


def test_import_scan_preserves_source_decoding_errors(tmp_path: Path) -> None:
    path = tmp_path / "invalid_encoding.py"
    path.write_bytes(bytes([255]))
    with pytest.raises(UnicodeDecodeError):
        _imports(path)


@pytest.mark.parametrize("relative,source,allowed", [
    ("untrusted.py", "if False:\n    from integrations.mastermind_window_reader.production_binding import X\n", False),
    ("untrusted.py", "try:\n    pass\nexcept Exception:\n    from integrations.mastermind_window_reader.owner_read_resource import X\n", False),
    ("integrations/mastermind_steward_app/installed.py", "from integrations.mastermind_window_reader.production_binding import X\n", True),
    ("integrations/mastermind_steward_app/installed.py", "from integrations.mastermind_window_reader.live_window_read import X\n", False),
    ("integrations/mastermind_window_reader/local.py", "from integrations.mastermind_window_reader.live_window_read import X\n", True),
    ("tests/mastermind_window_reader/test_local.py", "from integrations.mastermind_window_reader.live_window_read import X\n", True),
    ("tests/mastermind_window_reader_extra/test_local.py", "from integrations.mastermind_window_reader.live_window_read import X\n", False),
])
def test_import_fence_still_rejects_unapproved_nested_importers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    relative: str, source: str, allowed: bool,
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    if allowed:
        test_window_reader_modules_have_only_package_and_test_importers()
    else:
        with pytest.raises(AssertionError):
            test_window_reader_modules_have_only_package_and_test_importers()


def test_import_scan_preserves_missing_source_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _imports(tmp_path / "absent.py")
