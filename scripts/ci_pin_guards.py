"""Early standalone source-identity guard suite for every CI event.

The pinned modules below assert the exact identity of repository source --
sha256 full-file pins, reviewed-site token scans, D8 protected-default
topology, reviewed release tokens and the overnight tool wiring -- using
only the checked-out source tree: no network, no service fixtures and no
privileged credentials. Four modules move out of the six canonical pytest
shards (``ci/pytest_exclusions.toml``); two protected modules also stay in
the shards. All six run in ``Pin and identity guards`` on every PR, merge
group, protected push and manual CI run, so moving their placement never
removes coverage when no reusable merge-group proof exists.

This is placement only. The assertions are byte-identical; discovery and
coverage for every other module are unchanged, and the fail-closed fan-in
gate still refuses any non-success result from this job.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from scripts import ci_pytest

# Exact modules moved out of the canonical shards into the early job.
# Every entry must also appear in ci/pytest_exclusions.toml with a
# replacement_gate naming this job; tests/test_ci_pin_guards.py enforces
# that the two lists stay identical and disjoint from shard coverage.
EXCLUDED_GUARD_MODULES: tuple[str, ...] = (
    "tests/test_ceo_submit_armed_composition.py",
    "tests/test_hermes_fabric_native_identity_review.py",
    "tests/test_overnight.py",
    "tests/test_workspace_fabric_review_pins.py",
)

# Same identity-guard family that must ALSO keep running inside the canonical
# shards: the protected-executive prefix policy (ci_pytest.PROTECTED_PREFIXES)
# forbids excluding these modules, so the early job deliberately runs them a
# second time. The duplicated cost is measured in seconds; the early run is
# what catches a churned pin in minutes instead of at full proof depth.
SHARD_RESIDENT_GUARD_MODULES: tuple[str, ...] = (
    "tests/test_executive_fabric_release_identity_review.py",
    "tests/test_executive_reviewed_site_identity_tokens.py",
)

GUARD_MODULES: tuple[str, ...] = (
    *EXCLUDED_GUARD_MODULES,
    *SHARD_RESIDENT_GUARD_MODULES,
)


def resolve_modules(root: Path) -> tuple[str, ...]:
    """Fail closed unless every pinned guard module exists in the checkout."""
    if not GUARD_MODULES:
        raise ci_pytest.PolicyError("guard module manifest is empty")
    missing = [path for path in GUARD_MODULES if not (root / path).is_file()]
    if missing:
        raise ci_pytest.PolicyError(f"guard modules missing: {missing}")
    duplicate = len(set(GUARD_MODULES)) != len(GUARD_MODULES)
    if duplicate:
        raise ci_pytest.PolicyError("guard module manifest contains duplicates")
    return GUARD_MODULES


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (defaults to the checkout that contains this script)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the resolved guard module set and exit without running pytest",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve() if args.root else ci_pytest.repo_root()
    try:
        modules = resolve_modules(root)
    except ci_pytest.PolicyError as error:
        print(f"ci_pin_guards policy error: {error}", file=sys.stderr)
        return 2
    print(
        f"pin_guards modules={len(modules)} "
        + " ".join(modules),
        flush=True,
    )
    if args.plan_only:
        return 0
    completed = subprocess.run(ci_pytest.pytest_argv(modules), cwd=root, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
