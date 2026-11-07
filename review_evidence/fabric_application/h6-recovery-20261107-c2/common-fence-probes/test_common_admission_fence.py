"""Cross-process proof of the isolated physical-owner/selector composition."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time
import types

import pytest

from test_current_selection_reader import ROOT, G, B, S, release, pointer

def emit(value):
    print(json.dumps(value), flush=True)

def worker(kind, store, generation, expected):
    store = Path(store)
    if kind == "select":
        original = G.publication_lock
        @contextmanager
        def observed(path):
            with original(path):
                emit({"phase": "publication-held"})
                yield
        G.publication_lock = observed
        value = G.select(store, generation, None if expected == "absent" else expected)
        emit({"phase": "selected", "value": value})
    elif kind == "hold":
        with G.verified_admission_scope(store, generation) as check:
            check()
            emit({"phase": "admission-held"})
            assert sys.stdin.readline().strip() == "release"
            check()
        emit({"phase": "released"})
    else:
        raise ValueError("unknown fixture operation")

def start(kind, release, generation=None):
    return subprocess.Popen(
        [sys.executable, "-B", str(Path(__file__).resolve()), kind,
         str(release["store"]), generation or release["first"].name,
         release["first"].name],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)

def read_event(process, timeout=5):
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    assert ready, "fixture process did not reach its bounded barrier"
    line = process.stdout.readline()
    assert line, process.stderr.read()
    return json.loads(line)

def finish(process):
    try:
        code = process.wait(timeout=5)
        assert code == 0, process.stderr.read()
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()

def stop_if_running(process):
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=5)

def publish_successor(release, *, omit_helper=False, historical_helper=False):
    source = release["base"] / "successor"
    shutil.copytree(release["source"], source)
    with (source / "pool").open("ab") as handle:
        handle.write(b"\n# isolated selector successor\n")
    names = list(release["names"])
    if omit_helper:
        names.remove("ext/support_bundle.py")
    elif historical_helper:
        shutil.copyfile(ROOT.parent / "pre-fence/ext/support_bundle.py",
                        source / "ext/support_bundle.py")
    files = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
             for name in names}
    return G.publish(source, release["stable"], files)

def test_selector_waits_behind_same_physical_owner_across_generations(release):
    second = publish_successor(release)
    lock_path = release["stable"] / "active/.admission.lock"
    lock_before = lock_path.stat()
    with G.verified_admission_scope(release["store"], release["first"].name) as held:
        held()
        child = start("select", release, second.name)
        try:
            assert read_event(child) == {"phase": "publication-held"}
            # The selector has publication first, and cannot commit while this
            # existing physical scope is held. No mocked lock or claim result.
            assert select.select([child.stdout], [], [], 0.15)[0] == []
            assert G.current(release["store"]) == release["selected"]
            with pytest.raises(ValueError, match="publication already in progress"):
                with G.publication_lock(release["store"]):
                    pytest.fail("publication ownership split")
            held()
        except BaseException:
            stop_if_running(child)
            raise
    try:
        event = read_event(child)
        assert event["phase"] == "selected"
        assert event["value"]["generation"] == second.name
        assert event["value"]["previous"] == release["first"].name
        assert event["value"]["sequence"] == 2
        finish(child)
    finally:
        stop_if_running(child)
    lock_after = lock_path.stat()
    assert (lock_before.st_dev, lock_before.st_ino) == (
        lock_after.st_dev, lock_after.st_ino)
    assert B.require_current_selection(second / "ext") == event["value"]
    with pytest.raises(ValueError, match="no longer selected"):
        B.require_current_selection(release["first"] / "ext")

def test_bounded_deadline_waits_on_real_other_process_owner(release):
    child = start("hold", release)
    try:
        assert read_event(child) == {"phase": "admission-held"}
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="ADMISSION_DEADLINE_EXPIRED"):
            with G.verified_admission_scope(
                release["store"], release["first"].name,
                deadline_ns=time.monotonic_ns() + 80_000_000):
                pytest.fail("deadline did not bound physical lock wait")
        assert time.monotonic() - started < 0.75
        assert G.current(release["store"]) == release["selected"]
        child.stdin.write("release\n")
        child.stdin.flush()
        assert read_event(child) == {"phase": "released"}
        finish(child)
    finally:
        stop_if_running(child)

@pytest.mark.parametrize("kind", ["missing", "symlink", "hardlink", "mode", "nonempty"])
def test_selector_refuses_bad_physical_lock_without_repair(release, kind):
    second = publish_successor(release)
    lock = release["stable"] / "active/.admission.lock"
    if kind == "missing":
        lock.unlink()
    elif kind == "symlink":
        lock.unlink()
        lock.symlink_to(release["base"] / "absent-target")
    elif kind == "hardlink":
        os.link(lock, release["base"] / "lock-alias")
    elif kind == "mode":
        lock.chmod(0o644)
    else:
        lock.write_bytes(b"unexpected")
    before = pointer(release).read_bytes()
    with pytest.raises((ValueError, OSError)):
        G.select(release["store"], second.name, release["first"].name)
    assert pointer(release).read_bytes() == before
    if kind == "missing":
        assert not os.path.lexists(lock)

def test_held_check_detects_replaced_physical_owner(release):
    with G.verified_admission_scope(release["store"], release["first"].name) as held:
        active = release["stable"] / "active"
        active.rename(release["stable"] / "old-active")
        active.mkdir(mode=0o700)
        with pytest.raises(ValueError, match="DIRECTORY_CHANGED"):
            held()
    assert G.current(release["store"]) == release["selected"]

@pytest.mark.parametrize("kind", ["missing-helper", "historical-helper"])
def test_historical_verification_does_not_grant_fenced_selection(release, kind):
    second = publish_successor(release,
        omit_helper=kind == "missing-helper",
        historical_helper=kind == "historical-helper")
    assert G.verify(release["store"], second.name)[0] == second
    with pytest.raises(ValueError, match="common admission"):
        G.select(release["store"], second.name, release["first"].name)
    assert G.current(release["store"]) == release["selected"]

def test_selector_private_helper_does_not_occupy_runtime_module_slot(release, monkeypatch):
    second = publish_successor(release)
    foreign = types.ModuleType("support_bundle")
    monkeypatch.setitem(sys.modules, "support_bundle", foreign)
    value = G.select(release["store"], second.name, release["first"].name)
    assert value["generation"] == second.name
    assert sys.modules["support_bundle"] is foreign

def test_changed_sealed_helper_stops_before_selection(release):
    second = publish_successor(release)
    helper = second / "ext/support_bundle.py"
    helper.chmod(0o755)
    with helper.open("ab") as handle:
        handle.write(b"\n# unexpected drift\n")
    helper.chmod(0o555)
    with pytest.raises(ValueError, match="generation code digest mismatch"):
        G.select(release["store"], second.name, release["first"].name)
    assert G.current(release["store"]) == release["selected"]

def test_direct_installer_selection_entry_uses_the_same_fence(release):
    second = publish_successor(release)
    child = start("hold", release)
    try:
        assert read_event(child) == {"phase": "admission-held"}
        # Direct callers of _select_locked already hold publication. The public
        # scope's deadline is checked separately above; here use a bounded
        # helper instrumentation solely to make the test avoid a two-second wait.
        original = G.verified_admission_scope
        @contextmanager
        def bounded(store, generation):
            with original(store, generation,
                          deadline_ns=time.monotonic_ns() + 80_000_000) as held:
                yield held
        G.verified_admission_scope = bounded
        try:
            with G.publication_lock(release["store"]):
                with pytest.raises(TimeoutError, match="ADMISSION_DEADLINE_EXPIRED"):
                    G._select_locked(release["store"], second.name, release["first"].name)
        finally:
            G.verified_admission_scope = original
        assert G.current(release["store"]) == release["selected"]
        child.stdin.write("release\n")
        child.stdin.flush()
        assert read_event(child) == {"phase": "released"}
        finish(child)
    finally:
        stop_if_running(child)

if __name__ == "__main__":
    worker(*sys.argv[1:])
