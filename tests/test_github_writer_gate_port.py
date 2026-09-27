from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest

from integrations.mastermind_github_app.github_port import HttpResponse
from integrations.mastermind_github_app.models import AuthenticatedPrincipal
from integrations.mastermind_github_app.writer_gate_port import (
    GithubWriterGatePort, WriterGateServiceRefused, WriterGateTarget,
    WRITER_GATE_SCOPE, WRITER_GATE_TOOL_SPEC,
)


class Owner:
    def __init__(self):
        self.now = 1700000000
        self.principal = AuthenticatedPrincipal("a" * 64, (WRITER_GATE_SCOPE,))
        self.target = WriterGateTarget("operation:test", "example/repository", "sol/example",
            "b" * 40, 987654, "generation:one", self.now + 60)
        self.token_calls = 0
        self.calls = []
        self.status = 200
        self.variant = "normal"

    async def current_principal(self):
        return self.principal

    async def resolve_writer_gate_target(self, operation_key, principal_digest):
        assert operation_key == "operation:test"
        assert principal_digest == self.principal.principal_digest
        return self.target

    async def installation_token(self):
        self.token_calls += 1
        return "synthetic-service-value"

    def read(self, method, url, headers, body, timeout_seconds):
        self.calls.append((method, url, body))
        assert method == "GET" and body is None
        assert headers["Authorization"] == "Bearer synthetic-service-value"
        if self.status != 200:
            return HttpResponse(self.status, {}, b'{"message":"private-upstream-detail"}')
        if url.endswith("/protection"):
            return HttpResponse(200 if self.variant == "classic" else 404, {}, b"{}")
        if "/rules/branches/" in url:
            types = ["update", "deletion", "non_fast_forward"]
            if self.variant == "unknown_rule":
                types += ["future_rule"]
            payload = [{"type": t, "ruleset_id": 1234, "ruleset_source_type": "Repository"} for t in types]
        elif "/rulesets/" in url:
            payload = {"id": 1234, "source_type": "Repository", "enforcement": "active",
                "bypass_actors": [{"actor_type": "Integration", "actor_id": 987654, "bypass_mode": "always"}]}
            if self.variant == "widened":
                payload["bypass_actors"].append({"actor_type": "Integration", "actor_id": 54321, "bypass_mode": "always"})
        else:
            head = "b" * 40
            if self.variant == "drift" and len(self.calls) > 4:
                head = "c" * 40
            payload = {"commit": {"sha": head}, "protected": True}
        if self.variant == "expire":
            self.now += 61
        if self.variant == "malformed":
            return HttpResponse(200, {}, b"not-json")
        return HttpResponse(200, {}, json.dumps(payload).encode())


def port(owner, *, enabled=True):
    return GithubWriterGatePort(principals=owner, authority=owner, token_provider=owner,
        clock=lambda: owner.now, read_transport=owner.read, production_armed=enabled)


def call(subject):
    return asyncio.run(subject.observe_writer_gate("operation:test"))


def test_disarmed_default_never_reads_credential_or_network():
    owner = Owner()
    subject = GithubWriterGatePort(principals=owner, authority=owner, token_provider=owner,
        clock=lambda: owner.now, read_transport=owner.read)
    with pytest.raises(WriterGateServiceRefused, match="PRODUCTION_DISARMED"):
        call(subject)
    assert owner.token_calls == 0 and owner.calls == []


def test_owner_bound_gets_produce_original_canonical_receipt():
    owner = Owner()
    result = call(port(owner))
    assert result["schema"] == "mastermind.source_continuity_writer_gate/v1"
    assert result["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert result["branch_head_sha"] == owner.target.expected_head_sha
    assert result["merge_authorized"] is False and result["authority_effect"] == "NONE"
    assert owner.token_calls == 1 and len(owner.calls) == 8
    assert "synthetic-service-value" not in json.dumps(result)


@pytest.mark.parametrize("status,code", [(401,"GITHUB_AUTH_UNAVAILABLE"), (403,"GITHUB_PERMISSION_DENIED"),
    (429,"GITHUB_RATE_LIMITED"), (302,"GITHUB_REDIRECT_REFUSED"), (500,"GITHUB_READ_FAILED")])
def test_upstream_failure_stays_typed_without_payload_or_retry(status, code):
    owner = Owner()
    owner.status = status
    with pytest.raises(WriterGateServiceRefused, match=code) as error:
        call(port(owner))
    assert len(owner.calls) == 1
    assert "private-upstream-detail" not in str(error.value)
    assert "synthetic-service-value" not in str(error.value)


@pytest.mark.parametrize("variant,defect", [("classic","LEGACY_PROTECTION_PRESENT"),
    ("unknown_rule","UNKNOWN_APPLICABLE_RULE"), ("widened","BYPASS_WIDENED")])
def test_source_continuity_not_adapter_owns_gate_classification(variant, defect):
    owner = Owner()
    owner.variant = variant
    result = call(port(owner))
    assert result["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert defect in result["defects"]
    assert result["merge_authorized"] is False


@pytest.mark.parametrize("variant,code", [("drift","GITHUB_SOURCE_MOVED"),
    ("expire","AUTHORITY_EXPIRED"), ("malformed","GITHUB_READ_FAILED")])
def test_changed_or_incomplete_evidence_never_becomes_a_receipt(variant, code):
    owner = Owner()
    owner.variant = variant
    with pytest.raises(WriterGateServiceRefused, match=code):
        call(port(owner))


def test_missing_read_scope_refuses_before_credential_use():
    owner = Owner()
    owner.principal = dataclasses.replace(owner.principal, scopes=("mastermind.github.exact_branch_repair",))
    with pytest.raises(WriterGateServiceRefused, match="SCOPE_REFUSED"):
        call(port(owner))
    assert owner.token_calls == 0 and owner.calls == []


def test_expected_head_is_owned_and_cannot_be_silently_retargeted():
    owner = Owner()
    owner.target = dataclasses.replace(owner.target, expected_head_sha="f" * 40)
    with pytest.raises(WriterGateServiceRefused, match="GITHUB_SOURCE_MOVED"):
        call(port(owner))


def test_model_schema_has_no_repository_endpoint_credential_or_mutation_input():
    schema = WRITER_GATE_TOOL_SPEC["inputSchema"]
    assert set(schema["properties"]) == {"operation_key"}
    assert schema["additionalProperties"] is False
    assert WRITER_GATE_TOOL_SPEC["annotations"]["readOnlyHint"] is True
    owner = Owner()
    with pytest.raises(TypeError):
        asyncio.run(port(owner).observe_writer_gate("operation:test", repository="foreign/repo"))
    assert owner.token_calls == 0 and owner.calls == []


@pytest.mark.parametrize("change", ["generation", "principal", "scope", "expires"])
def test_authority_change_during_token_acquisition_refuses_before_http(change):
    owner = Owner()
    original_token = owner.installation_token
    async def changed_token():
        token = await original_token()
        if change == "generation":
            owner.target = dataclasses.replace(owner.target, authority_generation="generation:two")
        elif change == "principal":
            owner.principal = dataclasses.replace(owner.principal, principal_digest="d" * 64)
        elif change == "scope":
            owner.principal = dataclasses.replace(owner.principal, scopes=())
        else:
            owner.now += 60
        return token
    owner.installation_token = changed_token
    with pytest.raises(WriterGateServiceRefused, match="AUTHORITY_CHANGED|SCOPE_REFUSED|AUTHORITY_EXPIRED"):
        call(port(owner))
    assert owner.calls == []


def test_authority_change_during_http_refuses_result_without_remapping():
    owner = Owner()
    original_read = owner.read
    def changed_read(*args):
        response = original_read(*args)
        owner.target = dataclasses.replace(owner.target, branch="sol/replacement")
        return response
    owner.read = changed_read
    with pytest.raises(WriterGateServiceRefused, match="AUTHORITY_CHANGED"):
        call(port(owner))
    assert all("replacement" not in url for _, url, _ in owner.calls)


def test_expiry_during_first_http_read_prevents_further_reads():
    owner = Owner()
    owner.variant = "expire"
    with pytest.raises(WriterGateServiceRefused, match="AUTHORITY_EXPIRED"):
        call(port(owner))
    assert len(owner.calls) == 1


@pytest.mark.parametrize("link_header", ["Link", "link"])
def test_paginated_partial_rule_response_never_claims_complete_receipt(link_header):
    owner = Owner()
    original_read = owner.read
    def incomplete_read(*args):
        response = original_read(*args)
        if "/rules/branches/" in args[1]:
            return dataclasses.replace(response, headers={link_header:
                '<https://api.github.com/repos/example/repository/rules/branches/sol%2Fexample?page=2>; rel="next"'})
        return response
    owner.read = incomplete_read
    with pytest.raises(WriterGateServiceRefused, match="GITHUB_CENSUS_INCOMPLETE"):
        call(port(owner))


@pytest.mark.parametrize("url", ["https://example.invalid/steal", "https://api.github.com/repos/foreign/repo/branches/main",
    "https://api.github.com/repos/example/repository/rulesets/1234?other=yes",
    "https://api.github.com/repos/example/repository/rulesets/../branches/main"])
def test_closed_transport_refuses_non_owner_endpoint_before_http(url):
    owner = Owner()
    with pytest.raises(WriterGateServiceRefused, match="GITHUB_READ_FAILED"):
        port(owner)._get(owner.target, url, "synthetic-service-value", 1)
    assert owner.calls == []


@pytest.mark.parametrize("body", [b'{"commit":{},"commit":{}}', b'{"value":NaN}', b'\xff'])
def test_malformed_json_stays_closed_without_a_receipt(body):
    owner = Owner()
    owner.read = lambda *_args: HttpResponse(200, {}, body)
    with pytest.raises(WriterGateServiceRefused, match="GITHUB_READ_FAILED"):
        call(port(owner))


def test_repository_and_operation_binding_are_validated_before_token():
    owner = Owner()
    owner.target = dataclasses.replace(owner.target, operation_key="operation:foreign")
    with pytest.raises(WriterGateServiceRefused, match="TARGET_UNRESOLVED"):
        call(port(owner))
    assert owner.token_calls == 0
