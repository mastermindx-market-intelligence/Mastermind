"""Public native-preflight failures in the incumbent fixed CI artifact.

Observe live framework exceptions, never logs/JUnit/private representations.
The source-qualified records grant no admission, permission or replay authority.
Repository diagnostics and their default writer/format remain unchanged.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
import os
from pathlib import Path
import stat
import unittest
try:
    import pytest
except ImportError:
    pytest = None  # Optional diagnostics never add a unittest dependency.

from scripts import ci_fixed_diagnostics as fixed
from scripts import native_unittest_diagnostics as native

ROOT = Path(__file__).resolve().parents[1]
UNIT_PATTERNS = (
    'test_application_turn_*.py', 'test_go_application_*.py',
    'test_application_http_transports.py', 'test_quota_continuity.py',
    'test_application_http_admission.py', 'test_application_http_realm_projection.py',
    'test_bailian_application_handler_composition.py', 'test_broker_prelease_deadline.py',
    'test_slot_release_custody.py', 'test_qwen_account_eligibility.py',
    'test_qwen_429_account_priority.py',
)
ROLLOUT_MODULES = frozenset(native.PREFIX + 'tests/' + name for name in (
    'test_go_native_stage.py', 'test_go_native_release.py', 'test_go_native_entry.py',
    'test_go_native_install.py', 'test_go_service_enrollment.py',
    'test_go_service_startup.py', 'test_application_http_native_startup.py',
)) | frozenset(native.PREFIX + 'rollout/' + name for name in (
    'test_native_generation.py', 'test_native_launcher_upgrade.py',
    'test_native_runtime_bindings.py',
)) | {'tests/test_native_launcher_successor_transition.py'}
PROFILES = frozenset(('native-admission-unit', 'native-admission-rollout'))


class PreflightDiagnostics(fixed.FixedDiagnostics):
    """Same bounded writer, separately scoped cooperative phase subdirectory.

    Framework callbacks retain rows checked against immutable public HEAD
    source and the closed selected phase. Same-process capture is cooperative,
    not origin authentication or test/permission authority. There is no log or
    serialized-dictionary ingestion path.
    """
    def __init__(self, catalog, directory):
        self._observed_rows = {}
        super().__init__(catalog, directory)

    def failure_record(self, nodeid, phase, *, error=None, crash=None):
        value = self.catalog.failure(nodeid, phase, error=error, crash=crash)
        if value is None:
            self.truncated = True
        elif len(self.failures) < fixed.MAX_FAILURES:
            row = value.copy()
            self._observed_rows[len(self.failures)] = (row, tuple(sorted(row.items())))
            self.failures.append(row)
        else:
            self.truncated = True
        self.flush()

    def _closed(self):
        if (not fixed.re.fullmatch(r'[a-f0-9]{40}', self.catalog.head or '')
                or type(self.truncated) is not bool or self.progress != []
                or type(self.failures) is not list or len(self.failures) > fixed.MAX_FAILURES
                or set(self._observed_rows) != set(range(len(self.failures)))):
            return False
        for index, row in enumerate(self.failures):
            admitted = self._observed_rows[index]
            if (type(row) is not dict or set(row) != native.FIELDS
                    or admitted[0] is not row or admitted[1] != tuple(sorted(row.items()))):
                return False
            source = self.catalog.source(row['module'])
            if (source is None or row['phase'] not in fixed.PHASES
                    or type(row['kind']) is not str or row['kind'] not in {*fixed.KINDS.values(), 'UNKNOWN'}
                    or (row['case'] is not None and row['case'] not in source['cases'])
                    or (row['function'] is not None and row['function'] not in source['functions'])
                    or (row['line'] is not None and (type(row['line']) is not int or not 0 < row['line'] <= source['lines']))):
                return False
        return True


def _writer(profile):
    """The existing per-job private directory is the sole artifact destination."""
    try:
        if profile not in PROFILES:
            return None
        raw = os.environ.get('MMX_CI_FIXED_DIAGNOSTICS_DIR')
        if raw is None:
            return None
        parent = Path(raw)
        info = parent.lstat()
        if (not parent.is_absolute() or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != stat.S_IRWXU):
            return None
        catalog = fixed.PublicCatalog(ROOT, native=True)
        if profile == 'native-admission-unit':
            catalog.blobs = {name: blob for name, blob in catalog.blobs.items()
                if name.startswith(native.PREFIX + 'tests/')
                and any(fnmatchcase(name.rsplit('/', 1)[-1], pattern) for pattern in UNIT_PATTERNS)}
        else:
            ordinary = fixed.PublicCatalog(ROOT)
            if ordinary.head != catalog.head:
                return None
            extra = 'tests/test_native_launcher_successor_transition.py'
            if extra in ordinary.blobs:
                catalog.blobs[extra] = ordinary.blobs[extra]
            catalog.blobs = {name: blob for name, blob in catalog.blobs.items() if name in ROLLOUT_MODULES}
        if catalog.head is None:
            return None
        directory = parent / profile
        directory.mkdir(mode=stat.S_IRWXU)  # No overwrite/reuse of a prior phase.
        return PreflightDiagnostics(catalog, directory)
    except Exception:
        return None  # Optional capture must never change the original result.


def unittest_runner(*, verbosity=2):
    diagnostics = _writer('native-admission-unit')
    class Result(unittest.TextTestResult):
        def observe(self, test, error):
            if diagnostics is None:
                return
            try:
                for selection in native.OWNER_SELECTIONS:
                    node = native._node(test, diagnostics.catalog, 'tests', selection)
                    if node is not None:
                        diagnostics.failure_record(node, 'call', error=error)
                        return
                    holder = native._holder(test, diagnostics.catalog, 'tests', selection)
                    if holder is not None:
                        module, phase, _ = holder
                        diagnostics.failure_record(module, phase, error=error)
                        return
                diagnostics.truncated = True
                diagnostics.flush()
            except Exception:
                pass
        def addFailure(self, test, error):
            super().addFailure(test, error); self.observe(test, error[1])
        def addError(self, test, error):
            super().addError(test, error); self.observe(test, error[1])
        def addSubTest(self, test, subtest, error):
            super().addSubTest(test, subtest, error)
            if error is not None: self.observe(test, error[1])
        def addUnexpectedSuccess(self, test):
            super().addUnexpectedSuccess(test); self.observe(test, None)
    return unittest.TextTestRunner(verbosity=verbosity, resultclass=Result)


# Loaded explicitly only by the existing native rollout pytest command.
_PYTEST_WRITER = None


def pytest_configure(config):
    global _PYTEST_WRITER
    _PYTEST_WRITER = _writer('native-admission-rollout')


def pytest_unconfigure(config):
    global _PYTEST_WRITER
    _PYTEST_WRITER = None


def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if _PYTEST_WRITER is not None and report.failed:
        try:
            _PYTEST_WRITER.failure_record(item.nodeid, call.when,
                error=call.excinfo.value if call.excinfo is not None else None)
        except Exception:
            pass


if pytest is not None:
    pytest_runtest_makereport = pytest.hookimpl(hookwrapper=True)(pytest_runtest_makereport)


def pytest_collectreport(report):
    if _PYTEST_WRITER is not None and report.failed:
        try:
            _PYTEST_WRITER.failure_record(report.nodeid, 'collect',
                crash=getattr(report.longrepr, 'reprcrash', None))
        except Exception:
            pass
