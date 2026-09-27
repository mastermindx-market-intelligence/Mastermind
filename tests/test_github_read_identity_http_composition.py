"""Whole local auth -> installation exchange -> writer receipt composition.
No external service, real key, credential, listener or GitHub request is used.
"""
from __future__ import annotations
import asyncio
import dataclasses
import json
import pytest
from test_github_read_installation_identity import Owner as CredentialOwner, TOKEN
from test_github_writer_gate_http import setup, client_for, rpc, payload
from integrations.mastermind_github_app.read_installation_identity import ReadInstallationTokenProvider, RsaAppJwtSigner


def composed(setup, variant="normal"):
    gate_owner, _, _, _, _ = setup
    identity = CredentialOwner()
    identity.now = gate_owner.now
    identity.binding = dataclasses.replace(identity.binding, expires_at=identity.now + 600)
    identity.variant = variant
    provider = ReadInstallationTokenProvider(resolve_binding=identity.current_binding,
        signer=RsaAppJwtSigner(identity.key), transport=identity, clock=lambda: identity.now,
        production_armed=True)
    def read(method, url, headers, body, timeout_seconds):
        assert headers["Authorization"] == "Bearer " + TOKEN
        # Preserve the existing fact fixture; actual outgoing credential checked above.
        return gate_owner.read(method, url, {**headers, "Authorization": "Bearer synthetic-service-value"}, body, timeout_seconds)
    return identity, provider, read


def test_authenticated_http_uses_concrete_scoped_identity_then_canonical_verifier(setup):
    async def run():
        gate, _, _, audit, caller_token = setup
        identity, provider, read = composed(setup)
        raw = caller_token()
        async with client_for(setup, armed=True, token_provider=provider, read_transport=read) as client:
            result, receipt = payload(await rpc(client, raw))
        assert not result.get("isError", False)
        assert receipt["schema"] == "mastermind.source_continuity_writer_gate/v1"
        assert receipt["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
        assert receipt["merge_authorized"] is False
        assert len(identity.calls) == 2 and len(gate.calls) == 8
        visible = json.dumps([receipt, audit.events, provider.evidence()])
        assert TOKEN not in visible and raw not in visible
    asyncio.run(run())


def test_bad_caller_never_reaches_signer_or_installation_exchange(setup):
    async def run():
        gate, _, _, _, _ = setup
        identity, provider, read = composed(setup)
        async with client_for(setup, armed=True, token_provider=provider, read_transport=read) as client:
            response = await rpc(client, "not-a-caller-token")
        assert response.status_code in {401, 403}
        assert identity.calls == [] and gate.calls == []
    asyncio.run(run())


@pytest.mark.parametrize("variant", ["lost_post", "write_token", "post_denied"])
def test_uncertain_credential_issuance_remains_distinct_in_model_visible_error(setup, variant):
    async def run():
        gate, _, _, _, caller_token = setup
        identity, provider, read = composed(setup, variant)
        async with client_for(setup, armed=True, token_provider=provider, read_transport=read) as client:
            first, body = payload(await rpc(client, caller_token()))
            second, again = payload(await rpc(client, caller_token()))
        assert first["isError"] and second["isError"]
        assert body == again == {"code": "GITHUB_CREDENTIAL_ISSUANCE_UNRESOLVED", "receipt": None}
        assert len(identity.calls) == 2 and gate.calls == []
        assert TOKEN not in json.dumps(body)
    asyncio.run(run())
