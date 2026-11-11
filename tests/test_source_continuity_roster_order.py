"""Roster coverage containment and single-response custody revalidation.

The retained live-churn fake can model the unsafe offset/tail algorithm. The
real reader now refuses its full first page instead of claiming coverage.
"""
from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

import test_source_continuity as fx
import test_source_continuity_census_budget as budget


# 1 target + 249 foreign rows: pages of 100, 100 and 50. Numbers are spaced so
# a reopened older PR can sort between existing rows.
FOREIGN = tuple(1000 + 10 * index for index in range(249))
NEW_PR = 5000
OWNED_PATH = fx.FINAL_OWNED_PATHS[0]
ROSTER_URL = f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/pulls"
# Oldest-first, the row at offset 100 of the full roster: the first row of page
# 2, which a closure on page 1 pushes back onto the page already read.
BOUNDARY_PR = 1990


class ChurnHTTP(fx._ProbeHTTP):
    """A conditional transport over an open-PR estate that changes mid-roster.

    Rows are ordered by number, which stands in for creation order. A roster
    request with no `direction` is served newest-first, as GitHub does; one
    with `direction=desc` is the tail page read after the oldest-first pages.
    ``events[(pass, page)]`` runs after that roster page is served, and
    ``events[(pass, "tail")]`` after that pass's tail page.
    """

    _source_continuity_conditional = True

    def __init__(self, module, *, colliders=(), events=None):
        super().__init__()
        self.module = module
        self.heads = {number: f"{number:040x}" for number in FOREIGN}
        self.open = {fx.PR_NUMBER, *FOREIGN}
        self.colliders = set(colliders)
        self.events = dict(events or {})
        self.passes = 0
        self.served: dict[int, list[int]] = {}
        self.tail_served: dict[int, list[int]] = {}
        self.tail_mutator = None
        self.before_second = None
        self.roster_urls: list[str] = []
        self.direct_reads: list[int] = []
        self.direct_mutators: dict[int, object] = {}
        self.file_reads: list[int] = []

    def _row(self, number: int, state: str = "open") -> dict[str, object]:
        if number == fx.PR_NUMBER:
            head_sha, base_sha = fx.HEAD_SHA, fx.CURRENT_BASE_SHA
        else:
            head_sha, base_sha = self.heads[number], "d" * 40
        return {
            "number": number,
            "state": state,
            "head": {"sha": head_sha, "repo": {"full_name": fx.REPOSITORY}},
            "base": {"sha": base_sha, "repo": {"full_name": fx.REPOSITORY}},
        }

    def _roster(self, url: str) -> list[dict[str, object]]:
        query = parse_qs(urlparse(url).query)
        assert query.get("sort", ["created"]) == ["created"]
        page = int(query["page"][0])
        if query.get("direction") == ["desc"]:
            assert page == 1
            tail = sorted(self.open, reverse=True)[:100]
            self.tail_served[self.passes] = tail
            payload = [self._row(number) for number in tail]
            if self.tail_mutator is not None:
                payload = self.tail_mutator(payload)
            event = self.events.get((self.passes, "tail"))
            if event is not None:
                event(self, tail)
            return payload
        if page == 1:
            if self.passes == 1 and self.before_second is not None:
                self.before_second(self)
                self.before_second = None
            self.passes += 1
        newest_first = query.get("direction") != ["asc"]
        ordered = sorted(self.open, reverse=newest_first)
        served = ordered[(page - 1) * 100:page * 100]
        self.served.setdefault(self.passes, []).extend(served)
        payload = [self._row(number) for number in served]
        event = self.events.get((self.passes, page))
        if event is not None:
            event(self, served)
        return payload

    def _payload(self, url: str, *, token: str, timeout: float) -> object:
        parsed = urlparse(url)
        path = parsed.path
        if url.startswith(ROSTER_URL + "?"):
            self.calls.append((url, token, timeout))
            self.roster_urls.append(url)
            return self._roster(url)
        prefix = f"/repos/{fx.REPOSITORY}/pulls/"
        if path.startswith(prefix):
            suffix = path[len(prefix):]
            if suffix.isdigit() and int(suffix) != fx.PR_NUMBER:
                self.calls.append((url, token, timeout))
                number = int(suffix)
                self.direct_reads.append(number)
                row = self._row(number, "open" if number in self.open else "closed")
                mutate = self.direct_mutators.get(number)
                if mutate is not None:
                    mutate(row)
                return row
            number_text, _, rest = suffix.partition("/")
            if rest == "files" and int(number_text) != fx.PR_NUMBER:
                self.calls.append((url, token, timeout))
                number = int(number_text)
                self.file_reads.append(number)
                page = int(parse_qs(parsed.query)["page"][0])
                path_name = (
                    OWNED_PATH
                    if number in self.colliders
                    else f"docs/foreign-{number}.md"
                )
                return [{"filename": path_name, "status": "modified"}] if page == 1 else []
        return super().__call__(url, token=token, timeout=timeout)

    def __call__(self, url, *, token, timeout, if_none_match=None):
        assert token == fx.TOKEN and timeout > 0
        if if_none_match is not None:
            return self.module._HTTPRepresentation(
                payload=None,
                etag=if_none_match.removeprefix("W/"),
                not_modified=True,
            )
        payload = self._payload(url, token=token, timeout=timeout)
        return self.module._HTTPRepresentation(
            payload=payload,
            etag='W/"' + hashlib.sha256(url.encode()).hexdigest() + '"',
            not_modified=False,
        )


def close_served(index: int):
    """Close a row already served on this page, before the cursor."""

    def event(http: ChurnHTTP, served: list[int]) -> None:
        http.open.discard(served[index])

    return event


def open_pr(number: int, *, collides: bool = False):
    """Open (or reopen) a PR; its number fixes where it sorts."""

    def event(http: ChurnHTTP, served: list[int]) -> None:
        http.heads[number] = f"{number:040x}"
        http.open.add(number)
        if collides:
            http.colliders.add(number)

    return event


def move(number: int, *, collides: bool):
    def event(http: ChurnHTTP, served: list[int]) -> None:
        http.heads[number] = "e" * 40
        if collides:
            http.colliders.add(number)
        else:
            http.colliders.discard(number)

    return event


def both(*events):
    def event(http: ChurnHTTP, served: list[int]) -> None:
        for each in events:
            each(http, served)

    return event


def _run(http: ChurnHTTP, capsys, monkeypatch) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr(http.module, "monotonic", budget.Clock(), raising=False)
    return budget.run_cli(http.module, capsys, http)


def _churn(**kwargs) -> ChurnHTTP:
    return ChurnHTTP(fx._cli_module(), **kwargs)


def _short_churn(**kwargs) -> ChurnHTTP:
    http = _churn(**kwargs)
    http.open = {fx.PR_NUMBER, FOREIGN[0], BOUNDARY_PR}
    return http


@pytest.mark.parametrize(
    "event",
    [None, open_pr(NEW_PR), open_pr(1005, collides=True), close_served(50)],
    ids=["stable", "new-pr", "reopened-collider", "closure"],
)
def test_full_roster_refuses_before_offset_or_tail_reads(
    event, capsys, monkeypatch
) -> None:
    http = _churn(events={} if event is None else {(1, 1): event})

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert http.roster_urls == [
        f"{ROSTER_URL}?state=open&sort=created&direction=asc&per_page=100&page=1"
    ]
    assert http.passes == 1
    assert http.tail_served == {}
    assert http.direct_reads == http.file_reads == []


def test_older_reopened_collider_cannot_mint_a_complete_receipt(
    capsys, monkeypatch
) -> None:
    # Exact accepted counterexample from #2006 comment6613931737: 1990 is
    # absent in observation one, reopens after its tail, then closure of 1000
    # shifts it behind observation two's cursor. Its old creation order also
    # excludes it from the tail. The former reader returned complete/DISJOINT.
    def close_1000(http, _served):
        http.open.discard(1000)

    http = _churn(
        colliders={BOUNDARY_PR},
        events={
            (1, "tail"): open_pr(BOUNDARY_PR, collides=True),
            (2, 1): close_1000,
        },
    )
    http.open.discard(BOUNDARY_PR)

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert payload["schema"] == "mastermind.source_continuity_refusal/v1"
    assert http.passes == 1 and http.tail_served == {}
    assert http.file_reads == http.direct_reads == []


def test_short_roster_uses_one_exact_response_per_observation(capsys, monkeypatch):
    http = _short_churn()

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 0 and payload["collision_state"] == "DISJOINT"
    assert http.roster_urls == [
        f"{ROSTER_URL}?state=open&sort=created&direction=asc&per_page=100&page=1"
    ] * 2
    assert http.direct_reads == []
    assert http.tail_served == {}


@pytest.mark.parametrize(
    ("defect", "rc", "code"),
    [
        ("wrong-number", 2, "REMOTE_PROBE_FAILED"),
        ("missing-state", 1, "REMOTE_PROOF_CHANGED"),
        ("merged-state", 1, "REMOTE_PROOF_CHANGED"),
        ("upper-state", 1, "REMOTE_PROOF_CHANGED"),
    ],
)
def test_short_roster_missing_pr_still_validates_direct_detail(
    defect, rc, code, capsys, monkeypatch
):
    http = _short_churn()
    http.before_second = lambda source: source.open.discard(BOUNDARY_PR)
    if defect == "wrong-number":
        http.direct_mutators[BOUNDARY_PR] = lambda row: row.update(number=BOUNDARY_PR+1)
    else:
        invalid_state = {"missing-state": None, "merged-state": "merged", "upper-state": "OPEN"}[defect]
        http.direct_mutators[BOUNDARY_PR] = lambda row: row.update(state=invalid_state)

    actual_rc, payload = _run(http, capsys, monkeypatch)

    assert actual_rc == rc and payload["code"] == code
    assert http.direct_reads == [BOUNDARY_PR]
    assert http.tail_served == {}


@pytest.mark.parametrize("observation", [1, 2])
def test_short_roster_must_contain_the_target(observation, capsys, monkeypatch):
    http = _short_churn()
    if observation == 1:
        http.open.discard(fx.PR_NUMBER)
    else:
        http.before_second = lambda source: source.open.discard(fx.PR_NUMBER)

    rc, payload = _run(http, capsys, monkeypatch)

    assert (rc, payload["code"]) == (
        (2, "REMOTE_PROBE_FAILED") if observation == 1
        else (1, "REMOTE_PROOF_CHANGED")
    )


def _roster_row(number: int) -> dict[str, object]:
    return {
        "number": number,
        "state": "open",
        "head": {"sha": "a" * 40, "repo": {"full_name": fx.REPOSITORY}},
        "base": {"sha": "d" * 40, "repo": {"full_name": fx.REPOSITORY}},
    }


@pytest.mark.parametrize(
    ("query", "provable"),
    [
        ("state=open&sort=created&direction=asc&per_page=100&page=1", True),
        ("page=16&per_page=100&direction=asc&sort=created&state=open", True),
        ("state=open&per_page=100&page=1", False),
        ("state=open&sort=created&direction=desc&per_page=100&page=1", False),
        ("state=open&sort=updated&direction=asc&per_page=100&page=1", False),
        ("state=open&direction=asc&per_page=100&page=1", False),
        ("state=open&sort=created&direction=asc&per_page=100&page=17", False),
        ("state=open&sort=created&direction=asc&direction=asc&per_page=100&page=1", False),
        ("state=open&sort=created&direction=asc&per_page=100&page=1&extra=1", False),
    ],
)
def test_roster_semantics_require_the_oldest_first_query(query, provable) -> None:
    module = fx._cli_module()
    url = f"{ROSTER_URL}?{query}"

    semantics = module._open_pull_roster_semantics(url, [_roster_row(7)])

    assert (semantics is not module._UNPROVABLE) is provable
