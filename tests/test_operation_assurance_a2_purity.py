"""tests.test_operation_assurance_a2_purity — OLS-A2 no-rebuild/purity fence.

Design Section 2 + Section 8: operation_assurance_compiler.py is pure
(stdlib-only, zero I/O); operation_assurance_sources.py is the ONLY module
with read I/O (no network, no subprocess, no write/cache/persist, no
retry loop, no clock read). scripts/operation_assurance_compile.py is a
bounded JSON-in/JSON-out projection, never an actuator.

Pattern follows tests/test_chairman_cognition_source_contract.py's
``test_pure_core_imports_no_runtime_io_network_or_connector_owner`` /
``test_cli_is_a_bounded_json_projection_not_an_actuator``, which the OLS-A2
design (Section 8) cites as the accepted receipt-shape precedent.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "control_plane" / "operation_assurance_sources.py"
COMPILER = ROOT / "control_plane" / "operation_assurance_compiler.py"
CLI = ROOT / "scripts" / "operation_assurance_compile.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imported_modules(tree: ast.AST) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    return imported


_FORBIDDEN_IO_FRAGMENTS = (
    "subprocess",
    "socket",
    "urllib",
    "httpx",
    "requests",
    "sqlite",
    "shutil",
    "tempfile",
)


def test_compiler_is_pure_stdlib_only_zero_io() -> None:
    tree = ast.parse(_text(COMPILER))
    imported = _imported_modules(tree)
    offenders = sorted(m for m in imported if any(frag in m.lower() for frag in _FORBIDDEN_IO_FRAGMENTS))
    assert not offenders, offenders
    # the compiler must never import the sources module's own I/O entry
    # point (gather_agent_os_source_facts) — only its typed value objects
    # and pure helpers.
    assert "operation_assurance_sources.gather_agent_os_source_facts" not in imported


def test_compiler_module_source_never_calls_open_or_git() -> None:
    tree = ast.parse(_text(COMPILER))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in calls
    text = _text(COMPILER)
    assert "import subprocess" not in text
    assert "os.system" not in text
    assert "datetime.now" not in text and "time.time" not in text  # never reads a clock


def test_sources_module_forbids_network_subprocess_and_clock() -> None:
    tree = ast.parse(_text(SOURCES))
    imported = _imported_modules(tree)
    offenders = sorted(m for m in imported if any(frag in m.lower() for frag in _FORBIDDEN_IO_FRAGMENTS))
    assert not offenders, offenders
    text = _text(SOURCES)
    assert "import subprocess" not in text
    assert "os.system" not in text
    assert "datetime.now" not in text and "time.time" not in text  # observed_at is caller-supplied, never sampled


def test_sources_module_never_writes_caches_or_retries() -> None:
    tree = ast.parse(_text(SOURCES))

    def _receiver_name(node: ast.Attribute) -> str | None:
        return node.value.id if isinstance(node.value, ast.Name) else None

    forbidden_write_methods = {"write_text", "write_bytes", "unlink", "replace", "mkdir", "rmdir", "rename"}
    offenders = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in forbidden_write_methods:
            continue
        if node.func.attr == "replace" and _receiver_name(node.func) == "dataclasses":
            continue  # dataclasses.replace() is a pure value constructor, not a filesystem write
        offenders.add(node.func.attr)
    assert not offenders, offenders
    text = _text(SOURCES)
    # every open() call in this module is a read: literal write modes never appear
    assert '"w"' not in text and "'w'" not in text
    assert '"wb"' not in text and "'wb'" not in text
    assert '"a"' not in text and "'a'" not in text


def test_sources_module_open_calls_are_read_only() -> None:
    tree = ast.parse(_text(SOURCES))
    open_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "open")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "open")
        )
    ]
    assert open_calls, "expected at least one read call in the sole I/O module"
    for node in open_calls:
        modes = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                modes.append(kw.value.value)
        for mode in modes:
            assert mode in ("r", "rb"), f"non-read open() mode found: {mode!r}"


def test_cli_is_a_bounded_json_projection_not_an_actuator() -> None:
    tree = ast.parse(_text(CLI))
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "write_text" not in calls
    assert "write_bytes" not in calls
    assert "unlink" not in calls
    assert "system" not in calls
    text = _text(CLI)
    assert "subprocess" not in text
    assert '"w"' not in text and "'w'" not in text
    assert '"wb"' not in text and "'wb'" not in text


def test_no_module_imports_a_second_steward_or_federated_reader() -> None:
    # design Section 8 no-rebuild boundary: never a parallel Steward
    for path in (SOURCES, COMPILER, CLI):
        text = _text(path)
        assert "class ExecutiveSteward" not in text
        assert "class Steward" not in text


def test_compiler_reuses_the_existing_steward_not_a_copy() -> None:
    text = _text(COMPILER)
    assert "from control_plane.executive_steward import" in text
    assert "ExecutiveStewardSnapshot(" in text
