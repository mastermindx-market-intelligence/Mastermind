"""Actual installed profiles, JWT verifier and temporary permission socket.

Synthetic enrollment/configuration and native process premises only; no installed
socket, OAuth request, token persistence, provider or private source body read.
"""
import asyncio
from dataclasses import asdict, replace
import json
import jwt

from common import native_authorization_identity_contract as wire
from control_plane.executive_content_observer import ExecutiveContentObserver
from control_plane.executive_worker_broker import WorkerBrokerClient
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.executive_content_contract import ContentObserverProfile, ContentProfileKey, ACCESS_SCHEMA, canonical, digest
from integrations.mastermind_steward_app.installed import LiveWindowProfilesConfig, build_installed_steward_app_with_profiles
from tests.test_executive_ceo_ingress import short_socket_root
from tests.test_steward_content_integration import fixture
from tests.test_mastermind_steward_app_live_window import (
    _key, _cache, _content_policy, _steward_policy, _steward_verifier,
    _Sink, _invoke, _headers, CONTENT_ISSUER, CONTENT_SUBJECT, CONTENT_CLIENT, KID)

ORIGIN = "https://mcp.mastermind-x.com"


def test_actual_installed_profile_metadata_uses_existing_access_and_never_pages(tmp_path, short_socket_root):
    clock, runtime, original, _adapter, broker = fixture(tmp_path)
    # A new typed synthetic enrollment at the real fixed origin, preserving
    # this fixture's actual Runtime epoch/attempt/process/turn coordinates.
    fields = asdict(original)
    fields["content_resource"] = wire.RESOURCES["CONTENT"]
    fields["profile_digest"] = digest({key: value for key, value in fields.items() if key != "profile_digest"})
    profile = ContentObserverProfile.from_mapping(fields)
    envelope = {"schema": "mastermind.executive_content_profiles.v1", "profiles": {
        "web": {"enabled": True, "profile": asdict(profile)},
        "mac": {"enabled": False, "profile": None}}}

    async def exercise():
        broker_path = short_socket_root / "identity-broker.sock"
        ingress_path = short_socket_root / "identity-ingress.sock"
        seen = []
        async def serve_broker(reader, writer):
            frame = json.loads(await reader.readline())
            result = await broker._dispatch(frame["operation"], frame["payload"])
            writer.write(canonical({"schema_version": "mastermind.executive_worker_broker_response/v1",
                "request_id": frame["request_id"], "operation": frame["operation"], "ok": True, "result": result}) + b"\n")
            await writer.drain(); writer.close(); await writer.wait_closed()
        broker_server = await asyncio.start_unix_server(serve_broker, path=str(broker_path))
        observer = ExecutiveContentObserver(runtime=runtime, broker_client=WorkerBrokerClient(broker_path),
            profile_loader=lambda: envelope, now=lambda: clock.value // 1000)
        async def serve_ingress(reader, writer):
            frame = json.loads(await reader.readline()); seen.append(frame["schema"])
            reply = await observer.handle_frame(frame)
            writer.write(canonical(reply) + b"\n")
            await writer.drain(); writer.close(); await writer.wait_closed()
        async with broker_server:
            assert (await observer.enroll(ContentProfileKey.web))["status"] == "ACTIVE"
            ingress = await asyncio.start_unix_server(serve_ingress, path=str(ingress_path))
            async with ingress:
                key = _key()
                policy = replace(_content_policy(), resource=wire.RESOURCES["CONTENT"],
                    resource_metadata_url=ORIGIN + "/.well-known/oauth-protected-resource/workspace/window/current")
                steward = replace(_steward_policy(), resource=ORIGIN + "/mcp/steward/v1",
                    resource_metadata_url=ORIGIN + "/.well-known/oauth-protected-resource/mcp/steward/v1")
                app = build_installed_steward_app_with_profiles(profiles_config=LiveWindowProfilesConfig(
                    authenticator=JwtAuthenticator(policy=policy, jwks_cache=_cache(policy, key)),
                    content_policy=policy, profile_loader=lambda: envelope, ceo_ingress_socket_path=ingress_path,
                    now=lambda: clock.value // 1000, allowed_origin=ORIGIN, audit_sink=_Sink()),
                    steward_policy=steward, steward_token_verifier=_steward_verifier(steward, key))
                def token(subject=CONTENT_SUBJECT):
                    return jwt.encode({"iss": CONTENT_ISSUER, "sub": subject, "aud": wire.RESOURCES["CONTENT"],
                        "iat": clock.value // 1000 - 5, "nbf": clock.value // 1000 - 5,
                        "exp": clock.value // 1000 + 600, "scope": profile.content_scope,
                        "client_id": CONTENT_CLIENT, "jti": "identity-fixture"}, key,
                        algorithm="RS256", headers={"kid": KID, "typ": "at+jwt"})
                async def read(bearer):
                    return await _invoke(app, path=wire.ROUTES["CONTENT"],
                        headers=_headers(token=bearer, host="mcp.mastermind-x.com"))
                access = token()
                response = await read(access)
                assert response[0] == 200, response[2]
                body = wire.validate_body(json.loads(response[2]), "CONTENT")
                assert body["account_digest"] == wire.comparable_account_digest(
                    profile.issuer_digest, profile.subject_digest, profile.client_ref)
                assert seen and set(seen) == {ACCESS_SCHEMA}
                before = len(seen)
                assert (await read(token("foreign-synthetic-account")))[0] == 401
                assert len(seen) == before
                envelope["profiles"]["web"]["enabled"] = False
                refused = await read(access)
                assert refused[0] in (401, 403) and b"account_digest" not in refused[2]
                assert len(seen) == before
    asyncio.run(exercise())
