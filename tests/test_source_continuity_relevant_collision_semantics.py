"""Relevant-collision conditional revalidation must track custody, not roster noise."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

import test_source_continuity as fx
import test_source_continuity_saturated_foreign_pr as sat


FOREIGN_A = 991
FOREIGN_B = 992
A_HEAD = "a" * 40
A_HEAD_MOVED = "b" * 40
B_HEAD = "c" * 40
FOREIGN_BASE = "d" * 40


def _target_row() -> dict[str, object]:
    return {
        "number": fx.PR_NUMBER,
        "state": "open",
        "head": {
            "sha": fx.HEAD_SHA,
            "repo": {"full_name": fx.REPOSITORY},
        },
        "base": {
            "sha": fx.CURRENT_BASE_SHA,
            "repo": {"full_name": fx.REPOSITORY},
        },
    }


def _foreign_row(
    number: int,
    *,
    head_sha: str,
    state: str = "open",
) -> dict[str, object]:
    return {
        "number": number,
        "state": state,
        "head": {
            "sha": head_sha,
            "repo": {"full_name": fx.REPOSITORY},
        },
        "base": {
            "sha": FOREIGN_BASE,
            "repo": {"full_name": fx.REPOSITORY},
        },
    }


class CollisionChurnHTTP:
    """Conditional transport with a different second complete open-PR census."""

    _source_continuity_conditional = True

    def __init__(
        self,
        module,
        *,
        first_roster: list[dict[str, object]],
        second_roster: list[dict[str, object]],
        foreign_files: dict[int, tuple[str, ...]],
        direct_details: dict[int, dict[str, object]] | None = None,
    ) -> None:
        self.module = module
        self.base = fx._ProbeHTTP()
        self.first_roster = first_roster
        self.second_roster = second_roster
        self.foreign_files = foreign_files
        self.direct_details = direct_details or {}
        self.roster_reads = 0
        self.plain_calls: list[str] = []
        self.conditional_calls: list[str] = []

    @staticmethod
    def _etag(url: str) -> str:
        return 'W/"' + hashlib.sha256(url.encode()).hexdigest() + '"'

    @property
    def _open_roster_url(self) -> str:
        return (
            f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/pulls"
            "?state=open&per_page=100&page=1"
        )

    def _plain(self, url: str, *, token: str, timeout: float) -> object:
        self.plain_calls.append(url)
        if url == self._open_roster_url:
            self.roster_reads += 1
            return self.first_roster if self.roster_reads == 1 else self.second_roster

        prefix = f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/pulls/"
        if url.startswith(prefix):
            suffix = url[len(prefix):]
            if suffix.isdigit():
                number = int(suffix)
                if number in self.direct_details:
                    return self.direct_details[number]
            if "/files?per_page=100&page=1" in suffix:
                number = int(suffix.split("/", 1)[0])
                if number in self.foreign_files:
                    return [
                        {"filename": path, "status": "modified"}
                        for path in self.foreign_files[number]
                    ]

        return self.base(url, token=token, timeout=timeout)

    def __call__(
        self,
        url: str,
        *,
        token: str,
        timeout: float,
        if_none_match: str | None = None,
    ) -> object:
        assert token == fx.TOKEN
        assert timeout > 0
        if if_none_match is None:
            payload = self._plain(url, token=token, timeout=timeout)
            return self.module._HTTPRepresentation(
                payload=payload,
                etag=self._etag(url),
                not_modified=False,
            )

        self.conditional_calls.append(url)
        if url == self._open_roster_url:
            return self.module._HTTPRepresentation(
                payload=self.second_roster,
                etag='"' + "e" * 64 + '"',
                not_modified=False,
            )
        return self.module._HTTPRepresentation(
            payload=None,
            etag=if_none_match.removeprefix("W/"),
            not_modified=True,
        )


def _run(module, http: CollisionChurnHTTP, capsys) -> tuple[int, dict[str, object]]:
    exit_code = fx._run_cli(module, fx._cli_argv(), http=http)
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out)


def _assert_receipt(result: tuple[int, dict[str, object]]) -> None:
    exit_code, payload = result
    assert exit_code == 0
    assert payload["schema"] == "mastermind.source_continuity_receipt/v1"
    assert payload["local_equals_remote"] is True


def _assert_changed(result: tuple[int, dict[str, object]]) -> None:
    exit_code, payload = result
    assert exit_code == 1
    assert payload["code"] == "REMOTE_PROOF_CHANGED"


def test_new_disjoint_pr_is_freshly_proved_and_does_not_starve(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sat._module()
    http = CollisionChurnHTTP(
        module,
        first_roster=[_target_row(), _foreign_row(FOREIGN_A, head_sha=A_HEAD)],
        second_roster=[
            _target_row(),
            _foreign_row(FOREIGN_A, head_sha=A_HEAD),
            _foreign_row(FOREIGN_B, head_sha=B_HEAD),
        ],
        foreign_files={
            FOREIGN_A: ("docs/a.md",),
            FOREIGN_B: ("docs/b.md",),
        },
    )

    _assert_receipt(_run(module, http, capsys))
    assert any(f"/pulls/{FOREIGN_B}/files?" in url for url in http.plain_calls)


def test_moved_disjoint_pr_is_freshly_reproved_and_does_not_starve(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sat._module()
    http = CollisionChurnHTTP(
        module,
        first_roster=[_target_row(), _foreign_row(FOREIGN_A, head_sha=A_HEAD)],
        second_roster=[
            _target_row(),
            _foreign_row(FOREIGN_A, head_sha=A_HEAD_MOVED),
        ],
        foreign_files={FOREIGN_A: ("docs/a.md",)},
    )

    _assert_receipt(_run(module, http, capsys))


def test_missing_disjoint_pr_may_drop_only_when_direct_detail_proves_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sat._module()
    http = CollisionChurnHTTP(
        module,
        first_roster=[_target_row(), _foreign_row(FOREIGN_A, head_sha=A_HEAD)],
        second_roster=[_target_row()],
        foreign_files={FOREIGN_A: ("docs/a.md",)},
        direct_details={
            FOREIGN_A: _foreign_row(FOREIGN_A, head_sha=A_HEAD, state="closed"),
        },
    )

    _assert_receipt(_run(module, http, capsys))
    assert (
        f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/pulls/{FOREIGN_A}"
        in http.plain_calls
    )


def test_missing_disjoint_pr_that_direct_detail_still_reports_open_refuses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sat._module()
    http = CollisionChurnHTTP(
        module,
        first_roster=[_target_row(), _foreign_row(FOREIGN_A, head_sha=A_HEAD)],
        second_roster=[_target_row()],
        foreign_files={FOREIGN_A: ("docs/a.md",)},
        direct_details={
            FOREIGN_A: _foreign_row(FOREIGN_A, head_sha=A_HEAD, state="open"),
        },
    )

    _assert_changed(_run(module, http, capsys))


def test_new_colliding_pr_refuses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sat._module()
    http = CollisionChurnHTTP(
        module,
        first_roster=[_target_row(), _foreign_row(FOREIGN_A, head_sha=A_HEAD)],
        second_roster=[
            _target_row(),
            _foreign_row(FOREIGN_A, head_sha=A_HEAD),
            _foreign_row(FOREIGN_B, head_sha=B_HEAD),
        ],
        foreign_files={
            FOREIGN_A: ("docs/a.md",),
            FOREIGN_B: ("scripts/source_continuity.py",),
        },
    )

    _assert_changed(_run(module, http, capsys))


def test_colliding_pr_identity_movement_refuses_even_if_paths_still_collide(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sat._module()
    http = CollisionChurnHTTP(
        module,
        first_roster=[_target_row(), _foreign_row(FOREIGN_A, head_sha=A_HEAD)],
        second_roster=[
            _target_row(),
            _foreign_row(FOREIGN_A, head_sha=A_HEAD_MOVED),
        ],
        foreign_files={FOREIGN_A: ("scripts/source_continuity.py",)},
    )

    _assert_changed(_run(module, http, capsys))


def test_colliding_pr_closure_refuses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sat._module()
    http = CollisionChurnHTTP(
        module,
        first_roster=[_target_row(), _foreign_row(FOREIGN_A, head_sha=A_HEAD)],
        second_roster=[_target_row()],
        foreign_files={FOREIGN_A: ("scripts/source_continuity.py",)},
        direct_details={
            FOREIGN_A: _foreign_row(FOREIGN_A, head_sha=A_HEAD, state="closed"),
        },
    )

    _assert_changed(_run(module, http, capsys))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda row: row.update(labels="malformed"),
        lambda row: (
            row.update(draft="malformed"),
            row.update(labels=[{"name": "hold"}]),
        ),
    ],
)
def test_predecessor_subject_pr_malformed_hold_projection_remains_refused(
    mutator,
) -> None:
    module = sat._module()
    changed = copy.deepcopy(sat._target_pr_payload())
    mutator(changed)
    transport = sat.SemanticRevalidationTransport(
        module,
        {sat.TARGET_PULL_URL: sat._target_pr_payload()},
        changed={sat.TARGET_PULL_URL: changed},
    )
    bounded = module._BoundedHTTPGet(
        transport,
        subject_pull_url=sat.TARGET_PULL_URL,
    )
    bounded(sat.TARGET_PULL_URL, token=sat.TOKEN, timeout=20.0)

    assert bounded.validate_unchanged(token=sat.TOKEN) is False
