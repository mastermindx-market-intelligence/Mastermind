"""Reviewer tests: delayed owner reads must not return expired target contexts."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.workbench_attended_context import AttendedContextError, AttendedTargetBroker
from test_workbench_attended_context import Owner, _caller, _target


class SlowOwner(Owner):
    def __init__(self):
        super().__init__()
        self.now = 2000
        self.advance_to = None
        self.refresh_snapshot = False

    def list_targets(self, caller, identity):
        if self.advance_to is not None:
            self.now = self.advance_to
            if self.refresh_snapshot:
                return dataclasses.replace(self.snapshot, observed_at_ms=self.now)
        return super().list_targets(caller, identity)


def create_case(*, caller_expiry=200, target_expiry=150000, option_ttl=30000, context_ttl=60000):
    owner = SlowOwner()
    owner.snapshot = dataclasses.replace(owner.snapshot, targets=(_target(expires_at_ms=target_expiry),))
    caller = _caller(expires_at=caller_expiry)
    broker = AttendedTargetBroker(
        signing_key=b"fixture-only-key-does-not-enroll-a-host",
        clock_ms=lambda: owner.now,
        resolve_identity=owner.resolve_identity,
        list_targets=owner.list_targets,
        max_option_ttl_ms=option_ttl,
        max_context_ttl_ms=context_ttl,
        max_snapshot_age_ms=10000,
    )
    option = broker.list_permitted_targets(caller, client_call_ref="call:seed")["target_options"][0]["target_option_ref"]
    context = broker.prepare_attended_context(caller, target_option_ref=option, requested_scope=("project.read",), client_call_ref="call:prepare-seed")["workbench_context_ref"]
    return owner, caller, broker, option, context


def invoke(which, caller, broker, option, context):
    if which == "list":
        return broker.list_permitted_targets(caller, client_call_ref="call:test-list")
    if which == "prepare":
        return broker.prepare_attended_context(caller, target_option_ref=option, requested_scope=("project.read",), client_call_ref="call:test-prepare")
    return broker.resolve_context(caller, context, required_scope=("project.read",))


@pytest.mark.parametrize("which", ["list", "prepare", "resolve"])
@pytest.mark.parametrize("case", ["caller", "target", "snapshot"])
def test_expiry_during_owner_lookup_refuses(which, case):
    kw = {"caller_expiry":3} if case == "caller" else ({"target_expiry":3000} if case == "target" else {})
    owner, caller, broker, option, context = create_case(**kw)
    owner.advance_to = 12000 if case == "snapshot" else 3100
    with pytest.raises(AttendedContextError):
        invoke(which, caller, broker, option, context)


def test_option_expires_during_prepare_owner_lookup():
    owner, caller, broker, option, context = create_case(option_ttl=1000)
    owner.advance_to = 3100
    with pytest.raises(AttendedContextError):
        invoke("prepare", caller, broker, option, context)


def test_context_expires_during_resolve_owner_lookup():
    owner, caller, broker, option, context = create_case(context_ttl=1000)
    owner.advance_to = 3100
    with pytest.raises(AttendedContextError):
        invoke("resolve", caller, broker, option, context)


@pytest.mark.parametrize("which", ["list", "prepare", "resolve"])
def test_clock_regression_during_owner_lookup_refuses(which):
    owner, caller, broker, option, context = create_case()
    owner.advance_to = 1900
    with pytest.raises(AttendedContextError):
        invoke(which, caller, broker, option, context)


@pytest.mark.parametrize("which", ["list", "prepare", "resolve"])
def test_fresh_owner_snapshot_after_start_is_usable(which):
    owner, caller, broker, option, context = create_case()
    owner.advance_to = 2300
    owner.refresh_snapshot = True
    result = invoke(which, caller, broker, option, context)
    if which == "list":
        assert result["status"] == "OK"
        assert result["observed_at_ms"] == 2300
        assert result["target_options"][0]["expires_at_ms"] > owner.now
    elif which == "prepare":
        assert result["status"] == "PREPARED"
        assert result["expires_at_ms"] > owner.now
    else:
        assert result.host_id == _target().host_id
        assert result.expires_at_ms > owner.now


@pytest.mark.parametrize("which", ["list", "prepare", "resolve"])
def test_delay_without_expiry_preserves_exact_target(which):
    owner, caller, broker, option, context = create_case()
    owner.advance_to = 2300
    result = invoke(which, caller, broker, option, context)
    if which == "resolve":
        assert result.host_id == _target().host_id
        assert result.target_ref == _target().target_ref
    elif which == "prepare":
        assert result["bound_target_ref"] == _target().target_ref
    else:
        assert result["target_options"][0]["target_ref"] == _target().target_ref
