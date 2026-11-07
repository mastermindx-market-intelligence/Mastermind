"""Offline regression tests for the candidate observation diagnostic overlay."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"


def load(name, path):
    delivery = types.ModuleType("artifact_delivery")
    reader = types.ModuleType("artifact_reader")
    reader.canonical = lambda value: json.dumps(value, sort_keys=True,
                                                 separators=(",", ":")).encode()
    reader.strict_json = json.loads
    prior = {key: sys.modules.get(key) for key in ("artifact_delivery", "artifact_reader")}
    sys.modules["artifact_delivery"] = delivery
    sys.modules["artifact_reader"] = reader
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for key, value in prior.items():
            if value is None:
                del sys.modules[key]
            else:
                sys.modules[key] = value


candidate = load("candidate_run_observation_delivery", NATIVE / "candidate/run_observation_delivery.py")
source = load("source_run_observation_delivery", NATIVE / "source/run_observation_delivery.py")


class Chain:
    fd = 1
    def __init__(self): self.closed = 0
    def verify(self): pass
    def close(self): self.closed += 1


class Diagnostics(unittest.TestCase):
    def configure(self, module, *, transport=None, validate=None, publish=None,
                  qualify=None, reserve=None):
        chain = Chain()
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        patches = [
            mock.patch.object(module, "qualify", side_effect=qualify or (lambda *_a, **_k: evidence)),
            mock.patch.object(module.delivery, "reserve_destination", side_effect=reserve or (lambda _d: chain), create=True),
            mock.patch.object(module.delivery, "write_exclusive", create=True),
            mock.patch.object(module.delivery, "transport", side_effect=transport or (lambda *_a, **_k: b"response"), create=True),
            mock.patch.object(module, "validate_response", side_effect=validate or (lambda *_a: {"status": "observed"})),
            mock.patch.object(module.delivery, "publish_receipt", side_effect=publish or (lambda *_a, **_k: None), create=True),
            mock.patch.object(module.time, "time", return_value=1.0),
        ]
        return chain, patches

    def run_observe(self, module, **kwargs):
        chain, patches = self.configure(module, **kwargs)
        with contextlib.ExitStack() as stack:
            for patch in patches: stack.enter_context(patch)
            receipt = module.observe({"run_id": "fixture"}, "destination")
        return receipt, chain

    def main_result(self, module, request_error=None, observe_error=None):
        out, err = io.StringIO(), io.StringIO()
        request = {"run_id": "fixture"}
        with mock.patch.object(module, "request_for", side_effect=request_error or (lambda *_a, **_k: request)), \
             mock.patch.object(module, "observe", side_effect=observe_error or (lambda *_a: {"state": "OBSERVED"})), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = module.main(["fixture", "--root", "root", "--destination", "dest"])
        return rc, out.getvalue(), err.getvalue()

    def boundary_main(self, module, fault="normal"):
        """Run actual main -> observe against inert incumbent boundaries."""
        calls, out, err = [], io.StringIO(), io.StringIO()
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        chain = Chain()
        request = {"run_id": "fixture"}
        def qualify(*_a, **_k):
            calls.append("qualify")
            if fault == "qualification" and len(calls) == 1: raise ValueError("secret")
            if fault == "pretransportrevalidation" and calls.count("qualify") == 2: raise ValueError("secret")
            if fault == "postresponserevalidation" and calls.count("qualify") == 3: raise ValueError("secret")
            if fault == "publicationcallback" and calls.count("qualify") == 4: raise ValueError("secret")
            return evidence
        def reserve(_destination):
            calls.append("reserve")
            if fault == "destinationreservation": raise ValueError("secret")
            return chain
        def write(*_a):
            calls.append("write")
            if fault == "intentwrite": raise ValueError("secret")
        def transport(*_a, **_k):
            calls.append("transport")
            if fault == "transport": raise ValueError("secret")
            return b"response"
        def validate(*_a):
            calls.append("validate")
            if fault == "responsevalidation": raise ValueError("secret")
            return {"status": "unavailable" if fault == "unavailable" else "observed"}
        def publish(_chain, _receipt, _files, *, verify_source):
            calls.append("publish")
            if fault == "publicationcallback": verify_source()
            if fault == "publication": raise ValueError("secret")
        if fault == "cleanup":
            def close():
                chain.closed += 1
                raise ValueError("secret")
            chain.close = close
        with mock.patch.object(module, "request_for", return_value=request), \
             mock.patch.object(module, "qualify", side_effect=qualify), \
             mock.patch.object(module.delivery, "reserve_destination", side_effect=reserve, create=True), \
             mock.patch.object(module.delivery, "write_exclusive", side_effect=write, create=True), \
             mock.patch.object(module.delivery, "transport", side_effect=transport, create=True), \
             mock.patch.object(module, "validate_response", side_effect=validate), \
             mock.patch.object(module.delivery, "publish_receipt", side_effect=publish, create=True), \
             mock.patch.object(module.time, "time", return_value=1.0), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = module.main(["fixture", "--root", "root", "--destination", "dest"])
        return rc, out.getvalue(), err.getvalue(), calls

    def diagnostic(self, text):
        line = text.splitlines()[-1]
        self.assertRegex(line, r"^run_observation_delivery\.py: diagnostic phase=[a-z_]+ category=[a-z_]+ last_phase=[a-z_]+ last_category=[a-z_]+ transport=(not_attempted|attempted_unconfirmed|response_received)$")
        return dict(field.split("=", 1) for field in line.split()[2:])

    def test_candidate_is_an_overlay_and_source_preimage_is_unchanged(self):
        self.assertEqual(__import__("hashlib").sha256((NATIVE / "source/run_observation_delivery.py").read_bytes()).hexdigest(),
                         "db54aa15630e29535980e0fccb406c3904cc7df92c66d17ec520f40d4fd5447b")
        self.assertNotEqual((NATIVE / "candidate/run_observation_delivery.py").read_bytes(),
                            (NATIVE / "source/run_observation_delivery.py").read_bytes())

    def test_success_preserves_stdout_rc_and_strict_json(self):
        candidate_result = self.main_result(candidate)
        source_result = self.main_result(source)
        self.assertEqual(candidate_result[:2], source_result[:2])
        self.assertEqual(candidate_result[0], 0)
        self.assertEqual(json.loads(candidate_result[1])["state"], "OBSERVED")
        fields = self.diagnostic(candidate_result[2])
        self.assertEqual(fields["transport"], "not_attempted")

    def test_refusal_and_state_reset_do_not_leak(self):
        refused = self.main_result(candidate, request_error=candidate.ObservationScopeNotAdmitted())
        self.assertEqual((refused[0], refused[1]), (75, '{"state":"REFUSED","reason":"observation_scope_not_admitted"}\n'))
        self.assertEqual(self.diagnostic(refused[2])["category"], "scope_refusal")
        clean = self.main_result(candidate)
        self.assertEqual(self.diagnostic(clean[2])["category"], "none")

    def test_transport_states_and_inner_failure_survive_publication_failure(self):
        chain, patches = self.configure(candidate, transport=ValueError("secret\n" + "x" * 10000),
                                        publish=OSError("late"))
        token = candidate._diagnostic_start()
        try:
            with contextlib.ExitStack() as stack:
                for patch in patches: stack.enter_context(patch)
                with self.assertRaises(OSError):
                    candidate.observe({"run_id": "fixture"}, "destination")
            state = candidate._DIAGNOSTIC.get()
            self.assertEqual((state["phase"], state["category"]), ("transport", "value_error"))
            self.assertEqual((state["last_phase"], state["last_category"]), ("publication", "os_error"))
        finally:
            candidate._DIAGNOSTIC.reset(token)
        self.assertEqual(chain.closed, 1)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(candidate, "request_for", return_value={"run_id": "fixture"}), \
             mock.patch.object(candidate, "observe", side_effect=ValueError("top-secret")), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(candidate.main(["fixture", "--root", "root", "--destination", "dest"]), 75)
        self.assertNotIn("top-secret", err.getvalue())
        self.assertEqual(self.diagnostic(err.getvalue())["phase"], "request")

    def test_observe_records_transport_and_response_without_extra_calls(self):
        calls = []
        def transport(*_a, **_k):
            calls.append("transport")
            return b"response"
        receipt, chain = self.run_observe(candidate, transport=transport)
        self.assertEqual(receipt["state"], "OBSERVED")
        self.assertEqual(calls, ["transport"])
        self.assertEqual(chain.closed, 1)

    def test_diagnostic_sink_failures_do_not_change_result(self):
        for write_error, flush_error in ((OSError(), None), (None, OSError())):
            with self.subTest(write_error=write_error is not None):
                stderr = types.SimpleNamespace(
                    write=mock.Mock(side_effect=write_error),
                    flush=mock.Mock(side_effect=flush_error),
                )
                out = io.StringIO()
                with mock.patch.object(candidate, "request_for", return_value={"run_id": "fixture"}), \
                     mock.patch.object(candidate, "observe", return_value={"state": "OBSERVED"}), \
                     mock.patch.object(sys, "stderr", stderr), contextlib.redirect_stdout(out):
                    self.assertEqual(candidate.main(["fixture", "--root", "root", "--destination", "dest"]), 0)
                self.assertEqual(out.getvalue(), '{"state":"OBSERVED"}\n')

        out = io.StringIO()
        with mock.patch.object(candidate, "request_for", side_effect=candidate.ObservationScopeNotAdmitted()), \
             mock.patch.object(sys, "stderr", stderr), contextlib.redirect_stdout(out):
            self.assertEqual(candidate.main(["fixture", "--root", "root", "--destination", "dest"]), 75)
        self.assertEqual(out.getvalue(), '{"state":"REFUSED","reason":"observation_scope_not_admitted"}\n')

        with mock.patch.object(candidate, "request_for", return_value={"run_id": "fixture"}), \
             mock.patch.object(candidate, "observe", side_effect=KeyboardInterrupt()), \
             mock.patch.object(sys, "stderr", stderr):
            with self.assertRaises(KeyboardInterrupt):
                candidate.main(["fixture", "--root", "root", "--destination", "dest"])

    def test_deduplication_retains_exception_identity_not_reusable_ids(self):
        token = candidate._diagnostic_start()
        try:
            first = ValueError("first")
            second = ValueError("second")
            candidate._diagnostic_phase("transport")
            candidate._diagnostic_failure(first)
            candidate._diagnostic_phase("publication")
            candidate._diagnostic_failure(second)
            state = candidate._DIAGNOSTIC.get()
            self.assertIs(state["seen"][0], first)
            self.assertIs(state["seen"][1], second)
            self.assertEqual((state["last_phase"], state["last_category"]),
                             ("publication", "value_error"))
        finally:
            candidate._DIAGNOSTIC.reset(token)

    def test_real_main_candidate_matches_preimage_boundary_matrix(self):
        faults = ("normal", "qualification", "destinationreservation", "intentwrite",
                  "pretransportrevalidation", "transport", "responsevalidation",
                  "postresponserevalidation", "publication", "publicationcallback",
                  "cleanup", "unavailable")
        for fault in faults:
            with self.subTest(fault=fault):
                expected = self.boundary_main(source, fault)
                actual = self.boundary_main(candidate, fault)
                self.assertEqual(actual[0:2], expected[0:2])
                self.assertEqual(actual[3], expected[3])
                diagnostic = self.diagnostic(actual[2])
                if fault in {"qualification", "destinationreservation"}:
                    self.assertEqual(diagnostic["phase"], fault)
                self.assertNotIn("secret", actual[2])

    def test_closed_categories_and_malicious_values_are_bounded(self):
        expected = {
            candidate.ObservationScopeNotAdmitted(): "scope_refusal", OSError(): "os_error",
            ValueError(): "value_error", TypeError(): "type_error", KeyError(): "key_error",
            RecursionError(): "recursion_error", candidate.subprocess.SubprocessError(): "subprocess_error",
            candidate.sqlite3.Error(): "sqlite_error", KeyboardInterrupt(): "other_error",
        }
        self.assertEqual({candidate._diagnostic_category(exc) for exc in expected}, set(expected.values()))
        dangerous = "SECRET\\n/path/run-id=" + "x" * 20000
        rc, stdout, stderr = self.main_result(candidate, observe_error=ValueError(dangerous))
        self.assertEqual((rc, stdout), (75, '{"state":"REFUSED","reason":"original_run_observation_unconfirmed"}\n'))
        self.assertLessEqual(len(stderr), 220)
        self.assertNotIn("SECRET", stderr)
        self.assertNotIn("/path", stderr)

    def test_phase_fault_seams_preserve_existing_exception_and_cleanup(self):
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        cases = {
            "qualification": {"qualify": ValueError("secret")},
            "destinationreservation": {"reserve": ValueError("secret")},
            "intentwrite": {"write": ValueError("secret")},
            "transport": {"transport": ValueError("secret")},
            "responsevalidation": {"validate": ValueError("secret")},
            "publication": {"publish": ValueError("secret")},
        }
        for phase, fault in cases.items():
            with self.subTest(phase=phase):
                chain = Chain()
                qualify = fault.get("qualify", lambda *_a, **_k: evidence)
                reserve = fault.get("reserve", lambda _d: chain)
                token = candidate._diagnostic_start()
                try:
                    with mock.patch.object(candidate, "qualify", side_effect=qualify), \
                         mock.patch.object(candidate.delivery, "reserve_destination", side_effect=reserve, create=True), \
                         mock.patch.object(candidate.delivery, "write_exclusive", side_effect=fault.get("write"), create=True), \
                         mock.patch.object(candidate.delivery, "transport", side_effect=fault.get("transport", lambda *_a, **_k: b"response"), create=True), \
                         mock.patch.object(candidate, "validate_response", side_effect=fault.get("validate", lambda *_a: {"status": "observed"})), \
                         mock.patch.object(candidate.delivery, "publish_receipt", side_effect=fault.get("publish", lambda *_a, **_k: None), create=True), \
                         mock.patch.object(candidate.time, "time", return_value=1.0):
                        if phase in {"qualification", "destinationreservation", "intentwrite", "publication"}:
                            with self.assertRaises(ValueError):
                                candidate.observe({"run_id": "fixture"}, "destination")
                        else:
                            self.assertEqual(candidate.observe({"run_id": "fixture"}, "destination")["state"], "UNAVAILABLE")
                    state = candidate._DIAGNOSTIC.get()
                    if phase not in {"qualification", "destinationreservation"}:
                        self.assertEqual(state["phase"], phase)
                finally:
                    candidate._DIAGNOSTIC.reset(token)
                if phase not in {"qualification", "destinationreservation"}:
                    self.assertEqual(chain.closed, 1)

    def test_pre_and_post_revalidation_and_cleanup_fault_phases(self):
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        for target, values in (("pretransportrevalidation", [evidence, ValueError("x")]),
                               ("postresponserevalidation", [evidence, evidence, ValueError("x")])):
            with self.subTest(target=target):
                chain = Chain()
                token = candidate._diagnostic_start()
                try:
                    with mock.patch.object(candidate, "qualify", side_effect=values), \
                         mock.patch.object(candidate.delivery, "reserve_destination", return_value=chain, create=True), \
                         mock.patch.object(candidate.delivery, "write_exclusive", create=True), \
                         mock.patch.object(candidate.delivery, "transport", return_value=b"response", create=True), \
                         mock.patch.object(candidate, "validate_response", return_value={"status": "observed"}), \
                         mock.patch.object(candidate.delivery, "publish_receipt", create=True), \
                         mock.patch.object(candidate.time, "time", return_value=1.0):
                        receipt = candidate.observe({"run_id": "fixture"}, "destination")
                    self.assertEqual(receipt["state"], "UNAVAILABLE")
                    self.assertEqual(candidate._DIAGNOSTIC.get()["phase"], target)
                finally:
                    candidate._DIAGNOSTIC.reset(token)
                self.assertEqual(chain.closed, 1)

        class BrokenChain(Chain):
            def close(self):
                super().close()
                raise ValueError("secret")
        chain = BrokenChain()
        token = candidate._diagnostic_start()
        try:
            with mock.patch.object(candidate, "qualify", return_value=evidence), \
                 mock.patch.object(candidate.delivery, "reserve_destination", return_value=chain, create=True), \
                 mock.patch.object(candidate.delivery, "write_exclusive", create=True), \
                 mock.patch.object(candidate.delivery, "transport", return_value=b"response", create=True), \
                 mock.patch.object(candidate, "validate_response", return_value={"status": "observed"}), \
                 mock.patch.object(candidate.delivery, "publish_receipt", create=True), \
                 mock.patch.object(candidate.time, "time", return_value=1.0):
                with self.assertRaises(ValueError):
                    candidate.observe({"run_id": "fixture"}, "destination")
            self.assertEqual(candidate._DIAGNOSTIC.get()["phase"], "cleanup")
        finally:
            candidate._DIAGNOSTIC.reset(token)

    def test_publication_callback_failure_precedes_publisher_wrapper(self):
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        chain = Chain()
        calls = [0]
        def qualify(*_a, **_k):
            calls[0] += 1
            if calls[0] == 4:
                raise OSError("secret callback path")
            return evidence
        def publisher(_chain, _receipt, _files, *, verify_source):
            try:
                verify_source()
            except Exception:
                raise ValueError("publisher wrapper")
        token = candidate._diagnostic_start()
        try:
            with mock.patch.object(candidate, "qualify", side_effect=qualify), \
                 mock.patch.object(candidate.delivery, "reserve_destination", return_value=chain, create=True), \
                 mock.patch.object(candidate.delivery, "write_exclusive", create=True), \
                 mock.patch.object(candidate.delivery, "transport", return_value=b"response", create=True), \
                 mock.patch.object(candidate, "validate_response", return_value={"status": "observed"}), \
                 mock.patch.object(candidate.delivery, "publish_receipt", side_effect=publisher, create=True), \
                 mock.patch.object(candidate.time, "time", return_value=1.0):
                with self.assertRaises(ValueError):
                    candidate.observe({"run_id": "fixture"}, "destination")
            state = candidate._DIAGNOSTIC.get()
            self.assertEqual((state["phase"], state["category"]),
                             ("publicationrevalidation", "os_error"))
            self.assertEqual((state["last_phase"], state["last_category"]),
                             ("publication", "value_error"))
        finally:
            candidate._DIAGNOSTIC.reset(token)


if __name__ == "__main__":
    unittest.main()

# Fixed-directory failures are synthetic metadata/syscall seams only. No host,
# private file, process receipt, permissions or original operation is touched.
import errno
import hashlib
import stat
import pytest

_READER_PATHS = (
    NATIVE / 'candidate/run_observation.py',
)
_COMPONENTS = ('lanes', 'lanes/ext', 'lanes/ext/lanes')
_FAULTS = ('regular', 'symlink', 'other', 'uid', 'mode', 'open_io',
           'open_missing', 'open_permission', 'open_forbidden', 'fstat_io')


def _fixed_reader_failure(module, component, fault, observer=None):
    uid = 1000  # synthetic account, not an enrolled or observed principal
    reader = module.Reader.__new__(module.Reader)
    reader.uid, reader.fds, reader.edges = uid, [100], []
    paths, infos, opened, closed = {100: ''}, {}, [], []
    def info(fd, path):
        mode, owner = stat.S_IFDIR | 0o700, uid
        if path == component:
            mode = {'regular': stat.S_IFREG | 0o600,
                    'symlink': stat.S_IFLNK | 0o777,
                    'other': stat.S_IFIFO | 0o600,
                    'mode': stat.S_IFDIR | 0o722}.get(fault, mode)
            if fault == 'uid': owner += 1
        return types.SimpleNamespace(st_dev=1, st_ino=fd, st_mode=mode,
            st_uid=owner, st_gid=uid, st_nlink=1, st_size=0,
            st_mtime_ns=0, st_ctime_ns=0)
    def opening(name, flags, *, dir_fd):
        path = '/'.join(filter(None, (paths[dir_fd], name)))
        # A guarded parent failure must never continue to another component or
        # open the receipt, and every directory keeps both kernel flags.
        assert path in _COMPONENTS
        assert flags & module.os.O_NOFOLLOW and flags & module.os.O_DIRECTORY
        opened.append(path)
        errors = {'open_io': errno.EIO, 'open_missing': errno.ENOENT,
                  'open_permission': errno.EACCES, 'open_forbidden': errno.EPERM}
        if path == component and fault in errors:
            raise OSError(errors[fault], 'PRIVATE_ERROR_CANARY', '/PRIVATE_PATH_CANARY')
        fd = 100 + len(opened)
        paths[fd] = path; infos[fd] = info(fd, path)
        return fd
    def fstat(fd):
        if paths[fd] == component and fault == 'fstat_io':
            raise OSError(errno.EIO, 'PRIVATE_ERROR_CANARY')
        return infos[fd]
    with mock.patch.object(module.os, 'open', side_effect=opening), \
         mock.patch.object(module.os, 'fstat', side_effect=fstat), \
         mock.patch.object(module.os, 'stat', side_effect=lambda name, *, dir_fd, follow_symlinks:
             infos[next(fd for fd, path in paths.items()
                        if path == '/'.join(filter(None, (paths[dir_fd], name))))]), \
         mock.patch.object(module.os, 'close', side_effect=closed.append):
        try:
            result = (observer(reader) if observer is not None else
                      module.capture(lambda: module.process_receipt(reader, 'synthetic-run')))
        except OSError as exc:
            assert exc.errno in (errno.EACCES, errno.EPERM)
            result = dict(status='unavailable', reason='os_permission_denied',
                          errno=exc.errno, directory_diagnostic=exc.directory_diagnostic)
    assert opened == list(_COMPONENTS[:_COMPONENTS.index(component)+1])
    assert set(closed) == set(infos) and len(closed) == len(infos)
    assert reader.fds == [100] and reader.edges == []
    assert 'PRIVATE_' not in json.dumps(result)
    return result


@pytest.mark.parametrize('path', _READER_PATHS)
@pytest.mark.parametrize('component', _COMPONENTS)
@pytest.mark.parametrize('fault', _FAULTS)
def test_first_fixed_directory_failure_is_bounded_and_has_no_onward_reads(path, component, fault):
    module = load('fixed_directory_reader', path)
    row = _fixed_reader_failure(module, component, fault)
    diagnostic = row['directory_diagnostic']
    assert set(diagnostic) == {'component','kind','uid','mode','errno'}
    assert diagnostic['component'] == component
    if fault.startswith(('open_', 'fstat_')):
        assert diagnostic['kind'] == 'unknown'
        assert diagnostic['uid'] is None and diagnostic['mode'] is None
        if fault == 'open_missing':
            assert row['status'] == 'absent' and row['reason'] == 'missing_at_observation'
        elif fault in ('open_permission','open_forbidden'):
            assert row['reason'] == 'os_permission_denied'
        else:
            assert row['reason'] == 'filesystem_error'
    else:
        assert row['reason'] == 'directory_owner_mode_or_type'
        assert diagnostic['kind'] == (fault if fault in ('regular','symlink','other') else 'directory')
        assert diagnostic['uid'] == (1001 if fault == 'uid' else 1000)


@pytest.mark.parametrize('path', _READER_PATHS)
@pytest.mark.parametrize('permission', [False, True])
def test_observation_stops_after_first_directory_failure_without_reading_other_roles(path, permission):
    module = load('fixed_directory_stop_reader', path)
    failure = (OSError(errno.EACCES, 'PRIVATE_ERROR_CANARY') if permission
               else module.Invalid('directory_owner_mode_or_type'))
    info = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o722, st_uid=1000)
    module._directory_failure(failure, 'lanes/ext', None if permission else info)
    reader = mock.MagicMock()
    with mock.patch.object(module, 'Reader', return_value=reader), \
         mock.patch.object(module, 'support', return_value={}), \
         mock.patch.object(module, 'marker', side_effect=failure), \
         mock.patch.object(module, 'rc_file') as rc, \
         mock.patch.object(module, 'stdout_metadata') as stdout, \
         mock.patch.object(module, 'process_receipt') as receipt:
        report = module.observe('synthetic-run', 'a'*64)
    assert report['status'] == 'unavailable'
    assert rc.call_count == stdout.call_count == receipt.call_count == 0
    assert report['reason'] == ('os_permission_denied' if permission
                                else 'one_or_more_observations_unavailable')
    if permission:
        assert report['request_stopped'] is True
        assert report['directory_diagnostic']['component'] == 'lanes/ext'
    else:
        assert report['observations']['marker']['directory_diagnostic']['component'] == 'lanes/ext'
    assert 'PRIVATE_' not in json.dumps(report)


@pytest.mark.parametrize('module', [candidate])
def test_directory_diagnostic_wire_is_closed_and_legacy_failures_unchanged(module):
    legacy = dict(status='unavailable', reason='directory_owner_mode_or_type')
    assert module._failure(legacy)
    diagnostic = dict(component='lanes/ext/lanes', kind='directory', uid=1000, mode=0o722, errno=None)
    valid = dict(legacy, directory_diagnostic=diagnostic)
    assert module._failure(valid)
    malformed = [dict(diagnostic, component='/PRIVATE_PATH_CANARY'),
        dict(diagnostic, component='lanes/ext/PRIVATE_RUN_CANARY'),
        dict(diagnostic, kind='PRIVATE_TYPE_CANARY'), dict(diagnostic, uid=True),
        dict(diagnostic, uid=-1), dict(diagnostic, mode=True), dict(diagnostic, mode=2**12),
        dict(diagnostic, errno=errno.EIO), dict(diagnostic, extra='PRIVATE_VALUE_CANARY')]
    for bad in malformed:
        assert not module._failure(dict(legacy, directory_diagnostic=bad))
    unknown = dict(component='lanes', kind='unknown', uid=None, mode=None, errno=errno.EIO)
    assert module._failure(dict(status='unavailable',reason='filesystem_error',errno=errno.EIO,directory_diagnostic=unknown))
    assert not module._failure(dict(legacy,directory_diagnostic=unknown))
    # Exercise the real receiver's response shape/binding, without transport.
    request = dict(run_id='synthetic-run', support_digest='a'*64)
    report = dict(schema='mastermind.run_observation.v1', run_id=request['run_id'],
        expected_support_digest=request['support_digest'], status='unavailable',
        observations={'process_receipt': valid}, limits=module.LIMITS)
    module.delivery.digest = lambda raw: hashlib.sha256(raw).hexdigest()
    def wire(value):
        return json.dumps(dict(schema=module.SCHEMA,
            request_sha256=module.delivery.digest(module.reader.canonical(request)), report=value)).encode()
    with mock.patch.object(module,'validate_request'):
        assert module.validate_response(wire(report), request) == report
        stopped = dict(report, reason='filesystem_unavailable', errno=errno.EIO,
            request_stopped=True, directory_diagnostic=unknown)
        assert module.validate_response(wire(stopped),request) == stopped
        with pytest.raises(ValueError):
            module.validate_response(wire(dict(report,directory_diagnostic=diagnostic)),request)
        with pytest.raises(ValueError):
            module.validate_response(wire(dict(stopped,directory_diagnostic=dict(unknown,mode=0o700))),request)


def test_fixed_directory_diagnostics_preserve_original_custody_and_race_guards():
    import ast
    def definitions(path):
        tree=ast.parse(path.read_text())
        reader=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Reader')
        return {n.name:ast.dump(n,include_attributes=False) for n in reader.body
                if isinstance(n,ast.FunctionDef)}
    old=definitions(NATIVE/'source/run_observation.py')
    for path in _READER_PATHS:
        new=definitions(path)
        for name in ('__init__','verify','close','__enter__','__exit__','_file'):
            assert new[name]==old[name]
    for path in _READER_PATHS:
        module=load('fixed_directory_privacy_reader',path)
        error=module.Invalid('directory_owner_mode_or_type')
        info=types.SimpleNamespace(st_mode=stat.S_IFDIR|0o722,st_uid=1000)
        module._directory_failure(error,'/PRIVATE_PATH_CANARY',info)
        assert not hasattr(error,'directory_diagnostic')


def test_process_directory_failure_also_stops_an_opted_in_pid_read():
    module=load('fixed_directory_pid_stop_reader',_READER_PATHS[0])
    def observe(reader):
        # Actual process_receipt -> actual Reader -> original directory guard.
        # Only earlier roles and the root context are synthetic; the PID spy
        # must not be reached after this real fixed-component failure.
        with mock.patch.object(module,'Reader',return_value=contextlib.nullcontext(reader)), \
             mock.patch.object(module,'support',return_value={}), \
             mock.patch.object(module,'marker',return_value={'pid':123}), \
             mock.patch.object(module,'rc_file',return_value={}), \
             mock.patch.object(module,'stdout_metadata',return_value={}), \
             mock.patch.object(module,'proc_observation') as pid:
            report=module.observe('synthetic-run','a'*64,observe_pid=True)
        assert report['observations']['marker']['status']=='observed'
        assert report['observations']['process_receipt']['reason']=='directory_owner_mode_or_type'
        assert report['status']=='unavailable' and 'pid' not in report['observations']
        pid.assert_not_called()
        return report
    _fixed_reader_failure(module,'lanes/ext/lanes','mode',observer=observe)


def test_missing_fixed_directory_actual_reader_response_roundtrips_without_outer_errno():
    module=load('fixed_directory_missing_reader',_READER_PATHS[0])
    row=_fixed_reader_failure(module,'lanes/ext/lanes','open_missing')
    assert row['status']=='absent' and row['reason']=='missing_at_observation'
    assert 'errno' not in row and row['directory_diagnostic']['errno']==errno.ENOENT
    request=dict(run_id='synthetic-run',support_digest='a'*64)
    file=dict(device=1,inode=1,uid=1000,mode=0o600,bytes=0,mtime_ns=0)
    # Complete closed companion rows make an overall-status-only mutation
    # discriminate the directory diagnostic, not missing required row keys.
    observations=dict(
        support=dict(status='observed',digest=request['support_digest'],verified_code_files=21,
            verification='manifest_and_fixed_code_hashes',running_process_source_identity_proven=False,
            release_links_verified=False),
        marker=dict(status='observed',file=file,marker_sha256='b'*64,pid=123,
            started_at='2026-11-05T00:00:00+00:00',elapsed_since_marker_seconds=0,
            source_sha256=None,process_generation_proven=False,root_identity_proven=False),
        returncode=dict(status='absent',reason='missing_at_observation'),
        stdout=dict(status='observed',file=file,content_read=False,useful_progress_proven=False),
        process_receipt=row)
    report=dict(schema='mastermind.run_observation.v1',run_id=request['run_id'],
        expected_support_digest=request['support_digest'],status='unavailable',
        observations=observations,limits=candidate.LIMITS)
    def wire(value):
        return json.dumps(dict(schema=candidate.SCHEMA,
            request_sha256=candidate.delivery.digest(candidate.reader.canonical(request)),report=value)).encode()
    candidate.delivery.digest=lambda raw:hashlib.sha256(raw).hexdigest()
    with mock.patch.object(candidate,'validate_request'), \
         mock.patch.dict(sys.modules,{'run_observation':module}):
        assert candidate.validate_response(wire(report),request)==report
        with pytest.raises(ValueError):
            candidate.validate_response(wire(dict(report,status='observed')),request)
        for bad in [dict(row,errno=errno.ENOENT),
                    dict(row,directory_diagnostic=dict(row['directory_diagnostic'],errno=errno.EIO)),
                    dict(row,directory_diagnostic=dict(row['directory_diagnostic'],errno=None))]:
            with pytest.raises(ValueError):
                candidate.validate_response(wire(dict(report,observations={'process_receipt':bad})),request)


@pytest.mark.parametrize('packet_entry',[False,True])
def test_actual_packet_and_support_directory_failures_keep_distinct_wire_categories(packet_entry):
    module=load('fixed_directory_packet_entry_reader',_READER_PATHS[0])
    request=dict(run_id='synthetic-run',support_digest='a'*64)
    artifact=dict(packet_sha256='b'*64,
        support_files={name:'c'*64 for name in module.ARTIFACT_SUPPORT_FILES},
        contract=dict(schema='mastermind.fabric_artifact_production.v1',root='synthetic-root',
            parent='synthetic-parent',run_id=request['run_id'],names=['patch.diff'],
            body_sha256='d'*64,support_digest=request['support_digest']))
    def observe(reader):
        with mock.patch.object(module,'Reader',return_value=contextlib.nullcontext(reader)), \
             mock.patch.object(module,'marker') as marker, \
             mock.patch.object(module,'rc_file') as rc, \
             mock.patch.object(module,'stdout_metadata') as stdout, \
             mock.patch.object(module,'process_receipt') as receipt:
            report=module.observe(request['run_id'],request['support_digest'],
                                  artifact=artifact if packet_entry else None)
        assert marker.call_count==rc.call_count==stdout.call_count==receipt.call_count==0
        return report
    # Actual artifact_packet or support -> actual Reader -> fstat mode guard.
    # Both stop at the common first fixed directory, before packet/manifest bytes.
    report=_fixed_reader_failure(module,'lanes','mode',observer=observe)
    assert report['status']=='unavailable'
    assert 'errno' not in report and 'request_stopped' not in report
    if packet_entry:
        assert report['reason']=='directory_owner_mode_or_type'
        assert report['observations']=={}
        assert report['directory_diagnostic']['component']=='lanes'
    else:
        assert report['reason']=='original_support_unverified'
        assert 'directory_diagnostic' not in report
        assert report['observations']['support']['reason']=='directory_owner_mode_or_type'
        assert report['observations']['support']['directory_diagnostic']['component']=='lanes'
    def wire(value):
        return json.dumps(dict(schema=candidate.SCHEMA,
            request_sha256=candidate.delivery.digest(candidate.reader.canonical(request)),report=value)).encode()
    candidate.delivery.digest=lambda raw:hashlib.sha256(raw).hexdigest()
    with mock.patch.object(candidate,'validate_request'), \
         mock.patch.dict(sys.modules,{'run_observation':module}):
        assert candidate.validate_response(wire(report),request)==report
        if packet_entry:
            for bad in [dict(report,status='observed'),dict(report,request_stopped=True),
                        dict(report,reason='os_permission_denied',errno=errno.EACCES)]:
                with pytest.raises(ValueError):candidate.validate_response(wire(bad),request)
