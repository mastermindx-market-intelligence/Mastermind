"""Identity evidence only: no live admission or remote/provider execution."""
from __future__ import annotations

import copy
import dataclasses
import importlib
from types import SimpleNamespace

import pytest

HOST_A = "host-" + "a" * 64
HOST_B = "host-" + "b" * 64


@pytest.fixture
def api():
    try:
        return importlib.import_module("control_plane.executive_capacity_join")
    except ModuleNotFoundError:
        pytest.fail("the capacity-join reader is not implemented")


def join(**changes):
    value = {"schema": "mastermind.executive_capacity_join/v1", "host_ref": HOST_A,
             "capacity_capability_id": "codex_account_2",
             "provider_capacity_schema": "mastermind.provider_capacity.v1",
             "worker_source_config_digest": "c" * 64}
    value.update(changes)
    return value


def test_join_is_frozen_and_wire_is_defensive(api):
    raw = join()
    fact = api.validate_capacity_join(raw)
    raw["host_ref"] = HOST_B
    assert fact.host_ref == HOST_A
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.host_ref = HOST_B
    wire = fact.to_dict()
    wire["host_ref"] = HOST_B
    assert fact.to_dict() == join()


@pytest.mark.parametrize("field,value", [
    ("schema", "other"), ("host_ref", "127.0.0.1"), ("host_ref", "macbook"),
    ("host_ref", HOST_A + "\n"), ("host_ref", True),
    ("capacity_capability_id", "a/b"), ("capacity_capability_id", "a@b"),
    ("capacity_capability_id", "x" * 129),
    ("provider_capacity_schema", "other"),
    ("worker_source_config_digest", "C" * 64),
    ("worker_source_config_digest", "g" * 64),
    ("worker_source_config_digest", None),
])
def test_malformed_join_refuses(api, field, value):
    with pytest.raises(api.CapacityJoinError):
        api.validate_capacity_join(join(**{field: value}))


@pytest.mark.parametrize("raw", [None, [], {}, {**join(), "endpoint": "secret"}])
def test_closed_join_shape(api, raw):
    with pytest.raises(api.CapacityJoinError):
        api.validate_capacity_join(raw)


class Registry:
    def __init__(self):
        self.calls = []
        self.worker = SimpleNamespace(worker_id="worker-a", provider="codex")
        self.quota = SimpleNamespace(worker_id="worker-a", quota_class="pool",
                                     provider="codex", metadata={"capacity_join": join()})

    def get_worker(self, worker_id):
        self.calls.append(("worker", worker_id))
        return self.worker

    def get_quota_class(self, worker_id, quota_class):
        self.calls.append(("quota", worker_id, quota_class))
        return self.quota


def test_reader_returns_identity_only(api):
    registry = Registry()
    registry.quota.metadata["unrelated_secret"] = "DO_NOT_PROJECT"
    rows = api.read_remote_capacity_joins(registry, [("worker-a", "pool")])
    assert len(rows) == 1
    assert rows[0].capacity_join.host_ref == HOST_A
    assert rows[0].to_dict() == {"worker_id": "worker-a", "quota_class": "pool",
                                  "provider": "codex", "capacity_join": join()}
    assert registry.calls == [("quota", "worker-a", "pool")]
    assert "DO_NOT_PROJECT" not in str(rows[0].to_dict())


@pytest.mark.parametrize("keys", [[], "worker-a", [("worker-a",)],
    [("worker-a", "pool"), ("worker-a", "pool")], [("worker-a", "POOL")],
    [("worker-" + str(i), "pool") for i in range(4)]])
def test_bad_or_unbounded_keys_refuse_before_registry_io(api, keys):
    registry = Registry()
    with pytest.raises(api.CapacityJoinError):
        api.read_remote_capacity_joins(registry, keys)
    assert registry.calls == []


@pytest.mark.parametrize("change,code", [
    ("missing_quota", "QUOTA_MISSING"),
    ("quota_identity", "QUOTA_IDENTITY_MISMATCH"),
    ("missing_join", "JOIN_MISSING"),
    ("unbound", "REMOTE_HOST_UNBOUND"),
])
def test_registry_identity_refusals(api, change, code):
    registry = Registry()
    if change == "missing_quota": registry.quota = None
    elif change == "quota_identity": registry.quota.quota_class = "other"
    elif change == "missing_join": registry.quota.metadata = {}
    elif change == "unbound": registry.quota.metadata["capacity_join"] = join(host_ref="local-unbound")
    with pytest.raises(api.CapacityJoinError) as error:
        api.read_remote_capacity_joins(registry, [("worker-a", "pool")])
    assert error.value.code == code


def test_valid_local_canary_metadata_is_never_remote_evidence(api):
    assert api.validate_capacity_join(join(host_ref="local-unbound")).host_ref == "local-unbound"


def test_registry_error_is_not_missing_or_secret_output(api):
    registry = Registry()
    def denied(*_):
        raise PermissionError("SECRET_PROVIDER_PATH")
    registry.get_quota_class = denied
    with pytest.raises(api.CapacityJoinError) as error:
        api.read_remote_capacity_joins(registry, [("worker-a", "pool")])
    assert error.value.code == "REGISTRY_READ_FAILED"
    assert "SECRET_PROVIDER_PATH" not in str(error.value)


def test_real_registry_persistence_immutability_and_no_consumer_writes(api, tmp_path):
    from control_plane.executive_runtime import Runtime, StateConflict
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker("worker-a", provider="codex", account_label="not-a-capability-id",
                                     worker_type="mock", capabilities=["code"])
    kwargs = dict(provider="codex", metadata={"capacity_join": join()})
    runtime.workers.register_quota_class("worker-a", "pool", **kwargs)
    runtime.workers.register_quota_class("worker-a", "pool", **kwargs)
    def counts():
        with runtime.store.read() as connection:
            return tuple(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                         for table in ("workers", "worker_quota_classes", "jobs", "attempts", "events"))
    before = counts()
    rows = api.read_remote_capacity_joins(runtime.workers, [("worker-a", "pool")])
    assert rows[0].capacity_join.host_ref == HOST_A
    assert counts() == before
    with pytest.raises(StateConflict):
        runtime.workers.register_quota_class("worker-a", "pool", provider="codex",
            metadata={"capacity_join": join(host_ref=HOST_B)})
    assert api.read_remote_capacity_joins(runtime.workers, [("worker-a", "pool")]) == rows
    assert counts() == before


@pytest.mark.parametrize("second_host,refused", [(HOST_A, True), (HOST_B, False)])
def test_duplicate_capacity_identity_is_scoped_to_host(api, second_host, refused):
    registry = Registry()
    def worker(key):
        return SimpleNamespace(worker_id=key, provider="codex")
    def quota(key, name):
        return SimpleNamespace(worker_id=key, quota_class=name, provider="codex",
            metadata={"capacity_join": join(host_ref=HOST_A if key == "worker-a" else second_host)})
    registry.get_worker, registry.get_quota_class = worker, quota
    keys = [("worker-a", "pool"), ("worker-b", "pool")]
    if refused:
        with pytest.raises(api.CapacityJoinError, match="DUPLICATE_CAPACITY_JOIN"):
            api.read_remote_capacity_joins(registry, keys)
    else:
        rows = api.read_remote_capacity_joins(registry, keys)
        assert [r.capacity_join.host_ref for r in rows] == [HOST_A, HOST_B]
        # Distinct identity records are not two quota grants for a shared subscription.
        assert all(set(r.to_dict()) == {"worker_id", "quota_class", "provider", "capacity_join"} for r in rows)


def test_candidate_keys_are_consumed_once(api):
    class MovingKeys(list):
        calls = 0
        def __iter__(self):
            self.calls += 1
            return iter([("worker-a", "pool")] if self.calls == 1 else [("other", "pool")])
    keys = MovingKeys([("worker-a", "pool")])
    result = api.read_remote_capacity_joins(Registry(), keys)
    assert keys.calls == 1 and result[0].worker_id == "worker-a"


def test_oversized_custom_sequence_is_bounded_before_io(api):
    from collections.abc import Sequence
    class Endless(Sequence):
        reads = 0
        def __len__(self): return 1
        def __getitem__(self, index):
            self.reads += 1
            assert self.reads <= 4
            return ("worker-" + str(index), "pool")
    keys, registry = Endless(), Registry()
    with pytest.raises(api.CapacityJoinError):
        api.read_remote_capacity_joins(registry, keys)
    assert keys.reads == 4 and registry.calls == []


def test_oversized_inner_key_is_rejected_without_full_copy(api):
    import tracemalloc

    malformed = ["worker-a"] * 65_536
    registry = Registry()
    tracemalloc.start()
    try:
        with pytest.raises(api.CapacityJoinError, match="CANDIDATE_KEY_INVALID"):
            api.read_remote_capacity_joins(registry, [malformed])
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 65_536
    assert registry.calls == []


def test_no_unbounded_worker_materialization(api):
    registry = Registry()
    def forbidden(_):
        raise AssertionError("get_worker materializes all quota rows for this Worker")
    registry.get_worker = forbidden
    rows = api.read_remote_capacity_joins(registry, [("worker-a", "pool")])
    assert rows[0].worker_id == "worker-a"
    assert registry.calls == [("quota", "worker-a", "pool")]


@pytest.mark.parametrize("value", [None, True, "", "CODEX", "codex\n"])
def test_invalid_returned_provider_refuses(api, value):
    registry = Registry()
    registry.quota.provider = value
    with pytest.raises(api.CapacityJoinError, match="PROVIDER_INVALID"):
        api.read_remote_capacity_joins(registry, [("worker-a", "pool")])


def test_worker_provider_equality_is_enforced_by_existing_registration(api, tmp_path):
    from control_plane.executive_runtime import Runtime, StateConflict
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker("worker-a", provider="codex", account_label="different-label",
                                     worker_type="mock", capabilities=["code"])
    with pytest.raises(StateConflict, match="provider differs"):
        runtime.workers.register_quota_class("worker-a", "pool", provider="anthropic",
                                             metadata={"capacity_join": join()})
    assert runtime.workers.get_quota_class("worker-a", "pool") is None
    runtime.workers.register_quota_class("worker-a", "pool", provider="codex",
                                         metadata={"capacity_join": join()})
    reopened = Runtime.at(tmp_path)
    assert api.read_remote_capacity_joins(reopened.workers, [("worker-a", "pool")])[0].capacity_join.host_ref == HOST_A


def test_iterable_failure_is_closed_and_precedes_registry_io(api):
    class Broken(list):
        def __iter__(self): raise ValueError("PRIVATE_INPUT_DETAIL")
    registry = Registry()
    with pytest.raises(api.CapacityJoinError) as error:
        api.read_remote_capacity_joins(registry, Broken([("worker-a", "pool")]))
    assert error.value.code == "CANDIDATE_KEYS_INVALID"
    assert "PRIVATE_INPUT_DETAIL" not in str(error.value)
    assert registry.calls == []
