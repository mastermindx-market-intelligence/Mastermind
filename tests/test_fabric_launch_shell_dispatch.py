"""Prove Fabric bootstrap dispatch does not select ambient Bash.

These tests use injected fake calls. No provider, lease, auth or existing pool
wrapper is touched. The original dispatcher and argv remain authoritative.
"""
from pathlib import Path

from ops.fabric_launch import pool_entry as entry


def _kit(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    (kit / "ext").mkdir(parents=True)
    for name in ("sub.sh", "remote_sub.sh"):
        (kit / "ext" / name).write_text("#!/bin/bash\nexit 0\n")
    monkeypatch.setattr(entry, "execution_scopes", lambda *_: set())
    monkeypatch.setattr(
        entry, "materialize", lambda *_a, **_kw: ("prepared", {"delivery_mode": "plain"}),
    )
    return kit


def test_local_run_uses_explicit_os_bash_not_ambient_path(tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    calls = []
    assert entry.invoke(
        kit, "run", ["glm", "prompt", "/workspace", "glm-5.3"],
        task_class="review", call=lambda argv: calls.append(argv) or 23,
    ) == 23
    assert calls == [["/bin/bash", str(kit / "ext/sub.sh"),
                      "glm", "prepared", "/workspace", "glm-5.3"]]


def test_remote_dry_run_uses_exact_system_bash_without_side_effects(tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    packet = tmp_path / "review.txt"
    packet.write_text("read only")
    calls = []
    argv = ["auto", "glm", str(packet), "~/lanes", "glm-5.3", "--dry-run"]
    assert entry.invoke(
        kit, "remote", argv, task_class="review",
        call=lambda value: calls.append(value) or 0,
    ) == 0
    assert calls == [["/bin/bash", str(kit / "ext/remote_sub.sh"), *argv]]
    assert not (kit / "ext/state").exists()


def test_remote_dispatch_preserves_original_arguments_and_cleans_owned_files(tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    packet = tmp_path / "review.txt"
    packet.write_text("read only")
    calls = []
    argv = ["auto", "glm", str(packet), "~/lanes", "glm-5.3"]
    def receiver(value):
        calls.append(value)
        assert value[0] == "/bin/bash"
        assert value[1] == str(kit / "ext/remote_sub.sh")
        assert value[2:4] == argv[:2]
        assert value[5:] == argv[3:]
        assert Path(value[4]).read_text() == "prepared"
        return 0
    assert entry.invoke(kit, "remote", argv, task_class="review", call=receiver) == 0
    assert len(calls) == 1
    assert not list((kit / "ext/state/remote_sub").glob("boot-*"))
