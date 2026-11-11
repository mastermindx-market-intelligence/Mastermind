"""Disposable current-owner WAL coexistence; no runtime/credential read."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

import pytest
import importlib.util
import sys
_NATIVE = Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/candidate"
sys.path[:0] = [str(_NATIVE), str(_NATIVE.parent / "source")]
_spec = importlib.util.spec_from_file_location("preserving118_privacy", Path(__file__).resolve().parents[1] /
    "ops/native_fabric/provider_plans/memory118/fabric_memory_view.py")
view = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(view)
from fabric_operator_contract import DelegationRefused
import artifact_delivery


@pytest.fixture
def current(tmp_path):
    # Actual DirectoryChain refuses writable ancestors: use a private home fixture.
    with tempfile.TemporaryDirectory(prefix=".mmx-memory-wal-", dir=Path.home()) as name:
        here = Path(name) / "ext"
        broker = here / "broker"; broker.mkdir(parents=True, mode=0o700)
        (broker / "leases.lock").touch(mode=0o600)
        db = broker / "leases.sqlite"
        keeper = sqlite3.connect(db)
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("CREATE TABLE operator_child_authorizations(run_id TEXT, request_json TEXT, request_digest TEXT)")
        keeper.commit(); db.chmod(0o600)
        yield here, keeper
        keeper.close()


def bind(current, schema="mastermind.fabric_operator_child_request.v1"):
    here, keeper = current
    body = json.dumps({"schema": schema}, sort_keys=True, separators=(",", ":"))
    keeper.execute("INSERT INTO operator_child_authorizations VALUES (?,?,?)",
                   ("inert-run", body, hashlib.sha256(body.encode()).hexdigest()))
    keeper.commit()
    return here


def snapshot(here):
    return {p.name: p.read_bytes() for p in (here / "broker").iterdir() if p.is_file()}


def test_causal_old_reader_refuses_live_wal_but_current_classifier_preserves_ordinary(current):
    here = bind(current)
    before = snapshot(here)
    with pytest.raises(ValueError, match="lease_snapshot_has_live_sidecar"):
        artifact_delivery._retained_broker_row(
            "SELECT run_id,request_json,request_digest FROM operator_child_authorizations WHERE run_id=?",
            ("inert-run",), here=here)
    view.require_generic_channel(here, "inert-run")
    assert snapshot(here) == before  # No actual source checkpoint, sidecar or DB changes.


@pytest.mark.parametrize("schema", [view.SCHEMA, "unknown.future.wrapper"])
def test_private_and_unknown_row_still_refuse_before_any_original_body(current, schema):
    here = bind(current, schema)
    before = snapshot(here)
    with pytest.raises(DelegationRefused, match=view.VIEW_REQUIRED):
        view.require_generic_channel(here, "inert-run")
    assert snapshot(here) == before


@pytest.mark.parametrize("defect", ["wal_symlink", "wal_writable", "journal", "malformed"])
def test_unqualified_source_wal_cannot_authorize_generic_read(current, defect):
    here = bind(current)
    wal = here / "broker/leases.sqlite-wal"
    if defect == "wal_symlink":
        moved = wal.with_name("owned-wal"); wal.rename(moved); wal.symlink_to(moved)
    elif defect == "wal_writable": wal.chmod(0o666)
    elif defect == "journal": wal.with_name("leases.sqlite-journal").touch(mode=0o600)
    else: wal.write_bytes(b"invalid")
    with pytest.raises(DelegationRefused, match=view.VIEW_REQUIRED):
        view.require_generic_channel(here, "inert-run")


def test_row_changed_during_private_snapshot_query_refuses(current, monkeypatch):
    here = bind(current)
    original = sqlite3.connect
    keeper = current[1]
    class Changed(sqlite3.Connection):
        def execute(self, query, parameters=()):
            result = super().execute(query, parameters)
            if query.startswith("SELECT run_id,"):
                body = json.dumps({"schema":view.SCHEMA}, sort_keys=True, separators=(",", ":"))
                keeper.execute("UPDATE operator_child_authorizations SET request_json=?,request_digest=?",
                               (body, hashlib.sha256(body.encode()).hexdigest()))
                keeper.commit()
            return result
    def copying_only(*args, **kwargs):
        # This patched connection is the real SQLite private-copy query only.
        assert "fabric-privacy-snapshot-" in str(args[0]) and "mode=rw" in str(args[0])
        return original(*args, **kwargs, factory=Changed)
    monkeypatch.setattr(sqlite3, "connect", copying_only)
    with pytest.raises(DelegationRefused, match=view.VIEW_REQUIRED):
        view.require_generic_channel(here, "inert-run")


def test_busy_incumbent_lock_remains_refused(current, monkeypatch):
    here = bind(current)
    class Busy:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): raise ValueError("lease_snapshot_busy")
        def __exit__(self,*args): raise AssertionError("no lock acquired")
    monkeypatch.setattr(artifact_delivery, "LeaseSnapshotLock", Busy)
    with pytest.raises(DelegationRefused, match=view.VIEW_REQUIRED):
        view.require_generic_channel(here, "inert-run")


def test_corrupt_latest_private_frame_cannot_fall_back_to_old_ordinary_state(current):
    here = bind(current)
    # Keep a genuine committed older ordinary row and newer private row in WAL.
    keeper = current[1]
    body = json.dumps({"schema":view.SCHEMA}, sort_keys=True, separators=(",", ":"))
    keeper.execute("UPDATE operator_child_authorizations SET request_json=?,request_digest=?",
                   (body, hashlib.sha256(body.encode()).hexdigest()))
    keeper.commit()
    wal = here / "broker/leases.sqlite-wal"
    raw = bytearray(wal.read_bytes()); raw[-1] ^= 1; wal.write_bytes(raw)
    with pytest.raises(DelegationRefused, match=view.VIEW_REQUIRED):
        view.require_generic_channel(here, "inert-run")


@pytest.mark.parametrize("schema", ["mastermind.fabric_operator_child_request.v1", view.SCHEMA])
def test_existing_empty_wal_uses_current_main_database_without_runtime_checkpoint(current, schema):
    here = bind(current, schema)
    current[1].execute("PRAGMA wal_checkpoint(TRUNCATE)")  # Fixture preparation only.
    assert (here / "broker/leases.sqlite-wal").read_bytes() == b""
    before = snapshot(here)
    if schema == view.SCHEMA:
        with pytest.raises(DelegationRefused, match=view.VIEW_REQUIRED):
            view.require_generic_channel(here, "inert-run")
    else:
        view.require_generic_channel(here, "inert-run")
    assert snapshot(here) == before


def test_missing_table_exception_cannot_bypass_final_current_row_join(current, monkeypatch):
    here, keeper = current
    keeper.execute("DROP TABLE operator_child_authorizations"); keeper.commit()
    original = sqlite3.connect
    class Changed(sqlite3.Connection):
        def execute(self, query, parameters=()):
            try:
                return super().execute(query, parameters)
            finally:
                if query.startswith("SELECT run_id,"):
                    keeper.execute("CREATE TABLE operator_child_authorizations(run_id TEXT, request_json TEXT, request_digest TEXT)")
                    bind(current, view.SCHEMA)
    monkeypatch.setattr(sqlite3, "connect", lambda *a,**kw: original(*a,**kw,factory=Changed))
    with pytest.raises(DelegationRefused, match=view.VIEW_REQUIRED):
        view.require_generic_channel(here, "inert-run")
