"""Original-only enrollment contracts; SQLite and explicit native owner doubles.

No provider, role installation, live native session or product acceptance is
claimed by these tests. Native identity, ticket and creation APIs are doubles.
"""
import asyncio
from contextlib import contextmanager
import json
import os
import sqlite3
import sys
from types import ModuleType, SimpleNamespace

import pytest

from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime.errors import RuntimeRefusal

SHA = "a" * 40
REQUEST = "original-enrollment"


def module(monkeypatch, name, **members):
    value = ModuleType(name)
    value.__dict__.update(members)
    monkeypatch.setitem(sys.modules, name, value)
    return value


@pytest.fixture
def native(monkeypatch, tmp_path):
    home = tmp_path.resolve()
    principal = f"uid:{os.getuid()}"
    sid, route = "native-original", "agent:secretary:local:native-original"
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE state_meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE sessions(id TEXT PRIMARY KEY,source TEXT,user_id TEXT,
                              runtime_revision INTEGER,runtime_generation INTEGER,
                              session_key TEXT,chat_id TEXT,model_config TEXT,end_reason TEXT,parent_session_id TEXT);
        CREATE TABLE gateway_routing(scope TEXT,session_key TEXT,entry_json TEXT);
        CREATE TABLE runtime_epoch(singleton INTEGER PRIMARY KEY,epoch INTEGER,instance_id TEXT);
        INSERT INTO runtime_epoch VALUES(1,7,'native-owner');
    """)
    @contextmanager
    def read(**kwargs):
        yield conn
    db = SimpleNamespace(_read_ctx=read, _read_one=lambda sql, args: conn.execute(sql, args).fetchone(),
                         close=lambda: None)
    authority = SimpleNamespace(profile_id=str(home), instance_id="native-owner", epoch=7,
                                db=db, _mutation_tasks=set())
    state = SimpleNamespace(calls=[], closed=False, lost=False, wait=None, cleanup=None,
                            entered=None, cleanup_entered=None)
    receipt = dict(profile_id=str(home), principal_id=principal, request_id=REQUEST,
                   session_id=sid, route=route, entry=dict(session_id=sid, session_key=route,
                   origin=dict(chat_id=sid, user_id=principal, profile=None)),
                   policy=dict(source="tool", request_json='{"source":"tool"}'))
    def local_receipt(db, session_id):
        row = conn.execute("SELECT value FROM state_meta WHERE key=?", ("policy:" + session_id,)).fetchone()
        if row is None:
            raise ValueError("native missing or corrupt receipt")
        return json.loads(row[0])
    def commit():
        conn.execute("INSERT INTO sessions(id,source,user_id,runtime_revision,runtime_generation,session_key,chat_id) VALUES(?,?,?,?,?,?,?)",
                     (sid, "tool", principal, 0, 0, route, sid))
        conn.execute("INSERT INTO state_meta VALUES(?,?)", ("policy:" + sid, json.dumps(receipt)))
        conn.execute("INSERT INTO gateway_routing VALUES('',?,?)", (route, json.dumps(receipt["entry"])))
        conn.commit()
    def identity(profile, subject, request_id):
        assert (profile, subject, request_id) == (str(home), principal, REQUEST)
        return sid
    def track(authority, operation):
        task = asyncio.create_task(operation)
        authority._mutation_tasks.add(task)
        task.add_done_callback(authority._mutation_tasks.discard)
        return task
    @contextmanager
    def scope(value):
        yield
    class Transport:
        def __init__(self, *args):
            pass
        def close(self):
            pass
    class Connection:
        def __init__(self, owner, transport, identity, *, operator):
            assert owner is authority and not operator
            assert identity["user_id"] == principal and identity["profile_scope"] == "profile"
        async def dispatch(self, request):
            state.calls.append(request)
            if state.entered:
                state.entered.set()
            if state.wait:
                await state.wait.wait()
            commit()
            if state.lost:
                raise TimeoutError("native response lost after committed creation")
            return {"result": {"session_id": sid}}
        async def close(self):
            if state.cleanup_entered:
                state.cleanup_entered.set()
            if state.cleanup:
                await state.cleanup.wait()
            state.closed = True
    grant = dict(subject=principal, profile_id=str(home), instance_id="native-owner",
                 scope="profile", capabilities=["session:create", "session:read"])
    runner = SimpleNamespace(
        session_authority=authority,
        session_runtime_descriptor=dict(state="ready", instance_id="native-owner", authority_epoch=7),
        session_store=SimpleNamespace(_generate_session_key=lambda source: route),
        session_ticket_store=SimpleNamespace(redeem=lambda *args, **kwargs: grant),
        session_control_server=SimpleNamespace(private_handlers={}), _draining=False)
    authority.runner = runner
    module(monkeypatch, "hermes_state_keys", local_identity=identity)
    module(monkeypatch, "hermes_state_local", POLICY_PREFIX="policy:", local_receipt=local_receipt,
           same_create_retry=lambda saved, retry, client: json.loads(saved["request_json"]) == json.loads(retry) and client == {})
    module(monkeypatch, "hermes_state_mutation_retirement",
           retired_in=lambda connection, sid: connection.execute("SELECT 1 FROM state_meta WHERE key=?", ("retired:" + sid,)).fetchone() is not None)
    def lineage(connection, captured):
        assert connection is conn and connection.in_transaction
        return captured["entry"]["session_id"]
    def epoch(connection, expected):
        assert connection is conn and connection.in_transaction
        assert connection.execute("SELECT epoch FROM runtime_epoch WHERE singleton=1").fetchone()[0] == expected
    class Origin:
        def __init__(self, value):
            self.value = dict(value)
            self.profile = value.get("profile")
        def to_dict(self):
            return dict(self.value, profile=self.profile)
    class Entry:
        @staticmethod
        def from_dict(value):
            return SimpleNamespace(session_id=value["session_id"], session_key=value["session_key"],
                                   origin=Origin(value["origin"]))
    module(monkeypatch, "hermes_state_runtime", _epoch=epoch)
    module(monkeypatch, "hermes_state_local_lineage", validate_local_lineage=lineage)
    module(monkeypatch, "gateway.session", SessionEntry=Entry)
    module(monkeypatch, "gateway.session_local_recovery",
           local_source=lambda authority, sid, principal: Origin(dict(chat_id=sid, user_id=principal, profile=None)))
    module(monkeypatch, "gateway.session_runtime_workers", track_mutation=track,
           mutation_tasks=lambda authority: [t for t in authority._mutation_tasks if not t.done()])
    module(monkeypatch, "gateway.session_controls", AuthorityConnection=Connection)
    module(monkeypatch, "gateway.run_api", _embedded_chat_enabled=lambda: True)
    module(monkeypatch, "gateway.session_authorities", owner_scope=scope)
    module(monkeypatch, "gateway.run_idle_exit", attached_client=scope)
    module(monkeypatch, "tui_gateway.transport", StdioTransport=Transport,
           bind_transport=lambda transport: "bound", reset_transport=lambda token: None)
    monkeypatch.setattr(control, "_db", lambda home: db)
    params = dict(operation="enroll_session", implementation_sha=SHA, request_id=REQUEST,
                  profile_id=str(home), ticket="native-ticket")
    value = SimpleNamespace(home=home, principal=principal, sid=sid, route=route, conn=conn, db=db,
                            runner=runner, state=state, receipt=receipt, commit=commit, grant=grant,
                            params=params, authority=authority)
    yield value
    conn.close()


def inspect(native):
    return control._inspect_enrollment(native.runner, native.home, SHA, REQUEST, native.principal)


def test_qualified_absence_creates_once_and_reuses_the_native_original(native):
    async def run():
        assert inspect(native)["status"] == "ABSENT"
        result = await control._enrollment_operation(native.runner, native.home, native.params, native.principal)
        assert result["status"] == "ENROLLED"
        assert result["target"]["session_id"] == native.sid
        assert result["target"]["principal_id"] == native.principal
        assert native.state.closed
        again = await control._enrollment_operation(native.runner, native.home, native.params, native.principal)
        assert again == result
        assert native.state.calls == [{"jsonrpc": "2.0", "id": 1, "method": "session.create",
                                      "params": {"request_id": REQUEST, "source": "tool"}}]
    asyncio.run(run())


@pytest.mark.parametrize("state", ["orphan-row", "orphan-route", "retired", "corrupt", "huge", "changed-policy", "foreign-principal"])
def test_unknown_or_conflicting_store_state_never_creates(native, state):
    if state == "orphan-row":
        native.conn.execute("INSERT INTO sessions(id,source,user_id,runtime_revision,runtime_generation) VALUES(?,?,?,?,?)",
                            (native.sid, "tool", native.principal, 0, 0))
    elif state == "orphan-route":
        native.conn.execute("INSERT INTO gateway_routing VALUES('',?,?)", (native.route, "{}"))
    elif state == "retired":
        native.conn.execute("INSERT INTO state_meta VALUES(?,?)", ("retired:" + native.sid, "{}"))
    else:
        native.commit()
        saved = dict(native.receipt)
        if state == "changed-policy":
            saved["policy"] = dict(source="tool", request_json='{"source":"cli"}')
        if state == "foreign-principal":
            saved["principal_id"] = "uid:foreign"
        encoded = "{" if state == "corrupt" else ("x" * 65537 if state == "huge" else json.dumps(saved))
        native.conn.execute("UPDATE state_meta SET value=? WHERE key=?", (encoded, "policy:" + native.sid))
    native.conn.commit()
    async def run():
        assert inspect(native)["status"] in {"REFUSED", "UNAVAILABLE"}
        result = await control._enrollment_operation(native.runner, native.home, native.params, native.principal)
        assert result["status"] in {"REFUSED", "UNAVAILABLE"}
        assert native.state.calls == []
    asyncio.run(run())


def test_lost_native_reply_recovers_committed_original_after_detach(native):
    native.state.lost = True
    result = asyncio.run(control._enrollment_operation(native.runner, native.home, native.params, native.principal))
    assert result["status"] == "ENROLLED" and native.state.closed
    assert len(native.state.calls) == 1


def test_response_cancellation_retains_native_mutation_through_cleanup(native):
    async def run():
        native.state.entered, native.state.wait = asyncio.Event(), asyncio.Event()
        native.state.cleanup_entered, native.state.cleanup = asyncio.Event(), asyncio.Event()
        response = asyncio.create_task(control._enrollment_operation(
            native.runner, native.home, native.params, native.principal))
        await asyncio.wait_for(native.state.entered.wait(), 1)
        response.cancel()
        with pytest.raises(asyncio.CancelledError):
            await response
        assert inspect(native)["status"] == "EFFECT_UNKNOWN"
        tasks = list(native.authority._mutation_tasks)
        assert len(tasks) == 1 and not tasks[0].done()
        native.state.wait.set()
        await asyncio.wait_for(native.state.cleanup_entered.wait(), 1)
        assert not tasks[0].done() and not native.state.closed
        native.state.cleanup.set()
        await asyncio.wait_for(tasks[0], 1)
        assert inspect(native)["status"] == "ENROLLED"
        assert len(native.state.calls) == 1 and native.state.closed
    asyncio.run(run())


@pytest.mark.parametrize("field,value", [
    ("request_id", "replacement"), ("implementation_sha", "b" * 40),
    ("profile_id", "/foreign"), ("extra", True), ("peer", "uid:foreign")])
def test_private_owner_refuses_wrong_frozen_request_before_native_work(native, field, value):
    async def run():
        control.install_private_control(native.runner, native.home, "mmsecretary",
            implementation_sha=SHA, session_enrollment={"schema": control.ENROLLMENT_SCHEMA, "request_id": REQUEST})
        params, peer = dict(native.params), native.principal
        if field == "peer":
            peer = value
        else:
            params[field] = value
        response = await asyncio.to_thread(
            native.runner.session_control_server.private_handlers[control.VERB], params, peer)
        assert response["status"] == "REFUSED" and native.state.calls == []
    asyncio.run(run())


def test_v1_installation_has_no_enrollment_capability(native):
    async def run():
        control.install_private_control(native.runner, native.home, "mmsecretary", implementation_sha=SHA)
        value = await asyncio.to_thread(
            native.runner.session_control_server.private_handlers[control.VERB], native.params, native.principal)
        assert value["status"] == "REFUSED" and native.state.calls == []
    asyncio.run(run())


@pytest.mark.parametrize("operation", ["inspect_enrollment", "enroll_session"])
def test_http_dispatch_cannot_admit_enrollment(tmp_path, operation):
    client = control.NativeSecretaryClient(tmp_path, expected_pid=123)
    with pytest.raises(RuntimeRefusal):
        client.dispatch({"operation": operation, "implementation_sha": SHA, "request_id": REQUEST})


@pytest.mark.parametrize("change", [
    {"target": {}}, {"status": "CREATED"}, {"request_id": "\ud800"}, {"request_id": "x" * 257},
    {"implementation_sha": "wrong"}, {"extra": True},
])
def test_enrollment_result_is_closed_and_never_synthesizes_a_target(change):
    value = control.enrollment_result(SHA, REQUEST, "ABSENT")
    value.update(change)
    with pytest.raises(RuntimeRefusal):
        control.validate_enrollment_result(value)


def test_enrollment_parses_only_the_bounded_snapshot_without_reopening_receipt(native, monkeypatch):
    native.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError("bounded enrollment must not reopen the native receipt")
    monkeypatch.setattr(control, "_target", forbidden)
    monkeypatch.setattr(sys.modules["hermes_state_local"], "local_receipt", forbidden)
    result = asyncio.run(control._enrollment_operation(
        native.runner, native.home, native.params, native.principal))
    assert result["status"] == "ENROLLED" and native.state.calls == []
    assert not native.conn.in_transaction


def test_native_lineage_keeps_the_original_logical_enrollment_identity(native):
    native.commit()
    tip = native.sid + "-rotated"
    native.conn.execute(
        "INSERT INTO sessions(id,source,user_id,runtime_revision,runtime_generation,session_key,chat_id,parent_session_id) VALUES(?,?,?,?,?,?,?,?)",
        (tip, "tool", native.principal, 0, 0, native.route, native.sid, native.sid))
    receipt = dict(native.receipt, lineage=[native.sid, tip],
                   entry=dict(native.receipt["entry"], session_id=tip))
    native.conn.execute("UPDATE state_meta SET value=? WHERE key=?", (json.dumps(receipt), "policy:" + native.sid))
    native.conn.execute("UPDATE gateway_routing SET entry_json=?", (json.dumps(receipt["entry"]),))
    native.conn.execute("UPDATE sessions SET runtime_revision=4,runtime_generation=1 WHERE id=?", (native.sid,))
    native.conn.commit()
    result = asyncio.run(control._enrollment_operation(
        native.runner, native.home, native.params, native.principal))
    assert result["status"] == "ENROLLED"
    assert result["target"]["session_id"] == native.sid
    assert result["target"]["revision"] == 4
    assert result["target"]["execution_generation"] == 1
    assert native.state.calls == [] and not native.conn.in_transaction
