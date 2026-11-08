"""Pure two-phase OS public-edge transition planning; never installs or reloads Caddy.

Prepares the exact replacement of the installed public OS edge asset routes in
two phases: a prepare config admitting both the retired and candidate asset
paths plus the new fixed authenticated Control Room GET/POST routes, and a final
config admitting only candidate assets plus those same closed new routes. Both
the incumbent and expanded observed method-specific profiles are admitted;
mixed or extra routes fail closed. The optional dedicated source-operation POST
branch (exact 98304-byte cap) is planned the same way: an observed config
without it gains it at the canonical position between the legacy POST branch
and the MCP branches, and an observed config with it is validated exactly and
stays idempotent. The two public-MCP matchers are planned as one coherent
profile: an observed CEO-only metadata/transport pair is upgraded in place to
the complete CEO+COO pair, and an already complete pair stays idempotent. A
partial upgrade, a mixed pair, a duplicate, a wildcard or an extra path fails
closed, and a config with no public-MCP family at all never gains one here.
Configs are transformed only in memory;
staging writes plan/candidate JSON under an existing sealed parent. No network, SSH, subprocess, daemon, environment
override, ``caddy load``/reload or production write exists here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from ops.executive_os.os_public_edge import (
    COMPLETE_MCP_METADATA_ROUTES, COMPLETE_MCP_ROUTES, GET_ROUTES, HOST, LEGACY_GET_ROUTES,
    LEGACY_POST_ROUTES, MCP_MAX_BODY, MCP_METADATA_ROUTES, MCP_ROUTES,
    NATIVE_CONVERSATION_POST_ROUTES, NATIVE_MAX_BODY,
    POST_ROUTES, SOURCE_MAX_BODY, SOURCE_POST_ROUTES, TRANSITION_ROUTE_PROFILES,
    asset_routes,
)

PLAN_SCHEMA = "mastermind.os_public_edge_transition.plan.v1"
PREPARE_CHECK_SCHEMA = "mastermind.os_public_edge_transition.prepare_check.v1"
RESTART_SCHEMA = "mastermind.os_public_edge_transition.restart.v1"
STAGE_SCHEMA = "mastermind.os_public_edge_transition.stage.v1"
PLAN_NAME = "transition-plan.json"
PREPARE_NAME = "prepare-config.json"
FINAL_NAME = "final-config.json"
_INDEX = "index.html"
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}")
_MAX_INPUT_BYTES = 4 * 1024 * 1024


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sources(old_source: object, new_source: object) -> None:
    if (type(old_source) is not str or type(new_source) is not str
            or not _SOURCE_SHA.fullmatch(old_source) or not _SOURCE_SHA.fullmatch(new_source)
            or old_source == new_source):
        raise ValueError("OS edge transition source ids refused")


def _relay(relay_port: object) -> None:
    if type(relay_port) is not int or not 49152 <= relay_port <= 50200:
        raise ValueError("OS edge transition relay port refused")


def _asset_pair(current_manifest: object,
                candidate_manifest: object) -> tuple[tuple[str, ...], tuple[str, ...], list[str]]:
    current = asset_routes(current_manifest)
    candidate = asset_routes(candidate_manifest)
    retired = {item["path"]: item for item in current_manifest["files"]}
    replacing = {item["path"]: item for item in candidate_manifest["files"]}
    shared = []
    for path in sorted(set(retired) & set(replacing)):
        if path == _INDEX:
            # index.html is deliberately the switch; only its route stays fixed.
            continue
        was, now = retired[path], replacing[path]
        if (was["byte_count"], was["sha256"], was["mime"]) != (now["byte_count"], now["sha256"], now["mime"]):
            raise ValueError("OS edge shared asset bytes changed")
        shared.append(path)
    return current, candidate, shared


def _route_hosts(route: object) -> list[str]:
    if type(route) is not dict or type(route.get("match")) is not list:
        return []
    hosts = []
    for match in route["match"]:
        if type(match) is not dict or "host" not in match:
            continue
        entries = match["host"]
        if type(entries) is not list or any(type(entry) is not str for entry in entries):
            raise ValueError("OS edge transition host matcher refused")
        hosts.extend(entries)
    return hosts


def _subroute(handlers: object) -> list | None:
    if (type(handlers) is list and len(handlers) == 1
            and type(handlers[0]) is dict
            and set(handlers[0]) == {"handler", "routes"}
            and handlers[0]["handler"] == "subroute"
            and type(handlers[0]["routes"]) is list):
        return handlers[0]["routes"]
    return None


def _branch_handlers(handlers: object) -> list:
    # Caddy's adapter adds transparent singleton subroutes around handle blocks.
    # Only this closed wrapper shape may be removed for inspection, not mutation.
    for _ in range(8):
        nested = _subroute(handlers)
        if nested is None:
            if type(handlers) is not list or any(type(h) is not dict for h in handlers):
                raise ValueError("OS edge transition branch handlers refused")
            return handlers
        if len(nested) != 1 or type(nested[0]) is not dict or set(nested[0]) != {"handle"}:
            raise ValueError("OS edge transition branch wrapper refused")
        handlers = nested[0]["handle"]
    raise ValueError("OS edge transition wrapper depth refused")


_STRIPPED_REQUEST_HEADERS = ("Forwarded", "X-Forwarded-Host", "X-Forwarded-Port", "X-Real-IP",
                             "CF-Connecting-IP", "EO-Connecting-IP", "EO-Client-IP")


def _expected_proxy(relay_port: int, upstream_host: str) -> dict:
    return {
        "handler": "reverse_proxy",
        "upstreams": [{"dial": f"127.0.0.1:{relay_port}"}],
        "headers": {"request": {
            "delete": list(_STRIPPED_REQUEST_HEADERS),
            "set": {"Host": [upstream_host], "X-Forwarded-For": ["127.0.0.1"],
                    "X-Forwarded-Proto": ["https"]},
        }},
    }


def _proxy_matches(observed: object, relay_port: int, upstream_host: str) -> bool:
    if type(observed) is not dict:
        return False
    candidate = dict(observed)
    # The adapter emits no transport; an explicit plain-HTTP one is the same behavior.
    if candidate.get("transport") == {"protocol": "http"}:
        del candidate["transport"]
    return candidate == _expected_proxy(relay_port, upstream_host)


def _locate(fullconfig: object, current_routes: tuple[str, ...], relay_port: int) -> dict:
    _relay(relay_port)
    if type(fullconfig) is not dict:
        raise ValueError("OS edge transition fullconfig refused")
    try:
        servers = fullconfig["apps"]["http"]["servers"]
    except (KeyError, TypeError):
        raise ValueError("OS edge transition http servers refused") from None
    if type(servers) is not dict:
        raise ValueError("OS edge transition http servers refused")
    found = None
    for name, server in servers.items():
        if type(name) is not str or type(server) is not dict or type(server.get("routes")) is not list:
            raise ValueError("OS edge transition server routes refused")
        for index, route in enumerate(server["routes"]):
            hosts = _route_hosts(route)
            if HOST not in hosts:
                continue
            if found is not None or route.get("match") != [{"host": [HOST]}]:
                raise ValueError("OS edge transition host route ambiguous")
            found = (name, index, route)
    if found is None:
        raise ValueError("OS edge transition host route absent")
    name, index, route = found
    if set(route) != {"match", "handle", "terminal"} or route["terminal"] is not True:
        raise ValueError("OS edge transition host route shape refused")
    inner = _subroute(route["handle"])
    if inner is None:
        raise ValueError("OS edge transition host subroute refused")
    path = ("apps", "http", "servers", name, "routes", index, "handle", 0, "routes")
    for _ in range(8):
        if len(inner) != 1 or type(inner[0]) is not dict or set(inner[0]) != {"handle"}:
            break
        nested = _subroute(inner[0]["handle"])
        if nested is None:
            break
        inner = nested
        path += (0, "handle", 0, "routes")
    # Accepted inner shapes: GET/POST/abort, GET/POST/MCP-metadata-GET/MCP-POST/
    # abort (the public MCP entrypoint), and either of those two plus the
    # dedicated source-operation POST branch in its canonical position between
    # the legacy POST branch and the MCP branches. Arbitrary reordering,
    # partial upgrades and mixtures cannot pass.
    # A native branch is accepted only immediately before the terminal abort.
    # Remove only that exact matcher from topology counting; its entire body
    # and proxy are still qualified below. Malformed or displaced branches
    # cannot be treated as an absent native family.
    has_native = (len(inner) >= 2 and type(inner[-2]) is dict
        and inner[-2].get("match") == [{
            "method": ["POST"], "path": list(NATIVE_CONVERSATION_POST_ROUTES)}])
    incumbent_count = len(inner) - int(has_native)
    if incumbent_count not in (3, 4, 5, 6):
        raise ValueError("OS edge transition inner route set refused")
    has_source = incumbent_count in (4, 6)
    has_mcp = incumbent_count in (5, 6)
    mcp_meta_position = 3 if has_source else 2
    mcp_post_position = mcp_meta_position + 1
    # Match a complete admitted pair, not independent subsets or a cross-product.
    # Comparing list and set forms permits only the known index.html /os/ overlap.
    source_profiles = {index for index, (fixed_get, _) in enumerate(TRANSITION_ROUTE_PROFILES)
                       if "/workspace/source-operation/operation" in fixed_get}
    get_path = post_path = source_path = None
    mcp_meta_path = mcp_post_path = None
    mcp_meta_paths = mcp_post_paths = None
    post_group = None
    get_matches = post_matches = set()
    methods = set()
    for position, item in enumerate(inner):
        if type(item) is not dict:
            raise ValueError("OS edge transition inner route refused")
        if position == len(inner) - 1:
            if item != {"handle": [{"handler": "static_response", "abort": True}]}:
                raise ValueError("OS edge transition terminal route refused")
            if item["handle"][0]["abort"] is not True:
                raise ValueError("OS edge transition terminal flag refused")
            continue
        if set(item) not in ({"match", "handle"}, {"match", "handle", "group"}):
            raise ValueError("OS edge transition branch shape refused")
        if "group" in item and (type(item["group"]) is not str or not item["group"]):
            raise ValueError("OS edge transition branch group refused")
        match = item["match"]
        if type(match) is not list or len(match) != 1 or type(match[0]) is not dict or set(match[0]) != {"method", "path"}:
            raise ValueError("OS edge transition inner matcher refused")
        method, paths = match[0]["method"], match[0]["path"]
        if (type(method) is not list or len(method) != 1 or method[0] not in ("GET", "POST")
                or type(paths) is not list or any(type(value) is not str for value in paths)):
            raise ValueError("OS edge transition inner matcher refused")
        handlers = _branch_handlers(item["handle"])
        if has_native and position == len(inner) - 2:
            if (method != ["POST"] or paths != list(NATIVE_CONVERSATION_POST_ROUTES)
                    or len(handlers) != 2
                    or handlers[0] != {"handler": "request_body", "max_size": NATIVE_MAX_BODY}
                    or type(handlers[0].get("max_size")) is not int):
                raise ValueError("OS edge transition observed native route differs")
        elif has_mcp and position == mcp_meta_position:
            # Fixed, immutable MCP branches: only the two OS path lists change.
            # The metadata matcher carries exactly the CEO-only list or the
            # complete CEO+COO list, in that order. A partial COO upgrade, a
            # duplicate, a wildcard or any extra path is refused here.
            if (method != ["GET"]
                    or paths not in (list(MCP_METADATA_ROUTES), list(COMPLETE_MCP_METADATA_ROUTES))
                    or len(handlers) != 1):
                raise ValueError("OS edge transition observed MCP route differs")
            mcp_meta_paths = list(paths)
        elif has_mcp and position == mcp_post_position:
            if (method != ["POST"]
                    or paths not in (list(MCP_ROUTES), list(COMPLETE_MCP_ROUTES))
                    or len(handlers) != 2
                    or handlers[0] != {"handler": "request_body", "max_size": MCP_MAX_BODY}
                    or type(handlers[0].get("max_size")) is not int):
                raise ValueError("OS edge transition observed MCP route differs")
            mcp_post_paths = list(paths)
        elif has_source and position == 2:
            # Dedicated source branch: exact paths in canonical order, the
            # 98304-byte cap; no wildcard, duplicate, merged or reordered entry.
            if (method != ["POST"] or paths != list(SOURCE_POST_ROUTES) or len(handlers) != 2
                    or handlers[0] != {"handler": "request_body", "max_size": SOURCE_MAX_BODY}
                    or type(handlers[0].get("max_size")) is not int):
                raise ValueError("OS edge transition observed source route differs")
            source_path = path + (position, "match", 0, "path")
        elif position == 0 and method == ["GET"]:
            if method[0] in methods:
                raise ValueError("OS edge transition inner matcher refused")
            methods.add(method[0])
            get_matches = {
                index for index, (fixed_get, _) in enumerate(TRANSITION_ROUTE_PROFILES)
                if sorted(paths) in (
                    sorted(set(fixed_get) | set(current_routes)),
                    sorted(list(fixed_get) + list(current_routes)),
                )
            }
            if not get_matches or len(handlers) != 1:
                raise ValueError("OS edge transition observed GET routes differ")
            get_path = path + (position, "match", 0, "path")
        elif position == 1 and method == ["POST"]:
            if method[0] in methods:
                raise ValueError("OS edge transition inner matcher refused")
            methods.add(method[0])
            post_matches = {
                index for index, (_, fixed_post) in enumerate(TRANSITION_ROUTE_PROFILES)
                if sorted(paths) == sorted(fixed_post)
            }
            if (len(paths) != len(set(paths)) or not post_matches
                    or len(handlers) != 2
                    or handlers[0] != {"handler": "request_body", "max_size": 64000}
                    or type(handlers[0].get("max_size")) is not int):
                raise ValueError("OS edge transition observed POST route differs")
            post_path = path + (position, "match", 0, "path")
            if type(item.get("group")) is str and item["group"]:
                post_group = item["group"]
        else:
            raise ValueError("OS edge transition inner route order refused")
        # Every branch's proxy must be the whole rendered handler, not merely the
        # right upstream: a changed Host, header list, rewrite or transport would
        # alter what the gateway sees. Only the MCP POST branch presents the
        # gateway's loopback Host; the source branch presents the public HOST.
        upstream_host = "127.0.0.1" if has_mcp and position == mcp_post_position else HOST
        if not _proxy_matches(handlers[-1], relay_port, upstream_host):
            raise ValueError("OS edge transition relay upstream refused")
    if (methods != {"GET", "POST"} or get_path is None or post_path is None
            or (has_source and source_path is None)
            or not get_matches.intersection(post_matches)):
        raise ValueError("OS edge transition mixed or incomplete route profile")
    # All exact profiles containing the original-operation read retain its
    # dedicated POST branch, including the sealed predecessor before controls.
    # The intersection still requires one complete admitted GET/POST pair.
    matched_source = bool(get_matches.intersection(post_matches, source_profiles))
    if has_source and not matched_source:
        raise ValueError("OS edge transition source profile incomplete")
    if not has_source and matched_source:
        raise ValueError("OS edge transition mixed or incomplete route profile")
    # The two public-MCP matchers form one coherent profile: the CEO-only pair
    # or the complete CEO+COO pair. A metadata list upgraded without the
    # matching transport list is a partial upgrade and is refused.
    if has_mcp:
        metadata_complete = mcp_meta_paths == list(COMPLETE_MCP_METADATA_ROUTES)
        transport_complete = mcp_post_paths == list(COMPLETE_MCP_ROUTES)
        if metadata_complete != transport_complete:
            raise ValueError("OS edge transition mixed or incomplete MCP profile")
        mcp_profile = "complete" if metadata_complete else "ceo_only"
        mcp_meta_path = path + (mcp_meta_position, "match", 0, "path")
        mcp_post_path = path + (mcp_post_position, "match", 0, "path")
    else:
        mcp_profile = "absent"
    if has_native:
        current_profile = TRANSITION_ROUTE_PROFILES.index((GET_ROUTES, POST_ROUTES))
        if (not has_source or current_profile not in get_matches.intersection(post_matches)
                or mcp_profile not in {"absent", "complete"}):
            raise ValueError("OS edge transition native profile incomplete")
    return {"inner": path, "get": get_path, "post": post_path, "source": source_path,
            "source_branch": has_source, "native_branch": has_native, "post_group": post_group,
            "mcp_meta": mcp_meta_path, "mcp_post": mcp_post_path,
            "mcp_profile": mcp_profile}


def _source_branch(relay_port: int, group: object) -> dict:
    # The canonical dedicated source branch, identical to the rendered template
    # branch: the 98304-byte cap plus the same public HOST proxy with the same
    # stripped forwarded headers. Never a widened legacy matcher.
    branch = {
        "match": [{"method": ["POST"], "path": list(SOURCE_POST_ROUTES)}],
        "handle": [
            {"handler": "request_body", "max_size": SOURCE_MAX_BODY},
            _expected_proxy(relay_port, HOST),
        ],
    }
    if group is not None:
        branch = {"group": group, **branch}
    return branch


def _native_branch(relay_port: int, group: object) -> dict:
    branch = {
        "match": [{"method": ["POST"], "path": list(NATIVE_CONVERSATION_POST_ROUTES)}],
        "handle": [
            {"handler": "request_body", "max_size": NATIVE_MAX_BODY},
            _expected_proxy(relay_port, HOST),
        ],
    }
    if group is not None:
        branch = {"group": group, **branch}
    return branch


def _transition(*, fullconfig: object, current_manifest: object,
                candidate_manifest: object, relay_port: int) -> dict:
    current_routes, candidate_routes, shared = _asset_pair(current_manifest, candidate_manifest)
    located = _locate(fullconfig, current_routes, relay_port)
    return {
        "position": located["get"],
        "post_position": located["post"],
        "source_position": located["source"],
        "source_branch": located["source_branch"],
        "native_branch": located["native_branch"],
        "inner_position": located["inner"],
        "post_group": located["post_group"],
        "mcp_meta_position": located["mcp_meta"],
        "mcp_post_position": located["mcp_post"],
        "mcp_profile": located["mcp_profile"],
        "retired": list(current_routes),
        "candidate": list(candidate_routes),
        "shared": shared,
        # Sorted unique unions over the incumbent fixed routes.
        "prepare": sorted(set(GET_ROUTES) | set(current_routes) | set(candidate_routes)),
        "final": sorted(set(GET_ROUTES) | set(candidate_routes)),
    }


def _set_path(root: object, field_path: tuple, values: object) -> None:
    target = root
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = list(values)


def _rebuild(fullconfig: object, position: tuple, paths: list[str],
             *, post_position: tuple, post_paths: tuple[str, ...],
             source_position: tuple | None = None,
             source_paths: tuple[str, ...] | None = None,
             mcp_meta_position: tuple | None = None,
             mcp_meta_paths: tuple[str, ...] | None = None,
             mcp_post_position: tuple | None = None,
             mcp_post_paths: tuple[str, ...] | None = None,
             insert: tuple | None = None) -> dict:
    rebuilt = copy.deepcopy(fullconfig)
    _set_path(rebuilt, position, paths)
    _set_path(rebuilt, post_position, post_paths)
    if source_position is not None:
        _set_path(rebuilt, source_position, source_paths)
    # The public-MCP matchers are rewritten before the optional source-branch
    # insertion, so these positions are the observed ones. Only the two fixed
    # path lists change; the metadata branch keeps the public Host, the
    # transport branch keeps the gateway's loopback Host and 64000-byte cap.
    if mcp_meta_position is not None:
        _set_path(rebuilt, mcp_meta_position, mcp_meta_paths)
    if mcp_post_position is not None:
        _set_path(rebuilt, mcp_post_position, mcp_post_paths)
    if insert is not None:
        inner_path, index, branch = insert
        target = rebuilt
        for key in inner_path:
            target = target[key]
        if type(target) is not list or len(target) < 2 or index != 2:
            raise ValueError("OS edge transition insertion point refused")
        target.insert(index, copy.deepcopy(branch))
    return rebuilt


def _rebuilt(fullconfig: object, data: dict, get_paths: list[str], relay_port: int) -> dict:
    insert = None
    if not data["source_branch"]:
        insert = (data["inner_position"], 2,
                  _source_branch(relay_port, data["post_group"]))
    rebuilt = _rebuild(fullconfig, data["position"], get_paths,
                    post_position=data["post_position"], post_paths=POST_ROUTES,
                    source_position=data["source_position"],
                    source_paths=SOURCE_POST_ROUTES,
                    mcp_meta_position=data["mcp_meta_position"],
                    mcp_meta_paths=COMPLETE_MCP_METADATA_ROUTES,
                    mcp_post_position=data["mcp_post_position"],
                    mcp_post_paths=COMPLETE_MCP_ROUTES,
                    insert=insert)
    if not data["native_branch"]:
        target = rebuilt
        for key in data["inner_position"]:
            target = target[key]
        target.insert(len(target) - 1, _native_branch(relay_port, data["post_group"]))
    return rebuilt


def plan(*, old_source: str, new_source: str, fullconfig: object, current_manifest: object,
         candidate_manifest: object, relay_port: int) -> dict:
    _sources(old_source, new_source)
    data = _transition(fullconfig=fullconfig, current_manifest=current_manifest,
                       candidate_manifest=candidate_manifest, relay_port=relay_port)
    return {
        "schema": PLAN_SCHEMA,
        "host": HOST,
        "relay_port": relay_port,
        # Source ids are recorded as bindings only; this never asserts that the
        # protected sources or their authentication were verified here.
        "sources": {"retired": old_source, "candidate": new_source, "binding_only": True},
        "bindings": {
            "observed_fullconfig_sha256": _sha256(fullconfig),
            "current_manifest_sha256": _sha256(current_manifest),
            "candidate_manifest_sha256": _sha256(candidate_manifest),
            "prepare_fullconfig_sha256": _sha256(_rebuilt(fullconfig, data, data["prepare"], relay_port)),
            "final_fullconfig_sha256": _sha256(_rebuilt(fullconfig, data, data["final"], relay_port)),
        },
        "get_routes": {
            "fixed": list(GET_ROUTES),
            "retired": data["retired"],
            "candidate": data["candidate"],
            "prepare": data["prepare"],
            "final": data["final"],
        },
        "post_routes": list(POST_ROUTES),
        "source_post_routes": list(SOURCE_POST_ROUTES),
        "native_post_routes": list(NATIVE_CONVERSATION_POST_ROUTES),
        "native_max_body": NATIVE_MAX_BODY,
        "observed_native_branch": data["native_branch"],
        # Existing MCP profiles upgrade to the complete CEO+COO pair.
        # An absent MCP family stays absent in both planned configurations.
        "mcp_routes": {
            "observed_profile": data["mcp_profile"],
            "metadata": ([] if data["mcp_profile"] == "absent"
                         else list(COMPLETE_MCP_METADATA_ROUTES)),
            "transport": ([] if data["mcp_profile"] == "absent"
                          else list(COMPLETE_MCP_ROUTES)),
        },
        "shared_assets_verified": data["shared"],
        "installed": False,
        "published": False,
    }


def prepare_config(*, fullconfig: object, current_manifest: object,
                   candidate_manifest: object, relay_port: int) -> dict:
    data = _transition(fullconfig=fullconfig, current_manifest=current_manifest,
                       candidate_manifest=candidate_manifest, relay_port=relay_port)
    return _rebuilt(fullconfig, data, data["prepare"], relay_port)


def final_config(*, fullconfig: object, current_manifest: object,
                 candidate_manifest: object, relay_port: int) -> dict:
    data = _transition(fullconfig=fullconfig, current_manifest=current_manifest,
                       candidate_manifest=candidate_manifest, relay_port=relay_port)
    return _rebuilt(fullconfig, data, data["final"], relay_port)


def preparation_complete(*, observed: object, prepared: object) -> dict:
    if (type(observed) is not dict or type(prepared) is not dict
            or _canonical(observed) != _canonical(prepared)):
        raise ValueError("OS edge transition prepared config is not observed exactly")
    return {
        "schema": PREPARE_CHECK_SCHEMA,
        "observed_sha256": _sha256(observed),
        "prepared_sha256": _sha256(prepared),
        "prepared_observed_exactly": True,
        "installed": False,
        "published": False,
    }


def _host_routes(config: object) -> int:
    count = 0
    try:
        servers = config["apps"]["http"]["servers"]
    except (KeyError, TypeError):
        return count
    if type(servers) is not dict:
        return count
    for server in servers.values():
        if type(server) is not dict or type(server.get("routes")) is not list:
            continue
        count += sum(1 for route in server["routes"] if HOST in _route_hosts(route))
    return count


def restart_diagnostic(*, observed: object, autosave: object, startup: object) -> dict:
    if any(type(value) is not dict for value in (observed, autosave, startup)):
        raise ValueError("OS edge transition restart config refused")
    equals_startup = _canonical(observed) == _canonical(startup)
    return {
        "schema": RESTART_SCHEMA,
        "bindings": {
            "observed_sha256": _sha256(observed),
            "autosave_sha256": _sha256(autosave),
            "startup_sha256": _sha256(startup),
        },
        "host_routes": {"observed": _host_routes(observed), "autosave": _host_routes(autosave),
                        "startup": _host_routes(startup)},
        "observed_equals_autosave": _canonical(observed) == _canonical(autosave),
        "observed_equals_startup": equals_startup,
        "autosave_equals_startup": _canonical(autosave) == _canonical(startup),
        # Autosave equality alone never qualifies a restart: startup uses the
        # adapted combined Caddyfile while --resume loads the autosave.
        "restart_safe_by_config_equality": equals_startup,
        # Observed config equality is not an actually tested restart.
        "restart_verified": False,
        "autosave_alone_qualifies_restart": False,
        "verdict": ("config equality only; an actual restart remains separately "
                    "tested by the host owner" if equals_startup else
                    "effective startup config differs from the observed live config; "
                    "autosave equality does not qualify startup"),
    }


def _sealed_parent(parent: Path) -> None:
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022 or parent.resolve() != parent:
        raise ValueError("OS edge transition output directory refused")


def _stage_file(parent: Path, name: str, payload: bytes) -> str:
    target = parent / name
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    # Keep every partial artifact on failure, exactly as the incumbent stage
    # does. Its presence prevents blind re-entry after an uncertain write.
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def stage_transition(*, plan: dict, prepare: dict, final: dict, out: Path) -> dict:
    documents = ((PLAN_NAME, plan), (PREPARE_NAME, prepare), (FINAL_NAME, final))
    if any(type(value) is not dict for _, value in documents):
        raise ValueError("OS edge transition staged document refused")
    _sealed_parent(out)
    staged = {name: _stage_file(out, name, _canonical(value) + b"\n")
              for name, value in documents}
    return {"schema": STAGE_SCHEMA, "files": staged, "installed": False, "published": False}


def _no_duplicate(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError("OS edge transition JSON duplicate key refused")
        seen.add(key)
    return dict(pairs)


def _reject_constant(name):
    raise ValueError("OS edge transition JSON nonfinite refused")


def _load(path: Path) -> object:
    with Path(path).open("rb") as stream:
        data = stream.read(_MAX_INPUT_BYTES + 1)
    if len(data) > _MAX_INPUT_BYTES:
        raise ValueError("OS edge transition input too large")
    return json.loads(data, object_pairs_hook=_no_duplicate, parse_constant=_reject_constant)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--manifest-current", type=Path, required=True)
    parser.add_argument("--manifest-candidate", type=Path, required=True)
    parser.add_argument("--source-old", required=True)
    parser.add_argument("--source-new", required=True)
    parser.add_argument("--relay-port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--autosave", type=Path, default=None)
    parser.add_argument("--startup", type=Path, default=None)
    args = parser.parse_args()
    if (args.autosave is None) != (args.startup is None):
        raise SystemExit("--autosave and --startup are supplied together")
    live = _load(args.live)
    current_manifest = _load(args.manifest_current)
    candidate_manifest = _load(args.manifest_candidate)
    plan_value = plan(old_source=args.source_old, new_source=args.source_new, fullconfig=live,
                      current_manifest=current_manifest, candidate_manifest=candidate_manifest,
                      relay_port=args.relay_port)
    prepared = prepare_config(fullconfig=live, current_manifest=current_manifest,
                              candidate_manifest=candidate_manifest, relay_port=args.relay_port)
    final = final_config(fullconfig=live, current_manifest=current_manifest,
                         candidate_manifest=candidate_manifest, relay_port=args.relay_port)
    diagnostic = None
    if args.autosave is not None:
        diagnostic = restart_diagnostic(observed=live, autosave=_load(args.autosave), startup=_load(args.startup))
    receipt = stage_transition(plan=plan_value, prepare=prepared, final=final, out=args.out)
    summary = {
        "schema": receipt["schema"],
        "files": receipt["files"],
        "plan_sha256": _sha256(plan_value),
        "prepare_sha256": _sha256(prepared),
        "final_sha256": _sha256(final),
        "get_route_counts": {"prepare": len(plan_value["get_routes"]["prepare"]),
                             "final": len(plan_value["get_routes"]["final"])},
        "relay_port": args.relay_port,
        "installed": False,
        "published": False,
    }
    if diagnostic is not None:
        summary["restart"] = {key: diagnostic[key] for key in (
            "observed_equals_autosave", "observed_equals_startup",
            "restart_safe_by_config_equality", "restart_verified")}
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
