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

def test_explicit_ceo_choice_is_bound_to_original_authenticated_arguments(rsa_key):
    arguments = {**ARGS, "frontier_model_alias": "frontier.orchestrator"}
    result = run(rsa_key, {"bearer": token(rsa_key), "request_body": json.dumps({"arguments": arguments})})
    original = run(rsa_key, {"bearer": token(rsa_key), "request_body": json.dumps({"arguments": ARGS})})
    assert result["arguments_digest"] == hashlib.sha256(json.dumps(
        arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    assert result["arguments_digest"] != original["arguments_digest"]
    assert "frontier_selection" not in result
    assert "attempt_limit" not in arguments


@pytest.mark.parametrize("alias", ["Frontier.Orchestrator", "", " frontier.orchestrator", None, 123])
def test_invalid_ceo_choice_refuses_at_commission_authentication(rsa_key, alias):
    with pytest.raises(Exception):
        run(rsa_key, {"bearer": token(rsa_key), "request_body": json.dumps({
            "arguments": {**ARGS, "frontier_model_alias": alias},
        })})


def test_signed_principal_prepares_only_its_exact_multiworkstream_templates(rsa_key):
    """Real signed App auth -> actual Node preparer, with no source mutations."""
    import copy
    import subprocess
    from pathlib import Path
    from tests.test_os_multiworkstream_launch import grants_for
    from ops.executive_os import os_gateway_publication as compiler

    root = Path(__file__).resolve().parents[1]
    _, _, scope = setup(rsa_key)
    grants = grants_for()
    for grant in grants:
        grant["principal_scope"] = scope
    compiler._grants({"grants": grants})
    cases = [{"arguments": {**grant["template"], "objective": "Read the completion frontier."},
              "grants": copy.deepcopy(grants), "expected": "prepared"} for grant in grants]
    ccr = cases[2]["arguments"]
    cases.extend([
        {"arguments": {**ccr, "execution_profile": "native_research_only"},
         "grants": copy.deepcopy(grants), "expected": "refused"},
        {"arguments": {**ccr, "department": "foreign-project"},
         "grants": copy.deepcopy(grants), "expected": "refused"},
        {"arguments": dict(ccr), "grants": copy.deepcopy(grants), "expected": "refused",
         "reuse_ecosystem_key": True},
        {"arguments": dict(ccr), "grants": [
            {**grant, "principal_scope": "2" * 64} for grant in grants], "expected": "refused"},
    ])
    distinct = copy.deepcopy(grants)
    for grant in distinct:
        grant["template"]["department"] = (
            "ecosystem-project" if grant["template"]["workstream"] == grants[0]["template"]["workstream"]
            else "office-project")
    compiler._grants({"grants": distinct})
    cases.append({"arguments": {**ccr, "department": "ecosystem-project"},
                  "grants": distinct, "expected": "refused"})
    key_script = """
import { operationKeyForCommission } from './integrations/studio_direct_mcp/commission-prepare.mjs';
let raw = ''; for await (const chunk of process.stdin) raw += chunk;
const value = JSON.parse(raw);
process.stdout.write(JSON.stringify(value.cases.map(row =>
  operationKeyForCommission(row.arguments, value.scope))));
"""
    keys = json.loads(subprocess.check_output(
        ["node", "--input-type=module", "-e", key_script],
        input=json.dumps({"scope": scope, "cases": cases}).encode(), cwd=root))
    assert keys[0] != keys[2]
    for index, case in enumerate(cases):
        case["arguments"]["operation_key"] = keys[0] if case.get("reuse_ecosystem_key") else keys[index]
        case["authenticated"] = run(rsa_key, {"bearer": token(rsa_key),
            "request_body": json.dumps({"arguments": case["arguments"]})})
        assert case["authenticated"]["identity"]["principal_scope"] == scope
    prepare_script = """
import { createHash } from 'node:crypto';
import { createCommissionPreparer, commissionBytes } from './integrations/studio_direct_mcp/commission-prepare.mjs';
let raw = ''; for await (const chunk of process.stdin) raw += chunk;
const cases = JSON.parse(raw), outcomes = [], head = 'a'.repeat(40);
for (const row of cases) {
  let inspected = 0;
  const args = row.arguments, identity = row.authenticated.identity;
  const forbidden = async () => { throw Error('unexpected source mutation'); };
  const workspace = {
    inspect: async () => { inspected++; return {status:'PRESENT'}; },
    acquire: forbidden, commitCommission: forbidden, push: forbidden,
    commissionStatus: async () => ({
      operation_id: args.operation_key, branch: 'sol/web-' + args.operation_key,
      clean: true, local_head_sha: head, remote_head_sha: head,
      commission_content_sha256: createHash('sha256').update(
        commissionBytes(args, identity.principal_scope)).digest('hex'),
    }),
  };
  const prepare = createCommissionPreparer({
    workspace, files: {write: forbidden}, authenticate: async () => row.authenticated,
    baseSha: head, policyDigest: identity.policy_digest, grants: row.grants,
  }).prepare;
  const outcome = await prepare(args, 'inert-test-bearer-not-a-credential');
  outcomes.push({status: outcome.status, inspected});
}
process.stdout.write(JSON.stringify(outcomes));
"""
    outcomes = json.loads(subprocess.check_output(
        ["node", "--input-type=module", "-e", prepare_script],
        input=json.dumps(cases).encode(), cwd=root))
    assert outcomes == [{"status": case["expected"],
                         "inspected": 1 if case["expected"] == "prepared" else 0} for case in cases]
