"""Read-only bootstrap kernel extraction and ChatGPT Project parity checks."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_mastermind_bootstrap.py"
SOURCE = ROOT / "docs" / "sol_skills" / "BOOTSTRAP_KERNEL.md"


def _run(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def _kernel() -> str:
    from scripts.compare_mastermind_bootstrap import extract_kernel

    return extract_kernel(SOURCE.read_text(encoding="utf-8"))


def test_protected_kernel_stays_inside_project_budget():
    kernel = _kernel()
    assert len(kernel) <= 8000
    assert "Never delegate denied effects" in kernel
    assert "admitted paid Fabric" in kernel
    assert "No native Sol labor" in kernel
    assert "WAITING_EXTERNAL/review/CI/messages are lane-local" in kernel
    assert "actual missing evidence" in kernel


def test_compare_matches_an_exact_export(tmp_path: Path):
    export = tmp_path / "project.txt"
    export.write_text(_kernel(), encoding="utf-8")
    result = _run("--source", str(SOURCE), "--project", str(export))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH:" in result.stdout
    digest = hashlib.sha256(_kernel().encode()).hexdigest()
    assert digest in result.stdout


def test_compare_reports_drift(tmp_path: Path):
    export = tmp_path / "project.txt"
    export.write_text(_kernel().replace("Never delegate denied effects", "delegate freely"), encoding="utf-8")
    result = _run("--project", str(export))
    assert result.returncode == 1
    assert "DRIFT:" in result.stdout
    assert "Never delegate denied effects" in result.stdout


def test_print_and_write_kernel_are_byte_identical_to_source(tmp_path: Path):
    printed = _run("--print-kernel")
    assert printed.returncode == 0, printed.stderr
    written = tmp_path / "kernel.txt"
    result = _run("--write-kernel", str(written))
    assert result.returncode == 0, result.stderr
    assert printed.stdout == _kernel()
    assert written.read_text(encoding="utf-8") == _kernel()
