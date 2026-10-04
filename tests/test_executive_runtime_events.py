"""The existing Event owner reads the caller's transaction without another plane."""
from control_plane.executive_runtime import EventRegistry, RuntimeStore


def test_event_owner_reads_uncommitted_family_on_existing_connection(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path)
    with store.transaction() as connection:
        store.append_event(connection, aggregate_type="privileged_readiness", aggregate_id="pvrf-test",
            event_type="TEST", command_id="test-command")
        assert EventRegistry(store).list_events(aggregate_id="pvrf-test") == []
        def forbidden():
            raise AssertionError("transaction-aware read opened another connection")
        monkeypatch.setattr(store, "read", forbidden)
        inside = store.list_events(aggregate_type="privileged_readiness", aggregate_id="pvrf-test", connection=connection)
        assert len(inside) == 1 and inside[0].command_id == "test-command"
        delegated = EventRegistry(store).list_events(aggregate_id="pvrf-test", connection=connection)
        assert delegated == inside
        monkeypatch.undo()
    assert EventRegistry(store).list_events(aggregate_id="pvrf-test") == inside
    assert store.list_events(aggregate_type="another", aggregate_id="pvrf-test") == []
