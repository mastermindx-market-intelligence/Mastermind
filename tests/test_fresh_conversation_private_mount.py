"""Actual signed BFF -> real owned Unix socket/kernel App peer -> Control branch.

Reuses explicit synthetic installed policy/host readiness and inert provider
premises from the accepted component fixture. No installed host/provider effect.
"""
import asyncio
import dataclasses
import hashlib
import os
from pathlib import Path
import tempfile

from tests.test_fresh_conversation_http import mounted, post, rsa_key
from tests.test_fresh_conversation import cleanup
from tests import test_mastermind_executive_app_asgi as auth
from control_plane.fresh_conversation import FreshConversationOwner
from integrations.mastermind_executive_app.fresh_conversation_transport import (
    FreshConversationTransportApp, InstalledFreshConversationClient,
)
from integrations.mastermind_executive_app.gateway import CeoIngressClient


def test_real_private_kernel_peer_and_foreground_creation_mount(tmp_path, rsa_key, monkeypatch):
    async def run():
        original, token, workspace_token, service, runtime, request, adapters, _, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        # This is the fixture's trusted policy source, not incoming frame data.
        policy = auth._submit_policy()
        expected = (policy.policy_id, hashlib.sha256(policy.issuer.encode()).hexdigest(), policy.resource)
        current = True
        def provider(selected_runtime):
            if selected_runtime is not runtime or not current:
                raise ValueError("fixture current policy/namespace unavailable")
            return FreshConversationOwner(service, expected_policy=expected)
        service._ceo_ingress_app_binding = dataclasses.replace(
            service._ceo_ingress_app_binding, fresh_conversation_provider_factory=provider)
        with tempfile.TemporaryDirectory(prefix="fresh-ingress-", dir="/tmp") as directory:
            path = Path(directory) / "app.sock"
            server = await asyncio.start_unix_server(service._handle_ceo_ingress_connection, path=path)
            client = CeoIngressClient()
            app = FreshConversationTransportApp(original._inner, executive=original._executive,
                workspace_config=original._workspace, workspace_verifier=original._workspace_verifier,
                client=InstalledFreshConversationClient(path, client))
            try:
                code, preview = await post(app, "preview", request, token, workspace_token)
                assert code == 200 and preview["ok"] is True
                create = {**request, "preview_digest": preview["data"]["preview"]["digest"]}
                code, result = await post(app, "create", create, token, workspace_token)
                assert code == 200 and result["ok"] is True and result["data"]["state"] == "CREATED"
                selected = {name: request[name] for name in ("work_ref", "operation_key")}
                code, read = await post(app, "read", selected, token)
                assert code == 200 and read["ok"] is True and read["data"]["result"]
                count = len(runtime.jobs.list_jobs())
                before = runtime.events.list_events()
                code, duplicate = await post(app, "create", create, token, workspace_token)
                assert code == 200 and duplicate["ok"] is True
                assert len(runtime.jobs.list_jobs()) == count and runtime.events.list_events() == before
                assert len(adapters) == 1 and adapters[0].start_calls == 1
                current = False
                code, _ = await post(app, "status", selected, token)
                assert code == 503 and len(runtime.jobs.list_jobs()) == count
                current = True
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding, peer_uid=os.geteuid() + 1)
                code, _ = await post(app, "status", selected, token)
                assert code == 503 and len(runtime.jobs.list_jobs()) == count
            finally:
                server.close()
                await server.wait_closed()
                await cleanup(service)
                if service._ceo_ingress_tasks:
                    await asyncio.wait_for(asyncio.gather(*service._ceo_ingress_tasks), 5)
    asyncio.run(run())
