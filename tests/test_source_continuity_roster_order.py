"""Open-PR roster paging under live churn; no real HTTP or token.

GitHub pages `pulls` by offset in creation order. A row inserted before the
cursor while the roster is being paged duplicates a row; a row removed before
the cursor skips one. Paging oldest-first makes a newly opened PR append after
the rows already read, and a first-pass PR missing from the second roster is
read directly instead of being presumed closed.
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


def _skipped_in_second_pass(http: ChurnHTTP) -> set[int]:
    return set(http.served[1]) - set(http.served[2])


def test_roster_pages_oldest_first_with_an_exact_query(capsys, monkeypatch) -> None:
    http = _churn()

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 0, payload
    assert payload["collision_state"] == "DISJOINT"
    expected = [
        f"{ROSTER_URL}?state=open&sort=created&direction=asc&per_page=100&page={page}"
        for page in (1, 2, 3)
    ] + [f"{ROSTER_URL}?state=open&sort=created&direction=desc&per_page=100&page=1"]
    assert http.roster_urls == expected * 2
    assert http.tail_served[2] == sorted(http.open, reverse=True)[:100]
    assert http.served[1][0] == fx.PR_NUMBER
    assert http.direct_reads == []


@pytest.mark.parametrize("observation", [1, 2])
def test_pr_opened_mid_roster_appends_instead_of_duplicating(
    observation, capsys, monkeypatch
) -> None:
    http = _churn(events={(observation, 1): open_pr(NEW_PR)})

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 0, payload
    assert payload["collision_state"] == "DISJOINT"
    assert len(http.served[observation]) == len(set(http.served[observation]))
    assert NEW_PR in http.served[observation]
    assert http.file_reads.count(NEW_PR) == 1
    assert http.direct_reads == []


def test_colliding_pr_opened_mid_second_roster_refuses_changed(
    capsys, monkeypatch
) -> None:
    http = _churn(events={(2, 1): open_pr(NEW_PR, collides=True)})

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 1 and payload["code"] == "REMOTE_PROOF_CHANGED"
    assert NEW_PR in http.served[2]


def test_disjoint_pr_skipped_by_a_mid_roster_closure_is_read_directly(
    capsys, monkeypatch
) -> None:
    http = _churn(events={(2, 1): close_served(50)})

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 0, payload
    assert payload["collision_state"] == "DISJOINT"
    # The closed row was served before it closed; only the row it pushed back
    # onto page 1 is skipped.
    assert _skipped_in_second_pass(http) == {BOUNDARY_PR}
    assert http.direct_reads == [BOUNDARY_PR]
    # An unchanged identity reuses its first collision evidence.
    assert http.file_reads.count(BOUNDARY_PR) == 1


def test_collider_skipped_by_a_mid_roster_closure_is_reproved_directly(
    capsys, monkeypatch
) -> None:
    http = _churn(colliders={BOUNDARY_PR}, events={(2, 1): close_served(50)})

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 0, payload
    assert payload["collision_state"] == "OVERLAP"
    assert payload["colliding_pr_numbers"] == [BOUNDARY_PR]
    assert BOUNDARY_PR not in http.served[2]
    assert http.direct_reads == [BOUNDARY_PR]


def test_skipped_collider_that_moved_refuses_changed(capsys, monkeypatch) -> None:
    http = _churn(
        colliders={BOUNDARY_PR},
        events={(2, 1): both(close_served(50), move(BOUNDARY_PR, collides=True))},
    )

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 1 and payload["code"] == "REMOTE_PROOF_CHANGED"
    assert BOUNDARY_PR in http.direct_reads


def test_skipped_collider_that_closed_refuses_changed(capsys, monkeypatch) -> None:
    def close_boundary(http: ChurnHTTP, served: list[int]) -> None:
        http.open.discard(BOUNDARY_PR)

    http = _churn(
        colliders={BOUNDARY_PR},
        events={(2, 1): both(close_served(50), close_boundary)},
    )

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 1 and payload["code"] == "REMOTE_PROOF_CHANGED"
    assert BOUNDARY_PR in http.direct_reads


@pytest.mark.parametrize(
    ("collides", "rc", "code"),
    [(False, 0, None), (True, 1, "REMOTE_PROOF_CHANGED")],
)
def test_skipped_disjoint_pr_that_moved_is_freshly_reproved(
    collides, rc, code, capsys, monkeypatch
) -> None:
    http = _churn(
        events={(2, 1): both(close_served(50), move(BOUNDARY_PR, collides=collides))},
    )

    result_rc, payload = _run(http, capsys, monkeypatch)

    assert result_rc == rc, payload
    if code is None:
        assert payload["collision_state"] == "DISJOINT"
    else:
        assert payload["code"] == code
    assert BOUNDARY_PR in http.direct_reads
    assert http.file_reads.count(BOUNDARY_PR) == 2


def test_direct_read_naming_another_pr_fails_closed(capsys, monkeypatch) -> None:
    http = _churn(events={(2, 1): close_served(50)})
    http.direct_mutators[BOUNDARY_PR] = lambda row: row.update(number=BOUNDARY_PR + 1)

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"


@pytest.mark.parametrize("state", [None, "merged", "OPEN"])
def test_direct_read_with_an_unknown_state_refuses_changed(
    state, capsys, monkeypatch
) -> None:
    http = _churn(events={(2, 1): close_served(50)})
    http.direct_mutators[BOUNDARY_PR] = lambda row: row.update(state=state)

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 1 and payload["code"] == "REMOTE_PROOF_CHANGED"
    assert http.direct_reads == [BOUNDARY_PR]


def test_collider_skipped_by_the_first_roster_is_caught_by_the_second(
    capsys, monkeypatch
) -> None:
    http = _churn(colliders={BOUNDARY_PR}, events={(1, 1): close_served(50)})

    rc, payload = _run(http, capsys, monkeypatch)

    assert BOUNDARY_PR not in http.served[1]
    assert BOUNDARY_PR in http.served[2]
    assert rc == 1 and payload["code"] == "REMOTE_PROOF_CHANGED"


def test_reopened_older_pr_before_the_cursor_still_refuses(
    capsys, monkeypatch
) -> None:
    # Residual: oldest-first, a reopened PR older than the cursor duplicates a row.
    http = _churn(events={(2, 1): open_pr(1005)})

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"
    assert len(http.served[2]) != len(set(http.served[2]))


@pytest.mark.parametrize(
    ("collides", "rc", "code"),
    [(False, 0, None), (True, 1, "REMOTE_PROOF_CHANGED")],
)
def test_new_pr_skipped_at_the_roster_end_is_read_from_the_tail_page(
    collides, rc, code, capsys, monkeypatch
) -> None:
    # The first observation reads 200 rows. A PR opened after its roster sorts
    # last, first on page 3, and a closure on page 2 pushes it back onto the
    # page already read. It is in no first-pass record, so no direct read
    # would find it.
    http = _churn(
        events={(2, 1): open_pr(NEW_PR, collides=collides), (2, 2): close_served(0)},
    )
    http.open = {fx.PR_NUMBER, *FOREIGN[:199]}

    result_rc, payload = _run(http, capsys, monkeypatch)

    assert NEW_PR not in http.served[2]
    assert http.file_reads.count(NEW_PR) == 1
    assert result_rc == rc, payload
    if code is None:
        assert payload["collision_state"] == "DISJOINT"
    else:
        assert payload["code"] == code
    assert NEW_PR in http.tail_served[2]
    assert http.direct_reads == []


@pytest.mark.parametrize(("opened", "rc"), [(99, 0), (100, 2)])
def test_a_tail_page_of_only_new_prs_leaves_the_second_census_incomplete(
    opened, rc, capsys, monkeypatch
) -> None:
    # A full tail page vouches only for PRs created at least as recently as its
    # oldest row. Once every row is newer than the first observation, a new PR
    # skipped below it could be missed.
    def open_many(http: ChurnHTTP, served: list[int]) -> None:
        for number in range(NEW_PR, NEW_PR + opened):
            open_pr(number)(http, served)

    http = _churn(events={(2, 1): open_many})

    result_rc, payload = _run(http, capsys, monkeypatch)

    assert result_rc == rc, payload
    if rc == 0:
        assert payload["collision_state"] == "DISJOINT"
        assert min(http.tail_served[2]) == FOREIGN[-1]
    else:
        assert payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
        assert min(http.tail_served[2]) == NEW_PR


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda rows: {"items": rows}, id="not-a-list"),
        pytest.param(lambda rows: rows + rows[:1], id="over-a-page"),
        pytest.param(lambda rows: rows[:-1] + rows[:1], id="repeated-row"),
        pytest.param(lambda rows: rows[:-1] + ["row"], id="not-an-object"),
        pytest.param(
            lambda rows: [{**rows[0], "number": True}, *rows[1:]], id="bool-number"
        ),
        pytest.param(
            lambda rows: [{**rows[0], "number": 0}, *rows[1:]], id="zero-number"
        ),
    ],
)
def test_malformed_tail_page_fails_closed(mutate, capsys, monkeypatch) -> None:
    http = _churn()
    http.tail_mutator = mutate

    rc, payload = _run(http, capsys, monkeypatch)

    assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"
    assert 1 in http.tail_served


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
