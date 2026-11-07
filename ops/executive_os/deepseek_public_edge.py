"""Pure exact-host DSH ingress addition; the existing Caddy publisher owns effects."""
from __future__ import annotations

import copy
import fnmatch
import re

HOST = "chat.mastermind-x.com"
OS_HOST = "mcp.mastermind-x.com"
RELAY_PORT = 4181
NATIVE_PORT = 4180
SCHEMA = "mastermind.deepseek_public_edge.v1"


def require(value, message):
    if not value:
        raise ValueError(message)


def site_route():
    """The native Caddy JSON shape qualified by the existing Caddy adapter."""
    return {
        "match": [{"host": [HOST]}], "terminal": True,
        "handle": [{"handler": "subroute", "routes": [{"handle": [
            {"handler": "headers", "response": {"set": {"Referrer-Policy": ["no-referrer"]}}},
            {"handler": "headers", "response": {
                "require": {"headers": {"Content-Security-Policy": None}},
                "set": {"Content-Security-Policy": ["frame-ancestors https://" + OS_HOST]},
            }},
            {"handler": "reverse_proxy", "upstreams": [{"dial": "127.0.0.1:4181"}],
             "headers": {
                 "request": {"delete": ["Forwarded", "X-Forwarded-Host", "X-Forwarded-Port",
                                       "X-Real-IP", "CF-Connecting-IP", "EO-Connecting-IP", "EO-Client-IP"]},
                 "response": {"replace": {"Set-Cookie": [
                     {"search_regexp": "(.*)", "replace": "$1; Secure"}]}},
             }},
        ]}]}],
    }


def _hosts(route):
    require(type(route) is dict and type(route.get("match")) is list and route["match"],
            "explicit site host matcher required")
    result = []
    for matcher in route["match"]:
        require(type(matcher) is dict and set(matcher) == {"host"}
                and type(matcher["host"]) is list and matcher["host"],
                "ambiguous site matcher refused")
        for host in matcher["host"]:
            require(type(host) is str and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host),
                    "literal site host required")
            result.append(host)
    require(len(result) == len(set(result)), "duplicate site host")
    return result


def candidate_config(fullconfig):
    """Add exactly one terminal sibling site, preserving all existing JSON."""
    require(type(fullconfig) is dict, "full configuration required")
    servers = fullconfig.get("apps", {}).get("http", {}).get("servers")
    require(type(servers) is dict and servers, "HTTP servers required")
    selected = []
    for name, server in servers.items():
        require(type(server) is dict, "server object required")
        for route in server.get("routes", []):
            for matcher in route.get("match", []):
                for host in matcher.get("host", []):
                    require(type(host) is str and not fnmatch.fnmatchcase(HOST, host.lower()),
                            "chat host already present or overlaps another route")
                    if host == OS_HOST:
                        selected.append(name)
    require(len(selected) == 1, "one existing OS HTTPS site required")
    name = selected[0]
    server = servers[name]
    require(server.get("listen") == [":443"], "qualified HTTPS listener required")
    automatic = server.get("automatic_https", {})
    require(type(automatic) is dict and not automatic.get("disable")
            and not automatic.get("disable_certificates")
            and not any(fnmatch.fnmatchcase(HOST, value)
                        for key in ("skip", "skip_certificates") for value in automatic.get(key, [])),
            "automatic HTTPS does not admit the chat host")
    policies = server.get("tls_connection_policies", [{}])
    require(type(policies) is list and len(policies) == 1 and type(policies[0]) is dict
            and set(policies[0]) <= {"protocol_min", "protocol_max", "cipher_suites",
                                   "curves", "alpn"},
            "SNI-specific or client-auth TLS policy requires separate qualification")
    require("alpn" not in policies[0] or (
        type(policies[0]["alpn"]) is list and bool(policies[0]["alpn"])
        and set(policies[0]["alpn"]) <= {"h2", "http/1.1"}),
        "ordinary browser TLS protocols required")
    tls = fullconfig.get("apps", {}).get("tls", {})
    require(type(tls) is dict, "TLS application object required")
    for policy in tls.get("automation", {}).get("policies", []):
        require(type(policy) is dict, "TLS automation policy required")
        subjects = policy.get("subjects", [])
        require(type(subjects) is list and all(type(value) is str for value in subjects),
                "TLS automation subjects refused")
        if not subjects or any(fnmatch.fnmatchcase(HOST, value.lower()) for value in subjects):
            require(set(policy) <= {"subjects"},
                    "chat certificate issuance authority requires separate qualification")
    hosts = [host for route in server.get("routes", []) for host in _hosts(route)]
    require(len(hosts) == len(set(hosts)), "overlapping existing site host")
    result = copy.deepcopy(fullconfig)
    result["apps"]["http"]["servers"][name]["routes"].append(site_route())
    restored = copy.deepcopy(result)
    restored["apps"]["http"]["servers"][name]["routes"].pop()
    require(restored == fullconfig, "unrelated configuration changed")
    return result
