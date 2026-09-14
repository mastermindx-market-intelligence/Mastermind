from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
EXECUTIVE_OS_ROOT = REPO_ROOT / "ops" / "executive_os"
PYTHON_FLAGS = re.compile(
    r'(?:"\$PYTHON_BINARY"|\$SYSTEM_PYTHON|/usr/bin/python3|python3(?:\.\d+)?)'
    r"\s+-I\s+-S\s+-B"
)
QUOTED_TARGET = re.compile(r'"([^"\n]+\.py)"')
VARIABLE_TARGET = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)')


def _resolve_target(wrapper: Path, target_text: str) -> Path:
    target = Path(target_text)
    if target.is_absolute():
        return target.resolve()
    if target_text.startswith("$SCRIPT_DIR/"):
        target = wrapper.parent / target_text.removeprefix("$SCRIPT_DIR/")
    elif target_text.startswith("$ROOT_CARRIER/"):
        target = REPO_ROOT / target_text.removeprefix("$ROOT_CARRIER/")
    elif target_text.startswith("$RELEASE_ROOT/"):
        target = REPO_ROOT / target_text.removeprefix("$RELEASE_ROOT/")
    elif target_text.startswith("$RELEASE_STAGE/"):
        target = REPO_ROOT / target_text.removeprefix("$RELEASE_STAGE/")
    elif target_text.startswith("$release/"):
        target = REPO_ROOT / target_text.removeprefix("$release/")
    else:
        target = REPO_ROOT / target_text.removeprefix("$")
    return target.resolve()


def _shell_variable_target(wrapper: Path, target_text: str) -> Path | None:
    variable_match = VARIABLE_TARGET.fullmatch(target_text)
    if variable_match is None:
        return None
    variable = variable_match.group(1)
    assignment = re.search(
        rf"^{re.escape(variable)}=(.+)$", wrapper.read_text(encoding="utf-8"), re.MULTILINE
    )
    if assignment is None:
        return None
    return _resolve_target(wrapper, assignment.group(1).strip('"'))


def _wrapper_targets(wrapper: Path) -> list[tuple[Path, str]]:
    source = wrapper.read_text(encoding="utf-8").replace("\\\n", " ")
    targets: list[tuple[Path, str]] = []
    for match in PYTHON_FLAGS.finditer(source):
        nearby_source = source[match.end() : match.end() + 500]
        if re.match(r"\s+-[cm]\b|\s+-\s", nearby_source):
            continue
        variable_match = VARIABLE_TARGET.search(nearby_source)
        if variable_match is not None:
            target = _shell_variable_target(wrapper, f"${variable_match.group(1)}")
            if target is not None and target.is_file():
                targets.append((target, variable_match.group(0)))
                continue
        target_match = QUOTED_TARGET.search(nearby_source)
        assert target_match is not None, f"wrapper has non-file isolated Python launch: {wrapper}"
        target_text = target_match.group(1)
        resolved_target = _resolve_target(wrapper, target_text)
        assert resolved_target.is_file(), f"wrapper target is missing: {wrapper} -> {target_text}"
        targets.append((resolved_target, target_text))
    return targets


WRAPPERS = sorted(EXECUTIVE_OS_ROOT.glob("*.sh"))
TARGETS = sorted(
    {
        (target, target_text)
        for wrapper in WRAPPERS
        for target, target_text in _wrapper_targets(wrapper)
    },
    key=lambda item: item[0],
)
TARGETS = [target for target in TARGETS if target[0].name != "render_launchd_program_arguments.py"]

assert TARGETS, "no wrapper-invoked entrypoints discovered"

MINIMUM_EXPECTED_TARGETS = {
    "ops/executive_os/autonomy_control.py",
    "scripts/executive_os_phase1c.py",
    "scripts/executive_dr_cli.py",
}


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=lambda path: path.name)
def test_wrapper_target_discovery_succeeds(wrapper: Path) -> None:
    _wrapper_targets(wrapper)


def test_discovery_includes_patched_entrypoints() -> None:
    discovered_targets = {
        target_path.relative_to(REPO_ROOT).as_posix() for target_path, _ in TARGETS
    }
    assert MINIMUM_EXPECTED_TARGETS <= discovered_targets


@pytest.mark.parametrize(
    "target",
    TARGETS,
    ids=lambda item: item[0].relative_to(REPO_ROOT).as_posix(),
)
def test_wrapper_invoked_entrypoint_imports_without_implicit_repo_path(
    target: tuple[Path, str], tmp_path: Path
) -> None:
    target_path, _ = target
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(target_path), "--definitely-not-a-real-subcommand"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "ModuleNotFoundError" not in result.stderr
    assert "Traceback" not in result.stderr


def test_autonomy_control_imports_control_plane_under_wrapper_isolation(tmp_path: Path) -> None:
    target = REPO_ROOT / "ops" / "executive_os" / "autonomy_control.py"
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(target), "--status"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "ModuleNotFoundError: No module named 'control_plane'" not in result.stderr
    assert "Traceback" not in result.stderr
