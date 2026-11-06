"""Real signed two-principal Workspace-to-SDK journey, no live credentials.

This composes the incumbent HTTP/Unix/Runtime Mission owner fixture with
the actual SecretaryAccessClient. Distinct JWT subjects and clients see
one canonical mission. Revocation and release-time permission denial are
enforced by the existing owner, never by a new Secretary permission map.
This is a source fixture, not an installed GB1/S2 acceptance claim.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib

from tests import test_executive_coo_app as coo_owner
from integrations.mastermind_executive_app.gateway import CeoIngressResponse

import httpx

from integrations.secretary_team_access.client import SecretaryAccessClient
from integrations.secretary_team_access.mission import SUMMARY_SCHEMA
from tests.test_secretary_team_mission_http import (
    MEMBERS, _selection, transport,
)
from tests.test_workspace_read_app import NOW, rsa_key
from tests.test_workspace_read_socket import short_socket_root
from tests.test_workspace_result_service import result_owner


def _signed_client(parent: httpx.AsyncClient, token: str) -> httpx.AsyncClient:
    # The fixture's transport is an in-process ASGI adapter to the *real*
    # WorkspaceApp. Give each principal a distinct host-bound HTTP client.
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=parent._transport.app),
        base_url="https://mcp.mastermind-x.com",
        headers={"Authorization": "Bearer " + token},
        follow_redirects=False,
    )


def test_sdk_two_signed_principals_share_canonical_mission_and_revoke_independently(
        result_owner, rsa_key, tmp_path, short_socket_root):
    owner = result_owner
    selected = _selection(owner)

    async def exercise():
        async with transport(owner, rsa_key, tmp_path, short_socket_root) as (http, tokens, slots):
            async with _signed_client(http, tokens[MEMBERS[0]]) as first_http:
                async with _signed_client(http, tokens[MEMBERS[1]]) as second_http:
                    first = SecretaryAccessClient(
                        **selected, workspace=first_http, clock=lambda: NOW)
                    second = SecretaryAccessClient(
                        **selected, workspace=second_http, clock=lambda: NOW)

                    a = await first.read_mission()
                    b = await second.read_mission()
                    assert a["schema"] == b["schema"] == SUMMARY_SCHEMA
                    assert a["selection"] == b["selection"] == selected
                    assert a["fingerprint"] == b["fingerprint"]
                    assert a["read_state"]["state"] == b["read_state"]["state"] == "CURRENT"
                    assert a["coverage"]["scope"] == "single_mission"
                    assert a["coverage"]["full_fleet"] is False

                    same = await first.read_mission(previous_fingerprint=a["fingerprint"])
                    assert same["fingerprint"] == a["fingerprint"]
                    assert same["changed"] is False
                    assert same["read_state"]["state"] == "CURRENT"

                    # Original member grant is revoked, without touching
                    # the second principal or creating any new identity.
                    slots["profiles"][MEMBERS[0]]["enabled"] = False
                    revoked = await first.read_mission()
                    assert revoked["state"] == "REFUSED"
                    assert revoked["reason_code"] == "access_denied"
                    assert a["fingerprint"] not in repr(revoked)
                    survivor = await second.read_mission()
                    assert survivor["schema"] == SUMMARY_SCHEMA
                    assert survivor["fingerprint"] == b["fingerprint"]

    asyncio.run(exercise())


def test_sdk_mid_read_permission_change_releases_no_mission(
        result_owner, rsa_key, tmp_path, short_socket_root):
    owner = result_owner
    selected = _selection(owner)
    read_count = []

    def revoke_after_acquisition(slots):
        read_count.append(True)
        slots["profiles"][MEMBERS[1]]["binding"]["permission_digest"] = (
            hashlib.sha256(b"revoked-by-incumbent-owner").hexdigest())

    async def exercise():
        async with transport(owner, rsa_key, tmp_path, short_socket_root,
                             mid_read=revoke_after_acquisition) as (http, tokens, slots):
            async with _signed_client(http, tokens[MEMBERS[1]]) as enrolled:
                sdk = SecretaryAccessClient(**selected, workspace=enrolled,
                                            clock=lambda: NOW)
                result = await sdk.read_mission()
                assert result["state"] == "REFUSED"
                assert result["reason_code"] == "access_denied"
                assert "mission_workspace" not in repr(result)
                assert "result_refs" not in repr(result)
        assert read_count == [True]

    asyncio.run(exercise())


def test_sdk_foreign_mission_selector_refused_without_result_data(
        result_owner, rsa_key, tmp_path, short_socket_root):
    owner = result_owner
    selected = _selection(owner)

    async def exercise():
        async with transport(owner, rsa_key, tmp_path, short_socket_root) as (http, tokens, slots):
            async with _signed_client(http, tokens[MEMBERS[0]]) as enrolled:
                sdk = SecretaryAccessClient(
                    work_ref="WS:FOREIGN", root_job_id=selected["root_job_id"],
                    workspace=enrolled, clock=lambda: NOW)
                result = await sdk.read_mission()
                assert result["state"] == "REFUSED"
                assert result["reason_code"] == "selection_not_found"
                assert "mission_workspace" not in repr(result)

    asyncio.run(exercise())


def test_sdk_real_signed_coo_mandate_and_ungranted_intent_refusal(
        rsa_key, tmp_path):
    """Real App JWT, current mandate/authority and before-send grant fence."""
    app, token, current, _settings = coo_owner.setup(rsa_key, tmp_path)
    calls = []

    async def forbidden_send(_path, _frame):
        calls.append(True)
        raise AssertionError("ungranted intent must not reach incumbent ingress")

    app._client.send_frame = forbidden_send

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers={"Authorization": "Bearer " + token},
            follow_redirects=False,
        ) as coo_client:
            sdk = SecretaryAccessClient(
                work_ref="WS:ONE",
                root_job_id=current["mission"]["mission"]["root_job_id"],
                workspace=coo_client, coo=coo_client)
            mandate = await sdk.mandate()
            assert mandate["state"] == "OBSERVED"
            assert mandate["new_effect_gate"] == "OPEN"

            # Existing AuthorityFact revocation is decisive; an observed
            # mandate is not a new action grant and never bypasses it.
            current["authority"] = dataclasses.replace(
                current["authority"], principal_actions=("governed_orchestration",))
            refused = await sdk.submit_intent(coo_owner.payload())
            assert refused["state"] == "REFUSED"
            assert refused["reason_code"] == "authority_refused"
            assert refused["replay_authorized"] is False
        assert calls == []

    asyncio.run(exercise())


def test_sdk_real_signed_coo_uncertain_send_preserves_same_original_ref(
        rsa_key, tmp_path):
    """Real current signed COO app + grounding + one original mutation send."""
    app, token, current, _settings = coo_owner.setup(rsa_key, tmp_path)
    seen = []

    async def owner_send(_path, frame):
        seen.append(frame)
        if frame["schema"].endswith("grounding.v1"):
            return CeoIngressResponse(
                "sent_ok", ok=True,
                result={"mastermind_sha": "1" * 40,
                        "macro_sha": "2" * 40,
                        "boot_packet_schema": "mastermind.ceo_boot_packet.v1"})
        return CeoIngressResponse("sent_effect_unknown")

    app._client.send_frame = owner_send

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers={"Authorization": "Bearer " + token},
            follow_redirects=False,
        ) as coo_client:
            sdk = SecretaryAccessClient(
                work_ref="WS:ONE",
                root_job_id=current["mission"]["mission"]["root_job_id"],
                workspace=coo_client, coo=coo_client)
            original = await sdk.submit_intent(coo_owner.payload())
            assert original["state"] == "EFFECT_UNKNOWN"
            assert original["request_ref"].startswith("req-coo-")
            assert original["replay_authorized"] is False
            assert "PRIVATE_CANARY" not in repr(original)
            assert "Bearer " not in repr(original)
        assert len(seen) == 2  # grounding then ONE modifying owner send
        assert seen[-1]["request_ref"] == original["request_ref"]

    asyncio.run(exercise())
