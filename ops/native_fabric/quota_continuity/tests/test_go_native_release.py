"""Generation and ORIGINAL Go process ingress proofs in disposable owners."""
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
from types import ModuleType
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, published, g, installer, ROOT, loaded_entry


def test_old_descriptor_is_byte_exact_and_go_requires_complete_closure(published):
    spec = importlib.util.spec_from_file_location("go_old_generation_fixture", installer._HISTORICAL_LAUNCHER)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    files = {name: published.manifest[name] for name in g.ENTRYPOINTS.values()}
    assert g.canonical(g.descriptor(files, published.ext)) == old.canonical(old.descriptor(files, published.ext))
    for removed in g.GO_REQUIRED:
        broken = {k: v for k, v in published.manifest.items() if k != removed}
        with pytest.raises(ValueError, match="incomplete"):
            g.descriptor(broken, published.ext)
    assert g.verify(published.store, published.release.name)[1]["entrypoints"]["go"] == g.GO_ENTRY


def test_launch_uses_one_current_and_exact_verified_metadata(published):
    with loaded_entry(published) as entry:
        entry._native_generation_digest = published.release.name
        with mock.patch.object(g, "_GO_ENTRY_MODULE", entry), mock.patch.object(sys, "argv", [str(published.original)]), \
                mock.patch.object(g, "current", wraps=g.current) as current, \
                mock.patch.object(entry, "main", return_value=29) as main:
            assert g.launch(published.store, "go", []) == 29
            assert current.call_count == 1
            assert main.call_args.kwargs == {"verified_root": published.release, "verified_metadata": published.meta}
            assert entry.__file__ == str(published.release / g.GO_ENTRY)
        with mock.patch.object(sys, "argv", ["/wrong/ingress.py"]), pytest.raises(ValueError, match="original process"):
            g.launch(published.store, "go", [])


def test_same_filename_unowned_preloaded_entry_is_refused(published):
    foreign = ModuleType("native_go_entry")
    foreign.__file__ = str(published.release / g.GO_ENTRY)
    foreign._native_generation_digest = published.release.name
    with mock.patch.dict(sys.modules, {"native_go_entry": foreign}), \
            mock.patch.object(sys, "argv", [str(published.original)]), \
            pytest.raises(ValueError, match="module conflict"):
        g.launch(published.store, "go", [])


def install_original_bridge(published):
    raw = Path(g.__file__).read_bytes()
    directory = published.store / "launchers"
    directory.mkdir(mode=0o700)
    launcher = directory / (g.digest(raw) + ".py")
    launcher.write_bytes(raw)
    launcher.chmod(0o555)
    published.original.write_bytes(installer.go_bridge((ROOT / "source/go_shim.py").read_bytes(), launcher, published.store))
    return launcher


def environment(published):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GO_", "POOL_"))}
    env.update(GO_ACCOUNTS_PATH=str(published.profile), GO_STATE_DIR=str(published.ext / "go_shim"),
        GO_SHIM_PORT="0", GO_WORKER_CAPABILITIES="0", PYTHONDONTWRITEBYTECODE="1")
    env.pop("REMOTE_SUB_HERE", None)
    return env


def test_original_two_argument_python_process_enters_actual_B_and_retains_pid_owner(published):
    install_original_bridge(published)
    process = subprocess.Popen([sys.executable, str(published.original)], env=environment(published),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([process.stdout], [], [], 10)
        assert ready, "original Go process did not become ready"
        line = process.stdout.readline().strip()
        assert line.startswith("go_shim listening port="), (line, process.poll())
        port = int(line.rsplit("=", 1)[1])
        assert port > 0
        assert int((published.ext / "go_shim/shim.pid").read_text().strip()) == process.pid
        observed = subprocess.check_output(["ps", "-ww", "-p", str(process.pid), "-o", "command="], text=True).strip()
        assert str(published.original) in observed and "native_go_entry.py" not in observed
        assert observed.endswith(str(published.original))
        import http.client
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            assert response.status == 200
            response.read()
        finally:
            connection.close()
        assert (published.ext / "go_shim/shim.lock").is_file()
        # No entry-specific state directory, second database, or pyc ingress.
        assert not (published.release / "ext/__pycache__").exists()
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)


def test_original_bridge_refuses_changed_launcher_before_handler_or_pid(published):
    launcher = install_original_bridge(published)
    launcher.chmod(0o755)
    launcher.write_bytes(launcher.read_bytes() + b"\n# changed\n")
    launcher.chmod(0o555)
    result = subprocess.run([sys.executable, str(published.original)], env=environment(published),
        capture_output=True, text=True, timeout=5)
    assert result.returncode != 0 and "launcher source refused" in result.stderr
    assert not (published.ext / "go_shim/shim.pid").exists()
    assert not (launcher.parent / "__pycache__").exists()
