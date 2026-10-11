"""Independent synthetic review probes. No host, browser, network or credential use."""
import dataclasses
import pytest
from control_plane.workbench_attended_context import AttendedContextError, AttendedTargetBroker
from test_workbench_attended_context import Owner, _caller

class Clock:
    def __init__(self):
        self.now = 2000
    def __call__(self):
        return self.now

class DelayedOwner(Owner):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.delay = 0
    def list_targets(self, caller, identity):
        self.clock.now += self.delay
        return super().list_targets(caller, identity)

def setup(*, max_snapshot_age_ms=10000):
    clock = Clock()
    owner = DelayedOwner(clock)
    broker = AttendedTargetBroker(
        signing_key=b"synthetic-review-key-not-secret!!",
        clock_ms=clock,
        resolve_identity=owner.resolve_identity,
        list_targets=owner.list_targets,
        max_option_ttl_ms=30000,
        max_context_ttl_ms=60000,
        max_snapshot_age_ms=max_snapshot_age_ms,
    )
    return clock, owner, broker

def option(broker, caller):
    return broker.list_permitted_targets(caller, client_call_ref="call:review-list")["target_options"][0]["target_option_ref"]

def prepare(broker, caller, ref):
    return broker.prepare_attended_context(caller, target_option_ref=ref,
        requested_scope=("project.read",), client_call_ref="call:review-prepare")

def test_control_roundtrip_without_owner_delay():
    clock, owner, broker = setup()
    caller = _caller()
    prepared = prepare(broker, caller, option(broker, caller))
    actual = broker.resolve_context(caller, prepared["workbench_context_ref"])
    assert actual.expires_at_ms == 62000 and clock.now == 2000

@pytest.mark.parametrize("delay", [10000, 31000], ids=["snapshot-age-crossed", "option-expiry-crossed"])
def test_prepare_refuses_time_boundary_crossed_during_owner_read(delay):
    clock, owner, broker = setup(max_snapshot_age_ms=10000 if delay == 10000 else 600000)
    caller = _caller()
    ref = option(broker, caller)
    owner.delay = delay
    with pytest.raises(AttendedContextError):
        prepare(broker, caller, ref)

@pytest.mark.parametrize("delay", [10000, 61000], ids=["snapshot-age-crossed", "context-expiry-crossed"])
def test_resolve_refuses_time_boundary_crossed_during_owner_read(delay):
    clock, owner, broker = setup(max_snapshot_age_ms=10000 if delay == 10000 else 600000)
    caller = _caller()
    prepared = prepare(broker, caller, option(broker, caller))
    owner.delay = delay
    with pytest.raises(AttendedContextError):
        broker.resolve_context(caller, prepared["workbench_context_ref"])

def test_minted_reference_is_decodable_or_input_is_refused_before_mint():
    clock, owner, broker = setup()
    # Non-ASCII URI path stays within the public caller field's 2048-character ceiling.
    caller = _caller(resource="https://example.invalid/" + "研" * 2000)
    try:
        ref = option(broker, caller)
    except AttendedContextError:
        return  # Refusing an unsupported input before issuing a ref is safe.
    prepared = prepare(broker, caller, ref)
    assert broker.resolve_context(caller, prepared["workbench_context_ref"]).resource == caller.resource

def test_malformed_ref_has_closed_error_not_unicode_exception():
    clock, owner, broker = setup()
    with pytest.raises(AttendedContextError):
        broker.resolve_context(_caller(), "\ud800.AA")
