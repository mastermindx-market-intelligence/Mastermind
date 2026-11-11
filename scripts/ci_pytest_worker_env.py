"""Per-worker temp-directory scoping for parallel shard runs (hosted CI only).

Loaded with ``-p`` in the parallel shard argv (see ``ci_pytest.pytest_argv``),
so each pytest-xdist worker process applies it at plugin-import time -- before
any test, fixture or nested child asks ``tempfile`` for a directory.

Why: the custody guards in this repository (acceptance maintenance, native
fabric current-source observation) resolve a fixture's whole ancestor chain
from ``/`` with open/fstat plus a double-stat identity check (mtime, ctime,
nlink included).  Machine-global ``/tmp`` sits in every such chain whenever a
fixture lives there, and under ``-n 4`` the four workers churn ``/tmp``
constantly -- production ``mkdtemp`` sites and nested child suites create and
remove entries in it, flipping an ancestor's identity between the two stats
(CI runs 42994920108 shard 0 "retained supersession entry is unsafe", shard 1
"changed_during_read").  This plugin scopes ``TMPDIR`` so every other
``tempfile`` consumer lands in the worker's own quiet root, whose ancestor
chain only this worker touches (a worker runs its own tests serially, so
nothing races underneath it).

The root lives under ``$HOME/mmx`` rather than ``RUNNER_TEMP`` because the
first scoped attempt, parked under ``RUNNER_TEMP`` (``/home/runner/work/
_temp/...``), tripped three independent validators on CI run 43015530899:
the custody component alphabet rejects path components that start with an
underscore (``custody_path_invalid``, shard 1), the capacity artifact
ancestor walk refuses RUNNER_TEMP's sticky-shared-root ancestors outright
-- it authenticates exactly one /tmp-style sticky root and requires every
other ancestor free of group/other-write bits (``SOURCE_METADATA_INVALID``
for the whole capacity module, shard 2) -- and the longer prefix crossed
the 103-byte AF_UNIX bound the socket constructors enforce ("AF_UNIX path
too long", shard 0; "invalid principal Company host binding", shard 1).
The $HOME placement keeps components clean, ownership at the control uid,
ancestor modes free of group/other-write bits, and paths short.

Serial argv never loads this plugin; local runs without ``RUNNER_TEMP`` keep
today's behavior unchanged.  The scoped roots are deliberately not cleaned
up: hosted runners are ephemeral, and a mid-run cleanup would itself churn a
shared ancestor.
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
    home = os.environ.get("HOME", "").strip()
    if not runner_temp or not home or workers in _SERIAL_VALUES:
        return None
    try:
        # One root per process: workers and the controller each get their own,
        # created at bring-up (before any test runs), so no sibling ever
        # creates an entry inside another process's chain during the run.
        root = Path(home) / "mmx" / f"w{os.getpid()}"
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A refused mkdir degrades to today's unscoped behavior; it must never
        # fail the run.
        return None
    os.environ["TMPDIR"] = str(root)
    return root


_ROOT = _apply()
