"""Review the temporal origin of genuine, owner-minted references."""
import pytest
from control_plane.workbench_attended_context import AttendedContextError, AttendedTargetBroker
from test_workbench_attended_context import Owner, _caller


def setup():
    owner = Owner()
    now = [2000]
    broker = AttendedTargetBroker(signing_key=b"review-only-synthetic-key-value!!",
        clock_ms=lambda: now[0], resolve_identity=owner.resolve_identity,
        list_targets=owner.list_targets, max_option_ttl_ms=30000,
        max_context_ttl_ms=60000, max_snapshot_age_ms=10000)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:list")["target_options"][0]["target_option_ref"]
    return broker, now, option


def prepare(broker, option):
    return broker.prepare_attended_context(_caller(), target_option_ref=option,
        requested_scope=("browser",), client_call_ref="call:prepare")


@pytest.mark.parametrize("stage", ["prepare", "resolve"])
def test_future_minted_reference_refuses_after_between_call_clock_rollback(stage):
    broker, now, option = setup()
    context = prepare(broker, option)["workbench_context_ref"]
    now[0] = 1999  # Snapshot at 1000 stays fresh; only reference origin is future.
    with pytest.raises(AttendedContextError):
        if stage == "prepare":
            prepare(broker, option)
        else:
            broker.resolve_context(_caller(), context, required_scope=("browser",))


@pytest.mark.parametrize("clock", [2000, 2001])
def test_equal_or_later_reference_time_still_resolves(clock):
    broker, now, option = setup()
    context = prepare(broker, option)["workbench_context_ref"]
    now[0] = clock
    assert broker.resolve_context(_caller(), context).issued_at_ms == 2000
