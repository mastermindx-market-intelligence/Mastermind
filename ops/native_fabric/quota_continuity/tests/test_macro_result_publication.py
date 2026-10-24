"""Canonical Macro publication through the actual sealed native closure.

Finite local fixtures exercise the publisher and both Fabric result APIs.
NATIVE_ROLLOUT_TEST_ROOT may select an owned fixture parent with trusted
ancestry. No provider, network, live kit, or held run is invoked.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


# Every scenario imports fresh, real modules from the sealed generation. This
# avoids both module-cache cross-contamination and stubbing the Fabric reader.
CHILD = r'''
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from unittest import mock

HERE = Path(sys.argv[1])
OWNER = Path(sys.argv[2])
sys.path.insert(0, str(HERE))
import artifact_delivery as delivery
import fabric_task as task
import native_runtime_bindings as bindings
import remote_sub_helpers as helpers

assert task.HERE == HERE
assert delivery.HERE == HERE
assert HERE.parent.parent.name == "native-code-releases"
assert stat.S_IMODE(HERE.stat().st_mode) == 0o555
assert stat.S_IMODE(HERE.parent.stat().st_mode) == 0o555
assert stat.S_IMODE((HERE.parent / "RELEASE.json").stat().st_mode) == 0o444
assert len(json.loads((HERE.parent / "RELEASE.json").read_bytes())["files"]) == 98
assert (HERE / "lanes").is_symlink()
assert bindings.owner_path(HERE / "lanes", HERE) == OWNER / "lanes"
with delivery.DirectoryChain(HERE / "lanes") as chain:
    chain.verify()
    assert os.fstat(chain.fd).st_ino == (OWNER / "lanes").stat().st_ino

PAYLOAD = b"STATUS: COMPLETE\nexact binary bytes: \x00\xff\n"
POLICY = b"MACRO_RESULT_POLICY "
PUBLISHED = b"MACRO_RESULT_PUBLISHED "


def private_file(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            assert written > 0
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def refused(call):
    try:
        call()
    except (ValueError, OSError):
        return
    raise AssertionError("publisher/reader accepted unqualified evidence")


class Case:
    def __init__(self, suffix="one", *, custom=False, payload=PAYLOAD, legacy=False):
        self.run = "macro-publication-fixture-" + suffix
        self.host = "ubuntu0"
        self.log = HERE / "state/remote_sub" / (self.run + ".log")
        self.canonical = HERE / "lanes" / (self.run + ".remote.stdout")
        self.capture = HERE / "lanes" / (".macro-capture." + self.run + ".A1b2C3d4")
        self.output = OWNER / "custom" / (self.run + ".stdout") if custom else self.canonical
        self.payload = payload
        initial = b"" if legacy else self.line("MACRO_RESULT_REQUIRED schema=1")
        private_file(self.log, initial + self.line("RUN_RESERVED explicit=1"))

    def line(self, event):
        return ("2026-10-21T00:00Z [remote_sub id=" + self.run
                + " host=" + self.host + "] " + event + "\n").encode()

    def event(self, event):
        fd = os.open(self.log, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            raw = self.line(event)
            assert os.write(fd, raw) == len(raw)
            os.fsync(fd)
        finally:
            os.close(fd)

    def prepare(self):
        helpers.prepare_macro_result(HERE, self.log, self.run, self.host, self.output)
        lines = [line for line in self.log.read_bytes().splitlines()
                 if line.split(b"] ", 1)[1].startswith(POLICY)]
        assert len(lines) == 1
        policy = json.loads(lines[0].split(POLICY, 1)[1])
        assert policy["schema"] == "mastermind.fabric_macro_result_policy.v1"
        assert policy["run_id"] == self.run

    def capture_bytes(self):
        private_file(self.capture, self.payload)

    def publish(self):
        helpers.publish_macro_result(HERE, self.log, self.run, self.host,
                                     self.capture, self.output)

    def worker_done(self):
        self.event("LAUNCH stdout=fixture.remote.stdout")
        self.event("REMOTE_DONE rc=0")

    def done(self, rc=0, signal="ok"):
        self.event("DONE rc=" + str(rc) + " signal=" + signal)

    def success(self):
        self.prepare()
        self.worker_done()
        self.capture_bytes()
        self.publish()
        self.done()
        self.available()

    def available(self):
        status = task.inspect_run(self.run)
        assert status["result_available"] is True, status
        assert status["result_bytes"] == len(self.payload), status
        assert status["rc"] == 0 and status["signal"] == "ok", status
        assert status.get("accepted") is not True, status
        assert task.read_result(self.run, max_bytes=max(1, len(self.payload))) == self.payload
        assert helpers.read_macro_result(HERE, self.log, self.run,
            max(1, len(self.payload)), self.log.read_bytes()) == self.payload

    def unavailable(self):
        status = task.inspect_run(self.run)
        assert status["result_available"] is False, status
        assert status.get("result_bytes") is None, status
        try:
            task.read_result(self.run)
        except task.FabricTaskError:
            pass
        else:
            raise AssertionError("read_result exposed an unverified file")

    def record_line(self, marker):
        lines = [line for line in self.log.read_bytes().splitlines(keepends=True)
                 if line.split(b"] ", 1)[1].startswith(marker)]
        assert len(lines) == 1, lines
        return lines[0]

    def change_record(self, marker, change):
        line = self.record_line(marker)
        prefix, raw = line.split(marker, 1)
        value = json.loads(raw)
        change(value)
        replacement = prefix + marker + json.dumps(value, sort_keys=True,
            separators=(",", ":")).encode() + b"\n"
        body = self.log.read_bytes()
        assert body.count(line) == 1
        # Deliberate owned-fixture corruption, never a production log writer.
        self.log.write_bytes(body.replace(line, replacement))


def replace_sha_values(value, wanted):
    changed = 0
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "sha256":
                assert isinstance(item, str) and len(item) == 64
                value[key] = wanted
                changed += 1
            else:
                changed += replace_sha_values(item, wanted)
    elif isinstance(value, list):
        for item in value:
            changed += replace_sha_values(item, wanted)
    return changed


def replace_link_source(src, *, src_dir_fd, replacement):
    """Keep original A, substitute same-size B, and retain B's parent witness."""
    name = os.fspath(src)
    parent = os.dup(src_dir_fd) if src_dir_fd is not None else None
    saved = name + ".original-A"
    os.rename(name, saved, src_dir_fd=parent, dst_dir_fd=parent)
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent)
    try:
        assert os.write(fd, replacement) == len(replacement)
        os.fsync(fd)
        stamp = os.fstat(fd)
    finally:
        os.close(fd)
    return name, parent, saved, (stamp.st_dev, stamp.st_ino)


def assert_foreign_retained(witness, expected):
    name, parent, saved, identity = witness
    try:
        stamp = os.stat(name, dir_fd=parent, follow_symlinks=False)
        assert (stamp.st_dev, stamp.st_ino) == identity
        assert stat.S_ISREG(stamp.st_mode)
        assert stat.S_ISREG(os.stat(saved, dir_fd=parent, follow_symlinks=False).st_mode)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            assert os.read(fd, len(expected) + 1) == expected
        finally:
            os.close(fd)
    finally:
        if parent is not None:
            os.close(parent)
'''


def _unseal_fixture(root):
    """Only undo modes on directories created by this fixture; never follow links."""
    if root.exists():
        for current, _, _ in os.walk(root, followlinks=False):
            os.chmod(current, 0o700)


class MacroResultPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_parent = Path(os.environ.get(
            "NATIVE_ROLLOUT_TEST_ROOT", str(Path.home()))).resolve(strict=True)
        # Never weaken DirectoryChain to make a permissive /tmp fixture pass.
        for path in (fixture_parent, *fixture_parent.parents):
            info = path.stat()
            if (info.st_uid not in {0, os.getuid()} or info.st_mode & 0o022):
                raise unittest.SkipTest(
                    "NATIVE_ROLLOUT_TEST_ROOT needs trusted directory ancestry: " + str(path))
        cls.temp = tempfile.TemporaryDirectory(prefix="macro-publication-proof-",
                                               dir=fixture_parent)
        cls.base = Path(cls.temp.name).resolve()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.addClassCleanup(_unseal_fixture, cls.base)
        staged = cls.base / "staged"
        build = subprocess.run([sys.executable, "-B",
            str(ROOT / "rollout/build_review_stage.py"), "--output", str(staged)],
            text=True, capture_output=True, timeout=30)
        if build.returncode:
            raise AssertionError("actual current-source stage failed:\n" + build.stderr)
        cls.source = staged / "native-code-stage"
        cls.manifest = json.loads((staged / "native-manifest.json").read_bytes())
        if len(cls.manifest) != 98:
            raise AssertionError("Paid source integration changed the reviewed 98-file closure")
        spec = importlib.util.spec_from_file_location("macro_fixture_native_generation",
            ROOT / "rollout/native_generation.py")
        cls.generation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.generation)

    def setUp(self):
        self.base = self.__class__.base / self._testMethodName
        self.owner = self.base / "kit/ext"
        self.owner.mkdir(parents=True, mode=0o700)
        for name in ("lanes", "state", "state/remote_sub", "custom", "broker"):
            (self.owner / name).mkdir(mode=0o700)
        self.release = self.generation.publish(self.source, self.owner, self.manifest)
        verified, meta = self.generation.verify(self.release.parent, self.release.name)
        self.assertEqual(verified, self.release)
        self.assertEqual(len(meta["files"]), 98)

    def child(self, program):
        result = subprocess.run([sys.executable, "-B", "-c",
            CHILD + "\n" + textwrap.dedent(program), str(self.release / "ext"),
            str(self.owner)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # The real publisher and reader must not mutate sealed runtime bytes.
        self.generation.verify(self.release.parent, self.release.name)

    def test_declared_native_alias_publishes_exact_bytes_and_retains_known_links(self):
        self.child(r'''
            case = Case(custom=True)
            case.success()
            assert case.capture.read_bytes() == PAYLOAD
            assert case.canonical.read_bytes() == PAYLOAD
            assert case.output.read_bytes() == PAYLOAD
            assert case.capture.stat().st_ino == case.canonical.stat().st_ino
            assert case.canonical.stat().st_nlink == 2
            assert case.output.stat().st_nlink == 2
            copies = list(case.output.parent.glob(".macro-copy." + case.run + ".*"))
            assert len(copies) == 1
            assert copies[0].stat().st_ino == case.output.stat().st_ino
            assert stat.S_IMODE(case.canonical.stat().st_mode) == 0o600
            assert stat.S_IMODE(case.output.stat().st_mode) == 0o600
            value = json.loads(case.record_line(PUBLISHED).split(PUBLISHED, 1)[1])
            assert value["schema"] == "mastermind.fabric_macro_result_publication.v1"
            assert value["run_id"] == case.run
        ''')

    def test_physical_and_declared_canonical_paths_are_the_same_destination(self):
        self.child(r'''
            case = Case()
            case.output = OWNER / "lanes" / case.canonical.name
            case.success()
            assert case.canonical.stat().st_nlink == 2
            assert not list((OWNER / "lanes").glob(".macro-copy.*"))
        ''')

    def test_capture_path_substitution_at_link_never_exposes_wrong_result(self):
        self.child(r'''
            case = Case(payload=b"A" * 31)
            case.prepare(); case.worker_done(); case.capture_bytes()
            original_link = os.link
            witnesses = []
            wrong = b"B" * len(case.payload)
            def raced_link(src, dst, *args, **kwargs):
                if Path(dst).name == case.canonical.name:
                    witnesses.append(replace_link_source(src,
                        src_dir_fd=kwargs.get("src_dir_fd"), replacement=wrong))
                return original_link(src, dst, *args, **kwargs)
            with mock.patch.object(os, "link", side_effect=raced_link):
                refused(case.publish)
            assert len(witnesses) == 1
            assert case.canonical.read_bytes() == wrong
            assert_foreign_retained(witnesses[0], wrong)
            case.done()
            case.unavailable()
        ''')

    def test_custom_staging_substitution_keeps_foreign_names_and_canonical_unavailable(self):
        self.child(r'''
            case = Case(custom=True, payload=b"C" * 31)
            case.prepare(); case.worker_done(); case.capture_bytes()
            original_link = os.link
            witnesses = []
            wrong = b"D" * len(case.payload)
            def raced_link(src, dst, *args, **kwargs):
                if Path(dst).name == case.output.name:
                    witnesses.append(replace_link_source(src,
                        src_dir_fd=kwargs.get("src_dir_fd"), replacement=wrong))
                return original_link(src, dst, *args, **kwargs)
            with mock.patch.object(os, "link", side_effect=raced_link):
                refused(case.publish)
            assert len(witnesses) == 1
            assert case.canonical.read_bytes() == case.payload
            assert case.output.read_bytes() == wrong
            assert_foreign_retained(witnesses[0], wrong)
            case.done()
            case.unavailable()
        ''')

    def test_intermediate_publication_and_final_binding_without_done_are_unavailable(self):
        self.child(r'''
            case = Case(custom=True)
            case.prepare(); case.worker_done(); case.capture_bytes()
            original_link = os.link
            observed = []
            def inspect_link(src, dst, *args, **kwargs):
                value = original_link(src, dst, *args, **kwargs)
                if Path(dst).name == case.canonical.name:
                    case.unavailable()
                    observed.append(True)
                return value
            with mock.patch.object(os, "link", side_effect=inspect_link):
                case.publish()
            assert observed == [True]
            case.unavailable()
            case.done(); case.available()
        ''')

    def test_policy_only_crash_cut_cannot_promote_a_regular_file(self):
        self.child(r'''
            case = Case()
            case.prepare(); case.worker_done()
            private_file(case.canonical, case.payload)
            case.done()
            case.unavailable()
        ''')

    def test_custom_collision_after_prepare_preserves_winner_and_hides_loser(self):
        self.child(r'''
            first = Case("first", custom=True, payload=b"FIRST")
            second = Case("second", custom=True, payload=b"OTHER")
            second.output = first.output
            first.prepare(); second.prepare()
            first.worker_done(); first.capture_bytes(); first.publish(); first.done()
            winner = first.output.stat()
            second.worker_done(); second.capture_bytes()
            refused(second.publish)
            second.done()
            assert first.output.read_bytes() == b"FIRST"
            assert first.output.stat().st_ino == winner.st_ino
            first.available(); second.unavailable()
        ''')

    def test_preexisting_canonical_custom_and_dangling_symlink_refuse(self):
        self.child(r'''
            for number, kind in enumerate(("canonical", "custom", "symlink")):
                case = Case(str(number), custom=True)
                target = case.canonical if kind == "canonical" else case.output
                if kind == "symlink":
                    target.symlink_to(OWNER / "missing-fixture-target")
                else:
                    private_file(target, b"preexisting owner bytes")
                before = target.lstat()
                refused(case.prepare)
                assert target.lstat().st_ino == before.st_ino
                assert PUBLISHED not in case.log.read_bytes()
                if kind != "symlink":
                    assert target.read_bytes() == b"preexisting owner bytes"
        ''')

    def test_undeclared_custom_parent_symlink_is_not_resolved(self):
        self.child(r'''
            alias = OWNER / "custom-alias"
            alias.symlink_to(OWNER / "custom", target_is_directory=True)
            case = Case(custom=True)
            case.output = alias / case.output.name
            refused(case.prepare)
            assert not case.output.exists()
            assert not case.canonical.exists()
        ''')

    def test_state_internal_lanes_symlink_is_not_a_declared_native_alias(self):
        self.child(r'''
            case = Case()
            lanes = OWNER / "lanes"
            moved = OWNER / "original-lanes"
            lanes.rename(moved)
            lanes.symlink_to(moved, target_is_directory=True)
            refused(case.prepare)
            assert not case.canonical.exists()
        ''')

    def test_capture_symlink_and_shared_parent_refuse_without_publication(self):
        self.child(r'''
            case = Case("symlink")
            case.prepare(); case.worker_done()
            other = OWNER / "private-other-result"
            private_file(other, PAYLOAD)
            case.capture.symlink_to(other)
            refused(case.publish)
            assert other.read_bytes() == PAYLOAD
            assert case.capture.is_symlink()
            assert not case.canonical.exists()
            case.done(); case.unavailable()
            unsafe = Case("unsafe", custom=True)
            (OWNER / "custom").chmod(0o777)
            refused(unsafe.prepare)
        ''')

    def test_same_size_content_change_and_same_bytes_inode_replacement_refuse(self):
        self.child(r'''
            changed = Case("changed", payload=b"A" * 31)
            changed.success()
            changed.canonical.write_bytes(b"B" * 31)
            changed.unavailable()
            replaced = Case("replaced")
            replaced.success()
            retained = OWNER / "retained-canonical-A"
            replaced.canonical.rename(retained)
            private_file(replaced.canonical, replaced.payload)
            assert replaced.canonical.stat().st_ino != retained.stat().st_ino
            replaced.unavailable()
        ''')

    def test_digest_claim_is_validated_against_actual_canonical_bytes(self):
        self.child(r'''
            case = Case()
            case.success()
            def wrong_digest(value):
                assert replace_sha_values(value, "0" * 64) >= 1
            case.change_record(PUBLISHED, wrong_digest)
            assert case.canonical.read_bytes() == PAYLOAD
            case.unavailable()
        ''')

    def test_policy_and_final_record_run_ids_cannot_be_rebound(self):
        self.child(r'''
            for suffix, marker in (("policy", POLICY), ("published", PUBLISHED)):
                case = Case(suffix)
                case.success()
                case.change_record(marker, lambda value: value.update(run_id="another-run"))
                case.unavailable()
        ''')

    def test_duplicate_policy_or_publication_never_falls_back_to_legacy(self):
        self.child(r'''
            for suffix, marker in (("policy", POLICY), ("published", PUBLISHED)):
                case = Case(suffix)
                case.success()
                with case.log.open("ab") as stream:
                    stream.write(case.record_line(marker))
                case.unavailable()
        ''')

    def test_malformed_or_unknown_policy_never_falls_back_to_legacy(self):
        self.child(r'''
            unknown = Case("unknown")
            unknown.success()
            unknown.change_record(POLICY,
                lambda value: value.update(schema="mastermind.fabric_macro_result_policy.v99"))
            unknown.unavailable()
            malformed = Case("malformed")
            malformed.success()
            line = malformed.record_line(POLICY)
            prefix = line.split(POLICY, 1)[0]
            malformed.log.write_bytes(malformed.log.read_bytes().replace(
                line, prefix + POLICY + b"{not-json}\n"))
            malformed.unavailable()
        ''')

    def test_missing_and_incomplete_logs_refuse_even_with_published_result(self):
        self.child(r'''
            missing = Case("missing")
            missing.success(); missing.log.unlink()
            assert missing.canonical.read_bytes() == PAYLOAD
            missing.unavailable()
            partial = Case("partial")
            partial.success()
            partial.log.write_bytes(partial.log.read_bytes()[:-1])
            partial.unavailable()
        ''')

    def test_complete_legacy_logs_keep_existing_result_reads(self):
        self.child(r'''
            for suffix, legacy_log in (("prefixed", False), ("plain", True)):
                case = Case(suffix, legacy=True)
                private_file(case.canonical, case.payload)
                if legacy_log:
                    case.log.write_bytes(b"DONE rc=0 signal=ok\n")
                else:
                    case.done()
                raw = case.log.read_bytes()
                assert helpers.read_macro_result(HERE, case.log, case.run,
                    len(PAYLOAD), raw) is None
                assert task.read_result(case.run) == PAYLOAD
                assert task.inspect_run(case.run)["result_available"] is True
        ''')

    def test_worker_nonzero_diagnostics_stay_retained_but_unavailable(self):
        self.child(r'''
            case = Case()
            case.prepare()
            case.event("LAUNCH stdout=fixture.remote.stdout")
            case.event("REMOTE_DONE rc=1")
            private_file(case.canonical, b"retained failure diagnostics\n")
            case.done(rc=1, signal="other")
            case.unavailable()
            assert case.canonical.read_bytes() == b"retained failure diagnostics\n"
        ''')

    def test_publication_requires_observed_successful_worker_return(self):
        self.child(r'''
            for suffix, event in (("missing-return", None),
                                  ("failed-return", "REMOTE_DONE rc=1")):
                case = Case(suffix)
                case.prepare(); case.capture_bytes()
                case.event("LAUNCH stdout=fixture.remote.stdout")
                if event:
                    case.event(event)
                refused(case.publish)
                assert PUBLISHED not in case.log.read_bytes()
                case.done()
                case.unavailable()
        ''')

    def test_terminal_failures_and_effect_uncertainty_override_publication(self):
        self.child(r'''
            for number, (event, rc, signal) in enumerate((
                (None, 1, "other"),
                (None, 0, "effect_unknown"),
                ("RESULT_UNAVAILABLE worker_rc=0 rsync_rc=76", 0, "ok"),
                ("LEASE_PRESERVED effect_unknown=1 lease=fixture", 0, "ok"),
            )):
                case = Case(str(number))
                case.prepare(); case.worker_done(); case.capture_bytes(); case.publish()
                if event:
                    case.event(event)
                case.done(rc=rc, signal=signal)
                case.unavailable()
        ''')

    def test_supplied_old_log_snapshot_cannot_hide_the_current_policy(self):
        self.child(r'''
            case = Case(legacy=True)
            old_log = case.log.read_bytes()
            case.log.write_bytes(case.line("MACRO_RESULT_REQUIRED schema=1") + old_log)
            case.success()
            refused(lambda: helpers.read_macro_result(HERE, case.log, case.run,
                len(PAYLOAD), old_log))
        ''')

    def test_policy_path_cannot_fabricate_terminal_or_uncertain_state(self):
        self.child(r'''
            for number, text in enumerate((
                "DONE rc=0 signal=ok", "REMOTE_DONE rc=0", "LAUNCH stdout=fake",
                "REMOTE_EFFECT_UNKNOWN", "RESULT_UNAVAILABLE",
                "LEASE_PRESERVED effect_unknown=1", "signal=effect_unknown",
            )):
                case = Case("status-data-" + str(number), custom=True)
                case.output = OWNER / "custom" / text
                helpers.prepare_macro_result(HERE, case.log, case.run, case.host, case.output)
                status = task.inspect_run(case.run)
                assert status["state"] == "ACTIVE_OR_WAITING", status
                assert status["rc"] is None and status["signal"] is None, status
                assert status["result_available"] is False, status
                case.worker_done(); case.capture_bytes(); case.publish(); case.done()
                case.available()
        ''')

    def test_policy_append_failure_prevents_a_prepared_publication(self):
        self.child(r'''
            case = Case()
            with mock.patch.object(helpers, "_publish_log_line",
                    side_effect=OSError(errno.EIO, "fixture append failure")):
                refused(case.prepare)
            assert not case.canonical.exists()
            assert PUBLISHED not in case.log.read_bytes()
        ''')

    def test_partial_final_log_append_is_unavailable_and_preserves_outputs(self):
        self.child(r'''
            case = Case(custom=True)
            case.prepare(); case.worker_done(); case.capture_bytes()
            original_append = helpers._publish_log_line
            def partial_append(log_name, dir_fd, fd, chain, before, identity, raw, appended):
                if PUBLISHED in appended:
                    assert os.write(fd, appended[:-1]) == len(appended) - 1
                    os.fsync(fd)
                    raise OSError(errno.EIO, "fixture final append interruption")
                return original_append(log_name, dir_fd, fd, chain, before, identity,
                                       raw, appended)
            with mock.patch.object(helpers, "_publish_log_line", side_effect=partial_append):
                refused(case.publish)
            assert not case.log.read_bytes().endswith(b"\n")
            assert case.canonical.read_bytes() == PAYLOAD
            assert case.output.read_bytes() == PAYLOAD
            case.unavailable()
        ''')

    def test_empty_exact_max_and_oversize_capture_bounds(self):
        self.child(r'''
            empty = Case("empty", payload=b"")
            empty.success()
            maximum = Case("maximum", payload=b"X" * task.MAX_RESULT_BYTES)
            maximum.success()
            try:
                task.read_result(maximum.run, max_bytes=task.MAX_RESULT_BYTES - 1)
            except task.FabricTaskError:
                pass
            else:
                raise AssertionError("caller read bound was ignored")
            huge = Case("huge")
            huge.prepare(); huge.worker_done()
            fd = os.open(huge.capture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.ftruncate(fd, task.MAX_RESULT_BYTES + 1)
            finally:
                os.close(fd)
            refused(huge.publish)
            assert not huge.canonical.exists()
            assert huge.capture.stat().st_size == task.MAX_RESULT_BYTES + 1
            huge.done(); huge.unavailable()
        ''')


    def test_retained_result_reads_from_a_new_generation_with_the_same_state_owner(self):
        import hashlib
        import shutil

        # Default output intentionally uses generation A's logical ext/lanes
        # alias. This is the path that must not be retained as a future reader's
        # unresolved output-owner path in the durable policy record.
        self.child(r'''
            case = Case("generation-switch")
            assert case.output == HERE / "lanes" / (case.run + ".remote.stdout")
            case.success()
        ''')
        run_id = "macro-publication-fixture-generation-switch"
        retained_log = self.owner / "state/remote_sub" / (run_id + ".log")
        original_log = retained_log.read_bytes()
        canonical = self.owner / "lanes" / (run_id + ".remote.stdout")
        original_inode = (canonical.stat().st_dev, canonical.stat().st_ino)
        first_release = self.release

        # Reuse the entire actual 98-file source closure, changing only an
        # unrelated comment to mint a distinct fixture generation identity.
        next_source = self.base / "next-generation-source"
        shutil.copytree(self.source, next_source)
        changed_name = "ext/placement_view.py"
        changed_path = next_source / changed_name
        changed_path.write_bytes(changed_path.read_bytes() +
            b"\n# Offline Macro result fixture: distinct generation identity only.\n")
        next_manifest = dict(self.manifest)
        next_manifest[changed_name] = hashlib.sha256(changed_path.read_bytes()).hexdigest()
        self.assertEqual(len(next_manifest), 98)
        self.assertEqual({name for name in next_manifest
            if next_manifest[name] != self.manifest[name]}, {changed_name})

        second_release = self.generation.publish(next_source, self.owner, next_manifest)
        self.assertNotEqual(second_release.name, first_release.name)
        self.generation.verify(first_release.parent, first_release.name)
        self.generation.verify(second_release.parent, second_release.name)

        # child() starts a fresh interpreter, so task.HERE, delivery.HERE, and
        # owner_path all originate from B. Its existing prelude also proves B's
        # sealed metadata, exact 98-file closure, and original state aliases.
        self.release = second_release
        try:
            self.child(r'''
                run_id = "macro-publication-fixture-generation-switch"
                log_path = HERE / "state/remote_sub" / (run_id + ".log")
                status = task.inspect_run(run_id)
                assert status["state"] == "TERMINAL", status
                assert status["rc"] == 0 and status["signal"] == "ok", status
                assert status["result_available"] is True, status
                assert status["result_bytes"] == len(PAYLOAD), status
                assert status.get("accepted") is not True, status
                assert task.read_result(run_id, max_bytes=len(PAYLOAD)) == PAYLOAD
                assert helpers.read_macro_result(HERE, log_path, run_id,
                    len(PAYLOAD), log_path.read_bytes()) == PAYLOAD
            ''')
        finally:
            self.release = first_release

        self.assertEqual(retained_log.read_bytes(), original_log)
        self.assertEqual((canonical.stat().st_dev, canonical.stat().st_ino), original_inode)
        self.generation.verify(first_release.parent, first_release.name)
        self.generation.verify(second_release.parent, second_release.name)

    def test_reserved_event_words_in_run_ids_and_paths_are_literal_data(self):
        self.child(r'''
            # The full prefix contains the reserved word, but neither event
            # declares the Macro publication protocol. An intact legacy result
            # must therefore retain the legacy reader behavior.
            legacy = Case("legacy-MACRO_RESULT_POLICY", legacy=True)
            private_file(legacy.canonical, legacy.payload)
            legacy.done()
            legacy_status = task.inspect_run(legacy.run)
            assert legacy_status["result_available"] is True, legacy_status
            assert task.read_result(legacy.run) == PAYLOAD
            assert helpers.read_macro_result(HERE, legacy.log, legacy.run,
                len(PAYLOAD), legacy.log.read_bytes()) is None

            # These words appear inside a run ID and JSON path values. They
            # cannot become duplicate policy/publication events or uncertainty
            # events merely because a whole log line contains the substring.
            case = Case("new-MACRO_RESULT_PUBLISHED", custom=True)
            case.output = OWNER / "custom" / (
                "MACRO_RESULT_POLICY MACRO_RESULT_PUBLISHED "
                "EFFECT_UNKNOWN RESULT_UNAVAILABLE output.stdout")
            helpers.prepare_macro_result(HERE, case.log, case.run, case.host, case.output)
            case.worker_done()
            case.capture_bytes()
            helpers.publish_macro_result(HERE, case.log, case.run, case.host,
                                         case.capture, case.output)
            case.done()
            status = task.inspect_run(case.run)
            assert status["state"] == "TERMINAL", status
            assert status["rc"] == 0 and status["signal"] == "ok", status
            assert status["result_available"] is True, status
            assert task.read_result(case.run) == PAYLOAD
            assert helpers.read_macro_result(HERE, case.log, case.run,
                len(PAYLOAD), case.log.read_bytes()) == PAYLOAD
            assert case.output.read_bytes() == PAYLOAD

            # Boundary matching is applied after extracting the controller
            # prefix, and before interpreting the event's JSON payload.
            events = [line.split("] ", 1)[1] for line in
                      case.log.read_text().splitlines()]
            assert sum(event.startswith("MACRO_RESULT_POLICY ")
                       for event in events) == 1
            assert sum(event.startswith("MACRO_RESULT_PUBLISHED ")
                       for event in events) == 1
        ''')


    def test_malformed_partial_or_unknown_evidence_cannot_fabricate_terminal_status(self):
        self.child(r'''
            for number, event in enumerate((
                b'MACRO_RESULT_POLICY {"output":"/tmp/DONE rc=0 signal=ok',
                b'MACRO_RESULT_POLICYX DONE rc=0 signal=ok\n',
                b'MACRO_RESULT_PUBLISHED {"path":"REMOTE_EFFECT_UNKNOWN',
                b'MACRO_RESULT_UNKNOWN RESULT_UNAVAILABLE DONE rc=0 signal=ok\n',
                b'MACRO_RESULT_REQUIRED schema=99\n',
                b'MACRO_RESULT_REQUIRED schema=1\n',
                b'MACRO_RESULT_PREPARE_REFUSED DONE rc=0 signal=ok\n',
            )):
                case = Case("malformed-status-" + str(number))
                private_file(case.canonical, b"unqualified bytes")
                prefix = case.line("")[:-1]
                with case.log.open("ab") as stream:
                    stream.write(prefix + event)
                status = task.inspect_run(case.run)
                assert status["state"] == "STATUS_UNREADABLE", status
                assert status["rc"] is None and status["signal"] is None, status
                case.unavailable()
        ''')

    def test_reclaim_plan_treats_macro_worktree_words_in_policy_path_as_data(self):
        self.child(r'''
            case = Case("reclaim-path-data", custom=True)
            case.output = OWNER / "custom" / "FABRIC_NEW_MACRO_WORKTREE answer.stdout"
            pinned = "a" * 40
            case.prepare()
            case.event("FABRIC_NEW_MACRO_WORKTREE run=" + case.run + " commit=" + pinned
                       + " root=fixture-root parent=fixture-parent")
            case.worker_done(); case.capture_bytes(); case.publish(); case.done()
            case.available()
            original = case.log.read_bytes()
            # Only the independent acceptance owner is substituted. The real
            # status/result verifier and both reclaim observations still run.
            accepted = dict(accepted=True, accepted_by="deterministic",
                            acceptance_state="ACCEPTED", acceptance_reason="fixture",
                            root_id="fixture-root", parent_run_id="fixture-parent")
            with mock.patch.object(task.pool_ledger, "read_acceptance", return_value=accepted) as ledger:
                plan = task.plan_accepted_macro_worktree_release(case.run,
                    root_id="fixture-root", parent_run_id="fixture-parent", pinned_sha=pinned)
            assert ledger.call_count == 2
            assert plan["host"] == case.host
            assert plan["source_pinned_sha"] == pinned
            assert plan["cleanup_authorized"] is False
            assert plan["state"] == "HOST_WORKTREE_SOURCE_AND_LIVENESS_PROOF_REQUIRED"
            assert case.log.read_bytes() == original
        ''')

    def test_reservation_crash_boundaries_and_prepare_refusal_never_expose_stale_bytes(self):
        self.child(r'''
            for number, cut in enumerate(("empty", "partial", "required", "reserved", "refused")):
                case = Case("reservation-" + str(number))
                private_file(case.canonical, b"preexisting unrelated bytes")
                identity = case.canonical.stat().st_ino
                if cut == "empty":
                    case.log.write_bytes(b"")
                elif cut == "partial":
                    case.log.write_bytes(case.line("MACRO_RESULT_REQUIRED schema=1")[:-1])
                elif cut == "required":
                    case.log.write_bytes(case.line("MACRO_RESULT_REQUIRED schema=1"))
                elif cut == "refused":
                    refused(case.prepare)
                case.unavailable()
                assert case.canonical.read_bytes() == b"preexisting unrelated bytes"
                assert case.canonical.stat().st_ino == identity
        ''')


if __name__ == "__main__":
    unittest.main(verbosity=2)
