"""Signed mounted HTTP and existing Unix App-peer dispatcher, all inert owners."""
import asyncio
import copy

import pytest

from common import workspace_autonomy_read_contract as wire
from common.executive_workspace_contract import canonical
from integrations.mastermind_workspace_app.contract import principal_frame
from tests.test_workspace_admitted_plan_read import (
    plan_owner, rsa_key, short_socket_root, transport, request,
)

ROUTE = "/workspace/autonomy/current"


def test_signed_http_and_real_dispatcher_return_the_same_selected_policy(plan_owner, rsa_key, tmp_path, short_socket_root):
    async def run():
        async with transport(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, _, seen, client, principal, _):
            response = await http.get(ROUTE, params=plan_owner["selection"], headers={"Authorization":"Bearer " + token})
            assert response.status_code == 200, response.text
            body = wire.validate_body(response.json())
            assert body["availability"] == "AVAILABLE"
            assert response.headers["cache-control"] == "no-store"
            frame = request(plan_owner)
            frame.update(schema=wire.FRAME_SCHEMA, operation=wire.OPERATION, principal=principal_frame(principal))
            envelope = await client.request(frame)
            assert envelope["result"]["policy"] == body["policy"]
            assert len(canonical(envelope)) + 1 <= wire.MAX_RESPONSE_BYTES
            assert seen["factory"] == 2
    asyncio.run(run())


@pytest.mark.parametrize("mutation", ["disabled", "digest", "expired"])
def test_http_permission_and_token_expiry_are_rechecked_after_source_work(plan_owner, rsa_key, tmp_path, short_socket_root, mutation):
    def after(slots, clock):
        if mutation == "disabled": slots["profiles"]["web"]["enabled"] = False
        elif mutation == "digest": slots["profiles"]["web"]["binding"]["permission_digest"] = "b" * 64
        else: clock[0] += 86400
    async def run():
        async with transport(plan_owner, rsa_key, tmp_path, short_socket_root, after_app=after) as (http, token, *_):
            response = await http.get(ROUTE, params=plan_owner["selection"], headers={"Authorization":"Bearer " + token})
            assert response.status_code == 403
            assert "policy_sha" not in response.text
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["missing_auth", "missing_root", "extra_query", "duplicate_root", "post", "body", "trailing_slash"])
def test_new_read_is_closed_before_owner_acquisition(plan_owner, rsa_key, tmp_path, short_socket_root, fault):
    async def run():
        async with transport(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, _, seen, *_):
            headers = {"Authorization":"Bearer " + token}
            route, method, params, content = ROUTE, "GET", dict(plan_owner["selection"]), None
            if fault == "missing_auth": headers = {}
            elif fault == "missing_root": params.pop("root_job_id")
            elif fault == "extra_query": params["operation"] = "pause"
            elif fault == "duplicate_root": params = list(params.items()) + [("root_job_id",params["root_job_id"])]
            elif fault == "post": method = "POST"
            elif fault == "body": content = b"{}"
            else: route += "/"
            response = await http.request(method, route, params=params, headers=headers, content=content)
            assert response.status_code in (400,401,403,404,405), response.text
            assert seen["factory"] == 0
    asyncio.run(run())


def test_http_release_refuses_foreign_or_widened_policy_body():
    from integrations.mastermind_workspace_app.app import _autonomy_envelope_response
    from tests.test_workspace_autonomy_read import plan_body
    from control_plane.workspace_autonomy_read import compose_autonomy_policy_read
    body, policy = plan_body()
    original = compose_autonomy_policy_read(body, policy)
    for mutate in (
        lambda x:x["policy"].update(scope="GLOBAL"),
        lambda x:x["policy"]["limits"].update(max_depth=999),
        lambda x:x.update(extra="private"),
        lambda x:x["source_observation"]["runtime"].update(after=999),
    ):
        bad = copy.deepcopy(original)
        mutate(bad)
        assert _autonomy_envelope_response({"ok":True,"result":bad}).status_code == 503
