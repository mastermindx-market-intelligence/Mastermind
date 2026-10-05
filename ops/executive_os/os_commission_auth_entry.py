#!/usr/bin/env python3
"""Sealed one-shot authentication helper for the incumbent Studio owner.

Fixed installation/configuration only. The original bearer enters on stdin,
never argv/environment, and only an authenticated digest projection leaves stdout.
The installed Studio component owns deadlines and child-process cleanup.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT = Path("/Library/Application Support/MastermindExecutive")
CONFIG = ROOT / "config/os-commission-publication.json"
MAX_INPUT = 196_608


def _sealed(path: Path, directory: bool = False) -> None:
    for current in (path, *path.parents):
        value = current.lstat()
        is_dir = directory or current != path
        if (value.st_uid != 0 or value.st_mode & 0o022 or stat.S_ISLNK(value.st_mode)
                or not (stat.S_ISDIR(value.st_mode) if is_dir else stat.S_ISREG(value.st_mode))
                or (not is_dir and value.st_nlink != 1)):
            raise ValueError("sealed source required")


async def authenticate_document(raw, config, *, audit_sink, clock, jwks_cache=None):
    """Testable composition; production configuration is loaded below, not stdin."""
    from integrations.business_mcp_auth.contracts import load_resource_policy
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
    from integrations.executive_mcp.schemas import validate_tool_arguments
    from integrations.mastermind_executive_app.gateway import _default_jwks_cache
    from integrations.mastermind_executive_app.os_publication_auth import OsPublicationAuthenticator
    from integrations.mastermind_executive_app.os_transport import _parse_body

    if type(raw) is not bytes or len(raw) > MAX_INPUT:
        raise ValueError("input budget")
    value = _parse_body(raw)
    if set(value) not in ({"bearer"}, {"bearer", "request_body"}):
        raise ValueError("closed authentication input required")
    policy = load_resource_policy(config["policy"])
    if config["policy"] != json.loads(json.dumps(dataclasses.asdict(policy))):
        raise ValueError("canonical complete publication policy required")
    auth = JwtAuthenticator(policy=policy, jwks_cache=jwks_cache or _default_jwks_cache(policy))
    verifier = MastermindTokenVerifier(authenticator=auth, policy=policy, now=clock, audit_sink=audit_sink)
    gate = OsPublicationAuthenticator(
        verifier=verifier, authenticator=auth,
        allowed_principal_scopes=tuple(sorted({grant["principal_scope"] for grant in config["grants"]})), clock=clock,
    )
    identity = await gate.authenticate(value["bearer"])
    result = {"ok": True, "identity": dataclasses.asdict(identity)}
    if "request_body" in value:
        if type(value["request_body"]) is not str or len(value["request_body"].encode("utf-8")) > 65_536:
            raise ValueError("request body budget")
        body = _parse_body(value["request_body"].encode("utf-8"))
        if set(body) != {"arguments"}:
            raise ValueError("closed request body required")
        validate_tool_arguments("submit_ceo_intent", body["arguments"])
        # Validate under the canonical law, but bind the original wire payload.
        # Normalization inserts defaults; the app key deliberately hashes its exact form.
        args = body["arguments"]
        result["arguments_digest"] = hashlib.sha256(json.dumps(
            args, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
    return result


def main() -> int:
    sink = None
    try:
        if len(sys.argv) != 1 or not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError("fixed invocation required")
        source = Path(__file__).parent.parent.parent
        _sealed(source, directory=True)
        _sealed(Path(__file__))
        _sealed(CONFIG)
        encoded = CONFIG.read_bytes()
        if len(encoded) > 65_536:
            raise ValueError("configuration budget")
        config = json.loads(encoded)
        if (type(config) is not dict
                or set(config) != {"schema", "release_sha", "studio_uid", "studio_account", "studio_port", "policy", "grants", "base_sha", "audit_directory", "auth_helper_sha256", "file_helper_sha256"}
                or config["schema"] != "mastermind.os_commission_publication.v1"
                or type(config["release_sha"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", config["release_sha"])
                or source != ROOT / "releases" / config["release_sha"]
                or type(config["studio_uid"]) is not int or config["studio_uid"] <= 0
                or os.getuid() != os.geteuid()
                or os.geteuid() != config["studio_uid"]
                or type(config["grants"]) is not list):
            raise ValueError("configuration refused")
        audit = ROOT / "audit/os-commission-publication"
        if config["audit_directory"] != str(audit):
            raise ValueError("audit directory refused")
        # Only after root-owned exact-release source qualification.
        sys.path.insert(0, str(source))
        from integrations.business_mcp_auth.audit import DurableAuthAuditSink
        from integrations.business_mcp_auth.contracts import load_resource_policy

        policy = load_resource_policy(config["policy"])
        descriptor = os.open(audit, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            sink = DurableAuthAuditSink.open(descriptor, policy_id=policy.policy_id)
        finally:
            os.close(descriptor)
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError("input budget")
        result = asyncio.run(authenticate_document(
            raw, config, audit_sink=sink, clock=lambda: int(time.time()),
        ))
        sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
        return 0
    except Exception:
        sys.stdout.write('{"ok":false,"code":"authentication_required"}\n')
        return 1
    finally:
        if sink is not None:
            sink.close()


if __name__ == "__main__":
    raise SystemExit(main())
