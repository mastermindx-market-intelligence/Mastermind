"""Two signed Workspace members share one real Mission v3 join.

Actual signed fixture JWTs → HTTP workspace app → peer-uid Unix socket →
WorkspaceReadService → closed fixture Runtime owner.  One canonical mission
and root, two distinct enrolled subjects with independent revocation, a
mid-read permission change, and denied/expired/wrong-selection
differentiation.  This proves the SOURCE fixture join only — never deployed
enrollment, installation or a live service.  No live network is involved.
"""
import asyncio
import hashlib
from contextlib import asynccontextmanager

import httpx
import pytest

from integrations.business_mcp_auth.contracts import subject_digest
from integrations.mastermind_workspace_app.app import (
    WorkspaceAppConfig,
    create_workspace_app,
)
from integrations.mastermind_workspace_app.contract import (
    MEMBER_BINDINGS_SCHEMA,
    principal_frame,
    workspace_authorizers,
)
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_workspace_read_app import (
    ISSUER,
    NOW,
    _authenticator,
    _workspace_policy,
    _workspace_token,
    rsa_key,
)
from tests.test_workspace_read_socket import control, short_socket_root
from tests.test_workspace_result_service import result_owner

MEMBERS = ("secretary-member-a", "secretary-member-b")
_MISSION_ROUTE = "/workspace/mission/v3/current"


def _selection(owner):
    return {key: owner["selection"][key]
            for key in ("work_ref", "root_job_id")}


@asynccontextmanager
async def transport(o, rsa_key, tmp_path, socket_root, *, mid_read=None):
    """The existing two-gate transport with two enrolled member profiles."""

    policy = _workspace_policy(allowed_subject_digests=sorted(
        subject_digest(issuer=ISSUER, subject=subject) for subject in MEMBERS))
    auth = _authenticator(rsa_key, policy=policy)
    tokens = {subject: _workspace_token(rsa_key, sub=subject) for subject in MEMBERS}
    principals = {}
    for subject in MEMBERS:
        principals[subject] = await auth.verify_token(tokens[subject], now=NOW)
    assert len({principal.client_ref for principal in principals.values()}) == 1
    slots = {"schema": MEMBER_BINDINGS_SCHEMA, "primary_profile": MEMBERS[0],
             "profiles": {
                 MEMBERS[0]: {"enabled": True, "binding": dict(
                     principal_frame(principals[MEMBERS[0]]),
                     permission_digest=hashlib.sha256(b"enroll-a").hexdigest())},
                 MEMBERS[1]: {"enabled": True, "binding": dict(
                     principal_frame(principals[MEMBERS[1]]),
                     permission_digest=hashlib.sha256(b"enroll-b").hexdigest())},
             }}
    app_auth, control_auth = workspace_authorizers(policy=policy,
                                                   load_bindings=lambda: slots)

    def factory(actual):
        assert actual is o["writer"]
        svc = WorkspaceReadService(
            cache=o["cache"], runtime=actual, authorize=control_auth,
            armed={}, runtime_identity={"db_present": True},
            bounded_runtime=lambda owner: (
                o["reader"] if owner is o["writer"] else pytest.fail("wrong owner")))
        if mid_read is not None:
            original = svc._read_mission_v3

            def spied(frame):
                result = original(frame)
                mid_read(slots)  # runs after the read, before the release check
                return result

            svc._read_mission_v3 = spied
        return svc

    svc = control(tmp_path, socket_root, factory)
    svc._runtime_factory = lambda path: o["writer"]
    await svc.start()
    try:
        client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
        workspace = create_workspace_app(WorkspaceAppConfig(
            authenticator=auth, now=lambda: NOW, authorize_principal=app_auth,
            client=client))
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=workspace),
                base_url="https://mcp.mastermind-x.com") as http:
            yield http, tokens, slots
    finally:
        await svc.close()


def test_two_signed_members_share_one_canonical_mission_with_independent_revocation(
        result_owner, rsa_key, tmp_path, short_socket_root):
    o = result_owner
    selected = _selection(o)

    async def run():
        async with transport(o, rsa_key, tmp_path, short_socket_root) as (http, tokens, slots):
            headers = {subject: {"Authorization": "Bearer " + tokens[subject]}
                       for subject in MEMBERS}
            first = await http.get(_MISSION_ROUTE, params=selected, headers=headers["secretary-member-a"])
            assert first.status_code == 200, first.text
            body_a = first.json()
            assert body_a["schema"] == "mastermind.mission_workspace.v3"
            assert body_a["read_state"]["state"] == "CURRENT", body_a["source"]
            assert body_a["mission"]["root_job_id"] == selected["root_job_id"]
            assert body_a["program"]["work_ref"] == selected["work_ref"]
            assert first.headers["cache-control"] == "no-store"
            # The second distinct subject reads the same canonical mission/root.
            second = await http.get(_MISSION_ROUTE, params=selected, headers=headers["secretary-member-b"])
            assert second.status_code == 200, second.text
            body_b = second.json()
            assert body_b["mission"]["root_job_id"] == body_a["mission"]["root_job_id"]
            assert body_b["result_refs"]["refs"] == body_a["result_refs"]["refs"]
            assert (body_b["source"]["owner_observation"]["runtime"]["snapshot_digest"]
                    == body_a["source"]["owner_observation"]["runtime"]["snapshot_digest"])
            # The same bounded projection describes both principals' read.
            from integrations.secretary_team_access.mission import summarize_mission
            summary_a = summarize_mission(body_a, selection=selected, now=NOW)
            summary_b = summarize_mission(body_b, selection=selected, now=NOW)
            assert summary_a["fingerprint"] == summary_b["fingerprint"]
            assert summary_a["selection"] == selected
            # Revoking exactly one member leaves the other member's read intact.
            slots["profiles"][MEMBERS[0]]["enabled"] = False
            revoked = await http.get(_MISSION_ROUTE, params=selected, headers=headers["secretary-member-a"])
            assert revoked.status_code == 403
            assert revoked.json()["error"]["code"] == "access_denied"
            survivor = await http.get(_MISSION_ROUTE, params=selected, headers=headers["secretary-member-b"])
            assert survivor.status_code == 200, survivor.text
            assert survivor.json()["mission"]["root_job_id"] == selected["root_job_id"]

    asyncio.run(run())


def test_mid_read_permission_change_refuses_release(result_owner, rsa_key, tmp_path, short_socket_root):
    o = result_owner
    selected = _selection(o)

    async def run():
        changed = []

        def mutate(slots):
            changed.append(True)
            slots["profiles"][MEMBERS[1]]["binding"]["permission_digest"] = (
                hashlib.sha256(b"changed-mid-read").hexdigest())

        async with transport(o, rsa_key, tmp_path, short_socket_root,
                             mid_read=mutate) as (http, tokens, slots):
            response = await http.get(_MISSION_ROUTE, params=selected, headers={
                "Authorization": "Bearer " + tokens["secretary-member-b"]})
            assert changed == [True]
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "access_denied"
            # Material from the interrupted read never reaches the caller.
            assert "mission_workspace" not in response.text

    asyncio.run(run())


def test_denied_expired_and_wrong_selection_are_differentiated(
        result_owner, rsa_key, tmp_path, short_socket_root):
    o = result_owner
    selected = _selection(o)
    foreign = _workspace_token(rsa_key, sub="secretary-foreign-subject")
    expired = _workspace_token(rsa_key, sub="secretary-member-a", exp=NOW - 10)
    wrong_scope = _workspace_token(rsa_key, sub="secretary-member-a",
                                   scope="mastermind.executive.read")

    async def run():
        async with transport(o, rsa_key, tmp_path, short_socket_root) as (http, tokens, slots):
            before = o["namespace"].entries
            for headers in ({}, {"Authorization": "Bearer " + foreign},
                            {"Authorization": "Bearer " + expired},
                            {"Authorization": "Bearer " + wrong_scope}):
                response = await http.get(_MISSION_ROUTE, params=selected, headers=headers)
                assert response.status_code in (401, 403), (headers, response.status_code)
            assert o["namespace"].entries == before
            # Signed, enrolled member, foreign selection: exact typed refusal.
            response = await http.get(
                _MISSION_ROUTE, params={"work_ref": "WS:FOREIGN", "root_job_id": selected["root_job_id"]},
                headers={"Authorization": "Bearer " + tokens["secretary-member-a"]})
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "selection_not_found"
            assert o["namespace"].entries == before
            # Reads stay reads: no mutation route exists on the shared surface.
            posted = await http.post(_MISSION_ROUTE, headers={
                "Authorization": "Bearer " + tokens["secretary-member-a"]}, json={})
            assert posted.status_code in (400, 404, 405)
            assert o["namespace"].entries == before

    asyncio.run(run())
