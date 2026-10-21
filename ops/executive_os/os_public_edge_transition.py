"""Pure two-phase OS public-edge transition planning; never installs or reloads Caddy.

Prepares the exact replacement of the installed public OS edge asset routes in
two phases: a prepare config admitting both the retired and candidate asset
paths, and a final config admitting only the candidate paths. Configs are
transformed in memory only; staging writes plan/candidate JSON under an
existing sealed parent. No network, SSH, subprocess, daemon, environment
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
    GET_ROUTES, HOST, MCP_MAX_BODY, MCP_METADATA_ROUTE, MCP_ROUTES, POST_ROUTES, asset_routes,
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


def _locate(fullconfig: object, current_routes: tuple[str, ...],
            relay_port: int) -> tuple:
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
    # Two accepted shapes: the original GET/POST/abort and, with the public MCP
    # entrypoint (#1656), GET/POST/MCP-metadata-GET/MCP-POST/abort in that order.
    if len(inner) not in (3, 5):
        raise ValueError("OS edge transition inner route set refused")
    expected = sorted(set(GET_ROUTES) | set(current_routes))
    legacy = sorted(list(GET_ROUTES) + list(current_routes))
    get_path = None
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
        if position >= 2:
            # Fixed, immutable MCP branches: only the asset GET list ever changes.
            if position == 2:
                same = method == ["GET"] and paths == [MCP_METADATA_ROUTE] and len(handlers) == 1
            else:
                same = (method == ["POST"] and paths == list(MCP_ROUTES) and len(handlers) == 2
                        and handlers[0] == {"handler": "request_body", "max_size": MCP_MAX_BODY}
                        and type(handlers[0].get("max_size")) is int)
            if not same:
                raise ValueError("OS edge transition observed MCP route differs")
        else:
            if method[0] in methods:
                raise ValueError("OS edge transition inner matcher refused")
            methods.add(method[0])
            if method == ["GET"]:
                if sorted(paths) not in (expected, legacy) or len(handlers) != 1:
                    raise ValueError("OS edge transition observed GET routes differ")
                get_path = path + (position, "match", 0, "path")
            else:
                if (sorted(paths) != sorted(POST_ROUTES) or len(handlers) != 2
                        or handlers[0] != {"handler": "request_body", "max_size": 64000}
                        or type(handlers[0].get("max_size")) is not int):
                    raise ValueError("OS edge transition observed POST route differs")
        proxy = handlers[-1]
        if (proxy.get("handler") != "reverse_proxy"
                or proxy.get("upstreams") != [{"dial": f"127.0.0.1:{relay_port}"}]):
            raise ValueError("OS edge transition relay upstream refused")
    if methods != {"GET", "POST"} or get_path is None:
        raise ValueError("OS edge transition branch set refused")
    return get_path


def _transition(*, fullconfig: object, current_manifest: object,
                candidate_manifest: object, relay_port: int) -> dict:
    current_routes, candidate_routes, shared = _asset_pair(current_manifest, candidate_manifest)
    position = _locate(fullconfig, current_routes, relay_port)
    return {
        "position": position,
        "retired": list(current_routes),
        "candidate": list(candidate_routes),
        "shared": shared,
        # Sorted unique unions over the incumbent fixed routes.
        "prepare": sorted(set(GET_ROUTES) | set(current_routes) | set(candidate_routes)),
        "final": sorted(set(GET_ROUTES) | set(candidate_routes)),
    }


def _rebuild(fullconfig: object, position: tuple, paths: list[str]) -> dict:
    rebuilt = copy.deepcopy(fullconfig)
    target = rebuilt
    for key in position[:-1]:
        target = target[key]
    target[position[-1]] = list(paths)
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
            "prepare_fullconfig_sha256": _sha256(_rebuild(fullconfig, data["position"], data["prepare"])),
            "final_fullconfig_sha256": _sha256(_rebuild(fullconfig, data["position"], data["final"])),
        },
        "get_routes": {
            "fixed": list(GET_ROUTES),
            "retired": data["retired"],
            "candidate": data["candidate"],
            "prepare": data["prepare"],
            "final": data["final"],
        },
        "post_routes": list(POST_ROUTES),
        "shared_assets_verified": data["shared"],
        "installed": False,
        "published": False,
    }


def prepare_config(*, fullconfig: object, current_manifest: object,
                   candidate_manifest: object, relay_port: int) -> dict:
    data = _transition(fullconfig=fullconfig, current_manifest=current_manifest,
                       candidate_manifest=candidate_manifest, relay_port=relay_port)
    return _rebuild(fullconfig, data["position"], data["prepare"])


def final_config(*, fullconfig: object, current_manifest: object,
                 candidate_manifest: object, relay_port: int) -> dict:
    data = _transition(fullconfig=fullconfig, current_manifest=current_manifest,
                       candidate_manifest=candidate_manifest, relay_port=relay_port)
    return _rebuild(fullconfig, data["position"], data["final"])


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
