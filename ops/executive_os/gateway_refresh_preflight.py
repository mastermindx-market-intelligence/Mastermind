#!/usr/bin/env python3
"""Read-only qualification of one already-published Executive MCP generation.

This helper owns no publication or lifecycle effect. It composes the existing
installed-peer release/runtime closure and MCP config validators before
service-control may stop the running gateway.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

_ROOT = Path(__file__).resolve().parents[2]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane import executive_installed_peer as installed
from integrations.mastermind_executive_app.gateway import load_app_policies
from ops.executive_os.executive_mcp_entry import (
    build_additional_policies,
    validate_document,
)

_SHA = re.compile(r"[0-9a-f]{40}")

class GatewayRefreshPreflightError(RuntimeError):
    pass


def _refuse() -> None:
    raise GatewayRefreshPreflightError("gateway refresh preflight refused")


def _semantic_config(document: object, expected_sha: str) -> dict:
    if type(document) is not dict:
        _refuse()
    try:
        value = validate_document(copy.deepcopy(document))
        if value.get("release_sha") != expected_sha:
            _refuse()
        policies = load_app_policies(value["policies"])
        # Reuse the launcher's single canonical resource owner. It validates
        # connector tunnels, the optional OS Executive resource, collisions
        # with both primary resources, and every derived policy variant.
        build_additional_policies(value, policies)
    except GatewayRefreshPreflightError:
        raise
    except Exception:
        _refuse()
    return value


def _read_config(topology, budget, expected_sha: str):
    try:
        ancestors = installed._observe_ancestors(topology.config_path, budget)
        raw, info = installed._read_trusted_bytes(
            topology.config_path,
            budget=budget,
            maximum=4 * 1024 * 1024,
            expected_mode=topology.config_mode,
            expected_gid=topology.config_gid,
        )
        document = installed._load_strict_json(
            raw, code="SERVICE_CONFIG_MALFORMED"
        )
        _semantic_config(document, expected_sha)
        identity = installed._object_identity(info)
        current_ancestors = installed._observe_ancestors(
            topology.config_path, budget
        )
        if current_ancestors != ancestors:
            _refuse()
        return hashlib.sha256(raw).hexdigest(), identity, ancestors
    except GatewayRefreshPreflightError:
        raise
    except Exception:
        _refuse()


def qualify_gateway_refresh(expected_sha: str) -> dict[str, str]:
    if type(expected_sha) is not str or _SHA.fullmatch(expected_sha) is None:
        _refuse()
    try:
        topology = installed._role_topology("gateway")
        budget = installed._Budget(installed._SERVICE_BUDGET_SECONDS)

        plist = installed._verify_role_plist(
            topology, budget, expected_release=expected_sha
        )
        config_digest, config_identity, config_ancestors = _read_config(
            topology, budget, expected_sha
        )
        release = installed._verify_release(topology, expected_sha, budget)
        closure = installed._verify_network_closure(budget)

        # Recheck every filesystem identity after the expensive closure reads.
        current_plist = installed._verify_role_plist(
            topology, budget, expected_release=expected_sha
        )
        if current_plist != plist:
            _refuse()
        current_digest, current_identity, current_ancestors = _read_config(
            topology, budget, expected_sha
        )
        if (
            current_digest != config_digest
            or current_identity != config_identity
            or current_ancestors != config_ancestors
        ):
            _refuse()
        installed._recheck_release(release, budget)
        installed._recheck_network_closure(closure, budget)

        # Close the final TOCTOU window left by the expensive release/network
        # rechecks.  Match the incumbent installed-peer owner: the launchd
        # generation and the complete config leaf+ancestor identity must still
        # be exactly the generation qualified before any lifecycle effect.
        final_plist = installed._verify_role_plist(
            topology, budget, expected_release=expected_sha
        )
        if final_plist != plist:
            _refuse()
        final_digest, final_identity, final_ancestors = _read_config(
            topology, budget, expected_sha
        )
        if (
            final_digest != config_digest
            or final_identity != config_identity
            or final_ancestors != config_ancestors
        ):
            _refuse()
        # The final config read itself is non-atomic with the launchd plist.
        # Join the plist once more *after* that semantic read so publication
        # cannot replace the launch generation during config validation and
        # still receive a pre-effect PASS.
        final_plist_after_config = installed._verify_role_plist(
            topology, budget, expected_release=expected_sha
        )
        if final_plist_after_config != plist:
            _refuse()
    except GatewayRefreshPreflightError:
        raise
    except Exception:
        _refuse()
    return {
        "schema": "mastermind.gateway_refresh_preflight/v1",
        "release_sha": expected_sha,
        "config_sha256": config_digest,
        "release_manifest_sha256": release.manifest_digest,
        "network_closure_sha256": closure.aggregate,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--expected-sha", required=True)
    try:
        args = parser.parse_args(argv)
        result = qualify_gateway_refresh(args.expected_sha)
    except (GatewayRefreshPreflightError, SystemExit):
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": "GATEWAY_REFRESH_PREFLIGHT_REFUSED",
                },
                sort_keys=True,
            )
        )
        return 65
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
