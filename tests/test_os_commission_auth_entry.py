import asyncio
import dataclasses
import hashlib
import json

import pytest

from ops.executive_os.os_commission_auth_entry import authenticate_document
from test_os_publication_auth import composition, token, fixture, rsa_key

ARGS = {"operation_key": "mmos-launch-" + "a" * 40, "objective": "Read the current contract.",
        "department": "executive-infrastructure", "priority": 5, "execution_profile": "research_only",
        "workstream": "WS:NOIR"}


def setup(key):
    _, auth, _, sink, scope = composition(key)
    config = {"policy": json.loads(json.dumps(dataclasses.asdict(auth.policy))), "grants": [{"principal_scope": scope}]}
    return config, sink, scope


def run(key, request):
    config, sink, _ = setup(key)
    return asyncio.run(authenticate_document(json.dumps(request).encode(), config, audit_sink=sink,
        clock=lambda: fixture.NOW, jwks_cache=fixture._FakeJwksCache(key)))


def test_signed_bearer_only_projection_has_no_brief_or_bearer(rsa_key):
    bearer = token(rsa_key)
    result = run(rsa_key, {"bearer": bearer})
    assert set(result) == {"ok", "identity"}
    assert result["ok"] is True
    assert bearer not in repr(result)


def test_validated_arguments_digest_binds_the_exact_body(rsa_key):
    result = run(rsa_key, {"bearer": token(rsa_key), "request_body": json.dumps({"arguments": ARGS})})
    assert result["arguments_digest"] == hashlib.sha256(json.dumps(
        ARGS, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    assert ARGS["objective"] not in repr(result)


@pytest.mark.parametrize("body", [
    '{"arguments":{},"arguments":{}}',
    '{"arguments":{"operation_key":"a","operation_key":"b"}}',
    '{"arguments":{},"branch":"master"}',
    '{"arguments":{"operation_key":"a","objective":NaN}}',
])
def test_raw_body_duplicates_and_nonfinite_are_not_normalized_away(rsa_key, body):
    with pytest.raises(Exception):
        run(rsa_key, {"bearer": token(rsa_key), "request_body": body})


def test_body_never_supplies_principal_projection(rsa_key):
    with pytest.raises(ValueError):
        run(rsa_key, {"bearer": token(rsa_key), "principal_scope": "a" * 64})


@pytest.mark.parametrize("objective", ["Read the current contract.", "Read 🚀 café and \u2028 text."])
def test_signed_auth_policy_and_original_wire_digest_match_actual_node_composer(rsa_key, objective):
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    config, _, _ = setup(rsa_key)
    arguments = {**ARGS, "objective": objective}
    result = run(rsa_key, {"bearer": token(rsa_key), "request_body": json.dumps({"arguments": arguments})})
    script = """
import { createHash } from 'node:crypto';
import { canonicalJson } from './integrations/studio_direct_mcp/commission-prepare.mjs';
let raw = '';
for await (const chunk of process.stdin) raw += chunk;
const value = JSON.parse(raw);
const digest = (v) => createHash('sha256').update(canonicalJson(v)).digest('hex');
process.stdout.write(JSON.stringify({policy:digest(value.policy), arguments:digest(value.arguments)}));
"""
    observed = json.loads(subprocess.check_output(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps({"policy": config["policy"], "arguments": arguments}).encode(), cwd=root))
    assert result["identity"]["policy_digest"] == observed["policy"]
    assert result["arguments_digest"] == observed["arguments"]
    assert "attempt_limit" not in arguments  # schema normalization must not rekey the form


@pytest.mark.parametrize("mutation", ["omitted-default", "unsorted-scopes"])
def test_noncanonical_policy_is_refused_explicitly_instead_of_silent_digest_drift(rsa_key, mutation):
    config, sink, _ = setup(rsa_key)
    if mutation == "omitted-default":
        config["policy"].pop("clock_skew_seconds")
    else:
        config["policy"]["required_scopes"].reverse()
    from integrations.business_mcp_auth.contracts import AuthError
    with pytest.raises((AuthError, ValueError)):
        asyncio.run(authenticate_document(json.dumps({"bearer": token(rsa_key)}).encode(),
            config, audit_sink=sink, clock=lambda: fixture.NOW, jwks_cache=fixture._FakeJwksCache(rsa_key)))
