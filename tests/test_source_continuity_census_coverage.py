"""Collision coverage containment through the actual CLI; no real HTTP or token.

A full REST page is not an enumeration certificate. This deliberately retains
the single-response capability while refusing unqualified large-estate proof.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

import test_source_continuity as fx
import test_source_continuity_census_budget as budget
import test_source_continuity_macro_scale as scale


def _transport(module, mode, count, **kwargs):
    if mode == "legacy":
        return budget.EstateHTTP(count, **kwargs)
    return scale.ConditionalEstateHTTP(
        module, count,
        identityless={1000} if mode == "identityless" else (),
        **kwargs,
    )


def _roster_calls(http):
    return [url for url, _, _ in http.calls if urlparse(url).path.endswith("/pulls")]


def _assert_one_response_per_observation(http, observations):
    calls = _roster_calls(http)
    assert len(calls) == observations
    assert all(parse_qs(urlparse(url).query) == {
        "state": ["open"], "sort": ["created"], "direction": ["asc"],
        "per_page": ["100"], "page": ["1"],
    } for url in calls)


@pytest.mark.parametrize("mode", ["conditional", "identityless", "legacy"])
@pytest.mark.parametrize("kind", ["checkpoint", "remote-complete"])
@pytest.mark.parametrize("count", [99, 100, 101, 920, 1500])
def test_cli_requires_qualified_roster_coverage(mode, kind, count, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = _transport(module, mode, count)
    runner = fx._ProbeRunner()

    rc, payload = budget.run_cli(module, capsys, http, kind=kind, runner=runner)

    if count < 100:
        assert rc == 0, payload
        assert payload["collision_state"] == "DISJOINT"
        assert payload["authority_effect"] == "NONE"
        assert payload["merge_authorized"] is False
        assert payload["writer_release_authorized"] is False
        assert payload["receiver_transfer_authorized"] is False
        _assert_one_response_per_observation(http, 2)
    else:
        assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
        assert payload["schema"] == "mastermind.source_continuity_refusal/v1"
        assert runner.calls == []
        assert scale._foreign_file_calls(http) == []
        _assert_one_response_per_observation(http, 1)


@pytest.mark.parametrize("mode", ["conditional", "identityless", "legacy"])
@pytest.mark.parametrize("kind", ["checkpoint", "remote-complete"])
@pytest.mark.parametrize("first_count", [2, 99])
def test_complete_first_observation_cannot_hide_incomplete_second(
    mode, kind, first_count, capsys, monkeypatch
):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = _transport(module, mode, first_count, opened_between=100-first_count)

    rc, payload = budget.run_cli(module, capsys, http, kind=kind)

    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert payload["schema"] == "mastermind.source_continuity_refusal/v1"
    _assert_one_response_per_observation(http, 2)
    # No new identity or file read can turn the incomplete second roster into
    # accepted coverage, including the identityless and legacy fallbacks.
    assert len(scale._foreign_file_calls(http)) == first_count - 1


@pytest.mark.parametrize("count", [2, 100])
@pytest.mark.parametrize("defect", ["duplicate", "not-object", "bool", "closed"])
def test_malformed_first_page_remains_a_probe_failure(count, defect, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = budget.EstateHTTP(count)

    def corrupt(url, payload):
        if not urlparse(url).path.endswith("/pulls"):
            return
        if defect == "duplicate":
            payload[-1] = dict(payload[0])
        elif defect == "not-object":
            payload[-1] = "invalid"
        elif defect == "bool":
            payload[-1]["number"] = True
        else:
            payload[-1]["state"] = "closed"

    http.after_read = corrupt
    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"
    assert scale._foreign_file_calls(http) == []
    _assert_one_response_per_observation(http, 1)


def test_short_page_keeps_single_observation_without_a_tail_union(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = scale.ConditionalEstateHTTP(module, 2)
    # A historical tail query could report a different, later population. It
    # must never be unioned with the first response as one "complete" census.
    tail_calls = []
    original = http.__class__.__call__

    class ChangingTail(type(http)):
        def __call__(self, url, **kwargs):
            if parse_qs(urlparse(url).query).get("direction") == ["desc"]:
                tail_calls.append(url)
            return original(self, url, **kwargs)

    http.__class__ = ChangingTail
    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 0 and payload["collision_state"] == "DISJOINT"
    assert tail_calls == []
    _assert_one_response_per_observation(http, 2)
