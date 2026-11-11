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
"changed_during_read").  This plugin scopes ``TMPDIR`` so every ``tempfile``
consumer lands in the worker's own quiet root, whose ancestor chain only this
worker touches (a worker runs its own tests serially, so nothing races
underneath it).  A few dozen test fixtures deliberately pass ``dir="/tmp"``
for short AF_UNIX socket paths; while scoping is active those are redirected
into the same quiet root too (the scoped prefix is just as short), so no
pytest-world process creates or removes entries in ``/tmp`` itself mid-run.

The scoped root lives under ``/tmp/mmx`` because both alternatives were
refused by real validators on hosted runners:

* ``RUNNER_TEMP`` (run 43015530899): the ``_temp`` component starts with an
  underscore, which the custody component alphabet rejects outright; the
  path is a second sticky shared root the capacity artifact ancestor walk
  does not authenticate; and the prefix crosses the 103-byte AF_UNIX bound
  the socket constructors enforce.
* ``$HOME`` (run 43028788599): the hosted image's ``/home`` carries a
  default POSIX ACL (``system.posix_acl_default``), and the capacity
  ancestor walk refuses ANY ancestor xattr name outside its two approved
  macOS names, so every home-rooted chain fails wholesale
  (``SOURCE_METADATA_INVALID`` for the whole capacity module).

``/tmp/mmx`` satisfies every guard at once: the chain crosses exactly the one
sticky shared root the walk authenticates (1777 root:root, xattr-free),
components are custody-alphabet-clean, ownership stays at the control uid,
and no ancestor carries group/other-write bits.

Serial argv never loads this plugin; local runs without ``RUNNER_TEMP`` keep
today's behavior unchanged.  The scoped roots are deliberately not cleaned
up: hosted runners are ephemeral, and a mid-run cleanup would itself churn a
shared ancestor.
"""

import os
import tempfile
from pathlib import Path

# The switch values that keep the exact serial argv never scope either, so a
# nested process that re-imports this module without the parallel argv stays
# on the parent worker's already-scoped TMPDIR.
_SERIAL_VALUES = ("", "0", "1")

# Captured at module import so the redirect subclass always derives from the
# stdlib class, never from a previously-applied redirect (reload chains).
_UNSCOPED_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


def _apply() -> Path | None:
    runner_temp = os.environ.get("RUNNER_TEMP", "").strip()
    workers = os.environ.get("CI_PYTEST_WORKERS", "").strip()
    tmp_root = (os.environ.get("TMPDIR") or "/tmp").rstrip("/") or "/tmp"
    if not runner_temp or workers in _SERIAL_VALUES:
        return None
    try:
        # One root per process: workers and the controller each get their own,
        # created at bring-up (before any test runs), so no sibling ever
        # creates an entry inside another process's chain during the run.
        # Honoring an already-scoped TMPDIR nests nested builders' roots
        # inside their parent worker's quiet root.
        root = Path(tmp_root) / "mmx" / f"w{os.getpid()}"
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A refused mkdir degrades to today's unscoped behavior; it must never
        # fail the run.
        return None
    os.environ["TMPDIR"] = str(root)
    # tempfile.gettempdir() caches its first answer; pin the cache too so
    # every dir=None consumer in this process lands in the quiet root even
    # if something queried it before plugin load.
    tempfile.tempdir = str(root)

    # Redirect the deliberate dir="/tmp" tempfile calls (short AF_UNIX socket
    # roots in test fixtures) into this process's quiet root while scoping is
    # active, so /tmp itself never churns mid-run. Only the exact literal is
    # redirected: every prefix, suffix and semantic is untouched, and any
    # other dir argument (including None) keeps stdlib behavior. mkdtemp is a
    # plain function, so a wrapper is protocol-complete; TemporaryDirectory
    # is a class that tests also use as a class (they read and monkeypatch
    # its .cleanup), so the redirect must be a subclass -- a function wrapper
    # breaks that class surface (CI run 43038560847 shard 5,
    # "'function' object has no attribute 'cleanup'").
    unscoped_mkdtemp = tempfile.mkdtemp

    def _scoped_dir(directory):
        return str(root) if directory == "/tmp" else directory

    def _mkdtemp(suffix=None, prefix=None, dir=None, **kwargs):
        return unscoped_mkdtemp(
            suffix=suffix, prefix=prefix, dir=_scoped_dir(dir), **kwargs
        )

    class _ScopedTemporaryDirectory(_UNSCOPED_TEMPORARY_DIRECTORY):
        def __init__(self, suffix=None, prefix=None, dir=None, **kwargs):
            super().__init__(
                suffix=suffix, prefix=prefix, dir=_scoped_dir(dir), **kwargs
            )

    tempfile.mkdtemp = _mkdtemp
    tempfile.TemporaryDirectory = _ScopedTemporaryDirectory
    return root


_ROOT = _apply()
