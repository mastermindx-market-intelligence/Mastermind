"""Macro-scale Source Continuity profile regressions; no real HTTP or token."""
from __future__ import annotations

import pytest

import test_source_continuity as fx
import test_source_continuity_census_budget as budget


def _apply_frozen_profile(module) -> None:
    module._MAX_COLLISION_PRS = 300
    module._MAX_HTTP_CALLS = 768
    module._MAX_HTTP_NORMALIZED_BYTES = 64 * 1024 * 1024
    module._HTTP_READ_BUDGET_SECONDS = 240.0


def _foreign_file_calls(http) -> list[str]:
    return [
        url
        for url, _, _ in http.calls
        if "/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
    ]


def test_macro_300_profile_is_exact() -> None:
    module = fx._cli_module()
    assert module._MAX_COLLISION_PRS == 300
    assert module._MAX_HTTP_CALLS == 768
    assert module._MAX_HTTP_NORMALIZED_BYTES == 64 * 1024 * 1024
    assert module._HTTP_READ_BUDGET_SECONDS == 240.0
    assert module._MAX_HTTP_BODY_BYTES == 5_000_000


@pytest.mark.parametrize("count", [274, 300])
def test_macro_scale_estate_completes(count, capsys, monkeypatch) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock(), raising=False)
    http = budget.EstateHTTP(count)
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 0, payload
    assert payload["authority_effect"] == "NONE"
    assert payload["merge_authorized"] is False
    assert payload["writer_release_authorized"] is False
    assert payload["collision_state"] == "DISJOINT"
    assert http.passes == 2
    assert len(http.calls) <= 768


def test_macro_301_refuses_before_foreign_file_enumeration(
    capsys, monkeypatch
) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock(), raising=False)
    http = budget.EstateHTTP(301)
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert _foreign_file_calls(http) == []


def test_macro_300_call_budget_exact_and_one_under(
    capsys, monkeypatch
) -> None:
    control_module = fx._cli_module()
    _apply_frozen_profile(control_module)
    monkeypatch.setattr(control_module, "monotonic", budget.Clock())
    control = budget.EstateHTTP(300)
    assert budget.run_cli(control_module, capsys, control)[0] == 0
    required_calls = len(control.calls)
    assert required_calls < 768

    exact_module = fx._cli_module()
    _apply_frozen_profile(exact_module)
    exact_module._MAX_HTTP_CALLS = required_calls
    monkeypatch.setattr(exact_module, "monotonic", budget.Clock())
    assert budget.run_cli(exact_module, capsys, budget.EstateHTTP(300))[0] == 0

    under_module = fx._cli_module()
    _apply_frozen_profile(under_module)
    under_module._MAX_HTTP_CALLS = required_calls - 1
    monkeypatch.setattr(under_module, "monotonic", budget.Clock())
    rc, payload = budget.run_cli(under_module, capsys, budget.EstateHTTP(300))
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


def test_macro_300_byte_budget_exact_and_one_under(
    capsys, monkeypatch
) -> None:
    control_module = fx._cli_module()
    _apply_frozen_profile(control_module)
    monkeypatch.setattr(control_module, "monotonic", budget.Clock())
    sizes: list[int] = []
    control = budget.EstateHTTP(300)
    control.after_read = lambda _url, result: sizes.append(
        len(control_module.canonical_json(result).encode("utf-8", "backslashreplace"))
    )
    assert budget.run_cli(control_module, capsys, control)[0] == 0
    required_bytes = sum(sizes)
    assert required_bytes < 64 * 1024 * 1024

    exact_module = fx._cli_module()
    _apply_frozen_profile(exact_module)
    exact_module._MAX_HTTP_NORMALIZED_BYTES = required_bytes
    monkeypatch.setattr(exact_module, "monotonic", budget.Clock())
    assert budget.run_cli(exact_module, capsys, budget.EstateHTTP(300))[0] == 0

    under_module = fx._cli_module()
    _apply_frozen_profile(under_module)
    under_module._MAX_HTTP_NORMALIZED_BYTES = required_bytes - 1
    monkeypatch.setattr(under_module, "monotonic", budget.Clock())
    rc, payload = budget.run_cli(under_module, capsys, budget.EstateHTTP(300))
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


def test_time_budget_accepts_last_finite_instant_and_refuses_deadline(
    capsys, monkeypatch
) -> None:
    success_module = fx._cli_module()
    _apply_frozen_profile(success_module)
    success_clock = budget.Clock()
    monkeypatch.setattr(success_module, "monotonic", success_clock)
    success_http = budget.EstateHTTP(1)
    success_http.after_read = lambda _url, _result: setattr(
        success_clock, "now", 239.999
    )
    assert budget.run_cli(success_module, capsys, success_http)[0] == 0

    deadline_module = fx._cli_module()
    _apply_frozen_profile(deadline_module)
    deadline_clock = budget.Clock()
    monkeypatch.setattr(deadline_module, "monotonic", deadline_clock)
    deadline_http = budget.EstateHTTP(1)
    deadline_http.after_read = lambda _url, _result: setattr(
        deadline_clock, "now", 240.0
    )
    rc, payload = budget.run_cli(deadline_module, capsys, deadline_http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
