"""Relevant-collision semantic revalidation regressions.

These cases freeze issue #346 comments 5739262698 + 5739588486.
"""
from __future__ import annotations

import copy
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

import test_source_continuity_saturated_foreign_pr as sf


NEW_PR = 8123
FOREIGN_A = sf.FOREIGN_PR
A_HEAD = sf.HEAD
A_BASE = sf.BASE
A_MOVED_HEAD = "6" * 40
NEW_HEAD = "7" * 40
NEW_BASE = "8" * 40


def _row(number: int, head_sha: str, base_sha: str) -> dict[str, object]:
    return {
        "number": number,
        "state": "open",
        "head": {"sha": head_sha, "repo": {"full_name": sf.REPOSITORY}},
        "base": {"sha": base_sha, "repo": {"full_name": sf.REPOSITORY}},
    }


def _target_row() -> dict[str, object]:
    return _row(sf.TARGET_PR, sf.TARGET_HEAD, sf.TARGET_BASE_HEAD)


def _files(path: str) -> list[dict[str, object]]:
    return [{"filename": path, "status": "modified"}]


class RelevantCollisionHTTP:
    """Conditional transport with an explicit first and second collision census."""

    _source_continuity_conditional = True

    def __init__(
        self,
        module,
        *,
        first_roster: list[dict[str, object]],
        second_roster: list[dict[str, object]],
        first_files: dict[int, list[dict[str, object]]],
        second_files: dict[int, list[dict[str, object]]] | None = None,
        direct_details: dict[int, object] | None = None,
    ) -> None:
        self.module = module
        self.first_roster = first_roster
        self.second_roster = second_roster
        self.first_files = first_files
        self.second_files = second_files or {}
        self.direct_details = direct_details or {}
        self.roster_reads = 0
        self.file_reads: dict[int, int] = {}
        self.direct_reads: list[int] = []
        self.conditional_calls: list[str] = []

    @staticmethod
    def _etag(url: str) -> str:
        return 'W/"' + hashlib.sha256(url.encode("utf-8")).hexdigest() + '"'

    def _rep(self, url: str, payload: object, *, not_modified: bool = False):
        return self.module._HTTPRepresentation(
            payload=payload,
            etag=self._etag(url),
            not_modified=not_modified,
        )

    def __call__(
        self,
        url: str,
        *,
        token: str,
        timeout: float,
        if_none_match: str | None = None,
    ) -> object:
        assert token == sf.TOKEN and timeout > 0
        parsed = urlparse(url)

        if if_none_match is not None:
            self.conditional_calls.append(url)
            if parsed.path.endswith("/pulls"):
                return self._rep(url, copy.deepcopy(self.second_roster))
            return self.module._HTTPRepresentation(
                payload=None,
                etag=if_none_match.removeprefix("W/"),
                not_modified=True,
            )

        if parsed.path.endswith("/pulls"):
            payload = self.first_roster if self.roster_reads == 0 else self.second_roster
            self.roster_reads += 1
            return self._rep(url, copy.deepcopy(payload))

        if parsed.path.endswith("/files"):
            number = int(parsed.path.split("/")[-2])
            page = int(parse_qs(parsed.query).get("page", ["1"])[0])
            assert page == 1
            count = self.file_reads.get(number, 0)
            self.file_reads[number] = count + 1
            if count == 0 and number in self.first_files:
                payload = self.first_files[number]
            else:
                payload = self.second_files.get(number, self.first_files.get(number, []))
            return self._rep(url, copy.deepcopy(payload))

        if "/pulls/" in parsed.path:
            number = int(parsed.path.rsplit("/", 1)[1])
            self.direct_reads.append(number)
            if number not in self.direct_details:
                raise AssertionError(f"unexpected direct PR read: {url}")
            return self._rep(url, copy.deepcopy(self.direct_details[number]))

        raise AssertionError(url)


def _request(module):
    return module.SourceContinuityRequest(
        receipt_kind=module.ReceiptKind.CHECKPOINT_VERIFIED,
        operation_key="source-continuity-relevant-collision-test",
        repository=sf.REPOSITORY,
        pr_number=sf.TARGET_PR,
        branch=sf.TARGET_BRANCH,
        base_ref="main",
        pinned_base_sha=sf.TARGET_BASE_HEAD,
        owned_paths=sf.OWNED,
        verified_at="2026-09-19T00:00:00Z",
    )


def _result(module, transport: RelevantCollisionHTTP):
    bounded = module._BoundedHTTPGet(
        transport,
        subject_pull_url=sf.TARGET_PULL_URL,
    )
    first = module._collision_census(
        bounded,
        sf.TOKEN,
        sf.REPOSITORY,
        sf.TARGET_PR,
        sf.OWNED,
    )
    state, numbers, complete, snapshot = first
    assert complete is True
    return module._remote_still_matches(
        bounded,
        sf.TOKEN,
        _request(module),
        module._pr_identity(sf._target_pr_payload()),
        sf.TARGET_HEAD,
        sf.TARGET_BASE_HEAD,
        sf.OWNED,
        True,
        state,
        numbers,
        complete,
        snapshot,
    )


def test_unrelated_new_disjoint_pr_is_freshly_proved_and_allowed() -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[
            _target_row(),
            _row(FOREIGN_A, A_HEAD, A_BASE),
            _row(NEW_PR, NEW_HEAD, NEW_BASE),
        ],
        first_files={FOREIGN_A: _files("docs/a.md")},
        second_files={NEW_PR: _files("docs/new.md")},
    )

    assert _result(module, transport) is None
    assert transport.file_reads[FOREIGN_A] == 1
    assert transport.file_reads[NEW_PR] == 1


def test_moved_disjoint_pr_is_reproved_and_allowed_when_still_disjoint() -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[_target_row(), _row(FOREIGN_A, A_MOVED_HEAD, A_BASE)],
        first_files={FOREIGN_A: _files("docs/a.md")},
        second_files={FOREIGN_A: _files("docs/moved.md")},
    )

    assert _result(module, transport) is None
    assert transport.file_reads[FOREIGN_A] == 2


def test_closed_first_pass_disjoint_pr_requires_direct_closed_proof() -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[_target_row()],
        first_files={FOREIGN_A: _files("docs/a.md")},
        direct_details={FOREIGN_A: {"state": "closed"}},
    )

    assert _result(module, transport) is None
    assert transport.direct_reads == [FOREIGN_A]


def test_missing_first_pass_disjoint_pr_that_is_still_open_refuses() -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[_target_row()],
        first_files={FOREIGN_A: _files("docs/a.md")},
        direct_details={FOREIGN_A: {"state": "open"}},
    )

    result = _result(module, transport)
    assert result is not None
    assert result.code.value == "REMOTE_PROOF_CHANGED"


@pytest.mark.parametrize("detail", [{}, {"state": "merged"}, "malformed"])
def test_missing_first_pass_disjoint_pr_ambiguous_direct_state_refuses(detail) -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[_target_row()],
        first_files={FOREIGN_A: _files("docs/a.md")},
        direct_details={FOREIGN_A: detail},
    )

    result = _result(module, transport)
    assert result is not None


def test_new_foreign_pr_that_overlaps_owned_path_refuses() -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[
            _target_row(),
            _row(FOREIGN_A, A_HEAD, A_BASE),
            _row(NEW_PR, NEW_HEAD, NEW_BASE),
        ],
        first_files={FOREIGN_A: _files("docs/a.md")},
        second_files={NEW_PR: _files(sf.OWNED[0])},
    )

    result = _result(module, transport)
    assert result is not None
    assert result.code.value == "REMOTE_PROOF_CHANGED"


def test_moved_disjoint_pr_that_becomes_colliding_refuses() -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[_target_row(), _row(FOREIGN_A, A_MOVED_HEAD, A_BASE)],
        first_files={FOREIGN_A: _files("docs/a.md")},
        second_files={FOREIGN_A: _files(sf.OWNED[0])},
    )

    result = _result(module, transport)
    assert result is not None
    assert result.code.value == "REMOTE_PROOF_CHANGED"


def test_first_pass_colliding_pr_head_movement_refuses_without_reproof() -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[_target_row(), _row(FOREIGN_A, A_MOVED_HEAD, A_BASE)],
        first_files={FOREIGN_A: _files(sf.OWNED[0])},
        second_files={FOREIGN_A: _files(sf.OWNED[0])},
    )

    result = _result(module, transport)
    assert result is not None
    assert result.code.value == "REMOTE_PROOF_CHANGED"
    assert transport.file_reads[FOREIGN_A] == 1


def test_first_pass_colliding_pr_closure_refuses_without_direct_drop() -> None:
    module = sf._module()
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), _row(FOREIGN_A, A_HEAD, A_BASE)],
        second_roster=[_target_row()],
        first_files={FOREIGN_A: _files(sf.OWNED[0])},
    )

    result = _result(module, transport)
    assert result is not None
    assert result.code.value == "REMOTE_PROOF_CHANGED"
    assert transport.direct_reads == []


def test_duplicate_second_roster_refuses() -> None:
    module = sf._module()
    duplicate = _row(FOREIGN_A, A_HEAD, A_BASE)
    transport = RelevantCollisionHTTP(
        module,
        first_roster=[_target_row(), duplicate],
        second_roster=[_target_row(), duplicate, copy.deepcopy(duplicate)],
        first_files={FOREIGN_A: _files("docs/a.md")},
    )

    with pytest.raises(module._RemoteProbeError):
        _result(module, transport)


def test_shared_budgets_remain_exactly_the_accepted_profile() -> None:
    module = sf._module()
    assert module._MAX_COLLISION_PRS == 400
    assert module._MAX_HTTP_CALLS == 1152
    assert module._MAX_HTTP_NORMALIZED_BYTES == 96 * 1024 * 1024
    assert module._HTTP_READ_BUDGET_SECONDS == 300.0


def test_subject_pr_malformed_hold_shape_remains_fail_closed() -> None:
    module = sf._module()
    first = sf._target_pr_payload()
    changed = copy.deepcopy(first)
    changed["labels"] = "malformed"
    transport = sf.SemanticRevalidationTransport(
        module,
        {sf.TARGET_PULL_URL: first},
        changed={sf.TARGET_PULL_URL: changed},
    )
    bounded = module._BoundedHTTPGet(
        transport,
        subject_pull_url=sf.TARGET_PULL_URL,
    )
    bounded(sf.TARGET_PULL_URL, token=sf.TOKEN, timeout=20.0)

    assert bounded.validate_unchanged(token=sf.TOKEN) is False
