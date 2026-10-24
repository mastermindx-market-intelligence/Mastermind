"""Bootstrap kernel extraction, revision, fixture and ChatGPT Project parity checks."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_mastermind_bootstrap.py"
SOURCE = ROOT / "docs" / "sol_skills" / "BOOTSTRAP_KERNEL.md"
FIXTURE = ROOT / "tests" / "fixtures" / "bootstrap_kernel_project.txt"
MANIFEST = ROOT / "docs" / "sol_skills" / "BOOTSTRAP_KERNEL_RELEASE.json"
ARCHIVE = ROOT / "research" / "execution_bureaucracy_20261015" / "WEB_PROJECT_INSTRUCTIONS.txt"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def _kernel() -> str:
    from scripts.compare_mastermind_bootstrap import extract_kernel

    return extract_kernel(SOURCE.read_text(encoding="utf-8"))


def test_exact_match_export(tmp_path: Path):
    export = tmp_path / "project.txt"
    export.write_text(_kernel(), encoding="utf-8")
    result = _run("--project", str(export))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH:" in result.stdout


def test_one_character_drift(tmp_path: Path):
    kernel = _kernel()
    export = tmp_path / "project.txt"
    export.write_text(kernel[:-2] + "X\n", encoding="utf-8")
    result = _run("--project", str(export))
    assert result.returncode == 1
    assert "DRIFT:" in result.stdout


def test_stale_revision_is_drift(tmp_path: Path):
    kernel = _kernel().replace("bootstrap_revision = 2026.10.23.1", "bootstrap_revision = 2026.01.01.0")
    export = tmp_path / "project.txt"
    export.write_text(kernel, encoding="utf-8")
    result = _run("--project", str(export))
    assert result.returncode == 1
    assert "DRIFT:" in result.stdout
    assert "2026.10.23.1" in result.stdout


def test_wrong_source_missing_fence(tmp_path: Path):
    source = tmp_path / "BOOTSTRAP_KERNEL.md"
    source.write_text("# not a kernel\n", encoding="utf-8")
    result = _run("--source", str(source), "--print-kernel")
    assert result.returncode == 2
    assert "ERROR:" in result.stderr


def test_missing_source(tmp_path: Path):
    result = _run("--source", str(tmp_path / "absent.md"), "--print-kernel")
    assert result.returncode == 2
    assert "missing source" in result.stderr


def test_crlf_normalization_still_matches(tmp_path: Path):
    crlf = _kernel().replace("\n", "\r\n")
    export = tmp_path / "project.txt"
    export.write_bytes(crlf.encode("utf-8"))
    result = _run("--project", str(export))
    assert result.returncode == 0, result.stdout + result.stderr


def test_merged_rule_requirements_from_pr_1700_and_fabric_continuity():
    kernel = _kernel()
    for phrase in (
        "bootstrap_revision = 2026.10.23.1",
        "Keep DONE_WHEN and allowed surfaces",
        "versioned GitHub plan",
        "link Agent OS",
        "WAITING_EXTERNAL/review/CI/messages are lane-local",
        "Never delegate denied effects",
        "admitted paid Fabric",
        "No native Sol labor",
    ):
        assert phrase in kernel
    active = (ROOT / "docs" / "sol_skills" / "ACTIVE_EXECUTION.md").read_text(encoding="utf-8")
    cold = (ROOT / "docs" / "sol_skills" / "COLD_START.md").read_text(encoding="utf-8")
    assert "Durable project plan at the start, not only at handoff" in active
    assert "Action-scoped refusal is not mission-wide refusal." in active
    assert "PROJECT_BOOTSTRAP_DRIFT" in cold
    assert "PROJECT_SYNC_PENDING" in cold
    assert ARCHIVE.is_file()
    from scripts.compare_mastermind_bootstrap import normalized

    assert normalized(ARCHIVE.read_text(encoding="utf-8")) != kernel


def test_protected_kernel_stays_inside_project_budget():
    kernel = _kernel()
    assert len(kernel) <= 8000
    assert len(kernel) < 8000


def test_kernel_change_without_revision_bump_fails(tmp_path: Path):
    from scripts.compare_mastermind_bootstrap import check_revision_bump, extract_kernel, BootstrapParityError

    current = SOURCE.read_text(encoding="utf-8")
    mutated = current.replace("Never delegate denied effects.", "Never delegate denied effects!")
    assert mutated != current
    with pytest.raises(BootstrapParityError, match="without a bootstrap_revision bump"):
        check_revision_bump(extract_kernel(current), extract_kernel(mutated))
    bumped = mutated.replace("bootstrap_revision = 2026.10.23.1", "bootstrap_revision = 2026.10.23.2")
    check_revision_bump(extract_kernel(current), extract_kernel(bumped))


def test_generated_fixture_and_manifest_match_kernel():
    result = _run("--check")
    assert result.returncode == 0, result.stdout + result.stderr
    kernel = _kernel()
    assert FIXTURE.read_text(encoding="utf-8") == kernel
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["bootstrap_revision"] == "2026.10.23.1"
    assert manifest["kernel_sha256"] == __import__("hashlib").sha256(kernel.encode()).hexdigest()
    assert manifest["protected_merge_commit"] is None
    assert manifest["project_sync"] == "PROJECT_SYNC_PENDING"


def test_print_and_write_kernel_are_byte_identical_to_source(tmp_path: Path):
    printed = _run("--print-kernel")
    assert printed.returncode == 0, printed.stderr
    written = tmp_path / "kernel.txt"
    result = _run("--write-kernel", str(written))
    assert result.returncode == 0, result.stderr
    assert printed.stdout == _kernel()
    assert written.read_text(encoding="utf-8") == _kernel()
