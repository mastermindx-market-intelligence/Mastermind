"""Complete owner-bound rule census. All upstream responses are synthetic."""
from __future__ import annotations

import dataclasses
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import source_continuity as source
from control_plane.source_continuity import SourceContinuityRefusal, WriterGateRequest
from integrations.mastermind_github_app.github_port import HttpResponse
from integrations.mastermind_github_app.writer_gate_port import WriterGateServiceRefused
from test_github_writer_gate_port import Owner, call, port


class PagedOwner(Owner):
    def __init__(self, *, second_rule="creation", links=False):
        super().__init__()
        self.second_rule = second_rule
        self.links = links
        self.page_reads = []
        self.variant = "normal"
        # 100 valid distinct rules: three gate rules plus 97 inert rulesets.
        self.first = [{"type": t, "ruleset_id": 1234, "ruleset_source_type": "Repository"}
                      for t in ("update", "deletion", "non_fast_forward")]
        self.first += [{"type": "branch_name_pattern", "ruleset_id": 2000+i,
                        "ruleset_source_type": "Repository"} for i in range(97)]

    def read(self, method, url, headers, body, timeout_seconds):
        if "/rules/branches/" in url:
            self.calls.append((method, url, body))
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            page = int(query.get("page", ["1"])[0])
            self.page_reads.append(page)
            payload = self.first if page == 1 else ([] if self.second_rule is None else [
                {"type": self.second_rule, "ruleset_id": 1234, "ruleset_source_type": "Repository"}])
            if self.variant == "drift" and self.page_reads.count(2) > 1:
                payload = []
            if self.variant == "endless":
                payload = self.first
            if self.variant == "expire_second" and page == 2:
                self.now += 61
            if self.variant == "fail_second" and page == 2:
                return HttpResponse(503, {}, b"{}")
            metadata = {}
            if self.links:
                root = url.split("?", 1)[0]
                if page == 1:
                    metadata["Link"] = f'<{root}?per_page=100&page=2>; rel="next", <{root}?per_page=100&page=2>; rel="last"'
                else:
                    metadata["Link"] = f'<{root}?page=1&per_page=100>; rel="prev", <{root}?per_page=100&page=1>; rel="first"'
            return HttpResponse(200, metadata, json.dumps(payload).encode())
        if "/rulesets/" in url:
            self.calls.append((method, url, body))
            return HttpResponse(200, {}, json.dumps({"id": int(url.rsplit("/", 1)[1]),
                "source_type": "Repository", "enforcement": "active", "bypass_actors": [
                    {"actor_type": "Integration", "actor_id": 987654, "bypass_mode": "always"}]}).encode())
        # This fixture changes page two only, never the branch-head control.
        variant = self.variant
        self.variant = "normal"
        try:
            return super().read(method, url, headers, body, timeout_seconds)
        finally:
            self.variant = variant


def test_canonical_collector_includes_restriction_on_second_page():
    owner = PagedOwner()
    def get(url, *, token, timeout):
        response = owner.read("GET", url, {"Authorization": "Bearer " + token}, None, timeout)
        if response.status == 404:
            raise source._RemoteResourceMissing()
        return json.loads(response.body)
    request = WriterGateRequest(owner.target.operation_key, owner.target.repository,
        owner.target.branch, owner.target.accepted_integration_id, "2023-11-14T22:13:20Z")
    facts = source._probe_writer_gate_facts(source._BoundedHTTPGet(get), "synthetic-service-value", request)
    assert not isinstance(facts, SourceContinuityRefusal)
    assert len(facts.branch_rules) == 101
    assert facts.branch_rules[-1].rule_type == "creation"
    assert owner.page_reads == [1, 2]


@pytest.mark.parametrize("links", [False, True])
def test_service_cannot_hide_second_page_writer_restriction(links):
    owner = PagedOwner(links=links)
    result = call(port(owner))
    assert result["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert "creation" in result["rule_types"]
    assert owner.page_reads == [1, 2, 1, 2]
    assert all("per_page=100" in url for _, url, _ in owner.calls if "/rules/branches/" in url)


@pytest.mark.parametrize("links", [False, True])
def test_exact_full_page_requires_empty_terminal_page(links):
    owner = PagedOwner(second_rule=None, links=links)
    assert call(port(owner))["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert owner.page_reads == [1, 2, 1, 2]


@pytest.mark.parametrize("variant,code", [("drift", "GITHUB_SOURCE_MOVED"),
    ("expire_second", "AUTHORITY_EXPIRED"), ("fail_second", "GITHUB_READ_FAILED")])
def test_second_page_failure_or_drift_never_returns_receipt(variant, code):
    owner = PagedOwner()
    owner.variant = variant
    with pytest.raises(WriterGateServiceRefused, match=code):
        call(port(owner))
    if variant == "expire_second":
        assert "/rules/branches/" in owner.calls[-1][1] and owner.page_reads[-1] == 2


def test_page_budget_exhaustion_is_incomplete_not_partial_gate(monkeypatch):
    monkeypatch.setattr(source, "_MAX_PAGES", 2)
    owner = PagedOwner()
    owner.variant = "endless"
    result = call(port(owner))
    assert result["schema"] != "mastermind.source_continuity_writer_gate/v1"
    assert result["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert owner.page_reads == [1, 2]


def test_foreign_pagination_link_is_not_followed():
    owner = PagedOwner(links=True)
    original = owner.read
    def changed(*args):
        response = original(*args)
        if "/rules/branches/" in args[1]:
            return dataclasses.replace(response, headers={"Link": '<https://example.invalid/collect>; rel="next"'})
        return response
    owner.read = changed
    with pytest.raises(WriterGateServiceRefused, match="GITHUB_CENSUS_INCOMPLETE"):
        call(port(owner))
    assert all(url.startswith("https://api.github.com/") for _, url, _ in owner.calls)


@pytest.mark.parametrize("suffix", ["?per_page=100&page=0", "?per_page=100&page=11",
    "?per_page=30&page=2", "?page=2&per_page=100", "?per_page=100&page=02",
    "?per_page=100&page=2&extra=x", "?per_page=100&page=2#fragment"])
def test_only_canonical_bounded_request_urls_reach_transport(suffix):
    owner = PagedOwner()
    url = "https://api.github.com/repos/example/repository/rules/branches/sol%2Fexample" + suffix
    with pytest.raises(WriterGateServiceRefused, match="GITHUB_READ_FAILED"):
        port(owner)._get(owner.target, url, "synthetic-service-value", 1)
    assert owner.calls == []


@pytest.mark.parametrize("link", [
    '<https://api.github.com/repos/foreign/repository/rules/branches/sol%2Fexample?per_page=100&page=2>; rel="next"',
    '<https://api.github.com/repos/example/repository/rules/branches/sol%2Fexample?per_page=100&page=3>; rel="next"',
    '<https://api.github.com/repos/example/repository/rules/branches/sol%2Fexample?per_page=100&page=2&page=3>; rel="next"',
    '<https://api.github.com/repos/example/repository/rules/branches/sol%2Fexample?per_page=100&page=2>; rel="arbitrary"',
    'malformed-pagination',
])
def test_inconsistent_link_never_changes_the_owner_request_path(link):
    owner = PagedOwner()
    original = owner.read
    def changed(*args):
        response = original(*args)
        if "/rules/branches/" in args[1]:
            return dataclasses.replace(response, headers={"Link": link})
        return response
    owner.read = changed
    with pytest.raises(WriterGateServiceRefused, match="GITHUB_CENSUS_INCOMPLETE"):
        call(port(owner))
    assert owner.page_reads == [1]


def test_oversized_page_refuses_without_a_partial_gate():
    owner = PagedOwner()
    owner.first.append({"type": "creation", "ruleset_id": 1234, "ruleset_source_type": "Repository"})
    with pytest.raises(WriterGateServiceRefused, match="GITHUB_CENSUS_INCOMPLETE"):
        call(port(owner))
    assert owner.page_reads == [1]


def test_per_page_budget_is_fixed_to_github_maximum():
    assert source._PAGE_SIZE == 100
    assert source._branch_rules_endpoint("example/repository", "sol/example", 2).endswith("?per_page=100&page=2")
