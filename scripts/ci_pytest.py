"""Discovery-first repository test gate.

Every ``tests/**/test_*.py`` module runs unless its exact path is listed in
``ci/pytest_exclusions.toml``. New tests are included automatically. Exclusions
are fail-closed and cannot remove constitutional/security modules.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence


EXCLUSIONS_RELATIVE = Path("ci") / "pytest_exclusions.toml"
WORKFLOW_RELATIVE = Path(".github") / "workflows" / "ci.yml"
AUTHORITATIVE_STEP_NAME = "Run repository test gate"
AUTHORITATIVE_RUNNER = "scripts/ci_pytest.py"
PROTECTED_EXACT = frozenset(
    {
        "tests/test_ci_pytest_policy.py",
        "tests/test_secret_redaction.py",
        "tests/test_gate.py",
        "tests/test_vendored_read_ratchet.py",
        "tests/test_deploy_provenance.py",
        "tests/test_auth.py",
        "tests/test_book_state_isolation.py",
        "tests/test_web_exception_sanitization.py",
    }
)
PROTECTED_PREFIXES = ("tests/test_executive_",)
_TEST_MODULE_RE = re.compile(r"^test_.*\.py$")
_WORKFLOW_TEST_FILE_RE = re.compile(r"^tests/(?:[\w./-]+/)?test_\w+\.py$")


class PolicyError(ValueError):
    """The exclusion manifest or workflow coverage policy is invalid."""


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "tests").is_dir():
            return candidate
    raise PolicyError("could not resolve repository root from ci_pytest.py")


def discover_test_modules(root: Path) -> tuple[str, ...]:
    tests_root = (root / "tests").resolve()
    found: list[str] = []
    for path in tests_root.rglob("test_*.py"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.name.startswith("test_") and path.suffix == ".py":
            found.append(relative)
    return tuple(sorted(found))


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError(f"{label} must be a table")
    return value


def load_exclusions(root: Path, relative: Path = EXCLUSIONS_RELATIVE) -> tuple[dict[str, Any], ...]:
    path = root / relative
    if not path.is_file():
        raise PolicyError(f"exclusion manifest is missing: {relative.as_posix()}")
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if version != 1:
        raise PolicyError("exclusion manifest version must be 1")
    raw = payload.get("exclude", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise PolicyError("exclude must be an array of tables")
    rows: list[dict[str, Any]] = []
    for item in raw:
        rows.append(dict(_require_mapping(item, label="exclude entry")))
    return tuple(rows)


def is_protected(relative: str) -> bool:
    if relative in PROTECTED_EXACT:
        return True
    return any(relative.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def validate_exclusions(
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    discovered: Sequence[str],
) -> tuple[str, ...]:
    discovered_set = set(discovered)
    seen: set[str] = set()
    excluded: list[str] = []
    for row in rows:
        path = str(row.get("path") or "").strip()
        reason = str(row.get("reason") or "").strip()
        replacement = str(row.get("replacement_gate") or "").strip()
        if not path:
            raise PolicyError("exclusion path cannot be empty")
        if any(character in path for character in ("*", "?", "[", "]")):
            raise PolicyError(f"wildcard exclusion is forbidden: {path}")
        if path.endswith("/") or path == "tests" or path == "tests/":
            raise PolicyError(f"directory exclusion is forbidden: {path}")
        rendered = Path(path)
        if rendered.is_absolute() or ".." in rendered.parts:
            raise PolicyError(f"path escape is forbidden: {path}")
        if rendered.parts[:1] != ("tests",):
            raise PolicyError(f"exclusion path must be under tests/: {path}")
        if rendered.as_posix() != path:
            raise PolicyError(f"exclusion path must be a normalized posix path: {path}")
        if not _TEST_MODULE_RE.fullmatch(rendered.name):
            raise PolicyError(f"exclusion basename must be a pytest test module: {path}")
        if path in seen:
            raise PolicyError(f"duplicate exclusion: {path}")
        seen.add(path)
        if path not in discovered_set:
            raise PolicyError(f"stale exclusion names a missing file: {path}")
        if not reason:
            raise PolicyError(f"exclusion reason cannot be empty: {path}")
        if not replacement:
            raise PolicyError(f"replacement_gate is required: {path}")
        if is_protected(path):
            raise PolicyError(f"protected test cannot be excluded: {path}")
        excluded.append(path)
    return tuple(excluded)


def included_modules(discovered: Sequence[str], excluded: Sequence[str]) -> tuple[str, ...]:
    excluded_set = set(excluded)
    included = tuple(path for path in discovered if path not in excluded_set)
    if not included:
        raise PolicyError("included test set is empty")
    missing = excluded_set - set(discovered)
    if missing:
        raise PolicyError(f"excluded paths are not discovered: {sorted(missing)}")
    return included


def coverage_plan(
    *,
    discovered: Sequence[str],
    excluded: Sequence[str],
    included: Sequence[str],
) -> dict[str, int]:
    return {
        "discovered": len(discovered),
        "excluded": len(excluded),
        "running": len(included),
    }


def format_plan(plan: Mapping[str, int]) -> str:
    return (
        f"discovered={plan['discovered']} "
        f"excluded={plan['excluded']} "
        f"running={plan['running']}"
    )


def pytest_argv(included: Sequence[str], *, python: str | None = None) -> list[str]:
    return [python or sys.executable, "-m", "pytest", "-q", *included]


def workflow_contains_positive_allowlist(text: str) -> bool:
    """True when a workflow run block lists several tests/test_*.py files."""

    consecutive = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            consecutive = 0
            continue
        if _WORKFLOW_TEST_FILE_RE.fullmatch(stripped):
            consecutive += 1
            if consecutive >= 3:
                return True
            continue
        consecutive = 0
    return False


def validate_workflow(text: str) -> None:
    if AUTHORITATIVE_RUNNER not in text:
        raise PolicyError(
            f"authoritative CI step must invoke {AUTHORITATIVE_RUNNER}"
        )
    if AUTHORITATIVE_STEP_NAME not in text:
        raise PolicyError(
            f"CI workflow must name the step {AUTHORITATIVE_STEP_NAME!r}"
        )
    if workflow_contains_positive_allowlist(text):
        raise PolicyError(
            "CI workflow must not contain a positive tests/test_*.py filename allowlist"
        )


def resolve_gate(root: Path) -> dict[str, Any]:
    discovered = discover_test_modules(root)
    rows = load_exclusions(root)
    excluded = validate_exclusions(root, rows, discovered)
    included = included_modules(discovered, excluded)
    workflow = root / WORKFLOW_RELATIVE
    if workflow.is_file():
        validate_workflow(workflow.read_text(encoding="utf-8"))
    return {
        "discovered": discovered,
        "excluded": excluded,
        "included": included,
        "plan": coverage_plan(
            discovered=discovered, excluded=excluded, included=included
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the coverage plan and exit without running pytest",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (defaults to the checkout that contains this script)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve() if args.root else repo_root()
    try:
        gate = resolve_gate(root)
    except PolicyError as exc:
        print(f"ci_pytest policy error: {exc}", file=sys.stderr)
        return 2
    print(format_plan(gate["plan"]))
    if args.plan_only:
        return 0
    completed = subprocess.run(
        pytest_argv(gate["included"]),
        cwd=root,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
