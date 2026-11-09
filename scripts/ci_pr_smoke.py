"""Bounded source-proximate tests for trusted PR/merge-group smoke scope.

The trusted-base CI scope selects this non-privileged path. This selector
never edits branch protection, suppresses a required check, or publishes a
review verdict. No remote access, shell interpolation, credentials or workers.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
from collections.abc import Sequence

_MAX_DIFF_BYTES = 256_000
_MAX_SELECTED_MODULES = 3
_MAX_MODULE_BYTES = 160_000

# Run one deterministic always-present policy smoke even when source path
# naming does not map to an exact test. It is not claimed as complete coverage.
_BASELINE = "tests/test_ci_pytest_policy.py"

# The bridge's reviewed generation is owned by runtime_stage, not by a
# same-stem bridge test. Keep this dependency inside the existing module cap.
_PAPER_STAGE_SOURCES = frozenset({
    "integrations/paper_desktop/bridge.py",
    "integrations/paper_desktop/runtime_stage.py",
})
_PAPER_STAGE_TEST = "tests/test_paper_runtime_stage.py"


class SmokeUnqualified(ValueError):
    pass


def _diff_paths(repo: pathlib.Path, base: str, head: str) -> tuple[str, ...]:
    try:
        ancestor = subprocess.run(
            ["git", "-C", str(repo), "merge-base", base, head],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=12,
        ).stdout.decode("ascii").strip()
        result = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-only", "-z", "--no-renames",
             ancestor, head],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=12,
        ).stdout
    except (subprocess.SubprocessError, OSError, UnicodeError):
        raise SmokeUnqualified("SMOKE_SOURCE_DIFF_UNAVAILABLE") from None
    if len(result) > _MAX_DIFF_BYTES or not result.endswith(b"\x00"):
        raise SmokeUnqualified("SMOKE_DIFF_INCOMPLETE")
    try:
        paths = tuple(part.decode("utf-8") for part in result[:-1].split(b"\x00"))
    except UnicodeError:
        raise SmokeUnqualified("SMOKE_DIFF_PATH_INVALID") from None
    return paths


def select_modules(repo: pathlib.Path, changed: Sequence[str]) -> tuple[str, ...]:
    """Pick fixed dependencies then source-proximate tests, at most 3."""
    root = repo.resolve(strict=True)
    selected: set[str] = set()
    for path in changed:
        if not path or path.startswith("/") or ".." in pathlib.PurePosixPath(path).parts:
            raise SmokeUnqualified("SMOKE_PATH_UNSAFE")
        file = root / path
        if path.endswith(".py") and file.exists() and file.is_file():
            if not file.resolve().is_relative_to(root):
                raise SmokeUnqualified("SMOKE_PATH_ESCAPED")
            if path.startswith("tests/") and file.name.startswith("test_"):
                selected.add(path)
            else:
                candidate = root / "tests" / ("test_" + file.stem + ".py")
                if candidate.exists() and candidate.is_file():
                    selected.add(candidate.relative_to(root).as_posix())
    required = (_PAPER_STAGE_TEST,) if _PAPER_STAGE_SOURCES.intersection(changed) else ()
    for path in required:
        file = root / path
        try:
            available = (not file.is_symlink() and file.is_file()
                         and file.resolve().is_relative_to(root)
                         and file.stat().st_size <= _MAX_MODULE_BYTES)
        except OSError:
            available = False
        if not available:
            raise SmokeUnqualified("SMOKE_REQUIRED_TEST_UNAVAILABLE")
    # Fixed dependencies cannot be lost to alphabetic ties or the module cap.
    # Other source-proximate tests retain their deterministic
    # alphabetic ties and fixed cap. Never let a PR path select a workflow,
    # executable, shell expression, URL, or arbitrary filesystem target.
    ordered = sorted(selected)
    bounded = tuple(p for p in ordered
                    if (root / p).stat().st_size <= _MAX_MODULE_BYTES)
    remaining = tuple(p for p in bounded if p not in required)
    return tuple(dict.fromkeys((
        _BASELINE, *required, *remaining[:_MAX_SELECTED_MODULES - len(required)],
    )))


def check_changed_python(repo: pathlib.Path, changed: Sequence[str]) -> None:
    """Syntax-only on changed Python; no source execution on this step."""
    for relative in changed:
        if not relative.endswith(".py"):
            continue
        file = repo / relative
        if not file.is_file() or not file.resolve().is_relative_to(repo.resolve()):
            raise SmokeUnqualified("SMOKE_PYTHON_SOURCE_UNAVAILABLE")
        try:
            compile(file.read_bytes(), relative, "exec")
        except (OSError, UnicodeError, SyntaxError):
            raise SmokeUnqualified("SMOKE_PYTHON_SYNTAX_FAILED") from None


def main() -> int:
    p = argparse.ArgumentParser(description="Fast PR smoke checks")
    p.add_argument("--repo", type=pathlib.Path, required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    args = p.parse_args()
    root = args.repo.resolve(strict=True)
    if not (root / ".git").exists():
        raise SmokeUnqualified("SMOKE_REPO_UNAVAILABLE")
    paths = _diff_paths(root, args.base, args.head)
    check_changed_python(root, paths)
    selected = select_modules(root, paths)
    print(f"CI_PR_SMOKE selected_tests={len(selected)} changed_paths={len(paths)}",
          flush=True)
    try:
        # The GitHub job enforces its own overall timeout; subprocess is
        # additionally bounded to prevent a single slow test from stalling PRs.
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short", *selected],
            cwd=root, check=False, timeout=210,
        )
    except subprocess.TimeoutExpired:
        print("CI_PR_SMOKE_TEST_BUDGET_EXHAUSTED", file=sys.stderr)
        return 1
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
