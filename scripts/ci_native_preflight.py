"""Public native-preflight failures/timings in the incumbent fixed CI artifact.

Observe live framework exceptions, never logs/JUnit/private representations.
The source-qualified records grant no admission, permission or replay authority.
Repository diagnostics and their default writer/format remain unchanged.
Unittest's runner envelope includes class/module fixtures but excludes discovery
and imports before run(); pytest's session envelope includes collection, not
interpreter/plugin startup. Neither is the entire workflow-stage elapsed time.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
import json
import math
import os
from pathlib import Path
import stat
import time
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
    'test_application_auto_request.py', 'test_application_cross_pool_auto.py',
    'test_application_registered_pool_selection.py', 'test_application_registered_pool_composition.py',
    'test_bailian_application_handler_composition.py', 'test_broker_prelease_deadline.py',
    'test_slot_release_custody.py', 'test_qwen_account_eligibility.py',
    'test_qwen_429_account_priority.py',
)
ROLLOUT_MODULES = frozenset(native.PREFIX + 'tests/' + name for name in (
    'test_go_native_stage.py', 'test_go_native_release.py', 'test_go_native_entry.py',
    'test_go_native_install.py', 'test_provider_application_transition.py',
    'test_quota_reset_native_stage.py', 'test_quota_reset_native_entry.py',
    'test_go_service_enrollment.py',
    'test_go_service_startup.py', 'test_application_http_native_startup.py',
)) | frozenset(native.PREFIX + 'rollout/' + name for name in (
    'test_native_generation.py', 'test_native_launcher_upgrade.py',
    'test_native_runtime_bindings.py',
)) | {'tests/test_native_launcher_successor_transition.py'}
PROFILES = frozenset(('native-admission-unit', 'native-admission-rollout'))
TIMING_SCHEMA = 'ci.fixed-diagnostics.native-timing.v1'
MAX_TIMINGS = 128
MAX_OBSERVATIONS = 1000000
MAX_SECONDS = 7200


class PreflightDiagnostics(fixed.FixedDiagnostics):
    """Same bounded writer, separately scoped cooperative phase subdirectory.

    Framework callbacks retain rows checked against immutable public HEAD
    source and the closed selected phase. Same-process capture is cooperative,
    not origin authentication or test/permission authority. There is no log or
    serialized-dictionary ingestion path.
    """
    def __init__(self, catalog, directory, *, profile=None):
        self._observed_rows = {}
        self.profile = profile
        self.timings = []
        self._observed_timings = []
        self.timing_observations = 0
        self.envelope = None
        self._envelope_started = None
        self._observed_envelope = None
        super().__init__(catalog, directory)

    def timing_unavailable(self):
        self.truncated = True
        self.flush()

    def begin_envelope(self, scope):
        expected = {'native-admission-unit': 'unittest_runner',
                    'native-admission-rollout': 'pytest_session'}.get(self.profile)
        if expected is None or scope != expected or self._envelope_started is not None or self.envelope is not None:
            self.timing_unavailable(); return
        started = time.monotonic_ns()
        if type(started) is not int or started < 0:
            self.timing_unavailable(); return
        self._envelope_started = (scope, started)

    def end_envelope(self, scope):
        started = self._envelope_started
        self._envelope_started = None
        if started is None:
            return
        ended = time.monotonic_ns()
        if (scope != started[0] or type(ended) is not int or ended < started[1]
                or ended - started[1] > MAX_SECONDS * 1000000000):
            self.timing_unavailable(); return
        self.envelope = dict(scope=scope, seconds=round((ended-started[1])/1000000000, 6))
        self._observed_envelope = (self.envelope, tuple(sorted(self.envelope.items())))
        self.flush()

    def timing_record(self, nodeid, phase, seconds):
        """Cooperative framework observation, never a grant or a result override.

        Parameter IDs are stripped by the existing exact-HEAD catalogue. Keep
        at most 128 slowest observations, not an exhaustive test/performance log.
        Unittest 'test' spans setUp/call/tearDown, excluding class/module setup;
        pytest phases retain the framework's actual report.duration.
        """
        phases = {'test'} if self.profile == 'native-admission-unit' else (
            {'setup', 'call', 'teardown'} if self.profile == 'native-admission-rollout' else set())
        if (type(phase) is not str or phase not in phases
                or type(seconds) not in (int, float) or not 0 <= seconds <= MAX_SECONDS
                or not math.isfinite(seconds)
                or type(self.timing_observations) is not int
                or self.timing_observations < 0
                or self.timing_observations >= MAX_OBSERVATIONS):
            self.timing_unavailable(); return
        value = self.catalog.failure(nodeid, 'call')
        if (value is None or value['case'] is None or len(value['module']) > 512
                or len(value['case']) > 256):
            self.timing_unavailable(); return
        row = dict(module=value['module'], case=value['case'], phase=phase,
                   seconds=round(seconds, 6))
        self.timing_observations += 1
        self.timings.append(row)
        self._observed_timings.append((row, tuple(sorted(row.items()))))
        if len(self.timings) > MAX_TIMINGS:
            index = min(range(len(self.timings)), key=lambda i: self.timings[i]['seconds'])
            self.timings.pop(index); self._observed_timings.pop(index)
            self.truncated = True
        self.flush()

    def _payload(self):
        value = super()._payload()
        if not self.timing_observations and self.envelope is None:
            return value  # Existing failure-only records remain byte-compatible.
        value.update(schema=TIMING_SCHEMA, timing_observations=self.timing_observations,
                     timings=sorted(self.timings, key=lambda row: -row['seconds']),
                     envelope=self.envelope)
        while (len(json.dumps(value, sort_keys=True, separators=(',', ':'),
                              allow_nan=False).encode('ascii')) > fixed.MAX_SNAPSHOT
                and value['timings']):
            value['timings'].pop(); value['truncated'] = True
        if len(json.dumps(value, sort_keys=True, separators=(',', ':'),
                          allow_nan=False).encode('ascii')) > fixed.MAX_SNAPSHOT:
            value = super()._payload(); value['truncated'] = True
        return value

    def _closed_timings(self):
        if (type(self.timings) is not list or len(self.timings) > MAX_TIMINGS
                or type(self.timing_observations) is not int
                or not len(self.timings) <= self.timing_observations <= MAX_OBSERVATIONS
                or type(self._observed_timings) is not list
                or len(self.timings) != len(self._observed_timings)):
            return False
        for row, admitted in zip(self.timings, self._observed_timings):
            if (type(row) is not dict or set(row) != {'module', 'case', 'phase', 'seconds'}
                    or admitted[0] is not row or admitted[1] != tuple(sorted(row.items()))):
                return False
            if (type(row['module']) is not str or type(row['case']) is not str
                    or type(row['phase']) is not str):
                return False
            source = self.catalog.cache.get(row['module'])
            phases = {'test'} if self.profile == 'native-admission-unit' else (
                {'setup', 'call', 'teardown'} if self.profile == 'native-admission-rollout' else set())
            if (source is None or row['case'] not in source['cases']
                    or type(row['module']) is not str or len(row['module']) > 512
                    or type(row['case']) is not str or len(row['case']) > 256
                    or row['phase'] not in phases or type(row['seconds']) not in (int, float)
                    or not 0 <= row['seconds'] <= MAX_SECONDS or not math.isfinite(row['seconds'])):
                return False
        if self.envelope is None:
            return self._observed_envelope is None
        row = self.envelope; admitted = self._observed_envelope
        expected = {'native-admission-unit': 'unittest_runner',
                    'native-admission-rollout': 'pytest_session'}.get(self.profile)
        return (type(row) is dict and set(row) == {'scope', 'seconds'}
            and type(admitted) is tuple and len(admitted) == 2 and admitted[0] is row
            and admitted[1] == tuple(sorted(row.items())) and expected is not None and row['scope'] == expected
            and type(row['seconds']) in (int, float) and math.isfinite(row['seconds'])
            and 0 <= row['seconds'] <= MAX_SECONDS)

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
        return self._closed_timings()


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
        return PreflightDiagnostics(catalog, directory, profile=profile)
    except Exception:
        return None  # Optional capture must never change the original result.


def unittest_runner(*, verbosity=2):
    diagnostics = _writer('native-admission-unit')
    class Result(unittest.TextTestResult):
        def startTestRun(self):
            super().startTestRun()
            if diagnostics is not None:
                try: diagnostics.begin_envelope('unittest_runner')
                except Exception:
                    try: diagnostics.timing_unavailable()
                    except Exception: pass
        def stopTestRun(self):
            if diagnostics is not None:
                try: diagnostics.end_envelope('unittest_runner')
                except Exception:
                    try: diagnostics.timing_unavailable()
                    except Exception: pass
            super().stopTestRun()
        def startTest(self, test):
            super().startTest(test)
            self._timed_test = None
            if diagnostics is not None:
                try:
                    for selection in native.OWNER_SELECTIONS:
                        node = native._node(test, diagnostics.catalog, 'tests', selection)
                        if node is not None:
                            started = time.monotonic_ns()
                            if type(started) is not int or started < 0:
                                raise ValueError()
                            self._timed_test = (test, node, started)
                            return
                    diagnostics.timing_unavailable()
                except Exception:
                    try: diagnostics.timing_unavailable()
                    except Exception: pass
        def stopTest(self, test):
            timed = self._timed_test
            self._timed_test = None
            if diagnostics is not None and timed is not None and timed[0] is test:
                try:
                    ended = time.monotonic_ns()
                    if type(ended) is not int or ended < timed[2]:
                        raise ValueError()
                    diagnostics.timing_record(timed[1], 'test', (ended - timed[2]) / 1000000000)
                except Exception:
                    try: diagnostics.timing_unavailable()
                    except Exception: pass
            super().stopTest(test)
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


def pytest_sessionstart(session):
    if _PYTEST_WRITER is not None:
        try: _PYTEST_WRITER.begin_envelope('pytest_session')
        except Exception:
            try: _PYTEST_WRITER.timing_unavailable()
            except Exception: pass


def pytest_sessionfinish(session, exitstatus):
    if _PYTEST_WRITER is not None:
        try: _PYTEST_WRITER.end_envelope('pytest_session')
        except Exception:
            try: _PYTEST_WRITER.timing_unavailable()
            except Exception: pass


def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if _PYTEST_WRITER is not None and report.failed:
        try:
            _PYTEST_WRITER.failure_record(item.nodeid, call.when,
                error=call.excinfo.value if call.excinfo is not None else None)
        except Exception:
            pass
    if _PYTEST_WRITER is not None:
        try:
            _PYTEST_WRITER.timing_record(item.nodeid, report.when, report.duration)
        except Exception:
            try: _PYTEST_WRITER.timing_unavailable()
            except Exception: pass


if pytest is not None:
    pytest_runtest_makereport = pytest.hookimpl(hookwrapper=True)(pytest_runtest_makereport)


def pytest_collectreport(report):
    if _PYTEST_WRITER is not None and report.failed:
        try:
            _PYTEST_WRITER.failure_record(report.nodeid, 'collect',
                crash=getattr(report.longrepr, 'reprcrash', None))
        except Exception:
            pass
