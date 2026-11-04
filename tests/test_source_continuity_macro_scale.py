"""Retained Macro resource profile and truthful coverage limits; no real HTTP."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
from urllib.parse import urlparse

import pytest

import test_source_continuity as fx
import test_source_continuity_census_budget as budget


# Extra /files calls per non-saturated multi-page foreign PR (page-30 sentinel plus
# pages 2..n) observed in the live macro#7870 census of 2026-11-02 at 903 open PRs.
# The nine saturated PRs need compare/tree reads this fixture does not model.
LIVE_903_EXTRA_FILE_CALLS = (
    3, 2, 4, 3, 2, 2, 3, 2, 2, 2, 2, 2, 2, 23, 5, 3, 5, 3, 8, 2, 2,
    3, 2, 5, 5, 2, 8, 2, 2, 2, 2, 2, 4, 29, 3, 2, 5, 3, 3, 2, 2,
)


def _apply_frozen_profile(module) -> None:
    module._MAX_COLLISION_PRS = 1500
    module._MAX_ROSTER_PAGES = 16
    module._MAX_HTTP_CALLS = 4096
    module._MAX_HTTP_NORMALIZED_BYTES = 768 * 1024 * 1024
    module._HTTP_READ_BUDGET_SECONDS = 900.0


def _live_fanout_file_counts(copies: int) -> dict[int, int]:
    """A foreign PR with 100 * (e - 1) + 1 files costs exactly e extra /files calls."""
    extras = LIVE_903_EXTRA_FILE_CALLS * copies
    return {1000 + index: 100 * (extra - 1) + 1 for index, extra in enumerate(extras)}


def _foreign_file_calls(http) -> list[str]:
    return [
        url
        for url, _, _ in http.calls
        if "/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
    ]


class ConditionalEstateHTTP(budget.EstateHTTP):
    """The estate behind the production transport contract: ETags, 304s, workers.

    Roster rows carry the complete immutable identity GitHub returns, so the
    second observation takes the custody-aware reuse path instead of a full
    re-census. Numbers in ``identityless`` mimic a deleted fork (``head.repo``
    null), which has no identity and forces the full-re-census fallback.
    """

    _source_continuity_conditional = True
    _source_continuity_parallel_safe = True

    def __init__(self, module, count, *, identityless=(), **kwargs):
        super().__init__(count, **kwargs)
        self.module = module
        self.identityless = frozenset(identityless)
        self.conditional_calls: list[str] = []

    def _row(self, number):
        if number == fx.PR_NUMBER:
            head_sha, base_sha = fx.HEAD_SHA, fx.CURRENT_BASE_SHA
        else:
            head_sha, base_sha = f"{number:040x}", "d" * 40
        head_repo = None if number in self.identityless else {"full_name": fx.REPOSITORY}
        return {
            "number": number,
            "state": "open",
            "head": {"sha": head_sha, "repo": head_repo},
            "base": {"sha": base_sha, "repo": {"full_name": fx.REPOSITORY}},
        }

    def __call__(self, url, *, token, timeout, if_none_match=None):
        assert token == fx.TOKEN and timeout > 0
        if if_none_match is not None:
            self.conditional_calls.append(url)
            return self.module._HTTPRepresentation(
                payload=None,
                etag=if_none_match.removeprefix("W/"),
                not_modified=True,
            )
        payload = super().__call__(url, token=token, timeout=timeout)
        if urlparse(url).path.endswith("/pulls"):
            payload = [self._row(row["number"]) for row in payload]
        return self.module._HTTPRepresentation(
            payload=payload,
            etag='W/"' + hashlib.sha256(url.encode()).hexdigest() + '"',
            not_modified=False,
        )


def test_cli_bootstrap_does_not_write_repository_bytecode(tmp_path) -> None:
    checkout = tmp_path / "checkout"
    for relative in (
        "scripts/source_continuity.py",
        "control_plane/__init__.py",
        "control_plane/source_continuity.py",
    ):
        source = fx.ROOT / relative
        destination = checkout / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    env = os.environ.copy()
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    completed = subprocess.run(
        [sys.executable, str(checkout / "scripts/source_continuity.py"), "--help"],
        cwd=checkout,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert '"code":"INVALID_REQUEST"' in completed.stdout
    created = sorted(
        path.relative_to(checkout).as_posix() for path in checkout.rglob("*.pyc")
    )
    assert created == []


def test_macro_1500_profile_is_exact() -> None:
    module = fx._cli_module()
    assert module._MAX_COLLISION_PRS == 1500
    assert module._MAX_ROSTER_PAGES == 16
    assert module._MAX_HTTP_CALLS == 4096
    assert module._MAX_HTTP_NORMALIZED_BYTES == 768 * 1024 * 1024
    assert module._HTTP_READ_BUDGET_SECONDS == 900.0
    assert module._MAX_HTTP_BODY_BYTES == 5_000_000
    assert module._FOREIGN_PR_WORKERS == 4


@pytest.mark.parametrize("count", [274, 299, 300, 350, 384, 400, 409, 410, 419, 425, 450, 451, 457, 458, 465, 470, 475, 476, 477, 478, 479, 480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 600, 903, 907, 999, 1000, 1001, 1200, 1499, 1500])
def test_macro_scale_estate_refuses_unqualified_coverage(count, capsys, monkeypatch) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock(), raising=False)
    http = budget.EstateHTTP(count)
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert http.passes == 1
    assert _foreign_file_calls(http) == []
    assert len(_roster_calls(http)) == 1
    assert len(http.calls) < 4096


def test_macro_1501_refuses_before_foreign_file_enumeration(
    capsys, monkeypatch
) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock(), raising=False)
    http = budget.EstateHTTP(1501)
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert _foreign_file_calls(http) == []


def test_single_response_call_budget_exact_and_one_under(
    capsys, monkeypatch
) -> None:
    control_module = fx._cli_module()
    _apply_frozen_profile(control_module)
    monkeypatch.setattr(control_module, "monotonic", budget.Clock())
    control = budget.EstateHTTP(99)
    assert budget.run_cli(control_module, capsys, control)[0] == 0
    required_calls = len(control.calls)
    assert required_calls < 4096

    exact_module = fx._cli_module()
    _apply_frozen_profile(exact_module)
    exact_module._MAX_HTTP_CALLS = required_calls
    monkeypatch.setattr(exact_module, "monotonic", budget.Clock())
    assert budget.run_cli(exact_module, capsys, budget.EstateHTTP(99))[0] == 0

    under_module = fx._cli_module()
    _apply_frozen_profile(under_module)
    under_module._MAX_HTTP_CALLS = required_calls - 1
    monkeypatch.setattr(under_module, "monotonic", budget.Clock())
    rc, payload = budget.run_cli(under_module, capsys, budget.EstateHTTP(99))
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


def test_single_response_byte_budget_exact_and_one_under(
    capsys, monkeypatch
) -> None:
    control_module = fx._cli_module()
    _apply_frozen_profile(control_module)
    monkeypatch.setattr(control_module, "monotonic", budget.Clock())
    sizes: list[int] = []
    control = budget.EstateHTTP(99)
    control.after_read = lambda _url, result: sizes.append(
        len(control_module.canonical_json(result).encode("utf-8", "backslashreplace"))
    )
    assert budget.run_cli(control_module, capsys, control)[0] == 0
    required_bytes = sum(sizes)
    assert required_bytes < 768 * 1024 * 1024

    exact_module = fx._cli_module()
    _apply_frozen_profile(exact_module)
    exact_module._MAX_HTTP_NORMALIZED_BYTES = required_bytes
    monkeypatch.setattr(exact_module, "monotonic", budget.Clock())
    assert budget.run_cli(exact_module, capsys, budget.EstateHTTP(99))[0] == 0

    under_module = fx._cli_module()
    _apply_frozen_profile(under_module)
    under_module._MAX_HTTP_NORMALIZED_BYTES = required_bytes - 1
    monkeypatch.setattr(under_module, "monotonic", budget.Clock())
    rc, payload = budget.run_cli(under_module, capsys, budget.EstateHTTP(99))
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


def test_macro_1000_with_live_fanout_refuses_before_foreign_reads(
    capsys, monkeypatch
) -> None:
    """Historical file fanout cannot qualify an incomplete PR roster."""
    assert len(LIVE_903_EXTRA_FILE_CALLS) == 41
    assert sum(LIVE_903_EXTRA_FILE_CALLS) == 170
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = budget.EstateHTTP(1000, file_counts=_live_fanout_file_counts(1))

    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert http.passes == 1
    assert len(_roster_calls(http)) == 1
    assert _foreign_file_calls(http) == []


def test_macro_1500_doubled_fanout_does_not_claim_coverage_or_headroom(
    capsys, monkeypatch
) -> None:
    """The large estate is unqualified before its expensive file fanout."""
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = budget.EstateHTTP(1500, file_counts=_live_fanout_file_counts(2))

    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert http.passes == 1
    assert len(_roster_calls(http)) == 1
    assert _foreign_file_calls(http) == []


def _census_threads(http) -> set[str]:
    names: set[str] = set()
    http.after_read = lambda url, _result: (
        names.add(threading.current_thread().name)
        if "/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
        else None
    )
    return names


def _roster_calls(http) -> list[str]:
    return [url for url, _, _ in http.calls if "/pulls?" in url]


@pytest.mark.parametrize("count", [50, 99])
def test_conditional_reuse_path_reads_each_foreign_pr_once(
    count, capsys, monkeypatch
) -> None:
    """Production shape: identity rows, ETag replay, four census workers."""
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = ConditionalEstateHTTP(
        module, count, file_counts=_live_fanout_file_counts(1)
    )
    threads = _census_threads(http)
    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 0, payload
    assert payload["collision_state"] == "DISJOINT"
    assert payload["authority_effect"] == "NONE"
    assert http.passes == 2
    # Each observation uses exactly one complete short response.
    assert len(_roster_calls(http)) == 2
    foreign_files = _foreign_file_calls(http)
    assert len(foreign_files) == len(set(foreign_files)) == count - 1 + 170
    strict = [
        url
        for url, _, _ in http.calls
        if "/pulls?" not in url and url not in foreign_files
    ]
    assert sorted(http.conditional_calls) == sorted(strict)
    assert any(name.startswith("source-continuity-read") for name in threads)
    total = len(http.calls) + len(http.conditional_calls)
    assert total == 2 + count - 1 + 170 + 2 * len(strict)
    assert total < module._MAX_HTTP_CALLS // 2


def test_census_worker_count_is_the_shared_constant(capsys, monkeypatch) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    monkeypatch.setattr(module, "_FOREIGN_PR_WORKERS", 1)
    http = ConditionalEstateHTTP(module, 50)
    threads = _census_threads(http)
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 0, payload
    assert threads == {threading.current_thread().name}


def test_identityless_foreign_row_forces_full_second_census(
    capsys, monkeypatch
) -> None:
    """A deleted-fork row has no identity, so every foreign PR is re-read."""
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = ConditionalEstateHTTP(
        module, 99, identityless={1000}, file_counts=_live_fanout_file_counts(1)
    )
    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 0, payload
    assert payload["collision_state"] == "DISJOINT"
    assert http.passes == 2
    assert len(_foreign_file_calls(http)) == 2 * (98 + 170)


@pytest.mark.parametrize(("opened", "rc", "code"), [
    (98, 2, "REMOTE_CENSUS_INCOMPLETE"),
    (99, 2, "REMOTE_CENSUS_INCOMPLETE"),
])
@pytest.mark.parametrize("conditional", [True, False], ids=["identityless", "legacy"])
def test_full_second_response_leaves_revalidation_incomplete(
    conditional, opened, rc, code, capsys, monkeypatch
) -> None:
    """Neither re-census fallback may promote a full second page to success."""
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    if conditional:
        http = ConditionalEstateHTTP(
            module, 2, identityless={1000}, opened_between=opened
        )
    else:
        http = budget.EstateHTTP(2, opened_between=opened)
    rc_result, payload = budget.run_cli(module, capsys, http)

    assert rc_result == rc, payload
    assert payload["code"] == code
    assert http.passes == 2


def test_time_budget_accepts_last_finite_instant_and_refuses_deadline(
    capsys, monkeypatch
) -> None:
    success_module = fx._cli_module()
    _apply_frozen_profile(success_module)
    success_clock = budget.Clock()
    monkeypatch.setattr(success_module, "monotonic", success_clock)
    success_http = budget.EstateHTTP(1)
    success_http.after_read = lambda _url, _result: setattr(
        success_clock, "now", 899.999
    )
    assert budget.run_cli(success_module, capsys, success_http)[0] == 0

    deadline_module = fx._cli_module()
    _apply_frozen_profile(deadline_module)
    deadline_clock = budget.Clock()
    monkeypatch.setattr(deadline_module, "monotonic", deadline_clock)
    deadline_http = budget.EstateHTTP(1)
    deadline_http.after_read = lambda _url, _result: setattr(
        deadline_clock, "now", 900.0
    )
    rc, payload = budget.run_cli(deadline_module, capsys, deadline_http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


def test_final_receipt_check_refuses_at_exact_deadline(
    capsys, monkeypatch
) -> None:
    module = fx._cli_module()
    _apply_frozen_profile(module)
    clock = budget.Clock()
    monkeypatch.setattr(module, "monotonic", clock)
    original = module.verify_source_continuity

    def reach_deadline_after_verification(*args):
        result = original(*args)
        clock.now = 900.0
        return result

    monkeypatch.setattr(
        module, "verify_source_continuity", reach_deadline_after_verification
    )
    rc, payload = budget.run_cli(module, capsys, budget.EstateHTTP(1))
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
