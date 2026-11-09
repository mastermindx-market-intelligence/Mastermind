"""Secret-free cleanup diagnosis on disposable descriptors, never the live seat."""
import contextlib
import errno
import json
import os
from pathlib import Path
import select
import tempfile
import traceback
from types import SimpleNamespace
import unittest
from unittest import mock

from ops.executive_os import os_gateway_studio_reader as reader
from test_os_gateway_studio_prefix_identity import QueueFixture
import test_os_gateway_studio_home_acl as acl_fixture


class CleanupDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.queue = QueueFixture(self.temp)
        self.enterContext(mock.patch.multiple(select, create=True,
            KQ_NOTE_RENAME=32, KQ_NOTE_DELETE=1, KQ_NOTE_REVOKE=64,
            KQ_NOTE_ATTRIB=8, KQ_FILTER_VNODE=-4, KQ_EV_ADD=1, KQ_EV_CLEAR=32))
        self.enterContext(mock.patch.object(select, 'kevent', create=True,
            side_effect=lambda ident, **kw: SimpleNamespace(ident=ident, **kw)))
        self.enterContext(mock.patch.object(select, 'kqueue', create=True,
            return_value=self.queue))
        self.walk = reader._Walk(None, lambda: None)
        self.addCleanup(self.dispose)
        self.fd = self.walk.adopt(os.open(self.temp, reader._DIR_FLAGS))
        self.walk._prefix_guard.watch(('DO_NOT_ECHO_PATH',), self.fd, os.fstat(self.fd))
        self.held = self.walk._prefix_guard._held[('DO_NOT_ECHO_PATH',)][0]

    def dispose(self):
        self.queue.error = False
        with contextlib.suppress(reader.StudioObservationError):
            self.walk.close_all()

    def assertDisposed(self):
        self.assertFalse(self.walk._fds)
        self.assertFalse(self.walk._bindings)
        self.assertFalse(self.walk._paths)
        for fd in (self.fd, self.held):
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.assertEqual(self.queue.fileno(), -1)

    def records(self, exc):
        self.assertEqual(str(exc), 'gateway_studio_invalid')
        records = [json.loads(note) for note in exc.__notes__]
        self.assertLessEqual(len(records), 8)
        for record in records:
            self.assertEqual(set(record), {'phase', 'object_class', 'reason',
                'fields', 'event_flags', 'event_fflags', 'errno'})
        rendered = ''.join(traceback.format_exception(exc))
        for secret in ('DO_NOT_ECHO_PATH', 'SECRET_TEXT', self.temp):
            self.assertNotIn(secret, rendered)
        return records

    def test_event_and_phase_survive_cleanup_refusal_without_path(self):
        self.queue.events = [SimpleNamespace(flags=0, fflags=8,
            ident='SECRET_TEXT', data='SECRET_TEXT')]
        with self.assertRaises(reader.StudioObservationError) as caught:
            self.walk.close_all()
        records = self.records(caught.exception)
        self.assertTrue(any(x['reason'] == 'vnode_event' and x['event_fflags'] == 8
                            for x in records))
        self.assertTrue(any(x['phase'] == 'cleanup_before' for x in records))
        self.assertDisposed()

    def test_queue_errno_survives_but_exception_text_does_not(self):
        with mock.patch.object(self.queue, 'control',
                side_effect=OSError(errno.EIO, 'SECRET_TEXT', self.temp)):
            with self.assertRaises(reader.StudioObservationError) as caught:
                self.walk.close_all()
        records = self.records(caught.exception)
        self.assertTrue(any(x['reason'] == 'monitor_io' and x['errno'] == errno.EIO
                            for x in records))
        self.assertDisposed()

    def test_ordinary_close_errno_distinguished_and_all_resources_attempted(self):
        os.close(self.fd)
        with self.assertRaises(reader.StudioObservationError) as caught:
            self.walk.close_all()
        records = self.records(caught.exception)
        self.assertTrue(any(x['object_class'] == 'ordinary_fd' and
                            x['errno'] == errno.EBADF for x in records))
        self.assertDisposed()

    def test_primary_body_exception_retained_with_cleanup_evidence(self):
        primary = reader.StudioObservationError()
        self.queue.events = [SimpleNamespace(flags=0, fflags=32)]
        with self.assertRaises(reader.StudioObservationError) as caught:
            try:
                raise primary
            finally:
                reader._dispose_walk(self.walk)
        self.assertIs(caught.exception, primary)
        records = self.records(caught.exception)
        self.assertTrue(any(x['object_class'] == 'body' for x in records))
        self.assertTrue(any(x['reason'] == 'vnode_event' for x in records))
        self.assertDisposed()

    def test_diagnostics_are_closed_typed_and_bounded(self):
        exc = reader.StudioObservationError()
        for _ in range(30):
            reader._note_failure(exc, 'cleanup_before', 'prefix_guard', 'refused')
        records = self.records(exc)
        self.assertEqual(len(records), 8)
        self.assertEqual(records[-1]['reason'], 'additional_failures')
        for kwargs in ({'phase': 'SECRET_TEXT'}, {'fields': ('SECRET_TEXT',)},
                       {'event_flags': True}, {'event_fflags': 'SECRET_TEXT'},
                       {'error_number': -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                reader._note_failure(reader.StudioObservationError(),
                    **({'phase':'cleanup_before', 'object_class':'prefix_guard',
                        'reason':'refused'} | kwargs))

    def test_field_names_survive_without_values(self):
        expected = os.fstat(self.held)
        changed = SimpleNamespace(**{name: getattr(expected, name) +
            (1 if name == 'st_uid' else 0) for name in reader._IDENTITY_FIELDS})
        real = os.fstat
        with mock.patch.object(os, 'fstat',
                side_effect=lambda fd: changed if fd == self.held else real(fd)):
            with self.assertRaises(reader.StudioObservationError) as caught:
                self.walk.close_all()
        self.assertTrue(any(x['fields'] == ['st_uid']
                            for x in self.records(caught.exception)))
        self.assertDisposed()

    def test_guard_close_error_is_aggregated_after_ordinary_fds_close(self):
        close = self.queue.close
        def fail_after_close():
            close()
            raise OSError(errno.EIO, 'SECRET_TEXT', self.temp)
        with mock.patch.object(self.queue, 'close', side_effect=fail_after_close):
            with self.assertRaises(reader.StudioObservationError) as caught:
                self.walk.close_all()
        self.assertTrue(any(x['phase'] == 'cleanup_guard' and
            x['object_class'] == 'vnode_queue' and x['errno'] == errno.EIO
            for x in self.records(caught.exception)))
        self.assertDisposed()

    def test_arbitrary_exception_and_forged_notes_are_not_echoed(self):
        error = reader.StudioObservationError()
        error.add_note('SECRET_TEXT')
        error.add_note(json.dumps({'phase': 'SECRET_TEXT'}))
        with mock.patch.object(self.walk._prefix_guard, 'check', side_effect=error):
            with self.assertRaises(reader.StudioObservationError) as caught:
                self.walk.close_all()
        self.records(caught.exception)
        self.assertDisposed()


class ConnectedCleanupTests(acl_fixture.HomeAclReaderTestCase):
    def test_actual_observer_keeps_body_refusal_and_cleanup_failure(self):
        primary = reader.StudioObservationError()
        walks = []
        def refuse(walk):
            walks.append(walk)
            def io_failure():
                raise OSError(errno.EIO, 'DO_NOT_ECHO_SECRET')
            walk._prefix_guard.check = io_failure
            raise primary
        with acl_fixture.reader_overrides(), \
             mock.patch.object(reader._Walk, 'recheck_all', new=refuse):
            with self.assertRaises(reader.StudioObservationError) as caught:
                self.fx.observe()
        self.assertIs(caught.exception, primary)
        records = [json.loads(x) for x in primary.__notes__]
        self.assertTrue(any(x['object_class'] == 'body' for x in records))
        self.assertTrue(any(x['errno'] == errno.EIO for x in records))
        self.assertNotIn('DO_NOT_ECHO_SECRET', ''.join(traceback.format_exception(primary)))
        self.assertEqual(len(walks), 1)
        self.assertFalse(walks[0]._fds)
        self.assertFalse(walks[0]._prefix_guard._held)


@unittest.skipUnless(hasattr(select, 'kqueue'), 'real Darwin vnode qualification')
class NativeCleanupDiagnosticsTests(unittest.TestCase):
    def test_real_attribute_event_keeps_cause_and_closes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'prefix'; path.mkdir(mode=0o700)
            walk = reader._Walk(None, lambda: None)
            fd = walk.adopt(os.open(path, reader._DIR_FLAGS))
            walk._prefix_guard.watch(('inert',), fd, os.fstat(fd))
            held = walk._prefix_guard._held[('inert',)][0]
            path.chmod(0o700)
            with self.assertRaises(reader.StudioObservationError) as caught:
                walk.close_all()
            records = [json.loads(x) for x in caught.exception.__notes__]
            self.assertTrue(any(x['event_fflags'] is not None and
                x['event_fflags'] & select.KQ_NOTE_ATTRIB for x in records))
            for value in (fd, held):
                with self.assertRaises(OSError): os.fstat(value)
