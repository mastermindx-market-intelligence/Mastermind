"""Bounded source-proximate tests for trusted PR/merge-group smoke scope.

The trusted-base CI scope selects this non-privileged path. This selector
never edits branch protection, suppresses a required check, or publishes a
review verdict. No remote access, shell interpolation, credentials or workers.

Identity-pin ownership selection is literal text matching, not parsing: a
registry fires when a changed path appears as a quoted string literal in its
chain text read from the trusted base. Every real registry key is a literal
path string in the registry source, so bytes containment covers the same set
an interpreter would build without an allow/deny vocabulary that new Python
shapes could launder. Over-selection (a quoted path that is not a live key)
costs a few extra test modules. The live guard in tests/test_ci_pr_smoke.py
runs on every smoke candidate and fails when a runtime key is not present as
a quoted literal anywhere in its chain, so a registry that gains keys through
a module outside the listed chain (for example a deferred import that starts
resolving once a later PR adds the module) is refused on the PR that makes
those keys appear, not just on registry edits. The single residual is a key built dynamically inside
a function body, gated on a condition that is false when the guard runs: the
guard imports the real module, so such a key stays hidden from both selection
and the guard until the gating condition flips.
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

# Identity-reviewed sources are pinned by exact sha256/site literals, not by
# any same-stem test. The pin registries read for selection come from the
# trusted base commit (never the candidate checkout), so a candidate cannot
# edit its own reviewed-file set; the test modules themselves still run from
# the checkout and verify the checkout's pins against its sources. #2365
# (merge group 42592403849) certified a scoped group without these modules
# while master's full pytest failed the frozen identity pins. Each entry is
# (registry, chain, owning tests):
# - registry is the frozen registry module the owning tests import.
# - chain is every file whose text can contribute runtime keys: the registry
#   itself plus every module it imports REVIEWED_FILES from. The fabric
#   registry merges tests/test_hermes_workspace_oauth_identity_review.py via
#   ``from ... import REVIEWED_FILES as ...`` + ``REVIEWED_FILES.update(...)``;
#   that sub-registry imports no further registry modules.
# Selection fires when a changed path is quoted in the concatenated chain
# text, so a key edited only in the sub-registry still selects these owners.
_IDENTITY_PIN_REGISTRIES = (
    ("tests/executive_fabric_release_identity_review.py", (
        "tests/executive_fabric_release_identity_review.py",
        "tests/test_hermes_workspace_oauth_identity_review.py",
    ), (
        "tests/test_executive_reviewed_site_identity_tokens.py",
        "tests/test_executive_fabric_release_identity_review.py",
        "tests/test_hermes_fabric_native_identity_review.py",
    )),
    ("tests/executive_incident_identity_review.py", (
        "tests/executive_incident_identity_review.py",
    ), (
        "tests/test_incident_identity_review.py",
    )),
)
_MAX_REGISTRY_BYTES = 256_000
# A registry or chain edit is read from the trusted base, never from the
# candidate, so the candidate's new registry bytes would otherwise merge
# without ever meeting selection or the guard, and every later smoke
# candidate would silently lose that registry's ownership mapping. Editing
# any chain path therefore selects its owning tests and this live guard,
# which proves on the candidate checkout that every runtime key is a quoted
# literal in the chain text.
_REGISTRY_GUARD_TEST = "tests/test_ci_pr_smoke.py"
# The guard alone also runs on every smoke candidate (see main); a missing
# guard is a pytest collection error, so it fails closed rather than skipping.
_REGISTRY_GUARD_NODE = (
    _REGISTRY_GUARD_TEST
    + "::test_live_identity_registry_keys_are_quoted_literals_in_their_chain"
)


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


def _registry_blob(repo: pathlib.Path, base: str, path: str) -> bytes | None:
    """Bounded registry blob read; None only when absent at the base."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "blob", f"{base}:{path}"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12,
        )
    except (subprocess.SubprocessError, OSError):
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_UNAVAILABLE") from None
    if done.returncode != 0:
        # A nonzero exit conflates absence with an unreadable object store.
        # Only a listing that proves the path absent at the base keeps the
        # legacy empty mapping; every unclear case fails closed.
        try:
            probe = subprocess.run(
                ["git", "-C", str(repo), "ls-tree", base, "--", path],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12,
            )
        except (subprocess.SubprocessError, OSError):
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_UNAVAILABLE") from None
        if probe.returncode != 0 or probe.stdout.strip():
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_UNREADABLE")
        return None
    if len(done.stdout) > _MAX_REGISTRY_BYTES:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_OVER_BOUND")
    return done.stdout


def _quoted_path_in(text: bytes, path: str) -> bool:
    """True when path appears as a '...' or "..." string literal in text.

    Pure bytes containment with no parsing: comments, identifiers or split
    (dynamically constructed) spellings do not match, so an unquoted mention
    never selects. That under-selection edge is closed by the live guard,
    which fails the registry PR when a runtime key has no quoted spelling in
    its chain text, rather than by widening this match.
    """
    raw = path.encode("utf-8")
    return b"'" + raw + b"'" in text or b'"' + raw + b'"' in text


def _reviewed_registries(
    repo: pathlib.Path, base: str,
) -> tuple[tuple[bytes, tuple[str, ...]], ...]:
    """Read every wired identity registry's chain text from the trusted base.

    Each registry contributes the concatenated blobs of its chain (itself
    plus every module it imports REVIEWED_FILES from); selection later tests
    changed paths against that text by quoted-literal containment only. A
    registry absent at the base keeps its legacy empty text (nothing was
    identity reviewed there, so no ownership mapping can be lost); a chain
    member absent at the base contributes nothing for the same reason. An
    unreadable or over-bound blob fails closed instead of silently dropping
    identity-reviewed sources from smoke coverage. No base tree code is
    executed or parsed.
    """
    out: list[tuple[bytes, tuple[str, ...]]] = []
    for path, chain, tests in _IDENTITY_PIN_REGISTRIES:
        if _registry_blob(repo, base, path) is None:
            # No registry module at the base means no import chain there
            # either: the legacy empty mapping, exactly as before.
            out.append((b"", tests))
            continue
        text = b"".join(
            blob for blob in (
                _registry_blob(repo, base, member) for member in chain
            ) if blob is not None
        )
        out.append((text, tests))
    return tuple(out)


def select_modules(
    repo: pathlib.Path, changed: Sequence[str], *,
    identity_registries: Sequence[tuple[bytes, tuple[str, ...]]],
    require_complete: bool = False,
) -> tuple[str, ...]:
    """Pick fixed ownership dependencies, then capped source-proximate tests.

    Fixed dependencies — the paper stage pin and the owning test modules of
    every identity registry whose chain text quotes a changed path — are
    exempt from the ordinary PR module cap, so that selection legitimately
    exceeds _MAX_SELECTED_MODULES when several ownership groups fire.
    Complete merge-group qualification instead requires the deduplicated
    union of owners and source-proximate modules to fit the allowance;
    overflow escalates to full tests rather than truncating coverage.
    """
    root = repo.resolve(strict=True)
    selected: set[str] = set()
    for path in changed:
        if not path or path.startswith("/") or ".." in pathlib.PurePosixPath(path).parts:
            raise SmokeUnqualified("SMOKE_PATH_UNSAFE")
        file = root / path
        if (require_complete and path.startswith("tests/")
                and file.name.startswith("test_") and path.endswith(".py")):
            # A directly changed test is applicable even when the checkout
            # cannot provide it. Strict group qualification must refuse it.
            selected.add(path)
        if path.endswith(".py") and file.exists() and file.is_file():
            if not file.resolve().is_relative_to(root):
                raise SmokeUnqualified("SMOKE_PATH_ESCAPED")
            if path.startswith("tests/") and file.name.startswith("test_"):
                selected.add(path)
            else:
                candidate = root / "tests" / ("test_" + file.stem + ".py")
                if ((candidate.exists() and candidate.is_file())
                        or (require_complete
                            and (candidate.exists() or candidate.is_symlink()))):
                    selected.add(candidate.relative_to(root).as_posix())
    required: tuple[str, ...] = ()
    if _PAPER_STAGE_SOURCES.intersection(changed):
        required += (_PAPER_STAGE_TEST,)
    # Identity-reviewed ownership keeps the same fixed-dependency rule as the
    # paper stage pin: a registry fires when any changed path appears as a
    # quoted string literal in its chain text, contributes exactly its own
    # owning modules, cannot be lost to alphabetic ties or the module cap,
    # and an unavailable module fails the check.
    for chain_text, tests in identity_registries:
        if any(_quoted_path_in(chain_text, path) for path in changed):
            required += tests
    for path, chain, tests in _IDENTITY_PIN_REGISTRIES:
        if any(member in changed for member in chain):
            required += (*tests, _REGISTRY_GUARD_TEST)
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
    if require_complete:
        # The protected merge group may use smoke only when every known
        # applicable module fits. Ordinary PR feedback keeps its old cap.
        for path in selected:
            file = root / path
            try:
                available = (not file.is_symlink() and file.is_file()
                             and file.resolve().is_relative_to(root)
                             and file.stat().st_size <= _MAX_MODULE_BYTES)
            except OSError:
                available = False
            if not available:
                raise SmokeUnqualified("SMOKE_APPLICABLE_TEST_UNAVAILABLE")
        complete = tuple(dict.fromkeys((*required, *sorted(selected))))
        if len(set(complete) - {_BASELINE}) > _MAX_SELECTED_MODULES:
            raise SmokeUnqualified("SMOKE_SELECTION_EXCEEDS_BUDGET")
        return tuple(dict.fromkeys((_BASELINE, *complete)))
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
    # reviewed-source registries are read from that commit, not the checkout.
    selected = select_modules(
        root, paths, identity_registries=_reviewed_registries(root, args.base),
    )
    # Registry keys can change without any chain member changing (a deferred
    # import that starts resolving when another PR adds its module), so the
    # live guard checks the candidate on every smoke run, not only on edits.
    if _REGISTRY_GUARD_TEST not in selected:
        selected = (*selected, _REGISTRY_GUARD_NODE)
    print(f"CI_PR_SMOKE selected_tests={len(selected)} changed_paths={len(paths)}",
          flush=True)
    try:
        # The GitHub job enforces its own overall timeout; subprocess is
        # additionally bounded to prevent a single slow test from stalling
        # PRs. The bound also covers the fixed identity-review ownership
        # modules (~61s warm locally on an M2; shared runners run slower),
        # while staying inside the pr_fast job's own minutes budget.
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short", *selected],
            cwd=root, check=False, timeout=330,
        )
    except subprocess.TimeoutExpired:
        print("CI_PR_SMOKE_TEST_BUDGET_EXHAUSTED", file=sys.stderr)
        return 1
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
