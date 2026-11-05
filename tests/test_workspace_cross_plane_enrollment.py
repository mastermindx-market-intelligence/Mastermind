"""Host-only Session Truth enrollment does not mint authority or transport."""
from __future__ import annotations

import asyncio

import pytest

from control_plane.workspace_cross_plane_enrollment import (
    InstalledCrossPlaneEnrollment, select_installed_cross_plane,
)
from control_plane.workspace_read_service import workspace_provider_factory
from control_plane.session_truth_live_acquire import LiveScope
from tests.test_executive_cross_plane_live import Owners, NOW, _scope
from tests.test_workspace_control_room_factory import hosted, room_socket, owner, principal, frame


def _enrollment(owners, *, scope=None, selections=None):
    selections = [] if selections is None else selections
    def member_scope(member):
        selections.append(("scope", member["client_ref"]))
        return scope if scope is not None else _scope()
    def member_ports(member, member_scope):
        selections.append(("ports", member["client_ref"], member_scope))
        return owners.ports()
    return InstalledCrossPlaneEnrollment(member_scope, member_ports, 600)


def test_only_current_qualified_member_and_original_owner_get_source_handles(hosted):
    host, _ = hosted
    source_owners, calls = Owners(), []
    admitted = owner({"fixture-web"})
    select = select_installed_cross_plane(
        control_room=host, authorize=admitted,
        enrollment=_enrollment(source_owners, selections=calls), clock=lambda: NOW,
    )
    context = select(principal(), host.config)
    assert type(context.scope) is LiveScope
    assert context.scope == _scope()
    assert context.ports == source_owners.ports()
    assert context.observation_clock() == NOW
    assert calls == [("scope", "fixture-web"), ("ports", "fixture-web", _scope())]
    for foreign, bad_source in [(principal(), object()),
                                ({**principal(), "client_ref": "other"}, host.config),
                                ({**principal(), "scopes": []}, host.config),
                                ({**principal(), "role": "admin"}, host.config)]:
        with pytest.raises(ValueError, match="access_denied"):
            select(foreign, bad_source)
    assert len(calls) == 2


def test_stale_or_missing_reader_selection_never_creates_live_context(hosted):
    host, _ = hosted
    admitted = owner({"fixture-web"})
    bad_scope = InstalledCrossPlaneEnrollment(lambda p: None, lambda p, s: Owners().ports())
    select = select_installed_cross_plane(
        control_room=host, authorize=admitted, enrollment=bad_scope,
    )
    with pytest.raises(ValueError, match="source_scope_unavailable"):
        select(principal(), host.config)
    bad_ports = InstalledCrossPlaneEnrollment(lambda p: _scope(), lambda p, s: None)
    select = select_installed_cross_plane(
        control_room=host, authorize=admitted, enrollment=bad_ports,
    )
    with pytest.raises(ValueError, match="source_ports_unavailable"):
        select(principal(), host.config)
    with pytest.raises(ValueError, match="installed source reader selection"):
        InstalledCrossPlaneEnrollment(None, lambda p, s: Owners().ports())
    with pytest.raises(ValueError, match="bounded source staleness"):
        InstalledCrossPlaneEnrollment(lambda p: _scope(), lambda p,s: Owners().ports(), 90000)


def test_selection_revalidates_existing_binding_after_member_callback(hosted):
    host, _ = hosted
    allowed = {"fixture-web"}
    admitted = owner(allowed)
    def scoped(member):
        allowed.clear()
        return _scope()
    selector = select_installed_cross_plane(
        control_room=host, authorize=admitted,
        enrollment=InstalledCrossPlaneEnrollment(scoped, lambda p, s: Owners().ports()),
    )
    with pytest.raises(ValueError, match="access_denied"):
        selector(principal(), host.config)


def test_existing_private_frame_uses_only_installed_scoped_ports(hosted, monkeypatch):
    from scripts import chairman_control_room as ccr
    host, baseline = hosted
    # Same owner and permission frame as the existing Workspace factory.
    monkeypatch.setattr(ccr, "_discover_document", lambda *_: pytest.fail("not a Session Truth source"))
    source_owners = Owners()
    admitted = owner({"fixture-web"})
    from control_plane.workspace_cross_plane_enrollment import InstalledCrossPlaneEnrollment
    installed = _enrollment(source_owners)
    service = workspace_provider_factory(
        control_room=host, authorize=admitted, armed={}, runtime_identity={},
        cross_plane_enrollment=installed,
    )(object())
    async def exercise():
        await host.start()
        try:
            response = await service.handle_frame(frame("state"))
            assert response["ok"] is True
            assert response["result"]["control_room"] == baseline
            live = response["result"]["cross_plane"]
            assert live["state"] == "AVAILABLE"
            assert live["document"]["capability"] == {"read_only": True, "effect": "NONE"}
            assert live["document"]["execution"]["state"] == "NOT_PROJECTED"
            assert (await service.handle_frame(frame("discover")))["status"] == 403
        finally:
            await host.close()
    asyncio.run(exercise())
    assert sorted(source_owners.calls) == ["base", "executive", "github", "identities", "linear", "slack"]


def test_host_factory_rejects_conflicting_context_and_enrollment(hosted):
    host, _ = hosted
    source_owners = Owners()
    admitted = owner({"fixture-web"})
    installed = _enrollment(source_owners)
    with pytest.raises(ValueError, match="ambiguous cross-plane source selection"):
        workspace_provider_factory(
            control_room=host, authorize=admitted, armed={}, runtime_identity={},
            cross_plane_enrollment=installed, cross_plane_context=lambda *_: None,
        )
    with pytest.raises(ValueError, match="installed cross-plane source owner unavailable"):
        workspace_provider_factory(
            control_room=host, authorize=admitted, armed={}, runtime_identity={},
            cross_plane_enrollment=object(),
        )


def test_scope_reader_cannot_mutate_signed_member_into_foreign_port_identity(hosted):
    host, _ = hosted
    seen_ports = []
    signed = principal("fixture-web")
    before = dict(signed)

    def mutate_scope(member):
        member["client_ref"] = "fixture-mac"
        return _scope()

    def ports(member, scope):
        seen_ports.append(member["client_ref"])
        return Owners().ports()

    selector = select_installed_cross_plane(
        control_room=host, authorize=owner({"fixture-web"}),
        enrollment=InstalledCrossPlaneEnrollment(mutate_scope, ports),
    )
    with pytest.raises(ValueError, match="access_denied"):
        selector(signed, host.config)
    assert seen_ports == []
    assert signed == before


def test_port_reader_cannot_mutate_signed_member_without_refusal(hosted):
    host, _ = hosted
    signed = principal("fixture-web")
    before = dict(signed)

    def mutate_ports(member, scope):
        member["client_ref"] = "fixture-mac"
        return Owners().ports()

    selector = select_installed_cross_plane(
        control_room=host, authorize=owner({"fixture-web"}),
        enrollment=InstalledCrossPlaneEnrollment(lambda member: _scope(), mutate_ports),
    )
    with pytest.raises(ValueError, match="access_denied"):
        selector(signed, host.config)
    assert signed == before
