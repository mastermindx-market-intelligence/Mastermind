"""Retiring attention must preserve evidence and never reopen a stable run."""
import json
import os

import pytest

from integrations.session_bridge import fabric_stop_return as stop

ROOT, RUN, OTHER, PIN = "original", "accepted-run", "other-run", "a" * 64


@pytest.fixture
def owner(tmp_path):
    state = tmp_path / "attention"
    state.mkdir(mode=0o700)
    for run in (RUN, OTHER):
        stop.register_subscription(ROOT, run, state)
    status = dict(schema="mastermind.fabric_task_status.v1", run_id=RUN, root_id=ROOT,
                  parent_run_id=ROOT, state="TERMINAL", rc=0, signal="ok", result_available=True,
                  result_bytes=6, accepted=True, acceptance_state="ACCEPTED",
                  acceptance_reason="VALIDATED_OUTCOME", accepted_by="reviewer")
    attempts = dict(schema="mastermind.fabric_stop_attempts.v1", root=ROOT, runs={
        run: dict(run_id=run, result_bytes=6, result_sha256="b"*64,
                  state="PREPARED_DELIVERY_UNCONFIRMED", turn_id="turn", frame_sha256="c"*64,
                  adapter_sha256=PIN) for run in (RUN, OTHER)})
    with stop._ParentMetadata(ROOT, state) as store:
        store.write(".attempts.json", attempts)
    calls = []
    def read(operation, run):
        calls.append((operation, run))
        return json.dumps(status).encode()
    return state, status, read, calls


def retire(owner):
    return stop.retire_accepted_subscription(ROOT, RUN, state_dir=owner[0],
        adapter_sha256=PIN, read_adapter=owner[2])


def archive_path(owner):
    return owner[0] / (stop.digest(ROOT.encode()) + stop._retirement_suffix(RUN))


def snapshot(owner):
    return {p.name: p.read_bytes() for p in owner[0].iterdir()}


def test_one_slot_released_without_touching_run_evidence(owner, tmp_path, monkeypatch):
    evidence = tmp_path / "original.log"
    evidence.write_bytes(b"original run and acceptance ledger are retained")
    monkeypatch.setattr(stop, "MAX_SUBSCRIPTIONS", 2)
    with pytest.raises(stop.ReturnUnavailable, match="bound reached"):
        stop.register_subscription(ROOT, "new-run", owner[0])
    before = snapshot(owner)
    receipt = retire(owner)
    archive = json.loads(archive_path(owner).read_bytes())
    assert receipt["state"] == "ATTENTION_RETIRED" and receipt["remaining"] == 1
    assert receipt["retry_authorized"] is False and receipt["run_artifacts_changed"] is False
    assert owner[3] == [("status", RUN)] * 2  # Never result, accept, cancel or request.
    assert archive["status"] == owner[1]
    assert archive["index"] == json.loads(before[stop.digest(ROOT.encode()) + ".subscriptions.json"])
    assert archive["attempts"] == json.loads(before[stop.digest(ROOT.encode()) + ".attempts.json"])
    with stop._ParentMetadata(ROOT, owner[0]) as store:
        index = stop._load_index(store)
        assert index["runs"] == [OTHER]
        assert stop._load_attempts(store, index)["runs"] == {OTHER: archive["attempts"]["runs"][OTHER]}
    stop.register_subscription(ROOT, "new-run", owner[0])
    assert evidence.read_bytes() == b"original run and acceptance ledger are retained"
    with pytest.raises(stop.ReturnUnavailable, match="already retired"):
        stop.register_subscription(ROOT, RUN, owner[0])
    with pytest.raises(stop.ReturnUnavailable, match="already retired"):
        retire(owner)


@pytest.mark.parametrize("field,value", [
    ("schema", "foreign"), ("run_id", OTHER), ("root_id", OTHER), ("parent_run_id", OTHER),
    ("state", "EFFECT_UNKNOWN"), ("state", "TERMINAL_FAILURE"), ("rc", False), ("rc", 78),
    ("signal", "failed"), ("result_available", False), ("result_bytes", 0), ("result_bytes", True),
    ("accepted", False), ("acceptance_state", "NOT_ACCEPTED"),
    ("acceptance_reason", "OUTCOME_NOT_ACCEPTED"), ("accepted_by", "caller")])
def test_unqualified_snapshot_mutates_nothing(owner, field, value):
    owner[1][field] = value
    before = snapshot(owner)
    with pytest.raises(stop.ReturnUnavailable, match="accepted outcome"):
        retire(owner)
    assert snapshot(owner) == before


def test_changed_status_mutates_nothing(owner):
    before = snapshot(owner)
    def changed(operation, run):
        raw = owner[2](operation, run)
        owner[1]["accepted_by"] = "deterministic"
        return raw
    with pytest.raises(stop.ReturnUnavailable, match="status changed"):
        stop.retire_accepted_subscription(ROOT, RUN, state_dir=owner[0],
            adapter_sha256=PIN, read_adapter=changed)
    assert snapshot(owner) == before


@pytest.mark.parametrize("failure_at", [1, 2, 3, 4, 5, 6])
def test_every_durability_interruption_preserves_archive_and_refuses_replay(owner, monkeypatch, failure_at):
    real, count = os.fsync, 0
    def fail(fd):
        nonlocal count
        count += 1
        if count == failure_at:
            raise OSError("fixture durability interruption")
        return real(fd)
    with monkeypatch.context() as m:
        m.setattr(os, "fsync", fail)
        with pytest.raises(OSError):
            retire(owner)
    assert archive_path(owner).exists()
    with pytest.raises((stop.ReturnUnavailable, OSError)):
        stop.register_subscription(ROOT, RUN, owner[0])
    with pytest.raises((stop.ReturnUnavailable, OSError)):
        retire(owner)
    if failure_at < 6:
        with pytest.raises((stop.ReturnUnavailable, OSError)):
            stop.register_subscription(ROOT, "unrelated-new-run", owner[0])
    # Last directory fsync may leave a fully published index; no success was claimed.
    assert json.loads(archive_path(owner).read_bytes())["attempts"]["runs"][RUN]


@pytest.mark.parametrize("kind", ["corrupt", "symlink", "writable", "pending"])
def test_unsafe_archive_cannot_be_skipped_or_replaced(owner, kind, tmp_path):
    path = archive_path(owner)
    if kind == "symlink":
        path.symlink_to(tmp_path / "absent")
    elif kind == "pending":
        path.with_name(path.name + ".pending").write_bytes(b"partial")
    else:
        path.write_bytes(b"{}")
        path.chmod(0o600 if kind == "corrupt" else 0o666)
    with pytest.raises((stop.ReturnUnavailable, OSError)):
        retire(owner)
    with pytest.raises((stop.ReturnUnavailable, OSError)):
        stop.register_subscription(ROOT, RUN, owner[0])
    assert owner[3] == []


@pytest.mark.parametrize("suffix", [".subscriptions.json", ".attempts.json"])
def test_existing_pending_metadata_blocks_retirement_and_callback(owner, suffix):
    path = owner[0] / (stop.digest(ROOT.encode()) + suffix + ".pending")
    path.write_bytes(b"ambiguous original write")
    with pytest.raises(FileExistsError):
        retire(owner)
    event = dict(hook_event_name="Stop", session_id=ROOT, turn_id="turn", stop_hook_active=False)
    with pytest.raises(FileExistsError):
        stop.prepare_subscribed_stop(event, adapter_sha256=PIN,
            read_adapter=owner[2], state_dir=owner[0])
    assert not archive_path(owner).exists() and owner[3] == []


def test_directory_replacement_does_not_redirect_archive(owner):
    def changed(operation, run):
        raw = owner[2](operation, run)
        if len(owner[3]) == 1:
            owner[0].rename(owner[0].with_name("retained"))
            owner[0].mkdir(mode=0o700)
        return raw
    with pytest.raises(stop.ReturnUnavailable, match="changed subscription directory"):
        stop.retire_accepted_subscription(ROOT, RUN, state_dir=owner[0],
            adapter_sha256=PIN, read_adapter=changed)
    assert list(owner[0].iterdir()) == []


def test_cli_retirement_requires_current_original_parent_before_reads(owner, monkeypatch, capsys):
    monkeypatch.setattr(stop.sys, "argv", ["fabric_stop_return.py", "--retire-accepted",
        "--root", ROOT, "--run", RUN, "--subscribed-state-dir", str(owner[0]),
        "--adapter", "/not-read", "--adapter-sha256", PIN])
    monkeypatch.setenv("CODEX_THREAD_ID", "native-child")
    monkeypatch.setattr(stop.subprocess, "run", lambda *a, **kw: pytest.fail("no adapter read"))
    assert stop.main() == 75
    assert json.loads(capsys.readouterr().out)["state"] == "RETIREMENT_UNCONFIRMED"


def test_accepted_foreground_consumption_needs_no_stop_attempt(owner):
    with stop._ParentMetadata(ROOT, owner[0]) as store:
        store.write(".attempts.json", dict(schema="mastermind.fabric_stop_attempts.v1", root=ROOT, runs={}))
    assert retire(owner)["state"] == "ATTENTION_RETIRED"
    assert json.loads(archive_path(owner).read_bytes())["attempts"]["runs"] == {}


def test_archive_only_interruption_blocks_callback_before_adapter_read(owner, monkeypatch):
    original = stop._ParentMetadata.write
    def fail_attempt_prune(store, suffix, value):
        if suffix == ".attempts.json":
            raise OSError("interrupted after archive")
        return original(store, suffix, value)
    with monkeypatch.context() as m:
        m.setattr(stop._ParentMetadata, "write", fail_attempt_prune)
        with pytest.raises(OSError):
            retire(owner)
    owner[3].clear()
    event = dict(hook_event_name="Stop", session_id=ROOT, turn_id="new-turn", stop_hook_active=False)
    with pytest.raises(stop.ReturnUnavailable, match="incomplete subscription retirement"):
        stop.prepare_subscribed_stop(event, adapter_sha256=PIN, read_adapter=owner[2], state_dir=owner[0])
    assert owner[3] == []
