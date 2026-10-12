"""Future import changes cannot silently outgrow CAP-S1's sealed source list.

This is a static module-scope import check, deliberately independent of the
production bootstrap's digest collector. It does not run untrusted imports.
Dynamic imports require an explicit owned source update and separate proof.
"""
from __future__ import annotations

import ast
from collections import deque
import importlib.util
from pathlib import Path

import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_MODULES = (
    "scripts.ohf.cap_s1_mastermind_operator_canary",
    "scripts.ohf.capability_skill_projection",
    "scripts.ohf.protocol",
    "scripts.ohf.laboratory",
    "control_plane.codex_operator_adapter",
    "control_plane.executive_agent_capabilities",
    "control_plane.executive_capability_packages",
    "control_plane.operator_harness_contract",
)


def _source_for_module(source_root: Path, name: str) -> Path | None:
    candidate = source_root.joinpath(*name.split("."))
    file = candidate.with_suffix(".py")
    if file.is_file():
        return file
    package = candidate / "__init__.py"
    if package.is_file():
        return package
    return None


def _module_scope_imports(source: Path, name: str) -> set[str]:
    """Walk executable module/class/conditional statements, not function bodies.

    Python's relative import resolution uses the importing package; enumerate
    both `from package import module` and the package itself where resolvable.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    imported: set[str] = set()
    package = name if source.name == "__init__.py" else name.rpartition(".")[0]

    def collect(statements: list[ast.AST]) -> None:
        for statement in statements:
            if isinstance(statement, (
                ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef,
            )):
                # Class bodies execute at import; function/lambda bodies do not.
                if isinstance(statement, ast.ClassDef):
                    collect(statement.body)
                continue
            if isinstance(statement, ast.Import):
                imported.update(alias.name for alias in statement.names)
            elif isinstance(statement, ast.ImportFrom):
                if statement.level:
                    module = importlib.util.resolve_name(
                        "." * statement.level + (statement.module or ""), package
                    )
                else:
                    module = statement.module or ""
                if module:
                    imported.add(module)
                for alias in statement.names:
                    if alias.name != "*":
                        imported.add(f"{module}.{alias.name}" if module else alias.name)
            else:
                # Recurse through AST nodes, not just `ast.stmt`. A module-
                # level Try.handlers contains `ast.ExceptHandler` and a Match
                # contains `ast.match_case`; skipping those silently misses
                # imports that would execute during source bootstrap.
                for _field, value in ast.iter_fields(statement):
                    if isinstance(value, list):
                        collect([item for item in value if isinstance(item, ast.AST)])
                    elif isinstance(value, ast.AST):
                        collect([value])
            # Dynamic importlib.import_module() remains a separate owner gate.

    collect(tree.body)
    return imported


def _static_import_closure(source_root: Path, roots: tuple[str, ...]) -> set[str]:
    pending = deque(roots)
    seen: set[str] = set()
    while pending:
        name = pending.popleft()
        if name in seen:
            continue
        path = _source_for_module(source_root, name)
        if path is None:
            continue  # Third-party or stdlib imports are outside this repo.
        seen.add(name)
        parent = name
        while "." in parent:
            parent = parent.rpartition(".")[0]
            if _source_for_module(source_root, parent) is not None:
                pending.append(parent)
        for imported in _module_scope_imports(path, name):
            if _source_for_module(source_root, imported) is not None:
                pending.append(imported)
    return seen


def test_actual_bootstrap_seals_entire_static_local_import_closure():
    declared_rows = canary_module._CAP_S1_PYTEST_SOURCE_MODULES
    names = [name for name, _relative in declared_rows]
    assert len(names) == len(set(names))
    for name, relative in declared_rows:
        source = _source_for_module(REPO_ROOT, name)
        assert source is not None, f"declared module unavailable: {name}"
        assert source.relative_to(REPO_ROOT).as_posix() == relative
    closure = _static_import_closure(REPO_ROOT, BOOTSTRAP_MODULES)
    absent = sorted(closure - set(names))
    assert not absent, f"new unsealed bootstrap dependencies: {absent}"
    assert set(BOOTSTRAP_MODULES) <= closure


def test_new_transitive_import_is_detected_without_importing_it(tmp_path):
    package = tmp_path / "localpkg"; package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text(
        "from localpkg.helper import useful\n", encoding="utf-8"
    )
    (package / "helper.py").write_text(
        "from localpkg import new_dependency\n", encoding="utf-8"
    )
    (package / "new_dependency.py").write_text(
        "raise RuntimeError('must never import in closure check')\n",
        encoding="utf-8",
    )
    closure = _static_import_closure(tmp_path, ("localpkg.entry",))
    assert "localpkg.new_dependency" in closure
    old_seal = {"localpkg", "localpkg.entry", "localpkg.helper"}
    assert "localpkg.new_dependency" in closure - old_seal


def test_module_scope_except_handler_import_must_join_sealed_closure(tmp_path):
    package = tmp_path / "localpkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text(
        "try:\n    import json\nexcept ImportError:\n    from localpkg import fallback\n",
        encoding="utf-8",
    )
    (package / "fallback.py").write_text(
        "raise RuntimeError('static check must never import me')\n", encoding="utf-8",
    )
    discovered = _static_import_closure(tmp_path, ("localpkg.entry",))
    assert "localpkg.fallback" in discovered


def test_module_scope_match_case_import_must_join_sealed_closure(tmp_path):
    package = tmp_path / "localpkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text(
        "match 1:\n    case 1:\n        from localpkg import conditional\n",
        encoding="utf-8",
    )
    (package / "conditional.py").write_text(
        "raise RuntimeError('static check must never import me')\n", encoding="utf-8",
    )
    discovered = _static_import_closure(tmp_path, ("localpkg.entry",))
    assert "localpkg.conditional" in discovered
