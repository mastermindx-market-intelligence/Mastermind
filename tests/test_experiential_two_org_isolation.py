"""Hermetic two-organization RPM and bearer isolation on real gateway instances.

A and B here are synthetic fixture organizations only. This does not
authenticate or enable the Chairman's real held Account A.
"""
from __future__ import annotations

import asyncio
import json

import httpx

from ops.native_fabric.experiential_proxy.gateway import Settings, create_app


def test_distinct_org_gateway_instances_have_separate_quota_and_key_custody(tmp_path):
    keys = {
        "A": "fixture-host-only-provider-key-A",
        "B": "fixture-host-only-provider-key-B",
    }
    tokens = {
        "A": "fixture-local-proxy-token-for-org-A-1234",
        "B": "fixture-local-proxy-token-for-org-B-1234",
    }
    seen = {"A": [], "B": []}

    def make_upstream(org):
        def handle(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("authorization") == "Bearer " + keys[org]
            assert request.url.path == "/v1/chat/completions"
            assert json.loads(request.content)["model"] == "deepseek-v4.1-flash"
            seen[org].append(request.url.path)
            return httpx.Response(200, json={
                "model": "deepseek-v4.1-flash",
                "choices": [{"message": {"role": "assistant", "content": org}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1,
                          "cost": 0.0001, "is_byok": False},
            })
        return handle

    apps = {
        org: create_app(
            Settings(
                api_keys=(keys[org],),
                proxy_token=tokens[org],
                state_dir=tmp_path / org,
                safe_rpm=1,
                safe_rpm_shared=1,
                max_queue_wait_s=0.03,
                window_s=60.0,
                enable_account_metadata=True,
            ),
            transport=httpx.MockTransport(make_upstream(org)),
        )
        for org in ("A", "B")
    }

    async def exercise():
        async with apps["A"].router.lifespan_context(apps["A"]):
            async with apps["B"].router.lifespan_context(apps["B"]):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=apps["A"]),
                    base_url="http://fixture-a",
                ) as a:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=apps["B"]),
                        base_url="http://fixture-b",
                    ) as b:
                        ha = {"Authorization": "Bearer " + tokens["A"]}
                        hb = {"Authorization": "Bearer " + tokens["B"]}
                        body = {"model": "deepseek-v4.1-flash", "messages": [
                            {"role": "user", "content": "fixture only"}
                        ]}

                        # Wrong-org local bearer cannot reach provider or spend RPM.
                        assert (await a.post("/v1/chat/completions",
                                             headers=hb, json=body)).status_code == 401
                        assert (await b.post("/v1/chat/completions",
                                             headers=ha, json=body)).status_code == 401

                        a1 = await a.post("/v1/chat/completions", headers=ha, json=body)
                        b1 = await b.post("/v1/chat/completions", headers=hb, json=body)
                        assert a1.status_code == b1.status_code == 200
                        assert a1.json()["choices"][0]["message"]["content"] == "A"
                        assert b1.json()["choices"][0]["message"]["content"] == "B"

                        for client, headers in ((a, ha), (b, hb)):
                            status = await client.get("/statusz", headers=headers)
                            assert status.status_code == 200
                            data = status.json()
                            assert data["shared_rpm_cap"] == 1
                            assert data["shared_used_in_window"] == 1

                            # Each org's second request is locally denied; no
                            # cross-org fallback or second upstream send.
                            refused = await client.post(
                                "/v1/chat/completions", headers=headers, json=body,
                            )
                            assert refused.status_code == 504

    asyncio.run(exercise())
    assert seen == {
        "A": ["/v1/chat/completions"],
        "B": ["/v1/chat/completions"],
    }
