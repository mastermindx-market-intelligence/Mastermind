from __future__ import annotations

import dataclasses

import pytest

from control_plane.workbench_attended_context import (
    AttendedCaller,
    AttendedContextError,
    AttendedIdentity,
    AttendedTargetBroker,
    PermittedWorkbenchTarget,
    TargetSnapshot,
)


def _caller(**overrides):
    values = dict(
        subject_digest="a" * 64,
        client_ref="client:web-ceo",
        resource="https://workbench.example/mcp",
        expires_at=200,
    )
    values.update(overrides)
    return AttendedCaller(**values)


def _identity(**overrides):
    values = dict(
        conversation_ref="conversation:" + "b" * 32,
        conversation_generation="conversation-generation:" + "c" * 16,
    )
    values.update(overrides)
    return AttendedIdentity(**values)


def _target(**overrides):
    values = dict(
        target_ref="target:" + "d" * 32,
        project_ref="project:" + "e" * 32,
        host_id="f" * 64,
        boot_generation="boot:" + "1" * 16,
        source_ref="source:" + "2" * 32,
        policy_generation="policy:" + "3" * 16,
        capability_generation="capability:" + "4" * 16,
        scope_ceiling=("project.read", "project.action", "browser"),
        expires_at_ms=150_000,
    )
    values.update(overrides)
    return PermittedWorkbenchTarget(**values)


class Owner:
    def __init__(self):
        self.identity = _identity()
        self.snapshot = TargetSnapshot(
            policy_generation="policy:" + "3" * 16,
            observed_at_ms=1_000,
            coverage="complete",
            issues=(),
            targets=(_target(),),
        )

    def resolve_identity(self, _caller):
        return self.identity

    def list_targets(self, _caller, _identity):
        return self.snapshot


def _broker(owner: Owner, *, now_ms=2_000):
    return AttendedTargetBroker(
        signing_key=b"k" * 32,
        clock_ms=lambda: now_ms,
        resolve_identity=owner.resolve_identity,
        list_targets=owner.list_targets,
        max_option_ttl_ms=30_000,
        max_context_ttl_ms=60_000,
        max_snapshot_age_ms=10_000,
    )


def test_list_projects_existing_owner_targets_without_selecting_one():
    owner = Owner()
    receipt = _broker(owner).list_permitted_targets(_caller(), client_call_ref="call:1")
    assert receipt["status"] == "OK"
    assert receipt["coverage"] == "complete"
    assert receipt["policy_generation"] == owner.snapshot.policy_generation
    assert len(receipt["target_options"]) == 1
    option = receipt["target_options"][0]
    assert option["target_ref"] == owner.snapshot.targets[0].target_ref
    assert option["project_ref"] == owner.snapshot.targets[0].project_ref
    assert option["scope_ceiling"] == ["browser", "project.action", "project.read"]
    assert isinstance(option["target_option_ref"], str)
    assert "mini" not in option["target_option_ref"].lower()


def test_prepare_context_revalidates_owner_and_only_shrinks_scope():
    owner = Owner()
    broker = _broker(owner)
    listing = broker.list_permitted_targets(_caller(), client_call_ref="call:1")
    option_ref = listing["target_options"][0]["target_option_ref"]
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=option_ref,
        requested_scope=("browser", "project.read"),
        client_call_ref="call:2",
    )
    assert prepared["status"] == "PREPARED"
    assert prepared["bound_scope"] == ["browser", "project.read"]
    assert prepared["bound_target_ref"] == _target().target_ref
    assert prepared["conversation_identity_ref"] == _identity().conversation_ref
    context = broker.resolve_context(
        _caller(),
        prepared["workbench_context_ref"],
        required_scope=("browser",),
    )
    assert context.target_ref == _target().target_ref
    assert context.host_id == _target().host_id
    assert context.scope == ("browser", "project.read")


def test_context_is_target_binding_not_tool_permission():
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=option["target_option_ref"],
        requested_scope=("browser",),
        client_call_ref="call:2",
    )
    context = broker.resolve_context(_caller(), prepared["workbench_context_ref"])
    assert context.scope == ("browser",)
    assert not hasattr(context, "token")
    assert not hasattr(context, "credential")
    assert not hasattr(context, "permissions")


@pytest.mark.parametrize("requested", [(), ("admin",), ("browser", "admin")])
def test_requested_scope_cannot_expand_owner_ceiling(requested):
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]
    with pytest.raises(AttendedContextError):
        broker.prepare_attended_context(
            _caller(),
            target_option_ref=option["target_option_ref"],
            requested_scope=requested,
            client_call_ref="call:2",
        )


def test_partial_target_coverage_lists_but_cannot_prepare():
    owner = Owner()
    owner.snapshot = dataclasses.replace(owner.snapshot, coverage="partial", issues=("host-observation-stale",))
    broker = _broker(owner)
    listing = broker.list_permitted_targets(_caller(), client_call_ref="call:1")
    assert listing["coverage"] == "partial"
    with pytest.raises(AttendedContextError, match="coverage"):
        broker.prepare_attended_context(
            _caller(),
            target_option_ref=listing["target_options"][0]["target_option_ref"],
            requested_scope=("browser",),
            client_call_ref="call:2",
        )


def test_foreign_caller_cannot_reuse_target_option_or_context():
    owner = Owner()
    broker = _broker(owner)
    listing = broker.list_permitted_targets(_caller(), client_call_ref="call:1")
    with pytest.raises(AttendedContextError):
        broker.prepare_attended_context(
            _caller(subject_digest="9" * 64),
            target_option_ref=listing["target_options"][0]["target_option_ref"],
            requested_scope=("browser",),
            client_call_ref="call:2",
        )
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=listing["target_options"][0]["target_option_ref"],
        requested_scope=("browser",),
        client_call_ref="call:2",
    )
    with pytest.raises(AttendedContextError):
        broker.resolve_context(
            _caller(client_ref="client:other"),
            prepared["workbench_context_ref"],
        )


def test_conversation_generation_change_invalidates_option_and_context():
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=option["target_option_ref"],
        requested_scope=("browser",),
        client_call_ref="call:2",
    )
    owner.identity = dataclasses.replace(
        owner.identity,
        conversation_generation="conversation-generation:" + "8" * 16,
    )
    with pytest.raises(AttendedContextError, match="conversation"):
        broker.resolve_context(_caller(), prepared["workbench_context_ref"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("host_id", "7" * 64),
        ("boot_generation", "boot:" + "7" * 16),
        ("source_ref", "source:" + "7" * 32),
        ("policy_generation", "policy:" + "7" * 16),
        ("capability_generation", "capability:" + "7" * 16),
    ],
)
def test_target_movement_invalidates_existing_context(field, value):
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=option["target_option_ref"],
        requested_scope=("browser",),
        client_call_ref="call:2",
    )
    moved = dataclasses.replace(owner.snapshot.targets[0], **{field: value})
    owner.snapshot = dataclasses.replace(owner.snapshot, targets=(moved,))
    with pytest.raises(AttendedContextError, match="target"):
        broker.resolve_context(_caller(), prepared["workbench_context_ref"])


def test_target_removed_invalidates_context():
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=option["target_option_ref"],
        requested_scope=("browser",),
        client_call_ref="call:2",
    )
    owner.snapshot = dataclasses.replace(owner.snapshot, targets=())
    with pytest.raises(AttendedContextError, match="target"):
        broker.resolve_context(_caller(), prepared["workbench_context_ref"])


def test_stale_target_snapshot_cannot_mint_or_resolve_context():
    owner = Owner()
    broker = _broker(owner, now_ms=2_000)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=option["target_option_ref"],
        requested_scope=("browser",),
        client_call_ref="call:2",
    )
    stale = dataclasses.replace(owner.snapshot, observed_at_ms=1_000)
    owner.snapshot = stale
    late = _broker(owner, now_ms=20_000)
    with pytest.raises(AttendedContextError, match="stale"):
        late.list_permitted_targets(_caller(), client_call_ref="call:3")
    with pytest.raises(AttendedContextError, match="stale"):
        late.resolve_context(_caller(), prepared["workbench_context_ref"])


def test_tampered_reference_is_refused():
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]["target_option_ref"]
    replacement = "A" if option[-1] != "A" else "B"
    with pytest.raises(AttendedContextError, match="reference"):
        broker.prepare_attended_context(
            _caller(),
            target_option_ref=option[:-1] + replacement,
            requested_scope=("browser",),
            client_call_ref="call:2",
        )


def test_option_and_context_references_are_domain_separated():
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]["target_option_ref"]
    with pytest.raises(AttendedContextError, match="reference"):
        broker.resolve_context(_caller(), option)


def test_expired_target_option_cannot_mint_context():
    owner = Owner()
    early = _broker(owner, now_ms=2_000)
    option = early.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]["target_option_ref"]
    late = _broker(owner, now_ms=40_000)
    with pytest.raises(AttendedContextError, match="expired"):
        late.prepare_attended_context(
            _caller(),
            target_option_ref=option,
            requested_scope=("browser",),
            client_call_ref="call:2",
        )


def test_context_required_scope_cannot_exceed_bound_scope():
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:1")["target_options"][0]["target_option_ref"]
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=option,
        requested_scope=("project.read",),
        client_call_ref="call:2",
    )
    with pytest.raises(AttendedContextError, match="required scope"):
        broker.resolve_context(
            _caller(),
            prepared["workbench_context_ref"],
            required_scope=("browser",),
        )


def test_context_binding_is_independent_of_capability_scope_by_design():
    owner = Owner()
    broker = _broker(owner)
    option = broker.list_permitted_targets(_caller(), client_call_ref="call:scope-1")["target_options"][0]
    prepared = broker.prepare_attended_context(
        _caller(),
        target_option_ref=option["target_option_ref"],
        requested_scope=("browser",),
        client_call_ref="call:scope-2",
    )
    # The pure context broker intentionally has no OAuth/tool-scope field.
    # Target-list, Action, and Browser surfaces enforce their own scopes outside
    # this binding layer while reusing the same subject/client/resource context.
    context = broker.resolve_context(
        _caller(),
        prepared["workbench_context_ref"],
        required_scope=("browser",),
    )
    assert context.target_ref == _target().target_ref
    assert not hasattr(context, "oauth_scopes")
    assert not hasattr(context, "tool_scopes")
