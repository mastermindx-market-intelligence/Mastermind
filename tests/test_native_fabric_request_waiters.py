"""Request-demand source regressions; real SQLite, no provider/host/lease grants.

The source reference contains reviewed incumbent method excerpts after #1443's
logical-priority and sibling-priority patches. It is not an installable broker.
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
import itertools
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
from typing import List, Optional
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "ops/native_fabric/routing_audit_20261013/request_waiters"
PREIMAGE = os.environ.get("FABRIC_REQUEST_TEST_PREIMAGE") == "1"
PRIORITY = {"heal": 0, "build": 1, "review": 2, "mechanical": 3}


def source_bytes():
    before = (BUNDLE / "reference.py.txt").read_bytes()
    if PREIMAGE:
        return before
    with tempfile.TemporaryDirectory(prefix="fabric-request-slice-") as name:
        work = Path(name)
        (work / "ext").mkdir()
        target = work / "ext/lease_broker.py"
        target.write_bytes(before)
        result = subprocess.run(["git", "apply", str(BUNDLE / "request_waiters.patch")],
                                cwd=work, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return target.read_bytes()


SOURCE = source_bytes()
namespace = {"sqlite3": sqlite3, "List": List, "Optional": Optional,
             "uuid": uuid, "CLASS_PRIORITY": PRIORITY}
exec(compile(SOURCE, "<source-backed-request-waiters>", "exec"), namespace)
Broker = namespace["Broker"]


def identity(root="root-a", pool="synthetic", request="request-a"):
    # Current acquire initializes waiter_id=None; the candidate derives one
    # stable demand ID. The baseline fallback reproduces that current behavior.
    factory = namespace.get("_request_waiter_id", lambda *_: None)
    return factory(root, pool, request)


def database(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS waiters (
            id TEXT PRIMARY KEY, orchestrator_id TEXT NOT NULL,
            pool TEXT NOT NULL, account TEXT, task_class TEXT NOT NULL,
            host TEXT, enqueued_at REAL NOT NULL, priority INTEGER NOT NULL,
            need INTEGER NOT NULL DEFAULT 1, last_heartbeat REAL);
        CREATE TABLE IF NOT EXISTS leases (
            id TEXT PRIMARY KEY, orchestrator_id TEXT, pool TEXT, state TEXT);
    ''')
    return conn


@pytest.fixture
def state():
    conn = database()
    broker = Broker()
    clock = [1000.0]
    broker.now = lambda: clock[0]
    broker.provider_name = lambda name: name
    broker.pool_cap = lambda _: 12
    yield broker, conn, clock
    conn.close()


def enqueue(state, request, job="mechanical", root="root-a", pool="synthetic", account=None, host="host"):
    broker, conn, _ = state
    return broker._enqueue_waiter(conn, identity(root, pool, request), root,
                                  pool, account, "remote-synthetic", host, job_class=job)


def front(state, request, job="mechanical", root="root-a", pool="synthetic"):
    broker, conn, _ = state
    kwargs = {"job_class": job}
    if "waiter_id" in inspect.signature(broker._front_of_queue).parameters:
        kwargs["waiter_id"] = identity(root, pool, request)
    return broker._front_of_queue(conn, pool, root, "remote-synthetic", **kwargs)


def clear(state, request, root="root-a", pool="synthetic"):
    broker, conn, _ = state
    method = getattr(broker, "_clear_acquired_waiter", None)
    if method is None:
        # Verbatim successful-acquire cleanup SQL in the source-backed broker.
        conn.execute("DELETE FROM waiters WHERE orchestrator_id=? AND pool=?", (root, pool))
    else:
        method(conn, pool, root, identity(root, pool, request))
    conn.commit()


def rows(state):
    return [dict(row) for row in state[1].execute("SELECT * FROM waiters ORDER BY enqueued_at, rowid")]


def test_same_root_siblings_preserve_individual_demand(state):
    a = enqueue(state, "request-a", "heal", account="account-a", host="host-a")
    state[2][0] += 1
    b = enqueue(state, "request-b", "review", account="account-b", host="host-b")
    assert a != b
    assert [(r["account"], r["host"], r["priority"]) for r in rows(state)] == [
        ("account-a", "host-a", 0), ("account-b", "host-b", 2)]


def test_refresh_changes_only_its_own_heartbeat(state):
    enqueue(state, "a", "heal")
    state[2][0] += 1
    enqueue(state, "b", "review")
    original = rows(state)
    state[2][0] += 15
    enqueue(state, "a", "heal")
    current = rows(state)
    assert len(current) == 2
    assert current[0]["enqueued_at"] == original[0]["enqueued_at"]
    assert current[0]["last_heartbeat"] == state[2][0]
    assert current[1] == original[1]


def test_success_clears_only_the_exact_request(state):
    enqueue(state, "a", "heal")
    enqueue(state, "b", "review")
    clear(state, "a")
    assert [r["id"] for r in rows(state)] == [identity(request="b")]


def test_unqueued_success_cannot_erase_existing_sibling(state):
    enqueue(state, "a")
    before = rows(state)
    clear(state, "not-enqueued")
    assert rows(state) == before


def test_legacy_enqueue_cannot_overwrite_scoped_request(state):
    enqueue(state, "a", "heal")
    state[2][0] += 1
    legacy = enqueue(state, None, "mechanical")
    current = rows(state)
    assert len(current) == 2
    assert not legacy.startswith("rq-")
    assert current[0]["priority"] == 0


def test_legacy_cleanup_does_not_erase_scoped_requests(state):
    enqueue(state, "a", "heal")
    enqueue(state, None, "mechanical")
    clear(state, None)
    assert [r["id"] for r in rows(state)] == [identity(request="a")]


def test_scoped_cleanup_leaves_legacy_demand(state):
    legacy = enqueue(state, None, "review")
    enqueue(state, "a", "heal")
    clear(state, "a")
    assert [r["id"] for r in rows(state)] == [legacy]


@pytest.mark.parametrize("job", list(PRIORITY))
def test_new_sibling_cannot_borrow_same_priority_fifo_position(state, job):
    enqueue(state, "a", job)
    state[2][0] += 1
    enqueue(state, "b", job, root="root-b")
    assert front(state, "a", job)
    assert not front(state, "new-sibling", job)


def test_different_priority_sibling_does_not_bypass_own_urgent_demand(state):
    enqueue(state, "a", "heal")
    assert not front(state, "b", "mechanical")
    assert front(state, "b", "heal") is False


def test_legacy_request_cannot_borrow_scoped_fifo(state):
    enqueue(state, "a", "review")
    state[2][0] += 1
    enqueue(state, "b", "review", root="root-b")
    assert not front(state, None, "review")


def test_priority_change_requeues_without_stealing_old_position(state):
    enqueue(state, "a", "heal")
    state[2][0] += 1
    enqueue(state, "b", "review", root="root-b")
    state[2][0] += 1
    enqueue(state, "a", "review")
    current = {r["id"]: r for r in rows(state)}
    assert current[identity(request="a")]["enqueued_at"] == state[2][0]
    assert not front(state, "a", "review")


def test_identical_request_keeps_fifo_position_on_refresh(state):
    enqueue(state, "a", "review")
    state[2][0] += 1
    enqueue(state, "b", "review", root="root-b")
    state[2][0] += 20
    enqueue(state, "a", "review")
    assert front(state, "a", "review")
    assert len(rows(state)) == 2


def test_equal_timestamps_keep_insertion_fifo(state):
    enqueue(state, "first", "review")
    enqueue(state, "second", "review")
    assert front(state, "first", "review")
    assert not front(state, "second", "review")


@pytest.mark.parametrize("root,pool", [("root-b", "synthetic"), ("root-a", "other")])
def test_same_request_name_is_scoped_to_root_and_pool(state, root, pool):
    a = enqueue(state, "same")
    b = enqueue(state, "same", root=root, pool=pool)
    assert a != b
    assert identity(request="same") != identity(root, pool, "same")
    clear(state, "same")
    assert len(rows(state)) == 1


def test_identity_is_stable_across_processes_and_uses_all_scope_fields():
    factory = namespace.get("_request_waiter_id")
    assert factory is not None
    expected = "rq-" + hashlib.sha256(json.dumps(
        ["root-a", "synthetic", "request-a"], separators=(",", ":")).encode()).hexdigest()
    assert identity() == expected
    assert identity() == identity()
    assert len({identity(), identity(root="root-b"), identity(pool="other"), identity(request="b")}) == 4


@pytest.mark.parametrize("run_id", [0, 1, True, [], {}, " ", "a b", "x/y", "x\n", "-bad", "a" * 129])
def test_invalid_request_identity_is_rejected(run_id):
    with pytest.raises(ValueError, match="invalid_request_id"):
        identity(request=run_id)


@pytest.mark.parametrize("run_id", [None, ""])
def test_absent_request_identity_retains_legacy_mode(run_id):
    assert identity(request=run_id) is None


@pytest.mark.parametrize("run_id", ["a", "a:b.c_d-e", "a" * 128])
def test_valid_bounded_request_identity(run_id):
    value = identity(request=run_id)
    assert isinstance(value, str) and value.startswith("rq-") and len(value) == 67


def test_many_siblings_do_not_multiply_root_fair_share(state):
    for i in range(16):
        enqueue(state, f"a-{i}")
    enqueue(state, "b", root="root-b")
    assert len(rows(state)) == 17
    broker, conn, _ = state
    assert broker._active_orchestrators(conn, "synthetic") == ["root-a", "root-b"]
    assert broker.fair_share(conn, "synthetic") == 6
    assert broker.fair_share(conn, "synthetic", extra="root-c") == 4


def test_existing_heartbeat_expiry_remains_request_local(state):
    enqueue(state, "old")
    state[2][0] += 80
    enqueue(state, "alive")
    state[2][0] += 20
    # Unchanged incumbent expiry predicate; no added queue owner or TTL.
    state[1].execute("DELETE FROM waiters WHERE COALESCE(last_heartbeat, enqueued_at) < ?",
                     (state[2][0] - 90,))
    assert [r["id"] for r in rows(state)] == [identity(request="alive")]


def test_wrong_scope_cleanup_cannot_remove_any_demand(state):
    enqueue(state, "a")
    before = rows(state)
    clear(state, "a", root="another-root")
    clear(state, "a", pool="other-pool")
    assert rows(state) == before


def test_corrupt_cross_root_scoped_row_is_not_replaced(state):
    broker, conn, _ = state
    wanted = identity(request="a")
    assert wanted is not None
    conn.execute("INSERT INTO waiters VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (wanted, "wrong-root", "synthetic", None, "remote-synthetic", "host", 0, 3, 1, 0))
    conn.commit()
    before = rows(state)
    with pytest.raises(ValueError, match="waiter_scope_mismatch"):
        enqueue(state, "a")
    assert rows(state) == before


def test_queue_fifo_matches_request_level_reference(state):
    broker, conn, clock = state
    names = ["a", "b", "c"]
    roots = ["root-a", "root-a", "root-b"]
    jobs = list(PRIORITY) + ["unknown"]
    for priorities in itertools.product(jobs, repeat=3):
        for order in itertools.permutations(range(3)):
            conn.execute("DELETE FROM waiters")
            for stamp, index in enumerate(order):
                clock[0] = 1000 + stamp
                enqueue(state, names[index], priorities[index], roots[index])
            expected = min(range(3), key=lambda i: (PRIORITY.get(priorities[i], 4), order.index(i)))
            for index in range(3):
                assert front(state, names[index], priorities[index], roots[index]) == (index == expected)


def test_parallel_siblings_under_existing_single_writer_lock(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    database(path).close()
    writer_lock = threading.Lock()
    def job(i):
        with writer_lock:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            broker = Broker()
            broker.now = lambda: float(i + 1000)
            broker.provider_name = lambda name: name
            broker.pool_cap = lambda _: 12
            try:
                state = (broker, conn, [float(i + 1000)])
                enqueue(state, f"parallel-{i}")
                enqueue(state, f"parallel-{i}")
            finally:
                conn.close()
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(job, range(32)))
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM waiters").fetchone()[0] == 32
        assert conn.execute("SELECT COUNT(DISTINCT orchestrator_id) FROM waiters").fetchone()[0] == 1


def test_legacy_id_collision_cannot_replace_foreign_root(state):
    broker, conn, _ = state
    conn.execute("INSERT INTO waiters VALUES (?,?,?,?,?,?,?,?,?,?)",
                 ("legacy-collision", "foreign", "synthetic", None, "mechanical", "host", 0, 3, 1, 0))
    conn.commit()
    before = rows(state)
    with pytest.raises(sqlite3.IntegrityError):
        broker._enqueue_waiter(conn, "legacy-collision", "root-a", "synthetic", None,
                               "mechanical", "host")
    assert rows(state) == before


def test_patch_handles_actual_intervening_register_demand_method():
    before = (BUNDLE / "reference.py.txt").read_text()
    if "    def _register_demand(" not in before:
        before = before.replace("    def _front_of_queue(", '''    def _register_demand(
        self, conn, waiter_id, orch, pool, account, task_class, host,
        need=1, job_class=None,
    ):
        wid = self._enqueue_waiter(
            conn, waiter_id, orch, pool, account, task_class, host, need, job_class=job_class
        )
        share_now = self.fair_share(conn, pool)
        if self._below_share_waiters(conn, pool, "", share_now):
            self._mark_surplus_nonrenewable(conn, pool, share_now)
            conn.commit()
        return wid

    def _front_of_queue(''')
    before = before.replace("\n\nclass Broker:", "\n\n# native dataclasses remain between helper and Broker\n\nclass Broker:")
    with tempfile.TemporaryDirectory(prefix="fabric-request-offset-") as name:
        root = Path(name)
        (root / "ext").mkdir()
        (root / "ext/lease_broker.py").write_text("# source offset\n" * 600 + before)
        result = subprocess.run(["git", "apply", str(BUNDLE / "request_waiters.patch")],
                                cwd=root, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        ast.parse((root / "ext/lease_broker.py").read_text())


def wired_contexts():
    records = json.loads((BUNDLE / "wiring_contexts.json").read_text())
    if PREIMAGE:
        return {row["name"]: row["before"] for row in records}
    with tempfile.TemporaryDirectory(prefix="fabric-request-wire-") as name:
        root = Path(name)
        for path in {row["path"] for row in records}:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("".join(row["before"] + "\n\n" for row in records if row["path"] == path))
        result = subprocess.run(["git", "apply", str(BUNDLE / "request_waiters_wiring.patch")],
                                cwd=root, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        for path in {row["path"] for row in records}:
            expected = "".join(row["after"] + "\n\n" for row in records if row["path"] == path)
            assert (root / path).read_text() == expected
    return {row["name"]: row["after"] for row in records}


def test_wiring_carries_identity_at_each_broker_boundary():
    wire = wired_contexts()
    assert 'request_id: Optional[str] = None' in wire["acquire_signature"]
    assert '_request_waiter_id(orchestrator_id, pool, request_id)' in wire["acquire_identity"]
    assert 'waiter_id=waiter_id' in wire["queue_identity"]
    assert 'self._clear_acquired_waiter(conn, pool, orch, waiter_id)' in wire["success_cleanup"]
    assert 'request_id=args.request_id' in wire["cli_forward"]
    assert '"--request-id", default=None' in wire["cli_flag"]


def test_acquire_normalization_and_invalid_identity_before_lock():
    import textwrap
    block = wired_contexts()["acquire_identity"]
    # This invokes the actual amended identity block before the native lock/loop,
    # using only source-local stand-ins for its immutable result/time values.
    fake_source = ('def run(self, orchestrator_id, pool, request_id, wait=0):\n' +
                   textwrap.indent(textwrap.dedent(block), '    ') +
                   '    return waiter_id\n')
    env = {'_request_waiter_id': namespace.get('_request_waiter_id', lambda *_: None),
           'AcquireResult': lambda **kw: kw}
    exec(fake_source, env)
    owner = type('Clock', (), {'now': lambda _: 1.0})()
    assert env['run'](owner, 'root-a', 'synthetic', 'request-a') == identity()
    refused = env['run'](owner, 'root-a', 'synthetic', 'bad id')
    assert isinstance(refused, dict) and refused['reason'] == 'invalid_request_id'
    assert env['run'](owner, '', 'synthetic', 'request-a')['reason'] == 'missing_orchestrator_id'


@pytest.mark.parametrize("native", ["0", "1"])
def test_remote_shell_forwards_original_root_and_stable_request(tmp_path, native):
    wire = wired_contexts()["remote_forward"] + '  fi\nfi\n'
    # Execute only the retained acquisition call block with an argv recorder.
    # This is not remote_sub, a lease broker, SSH, a provider or a live host.
    script = tmp_path / 'record.sh'
    output = tmp_path / 'argv'
    script.write_text('''set -e
broker() { printf '%s\\n' "$@" > "$OUT"; }
log() { :; }
show_args() { printf '%s\\n' "$@" > "$OUT"; }
OPERATOR_CHILD_ARGS=(--operator-child-id "$ID")
''' + wire)
    env = {**os.environ, 'ACQUIRE_POOL': 'synthetic', 'DRY_RUN': '0',
           'NATIVE_MODE': native, 'ID': 'stable-child', 'MODE': 'glm',
           'POOL_TASK_CLASS': 'heal', 'MODEL': 'synthetic-model',
           'HOST_ARG': 'synthetic-host', 'POOL_ORCHESTRATOR_ID': 'original-root',
           'PROVIDER_LEASE_TTL': '180', 'LEASE_OUTPUT_FILE': str(tmp_path/'out'),
           'OUT': str(output)}
    result = subprocess.run(['bash', str(script)], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    args = output.read_text().splitlines()
    assert args[args.index('--request-id')+1] == 'stable-child'
    assert args[args.index('--orchestrator-id')+1] == 'original-root'
    assert args[args.index('--task-class')+1] == 'remote-glm'
    assert args[args.index('--job-class')+1] == 'heal'
    assert args[args.index('--operator-child-id')+1] == 'stable-child'
    assert args[args.index('--ttl')+1] == '180'


def test_remote_dry_run_uses_same_request_identity(tmp_path):
    wire = wired_contexts()["remote_forward"] + '  fi\nfi\n'
    source = 'show_args() { printf "%s\\n" "$@"; }; log() { :; };\n' + wire
    env = {**os.environ, 'ACQUIRE_POOL': 'synthetic', 'DRY_RUN': '1',
           'ID': 'stable-child', 'MODE': 'glm', 'MODEL': 'synthetic',
           'PROVIDER_LEASE_TTL': '180', 'POOL_TASK_CLASS': 'review'}
    result = subprocess.run(['bash', '-c', source], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    args = result.stdout.splitlines()
    assert args[args.index('--request-id')+1] == 'stable-child'
    assert args[args.index('--task-class')+1] == 'remote-glm'


def test_wiring_patch_does_not_depend_on_excerpt_separators():
    records = json.loads((BUNDLE / 'wiring_contexts.json').read_text())
    with tempfile.TemporaryDirectory(prefix='fabric-request-wire-shape-') as name:
        root = Path(name)
        for path in {r['path'] for r in records}:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('# source offset\n' * 800 + ''.join(
                r['before'] + '# intervening native implementation\n' * 15
                for r in records if r['path'] == path))
        answer = subprocess.run(['git', 'apply', str(BUNDLE/'request_waiters_wiring.patch')],
                                cwd=root, text=True, capture_output=True)
        assert answer.returncode == 0, answer.stderr
