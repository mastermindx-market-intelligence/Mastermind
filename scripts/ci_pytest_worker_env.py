"""Per-worker temp-directory scoping for parallel shard runs (hosted CI only).

Loaded with ``-p`` in the parallel shard argv (see ``ci_pytest.pytest_argv``),
so each pytest-xdist worker process applies it at plugin-import time -- before
any test, fixture or nested child asks ``tempfile`` for a directory.

Why: the custody guards in this repository (acceptance maintenance, native
fabric current-source observation) resolve a fixture's whole ancestor chain
from ``/`` with open/fstat plus a double-stat identity check (mtime, ctime,
nlink included).  Machine-global ``/tmp`` sits in every such chain whenever a
fixture lives there, and under ``-n 4`` the four workers churn ``/tmp``
constantly -- pytest's own tmp root, production ``mkdtemp`` sites and nested
child suites all create and remove entries in it, flipping an ancestor's
identity between the two stats (CI runs 42994920108 shard 0 "retained
supersession entry is unsafe", shard 1 "changed_during_read").  Parking
pytest's basetemp under ``RUNNER_TEMP`` fixes pytest's own churn; this plugin
scopes ``TMPDIR`` the same way so every other ``tempfile`` consumer lands in
the worker's own quiet root, whose ancestor chain only this worker touches
(a worker runs its own tests serially, so nothing races underneath it).

Serial argv never loads this plugin; local runs without ``RUNNER_TEMP`` keep
today's behavior unchanged.
"""

import os
from pathlib import Path

# The switch values that keep the exact serial argv never scope either, so a
# nested process that re-imports this module without the parallel argv stays
# on the parent worker's already-scoped TMPDIR.
_SERIAL_VALUES = ("", "0", "1")


def _apply() -> Path | None:
    runner_temp = os.environ.get("RUNNER_TEMP", "").strip()
    workers = os.environ.get("CI_PYTEST_WORKERS", "").strip()
    if not runner_temp or workers in _SERIAL_VALUES:
        return None
    try:
        # One root per process: workers and the controller each get their own,
        # created at bring-up (before any test runs), so no sibling ever
        # creates an entry inside another process's chain during the run.
        root = Path(runner_temp) / "pytest-worker-tmp" / f"p{os.getpid()}"
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A refused mkdir degrades to today's unscoped behavior; it must never
        # fail the run.
        return None
    os.environ["TMPDIR"] = str(root)
    return root


_ROOT = _apply()
