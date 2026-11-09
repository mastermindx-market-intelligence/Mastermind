"""Bounded source-proximate tests for trusted PR/merge-group smoke scope.

The trusted-base CI scope selects this non-privileged path. This selector
never edits branch protection, suppresses a required check, or publishes a
review verdict. No remote access, shell interpolation, credentials or workers.
"""
from __future__ import annotations

import argparse
import ast
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

# Identity-reviewed sources are pinned by exact sha256/site literals, not by
# any same-stem test. The pin registry read for selection comes from the
# trusted base commit (never the candidate checkout), so a candidate cannot
# edit its own reviewed-file set; the test modules themselves still run from
# the checkout and verify the checkout's pins against its sources. #2365
# (merge group 42592403849) certified a scoped group without these modules
# while master's full pytest failed the frozen identity pins.
_IDENTITY_PIN_REGISTRY = "tests/executive_fabric_release_identity_review.py"
_IDENTITY_REVIEW_TESTS = (
    "tests/test_executive_reviewed_site_identity_tokens.py",
    "tests/test_executive_fabric_release_identity_review.py",
    "tests/test_hermes_fabric_native_identity_review.py",
)
_MAX_REGISTRY_BYTES = 256_000


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


def _registry_dict_keys(node: ast.expr) -> set[str] | None:
    """Constant string keys of a dict-literal expression, else None."""
    if not isinstance(node, ast.Dict):
        return None
    keys = {
        key.value for key in node.keys
        if isinstance(key, ast.Constant) and type(key.value) is str
    }
    return keys if len(keys) == len(node.keys) else None


def _registry_subscript_key(target: ast.expr) -> str | None:
    """Constant string subscript target like REVIEWED_FILES['path']."""
    if (isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "REVIEWED_FILES"
            and isinstance(target.slice, ast.Constant)
            and type(target.slice.value) is str):
        return target.slice.value
    return None


def _mentions_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(sub, ast.Name) and sub.id == name
               for sub in ast.walk(node))


def _registry_blob(repo: pathlib.Path, base: str, path: str) -> bytes | None:
    """Bounded registry blob read; None when the path is absent at base."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "blob", f"{base}:{path}"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12,
        )
    except (subprocess.SubprocessError, OSError):
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_UNAVAILABLE") from None
    # An absent path (or an unreadable base ref) is reported on stderr with a
    # nonzero exit; only a zero-exit read proves the blob's presence.
    if done.returncode != 0:
        return None
    if len(done.stdout) > _MAX_REGISTRY_BYTES:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_OVER_BOUND")
    return done.stdout


def _registry_keys(repo: pathlib.Path, base: str, path: str,
                   seen: frozenset[str]) -> set[str]:
    """Extract the reviewed-file keys from one trusted-base registry module.

    Only top-level statements are interpreted, so test functions in a
    registry module cannot affect the extracted set, and no base tree code
    is executed. The recognized vocabulary is the frozen-literal shape:
    an initial ``REVIEWED_FILES = {...}``, constant subscript assignments,
    literal named dicts, ``REVIEWED_FILES.update(...)`` of those, and
    ``from X import REVIEWED_FILES as ALIAS`` merges. Anything else that
    could mutate the registry fails closed.
    """
    if path in seen:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
    blob = _registry_blob(repo, base, path)
    if blob is None or not blob:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
    try:
        tree = ast.parse(blob.decode("utf-8"), filename=path)
    except (UnicodeError, SyntaxError):
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED") from None
    keys: set[str] | None = None
    literals: dict[str, set[str]] = {}
    imports: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # module docstring
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue  # never executed during registry import
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "REVIEWED_FILES":
                    if node.module is None or alias.asname is None:
                        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                    imports[alias.asname] = node.module.replace(".", "/") + ".py"
            continue
        if isinstance(node, ast.Import):
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "REVIEWED_FILES":
                if keys is not None:
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                keys = _registry_dict_keys(node.value)
                continue
            literal = _registry_subscript_key(target)
            if literal is not None:
                if keys is None:
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                keys.add(literal)
                continue
            if isinstance(target, ast.Name):
                named = _registry_dict_keys(node.value)
                if named is not None:
                    literals[target.id] = named
                continue
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "update"
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == "REVIEWED_FILES"):
            if keys is None or len(node.value.args) != 1 or node.value.keywords:
                raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            argument = node.value.args[0]
            if isinstance(argument, ast.Name) and argument.id in literals:
                keys |= literals[argument.id]
            elif isinstance(argument, ast.Name) and argument.id in imports:
                keys |= _registry_keys(repo, base, imports[argument.id], seen | {path})
            else:
                added = _registry_dict_keys(argument)
                if added is None:
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                keys |= added
            continue
        if isinstance(node, (ast.For, ast.While, ast.If, ast.Try, ast.With,
                             ast.AugAssign, ast.AnnAssign, ast.Delete,
                             ast.Raise, ast.Assert, ast.Global, ast.Nonlocal)):
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
        if isinstance(node, ast.Expr) and _mentions_name(node, "REVIEWED_FILES"):
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
    if keys is None:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
    return keys


def _reviewed_sources(repo: pathlib.Path, base: str) -> frozenset[str]:
    """Read the identity-review pin registry from the trusted base commit.

    The registry is parsed with ``ast`` only; no base tree code is executed.
    A base object predating the registry keeps the legacy selection (an
    empty set); a present-but-unrecognized registry fails closed instead of
    silently dropping identity-reviewed sources from smoke coverage.
    """
    if _registry_blob(repo, base, _IDENTITY_PIN_REGISTRY) is None:
        # Missing object or pre-registry trusted base: nothing was identity
        # reviewed there, so no ownership mapping can be lost.
        return frozenset()
    return frozenset(_registry_keys(repo, base, _IDENTITY_PIN_REGISTRY, frozenset()))


def select_modules(repo: pathlib.Path, changed: Sequence[str], *,
                   reviewed_sources: frozenset[str] = frozenset()) -> tuple[str, ...]:
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
    required: tuple[str, ...] = ()
    if _PAPER_STAGE_SOURCES.intersection(changed):
        required += (_PAPER_STAGE_TEST,)
    # Identity-reviewed ownership keeps the same fixed-dependency rule as the
    # paper stage pin: the owning review modules cannot be lost to alphabetic
    # ties or the module cap, and an unavailable module fails the check.
    if reviewed_sources.intersection(changed):
        required += _IDENTITY_REVIEW_TESTS
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
    # Fixed dependencies are exempt from the cap; the cap bounds only the
    # source-proximate picks and never goes negative when several required
    # ownership groups fire together.
    return tuple(dict.fromkeys((
        _BASELINE, *required,
        *remaining[:max(0, _MAX_SELECTED_MODULES - len(required))],
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
    # args.base is the trusted-base classifier's verified base SHA; the
    # reviewed-source registry is read from that commit, not the checkout.
    selected = select_modules(
        root, paths, reviewed_sources=_reviewed_sources(root, args.base),
    )
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
