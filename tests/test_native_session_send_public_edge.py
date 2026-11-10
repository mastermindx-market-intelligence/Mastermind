"""Closed Session SEND exposure, real public fence and signed BFF owner.

Caddy is rendered/transition-validated, not installed or started. The actual
ASGI path fence and RS256 owner run with the incumbent inert private peer;
there is no live target, provider, grant or backend activation.
"""
import asyncio
import copy
import json

import pytest

from ops.executive_os import os_public_edge as edge
from ops.executive_os.os_public_edge_transition import prepare_config, final_config
from integrations.executive_mcp.server import _ExecutivePathFence
from tests.test_os_public_edge import manifest
from tests.test_project_controls_edge_join import predecessor, method_routes
from tests.test_mastermind_os_session_transport import (
    make_app, request, rsa_key, auth_fixture, ARGS, KEY, NOW,
)

ROUTE = "/os/executive/session/send"


def test_session_send_is_one_fixed_post_in_the_complete_composed_profile():
    assert ROUTE in edge.POST_ROUTES
    assert edge.PRE_BYOK_ROLES_GET_ROUTES == edge.PRE_NATIVE_SESSION_SEND_GET_ROUTES
    assert edge.PRE_AUTHORIZATION_IDENTITY_GET_ROUTES == edge.PRE_BYOK_ROLES_GET_ROUTES + ("/workspace/byok/roles/current",)
    assert edge.GET_ROUTES == edge.PRE_AUTHORIZATION_IDENTITY_GET_ROUTES + edge.AUTHORIZATION_IDENTITY_GET_ROUTES
    assert edge.PRE_BYOK_ROLES_POST_ROUTES == edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES + (ROUTE,)
    assert edge.PRE_DIRECT_NATIVE_POST_ROUTES == edge.PRE_BYOK_ROLES_POST_ROUTES + edge.PROJECT_EXECUTION_POST_ROUTES
    assert edge.PRE_COMPANY_PRIORITIES_POST_ROUTES == edge.PRE_DIRECT_NATIVE_POST_ROUTES + (
        "/os/executive/direct-native/result", "/os/executive/direct-native/consume",
        "/os/executive/direct-native/correction",
    )
    assert edge.POST_ROUTES == edge.PRE_COMPANY_PRIORITIES_POST_ROUTES + ("/os/executive/company-priorities",)
    assert (edge.PRE_AUTHORIZATION_IDENTITY_GET_ROUTES, edge.PRE_COMPANY_PRIORITIES_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert ROUTE not in edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES
    assert (edge.PRE_NATIVE_SESSION_SEND_GET_ROUTES,
            edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert ROUTE not in edge.GET_ROUTES and ROUTE not in edge.SOURCE_POST_ROUTES
    config = edge.render(manifest(), 49152)
    post = config.split("    @post {", 1)[1].split("    }", 1)[0]
    assert "method POST" in post and post.count(ROUTE) == 1
    assert config.count(ROUTE) == 1
    assert config.count("max_size 64KB") == 2
    assert config.count("max_size 98304") == 1
    assert config.count("reverse_proxy 127.0.0.1:49152") == 5


@pytest.mark.parametrize("maker", [prepare_config, final_config])
def test_real_transition_preserves_predecessor_and_changes_only_fixed_route_paths(maker):
    assert ROUTE in edge.POST_ROUTES
    old = predecessor()
    routes = method_routes(old)
    routes[0]["match"][0]["path"] = sorted(set(edge.PRE_NATIVE_SESSION_SEND_GET_ROUTES) |
                                              set(edge.asset_routes(manifest())))
    routes[1]["match"][0]["path"] = list(edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES)
    before = copy.deepcopy(old)
    result = maker(fullconfig=old, current_manifest=manifest(),
                   candidate_manifest=manifest(), relay_port=49152)
    expected = copy.deepcopy(old)
    method_routes(expected)[0]["match"][0]["path"] = sorted(set(edge.GET_ROUTES) | set(edge.asset_routes(manifest())))
    method_routes(expected)[1]["match"][0]["path"] = list(edge.POST_ROUTES)
    for route in method_routes(expected)[3:5]:
        route["match"][0]["path"] = (
            list(edge.COMPLETE_MCP_METADATA_ROUTES)
            if route["match"][0]["method"] == ["GET"]
            else list(edge.COMPLETE_MCP_ROUTES))
    assert result == expected and old == before
    for suffix in ("/", "-other", "/*"):
        malformed = copy.deepcopy(old)
        method_routes(malformed)[1]["match"][0]["path"].append(ROUTE + suffix)
        with pytest.raises(ValueError):
            maker(fullconfig=malformed, current_manifest=manifest(),
                  candidate_manifest=manifest(), relay_port=49152)


def public_owner(rsa_key):
    app, peer, clock, audit = make_app(rsa_key)
    return _ExecutivePathFence(app, "/.well-known/oauth-protected-resource",
                               os_session_transport=app), peer, clock, audit


def public_request(app, token, payload, *, method="POST", query=b"", raw_path=None,
                   header_changes=()):
    """Exercise the actual outer envelope as well as the leaf's own envelope."""
    headers = [(b"host", b"mcp.mastermind-x.com"),
               (b"content-type", b"application/json"),
               (b"authorization", ("Bearer " + token).encode())]
    for name, value in header_changes:
        if value is None: headers = [(k, v) for k, v in headers if k != name]
        else: headers.append((name, value))
    events = []
    async def receive():
        return {"type": "http.request", "body": json.dumps(payload).encode()}
    async def send(event): events.append(event)
    asyncio.run(app({"type": "http", "asgi": {"version": "3.0"},
        "method": method, "scheme": "https", "path": ROUTE,
        "raw_path": raw_path or ROUTE.encode(), "query_string": query,
        "headers": headers}, receive, send))
    starts = [e for e in events if e["type"] == "http.response.start"]
    assert len(starts) == 1
    raw = b"".join(e.get("body", b"") for e in events if e["type"] == "http.response.body")
    assert len(raw) <= 262144 and b"PRIVATE-" not in raw and token.encode() not in raw
    hs = dict(starts[0]["headers"])
    assert hs[b"cache-control"] == b"no-store" and hs[b"referrer-policy"] == b"no-referrer"
    assert hs[b"x-content-type-options"] == b"nosniff"
    return starts[0]["status"], json.loads(raw)


def test_actual_public_fence_to_signed_owner_keeps_exact_four_field_body(rsa_key):
    assert ROUTE in edge.POST_ROUTES
    app, peer, _, _ = public_owner(rsa_key)
    arguments = copy.deepcopy(ARGS)
    arguments["instruction"] = "Read the original.\n  保留原文  \n"
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send",
                             {"arguments": arguments})
    assert status == 200 and result["effect"] == "CONTINUATION_COMMITTED"
    assert len(peer.calls) == 1 and peer.calls[0]["arguments"] == arguments
    assert set(peer.calls[0]["arguments"]) == {
        "target_ref", "operation_key", "instruction", "stop_condition"}


@pytest.mark.parametrize("fault", ["read_only", "wrong_audience", "no_bearer", "duplicate_bearer",
                                  "extra_body", "get", "query", "trailing"])
def test_public_fence_scope_body_and_method_refuse_before_private_send(rsa_key, fault):
    assert ROUTE in edge.POST_ROUTES
    app, peer, _, _ = public_owner(rsa_key)
    token = auth_fixture._read_token(rsa_key) if fault == "read_only" else auth_fixture._submit_token(rsa_key)
    if fault == "wrong_audience":
        token = auth_fixture._submit_token(rsa_key, aud="https://mcp.mastermind-x.com/mcp")
    kwargs = {}
    payload = {"arguments": copy.deepcopy(ARGS)}
    if fault == "no_bearer": kwargs["header_changes"] = [(b"authorization", None)]
    if fault == "duplicate_bearer": kwargs["header_changes"] = [(b"authorization", b"Bearer foreign")]
    if fault == "extra_body": payload["principal_scope"] = "not-authority"
    if fault == "get": kwargs["method"] = "GET"
    if fault == "query": kwargs["query"] = b"target_ref=foreign"
    if fault == "trailing": kwargs["raw_path"] = (ROUTE + "/").encode()
    status, result = public_request(app, token, payload, **kwargs)
    assert status == {"read_only": 401, "wrong_audience": 401, "no_bearer": 403,
                      "duplicate_bearer": 403, "extra_body": 400,
                      "get": 404, "query": 404, "trailing": 404}[fault]
    assert peer.calls == []
    assert result.get("effect", "NONE") == "NONE"


def test_entered_original_send_expiry_remains_unknown_without_retry(rsa_key):
    assert ROUTE in edge.POST_ROUTES
    app, peer, clock, _ = public_owner(rsa_key)
    peer.after = lambda: clock.__setitem__(0, NOW + 400)
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send")
    assert status == 202 and result["effect"] == "UNKNOWN"
    assert result["operation_key"] == KEY and result["data"] is None
    assert len(peer.calls) == 1


def test_composed_profile_preserves_parent_native_and_project_predecessors():
    from integrations.mastermind_executive_app.project_execution_transport import ROUTES as execution_routes
    from integrations.executive_mcp.server import _WORKSPACE_ADDITIONAL_GET_ROUTES

    assert edge.PRE_BYOK_ROLES_POST_ROUTES == edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES + (ROUTE,)
    assert edge.PRE_PROJECT_EXECUTION_GET_ROUTES == edge.PRE_BYOK_ROLES_GET_ROUTES + edge.BYOK_READ_ROUTES
    assert edge.PRE_PROJECT_EXECUTION_POST_ROUTES == edge.PRE_BYOK_ROLES_POST_ROUTES
    assert edge.PRE_DIRECT_NATIVE_POST_ROUTES == edge.PRE_PROJECT_EXECUTION_POST_ROUTES + edge.PROJECT_EXECUTION_POST_ROUTES
    assert edge.PRE_COMPANY_PRIORITIES_POST_ROUTES == edge.PRE_DIRECT_NATIVE_POST_ROUTES + (
        "/os/executive/direct-native/result", "/os/executive/direct-native/consume",
        "/os/executive/direct-native/correction",
    )
    assert edge.POST_ROUTES == edge.PRE_COMPANY_PRIORITIES_POST_ROUTES + ("/os/executive/company-priorities",)
    assert (edge.PRE_AUTHORIZATION_IDENTITY_GET_ROUTES, edge.PRE_COMPANY_PRIORITIES_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert edge.PROJECT_EXECUTION_PRE_MERGE_GET_ROUTES == edge.PRE_NATIVE_SESSION_SEND_GET_ROUTES
    assert edge.PROJECT_EXECUTION_PRE_MERGE_POST_ROUTES == edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES + edge.PROJECT_EXECUTION_POST_ROUTES
    assert "/workspace/byok/roles/current" in _WORKSPACE_ADDITIONAL_GET_ROUTES
    assert set(edge.PROJECT_EXECUTION_POST_ROUTES) == set(execution_routes) | {
        "/os/executive/session/project-executions", "/os/executive/session/project-execution-read"}
    for pair in [(edge.PRE_BYOK_ROLES_GET_ROUTES, edge.PRE_BYOK_ROLES_POST_ROUTES),
                 (edge.PRE_PROJECT_EXECUTION_GET_ROUTES, edge.PRE_PROJECT_EXECUTION_POST_ROUTES),
                 (edge.PROJECT_EXECUTION_PRE_MERGE_GET_ROUTES, edge.PROJECT_EXECUTION_PRE_MERGE_POST_ROUTES)]:
        assert pair in edge.TRANSITION_ROUTE_PROFILES
    assert all("*" not in path for path in edge.GET_ROUTES + edge.POST_ROUTES)


@pytest.mark.parametrize("fault", ["missing_byok", "missing_project_post", "extra_byok", "wildcard_send"])
def test_composed_route_profiles_refuse_partial_or_expanded_sources(fault):
    old = predecessor()
    routes = method_routes(old)
    routes[0]["match"][0]["path"] = sorted(set(edge.GET_ROUTES) | set(edge.asset_routes(manifest())))
    routes[1]["match"][0]["path"] = list(edge.POST_ROUTES)
    if fault == "missing_byok":
        routes[0]["match"][0]["path"].remove("/workspace/byok/roles/current")
    elif fault == "missing_project_post":
        routes[1]["match"][0]["path"].remove("/os/executive/project-execution/submit")
    elif fault == "extra_byok":
        routes[0]["match"][0]["path"].append("/workspace/byok/keys/current")
    else:
        routes[1]["match"][0]["path"].append("/os/executive/session/*")
    with pytest.raises(ValueError):
        prepare_config(fullconfig=old, current_manifest=manifest(), candidate_manifest=manifest(), relay_port=49152)
