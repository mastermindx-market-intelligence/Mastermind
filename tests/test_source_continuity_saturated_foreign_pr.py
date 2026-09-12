from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "source_continuity.py"
REPOSITORY = "mastermindx-market-intelligence/macro"
TOKEN = "token"
TARGET_PR = 6996
FOREIGN_PR = 6657
OWNED = ("engine/entry_signal.py",)
HEAD, BASE, MERGE_BASE = (char * 40 for char in "abc")
HEAD_ROOT, BASE_ROOT, ENGINE_TREE, BLOB = (char * 40 for char in "def0")


def _module():
    name = "source_continuity_saturated_foreign_pr_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _foreign_pr() -> dict[str, object]:
    return {
        "number": FOREIGN_PR,
        "head": {"sha": HEAD, "repo": {"full_name": REPOSITORY}},
        "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
    }


def _bulk_rows(page: int) -> list[dict[str, object]]:
    return [
        {
            "filename": f"bulk/page-{page:02d}-{index:03d}.dat",
            "status": "modified",
        }
        for index in range(100)
    ]


def _tree(sha: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {"sha": sha, "truncated": False, "tree": rows}


class SaturatedDisjointHTTP:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        self.calls.append(url)
        parsed = urlparse(url)
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        if parsed.path.endswith("/pulls"):
            return [{"number": TARGET_PR}, _foreign_pr()]
        if parsed.path.endswith(f"/pulls/{FOREIGN_PR}/files"):
            if page in {*range(1, 11), 30}:
                return _bulk_rows(page)
            raise AssertionError(url)
        if parsed.path.endswith(f"/compare/{BASE}...{HEAD}"):
            return {"url": url, "base_commit": {"sha": BASE}, "merge_base_commit": {"sha": MERGE_BASE}}
        if parsed.path.endswith(f"/git/commits/{MERGE_BASE}"):
            return {"sha": MERGE_BASE, "tree": {"sha": BASE_ROOT}}
        if parsed.path.endswith(f"/git/commits/{HEAD}"):
            return {"sha": HEAD, "tree": {"sha": HEAD_ROOT}}
        if parsed.path.endswith(f"/git/trees/{BASE_ROOT}"):
            return _tree(BASE_ROOT, [{
                "path": "engine", "mode": "040000", "type": "tree",
                "sha": ENGINE_TREE,
            }])
        if parsed.path.endswith(f"/git/trees/{HEAD_ROOT}"):
            return _tree(HEAD_ROOT, [{
                "path": "engine", "mode": "040000", "type": "tree",
                "sha": ENGINE_TREE,
            }])
        if parsed.path.endswith(f"/git/trees/{ENGINE_TREE}"):
            return _tree(ENGINE_TREE, [{
                "path": "entry_signal.py", "mode": "100644", "type": "blob",
                "sha": BLOB, "size": 123,
            }])
        raise AssertionError(url)


def _file_pages(http: SaturatedDisjointHTTP) -> list[int]:
    return [
        int(parse_qs(urlparse(url).query)["page"][0])
        for url in http.calls
        if f"/pulls/{FOREIGN_PR}/files" in url
    ]


def _snapshot_evidence(snapshot: tuple[tuple[int, object], ...], number: int) -> object:
    return dict(snapshot)[number]


def test_saturated_foreign_pr_uses_owned_tree_entries_for_disjoint_proof() -> None:
    module = _module()
    http = SaturatedDisjointHTTP()

    state, numbers, complete, snapshot = module._collision_census(
        http,
        TOKEN,
        REPOSITORY,
        TARGET_PR,
        OWNED,
    )

    assert (state, numbers, complete) == (
        module.CollisionState.DISJOINT,
        (),
        True,
    )
    assert _file_pages(http) == [1, 30]
    assert _snapshot_evidence(snapshot, TARGET_PR) == ()
    evidence = _snapshot_evidence(snapshot, FOREIGN_PR)
    assert evidence.pr_number == FOREIGN_PR
    assert evidence.proof_method == "OWNED_PATH_TREE_DIFF"
    assert evidence.head_sha == HEAD
    assert evidence.base_sha == BASE
    assert evidence.merge_base_sha == MERGE_BASE
    assert evidence.owned_path_entries[0][0] == OWNED[0]


class SaturatedChangedHTTP(SaturatedDisjointHTTP):
    def __init__(
        self,
        *,
        base_entry: dict[str, object] | None,
        head_entry: dict[str, object] | None,
        truncate_head_root: bool = False,
        foreign_identity: dict[str, object] | None = None,
    ) -> None:
        super().__init__()
        self.base_entry = base_entry
        self.head_entry = head_entry
        self.truncate_head_root = truncate_head_root
        self.foreign_identity = foreign_identity or _foreign_pr()

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        parsed = urlparse(url)
        if parsed.path.endswith("/pulls"):
            self.calls.append(url)
            return [{"number": TARGET_PR}, self.foreign_identity]
        if parsed.path.endswith(f"/git/trees/{BASE_ROOT}"):
            self.calls.append(url)
            rows = [] if self.base_entry is None else [{
                "path": "engine", "mode": "040000", "type": "tree",
                "sha": "1" * 40,
            }]
            return _tree(BASE_ROOT, rows)
        if parsed.path.endswith(f"/git/trees/{HEAD_ROOT}"):
            self.calls.append(url)
            rows = [] if self.head_entry is None else [{
                "path": "engine", "mode": "040000", "type": "tree",
                "sha": "2" * 40,
            }]
            payload = _tree(HEAD_ROOT, rows)
            payload["truncated"] = self.truncate_head_root
            return payload
        if parsed.path.endswith("/git/trees/" + "1" * 40):
            self.calls.append(url)
            return _tree("1" * 40, [] if self.base_entry is None else [self.base_entry])
        if parsed.path.endswith("/git/trees/" + "2" * 40):
            self.calls.append(url)
            return _tree("2" * 40, [] if self.head_entry is None else [self.head_entry])
        return super().__call__(url, token=token, timeout=timeout)


def _entry(
    sha: str = BLOB,
    *,
    mode: str = "100644",
    object_type: str = "blob",
) -> dict[str, object]:
    return {
        "path": "entry_signal.py",
        "mode": mode,
        "type": object_type,
        "sha": sha,
        "size": 123,
    }


import pytest


@pytest.mark.parametrize(
    ("base_entry", "head_entry"),
    [
        (_entry(), _entry("3" * 40)),
        (_entry(), None),
        (None, _entry()),
        (_entry(), _entry(mode="100755")),
        (_entry(), _entry(mode="160000", object_type="commit")),
    ],
)
def test_saturated_foreign_pr_owned_entry_change_is_overlap(
    base_entry: dict[str, object] | None,
    head_entry: dict[str, object] | None,
) -> None:
    module = _module()
    http = SaturatedChangedHTTP(base_entry=base_entry, head_entry=head_entry)
    state, numbers, complete, snapshot = module._collision_census(
        http, TOKEN, REPOSITORY, TARGET_PR, OWNED
    )
    assert (state, numbers, complete) == (
        module.CollisionState.OVERLAP,
        (FOREIGN_PR,),
        True,
    )
    evidence = _snapshot_evidence(snapshot, FOREIGN_PR)
    assert evidence.owned_path_entries[0][1] != evidence.owned_path_entries[0][2]


def test_saturated_foreign_pr_truncated_tree_fails_closed() -> None:
    module = _module()
    http = SaturatedChangedHTTP(
        base_entry=_entry(),
        head_entry=_entry(),
        truncate_head_root=True,
    )
    with pytest.raises(module._RemoteProbeError):
        module._collision_census(http, TOKEN, REPOSITORY, TARGET_PR, OWNED)


@pytest.mark.parametrize(
    "identity",
    [
        {"number": FOREIGN_PR},
        {
            "number": FOREIGN_PR,
            "head": {"sha": HEAD, "repo": None},
            "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
        },
        {
            "number": FOREIGN_PR,
            "head": {"sha": "bad", "repo": {"full_name": REPOSITORY}},
            "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
        },
    ],
)
def test_saturated_foreign_pr_missing_immutable_identity_fails_closed(
    identity: dict[str, object],
) -> None:
    module = _module()
    http = SaturatedChangedHTTP(
        base_entry=_entry(), head_entry=_entry(), foreign_identity=identity
    )
    with pytest.raises(module._RemoteProbeError):
        module._collision_census(http, TOKEN, REPOSITORY, TARGET_PR, OWNED)


class NumberedParallelForeignHTTP:
    _source_continuity_parallel_safe = True

    def __init__(self, numbers: tuple[int, ...]) -> None:
        self.numbers = numbers
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.file_calls: list[int] = []

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        parsed = urlparse(url)
        if parsed.path.endswith("/pulls"):
            return [{"number": TARGET_PR}, *(
                {"number": number} for number in reversed(self.numbers)
            )]
        if parsed.path.endswith("/files"):
            number = int(parsed.path.split("/")[-2])
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                self.file_calls.append(number)
            time.sleep(0.08)
            with self.lock:
                self.active -= 1
            return [{"filename": f"docs/{number}.md", "status": "modified"}]
        raise AssertionError(url)


def test_numbered_parallel_foreign_observations_overlap_and_return_sorted_snapshot() -> None:
    module = _module()
    numbers = (8004, 8001, 8003, 8002)
    transport = NumberedParallelForeignHTTP(numbers)
    bounded = module._BoundedHTTPGet(transport)

    state, colliding, complete, snapshot = module._collision_census(
        bounded,
        TOKEN,
        REPOSITORY,
        TARGET_PR,
        OWNED,
    )

    assert (state, colliding, complete) == (
        module.CollisionState.DISJOINT,
        (),
        True,
    )
    assert transport.max_active >= 2
    assert tuple(number for number, _ in snapshot) == tuple(
        sorted((TARGET_PR, *numbers))
    )
    assert sorted(transport.file_calls) == sorted(numbers)


class MalformedTreeHTTP(SaturatedChangedHTTP):
    def __init__(self, defect: str) -> None:
        super().__init__(base_entry=_entry(), head_entry=_entry())
        self.defect = defect

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        payload = super().__call__(url, token=token, timeout=timeout)
        path = urlparse(url).path
        if path.endswith(f"/git/trees/{HEAD_ROOT}"):
            assert isinstance(payload, dict)
            rows = payload["tree"]
            assert isinstance(rows, list)
            if self.defect == "wrong_sha":
                payload["sha"] = "9" * 40
            elif self.defect == "unsafe_name":
                rows[0]["path"] = "engine/child"
            elif self.defect == "duplicate":
                rows.append(dict(rows[0]))
            elif self.defect == "mode_type":
                rows[0]["type"] = "blob"
            elif self.defect == "bad_size":
                rows[0]["size"] = -1
        return payload


@pytest.mark.parametrize(
    "defect",
    ["wrong_sha", "unsafe_name", "duplicate", "mode_type", "bad_size"],
)
def test_saturated_foreign_pr_malformed_tree_object_fails_closed(defect: str) -> None:
    module = _module()
    with pytest.raises(module._RemoteProbeError):
        module._collision_census(
            MalformedTreeHTTP(defect), TOKEN, REPOSITORY, TARGET_PR, OWNED
        )


class BadCompareHTTP(SaturatedDisjointHTTP):
    def __init__(self, defect: str) -> None:
        super().__init__()
        self.defect = defect

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        payload = super().__call__(url, token=token, timeout=timeout)
        if "/compare/" in url:
            assert isinstance(payload, dict)
            if self.defect == "base":
                payload["base_commit"] = {"sha": "9" * 40}
            elif self.defect == "merge_base":
                payload["merge_base_commit"] = {"sha": "bad"}
        return payload


@pytest.mark.parametrize("defect", ["base", "merge_base"])
def test_saturated_foreign_pr_compare_identity_mismatch_fails_closed(
    defect: str,
) -> None:
    module = _module()
    with pytest.raises(module._RemoteProbeError):
        module._collision_census(
            BadCompareHTTP(defect), TOKEN, REPOSITORY, TARGET_PR, OWNED
        )


class ExactHundredFilesHTTP:
    def __init__(self) -> None:
        self.pages: list[int] = []

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        parsed = urlparse(url)
        page = int(parse_qs(parsed.query)["page"][0])
        self.pages.append(page)
        if page == 1:
            return _bulk_rows(1)
        if page in {2, 30}:
            return []
        raise AssertionError(url)


def test_exact_hundred_foreign_files_remain_complete_not_saturated() -> None:
    module = _module()
    http = ExactHundredFilesHTTP()
    observation = module._foreign_files_observation(
        http, TOKEN, REPOSITORY, FOREIGN_PR
    )
    assert observation.saturated is False
    assert len(observation.paths) == 100
    assert http.pages == [1, 30, 2]


def test_parallel_shared_call_budget_never_overadmits(monkeypatch) -> None:
    module = _module()
    numbers = tuple(range(8100, 8112))
    transport = NumberedParallelForeignHTTP(numbers)
    bounded = module._BoundedHTTPGet(transport)
    monkeypatch.setattr(module, "_MAX_HTTP_CALLS", 6)

    with pytest.raises(module._ReadBudgetExceeded):
        module._collision_census(
            bounded,
            TOKEN,
            REPOSITORY,
            TARGET_PR,
            OWNED,
        )

    assert bounded._calls == 6
    assert len(transport.file_calls) == 5
    assert len(set(transport.file_calls)) == 5


def _sparse_repo(tmp_path: Path) -> tuple[Path, str]:
    import test_source_continuity_r3_hardening as r3

    repo = tmp_path / "sparse-source"
    head = r3.init_repo(repo, "owned")
    (repo / "outside.txt").write_text("outside\n", encoding="utf-8")
    r3.git(repo, "add", "outside.txt")
    r3.git(repo, "commit", "-qm", "add outside")
    head = r3.git(repo, "rev-parse", "HEAD^{commit}")
    r3.git(repo, "sparse-checkout", "init", "--no-cone")
    r3.git(repo, "sparse-checkout", "set", "value.txt")
    assert not (repo / "outside.txt").exists()
    assert r3.git(repo, "ls-files", "-v", "outside.txt").startswith("S ")
    return repo, head


def _probe_sparse(module, repo: Path, head: str):
    import test_source_continuity_r3_hardening as r3

    return module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        r3.request_with_owned_paths(module, repo, head, "value.txt"),
        head,
        head,
        (),
    )


def test_absent_out_of_scope_sparse_entry_does_not_block_clean_local_proof(
    tmp_path: Path,
) -> None:
    module = _module()
    repo, head = _sparse_repo(tmp_path)

    result = _probe_sparse(module, repo, head)

    assert not isinstance(result, module.SourceContinuityRefusal)
    local_facts, _ = result
    assert local_facts.uncommitted_in_scope_count == 0
    assert local_facts.uncommitted_out_of_scope_count == 0


def test_materialized_out_of_scope_sparse_entry_still_fails_closed(
    tmp_path: Path,
) -> None:
    module = _module()
    repo, _ = _sparse_repo(tmp_path)
    (repo / "outside.txt").write_text("concealed drift\n", encoding="utf-8")

    assert module._index_has_concealed_paths(
        "S outside.txt\0", str(repo), {"value.txt"}
    ) is True


@pytest.mark.parametrize(
    ("record", "protected"),
    [
        ("S value.txt\0", {"value.txt"}),
        ("h outside.txt\0", {"value.txt"}),
        ("s outside.txt\0", {"value.txt"}),
    ],
)
def test_owned_skip_or_any_assume_unchanged_entry_fails_closed(
    tmp_path: Path, record: str, protected: set[str]
) -> None:
    module = _module()
    repo, _ = _sparse_repo(tmp_path)

    assert module._index_has_concealed_paths(record, str(repo), protected) is True


class ConditionalRepresentationTransport:
    _source_continuity_conditional = True

    def __init__(self, module, *, changed_url: str | None = None) -> None:
        self.module = module
        self.changed_url = changed_url
        self.first_calls: list[str] = []
        self.conditional_calls: list[tuple[str, str]] = []

    @staticmethod
    def etag(url: str) -> str:
        import hashlib

        return 'W/"' + hashlib.sha256(url.encode("utf-8")).hexdigest() + '"'

    def __call__(
        self,
        url: str,
        *,
        token: str,
        timeout: float,
        if_none_match: str | None = None,
    ) -> object:
        assert token == TOKEN and timeout > 0
        etag = self.etag(url)
        if if_none_match is None:
            self.first_calls.append(url)
            return self.module._HTTPRepresentation(
                payload={"url": url, "value": "x" * 128},
                etag=etag,
                not_modified=False,
            )
        self.conditional_calls.append((url, if_none_match))
        if url == self.changed_url:
            return self.module._HTTPRepresentation(
                payload={"url": url, "value": "changed"},
                etag='"' + "f" * 64 + '"',
                not_modified=False,
            )
        return self.module._HTTPRepresentation(
            payload=None,
            etag=etag.removeprefix("W/"),
            not_modified=True,
        )


def test_conditional_validation_rechecks_every_representation_without_body_replay() -> None:
    module = _module()
    transport = ConditionalRepresentationTransport(module)
    bounded = module._BoundedHTTPGet(transport)
    urls = (
        "https://api.github.com/repos/example/repo/pulls?page=1",
        "https://api.github.com/repos/example/repo/pulls/7/files?page=1",
        "https://api.github.com/repos/example/repo/pulls/7/files?page=1",
    )

    payloads = [bounded(url, token=TOKEN, timeout=20.0) for url in urls]
    first_bytes = bounded._bytes

    assert all(payload["value"] == "x" * 128 for payload in payloads)
    assert bounded.conditional_validation_available is True
    assert bounded.validate_unchanged(token=TOKEN) is True
    assert bounded._bytes == first_bytes
    assert bounded._calls == len(urls) * 2
    assert sorted(url for url, _ in transport.conditional_calls) == sorted(urls)
    assert all(
        validator == transport.etag(url)
        for url, validator in transport.conditional_calls
    )


def test_conditional_changed_200_body_is_accounted_before_changed_result() -> None:
    module = _module()
    changed = "https://api.github.com/repos/example/repo/pulls/8/files?page=1"
    transport = ConditionalRepresentationTransport(module, changed_url=changed)
    bounded = module._BoundedHTTPGet(transport)
    bounded(changed, token=TOKEN, timeout=20.0)
    first_bytes = bounded._bytes

    assert bounded.validate_unchanged(token=TOKEN) is False
    assert bounded._bytes > first_bytes
    assert bounded._calls == 2


def test_conditional_304_with_body_refuses_without_accounting_body() -> None:
    module = _module()

    class BodyBearing304:
        _source_continuity_conditional = True

        def __call__(
            self,
            url: str,
            *,
            token: str,
            timeout: float,
            if_none_match: str | None = None,
        ) -> object:
            etag = '"abc"'
            if if_none_match is None:
                return module._HTTPRepresentation(
                    payload={"ok": True}, etag=etag, not_modified=False
                )
            return module._HTTPRepresentation(
                payload={"body": True}, etag=etag, not_modified=True
            )

    bounded = module._BoundedHTTPGet(BodyBearing304())
    bounded("https://api.github.com/repos/example/repo", token=TOKEN, timeout=20.0)
    first_bytes = bounded._bytes
    with pytest.raises(module._RemoteProbeError):
        bounded.validate_unchanged(token=TOKEN)
    assert bounded._bytes == first_bytes


@pytest.mark.parametrize("etag", [None, '"has space"', '"different"'])
def test_conditional_304_requires_single_equivalent_validator(etag: str | None) -> None:
    module = _module()

    class BadSecondValidator:
        _source_continuity_conditional = True

        def __call__(
            self,
            url: str,
            *,
            token: str,
            timeout: float,
            if_none_match: str | None = None,
        ) -> object:
            if if_none_match is None:
                return module._HTTPRepresentation(
                    payload={"ok": True}, etag='"original"', not_modified=False
                )
            return module._HTTPRepresentation(
                payload=None, etag=etag, not_modified=True
            )

    bounded = module._BoundedHTTPGet(BadSecondValidator())
    bounded("https://api.github.com/repos/example/repo", token=TOKEN, timeout=20.0)
    with pytest.raises(module._RemoteProbeError):
        bounded.validate_unchanged(token=TOKEN)


def test_duplicate_etag_headers_are_not_a_conditional_validator() -> None:
    module = _module()

    class DuplicateHeaders:
        @staticmethod
        def get_all(name: str) -> list[str]:
            assert name == "ETag"
            return ['"one"', '"two"']

    assert module._single_etag(DuplicateHeaders()) == ""


@pytest.mark.parametrize(
    "etag",
    [None, "", "not-quoted", 'W/"unterminated', '"has space"'],
)
def test_conditional_first_observation_requires_closed_etag(etag: str | None) -> None:
    module = _module()

    class BadETag:
        _source_continuity_conditional = True

        def __call__(self, url: str, *, token: str, timeout: float) -> object:
            return module._HTTPRepresentation(
                payload={"ok": True}, etag=etag, not_modified=False
            )

    bounded = module._BoundedHTTPGet(BadETag())
    with pytest.raises(module._RemoteProbeError):
        bounded("https://api.github.com/repos/example/repo", token=TOKEN, timeout=20.0)


class MainConditionalHTTP:
    _source_continuity_conditional = True

    def __init__(self, module, drift_url: str) -> None:
        import test_source_continuity as fx

        self.module = module
        self.base = fx._ProbeHTTP()
        self.drift_url = drift_url
        self.conditional_calls: list[tuple[str, str]] = []

    @staticmethod
    def etag(url: str) -> str:
        import hashlib

        return 'W/"' + hashlib.sha256(url.encode("utf-8")).hexdigest() + '"'

    def __call__(
        self,
        url: str,
        *,
        token: str,
        timeout: float,
        if_none_match: str | None = None,
    ) -> object:
        if if_none_match is not None:
            self.conditional_calls.append((url, if_none_match))
            if url == self.drift_url:
                return self.module._HTTPRepresentation(
                    payload={"changed": True},
                    etag='"' + "f" * 64 + '"',
                    not_modified=False,
                )
            return self.module._HTTPRepresentation(
                payload=None,
                etag=if_none_match.removeprefix("W/"),
                not_modified=True,
            )
        payload = self.base(url, token=token, timeout=timeout)
        return self.module._HTTPRepresentation(
            payload=payload,
            etag=self.etag(url),
            not_modified=False,
        )


def test_main_refuses_receipt_when_conditional_second_observation_changes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    import test_source_continuity as fx

    module = _module()
    drift_url = (
        f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/pulls/"
        f"{fx.PR_NUMBER}/files?per_page=100&page=1"
    )
    http = MainConditionalHTTP(module, drift_url)

    exit_code = fx._run_cli(module, fx._cli_argv(), http=http)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out)["code"] == "REMOTE_PROOF_CHANGED"
    assert any(url == drift_url for url, _ in http.conditional_calls)


from concurrent.futures import ThreadPoolExecutor
import threading
import time


class GateParallelForeignHTTP:
    _source_continuity_parallel_safe = True

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.release = threading.Event()
        self.inflight = 0
        self.overlapped = False
        self.calls: list[str] = []

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        self.calls.append(url)
        parsed = urlparse(url)
        if parsed.path.endswith("/pulls"):
            return [{"number": TARGET_PR}, {"number": 1002}, {"number": 1001}]
        if parsed.path.endswith("/files"):
            number = int(parsed.path.split("/")[-2])
            with self.lock:
                self.inflight += 1
                if self.inflight > 1:
                    self.overlapped = True
                    self.release.set()
                first = self.inflight == 1
            if first:
                self.release.wait(1.0)
            if number == 1001:
                time.sleep(0.03)
            with self.lock:
                self.inflight -= 1
            return [{"filename": f"docs/{number}.md", "status": "modified"}]
        raise AssertionError(url)


def test_collision_census_parallelizes_explicit_bounded_transport_and_sorts() -> None:
    module = _module()
    transport = GateParallelForeignHTTP()
    bounded = module._BoundedHTTPGet(transport)

    state, numbers, complete, snapshot = module._collision_census(
        bounded, TOKEN, REPOSITORY, TARGET_PR, OWNED
    )

    assert transport.overlapped is True
    assert (state, numbers, complete) == (
        module.CollisionState.DISJOINT,
        (),
        True,
    )
    assert snapshot == (
        (1001, ("docs/1001.md",)),
        (1002, ("docs/1002.md",)),
        (TARGET_PR, ()),
    )


def test_bounded_http_parallel_calls_share_exact_call_budget(monkeypatch) -> None:
    module = _module()
    transport = GateParallelForeignHTTP()
    monkeypatch.setattr(module, "_MAX_HTTP_CALLS", 2)
    bounded = module._BoundedHTTPGet(transport)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                bounded,
                f"https://api.github.com/repos/example/repo/pulls/{number}/files?per_page=100&page=1",
                token=TOKEN,
                timeout=20.0,
            )
            for number in (1001, 1002)
        ]
        assert all(future.result() for future in futures)

    with pytest.raises(module._ReadBudgetExceeded):
        bounded(
            "https://api.github.com/repos/example/repo/pulls/1003/files?per_page=100&page=1",
            token=TOKEN,
            timeout=20.0,
        )
    assert bounded._calls == 2
    assert len([url for url in transport.calls if "/files?" in url]) == 2
    bounded.check()


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError, Lock


class BarrierParallelForeignHTTP:
    _source_continuity_parallel_safe = True

    def __init__(self) -> None:
        self.barrier = Barrier(2)
        self.lock = Lock()
        self.active = 0
        self.max_active = 0

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        parsed = urlparse(url)
        if parsed.path.endswith("/pulls"):
            return [
                {"number": TARGET_PR},
                {"number": 9002},
                {"number": 9001},
            ]
        if parsed.path.endswith("/files"):
            number = int(parsed.path.split("/")[-2])
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                self.barrier.wait(timeout=3)
            except BrokenBarrierError as error:
                raise AssertionError("foreign observations did not overlap") from error
            finally:
                with self.lock:
                    self.active -= 1
            return [{"filename": f"docs/foreign-{number}.md", "status": "modified"}]
        raise AssertionError(url)


def test_parallel_foreign_observations_overlap_and_return_sorted_snapshot() -> None:
    module = _module()
    transport = BarrierParallelForeignHTTP()
    bounded = module._BoundedHTTPGet(transport)
    state, numbers, complete, snapshot = module._collision_census(
        bounded, TOKEN, REPOSITORY, TARGET_PR, OWNED
    )
    assert (state, numbers, complete) == (
        module.CollisionState.DISJOINT,
        (),
        True,
    )
    assert transport.max_active == 2
    assert [number for number, _ in snapshot] == [TARGET_PR, 9001, 9002]


class CountedParallelTransport:
    _source_continuity_parallel_safe = True

    def __init__(self) -> None:
        self.lock = Lock()
        self.calls = 0

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        with self.lock:
            self.calls += 1
        return {"url": url}


def test_parallel_budget_admits_exactly_the_shared_call_limit(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_MAX_HTTP_CALLS", 8)
    transport = CountedParallelTransport()
    bounded = module._BoundedHTTPGet(transport)

    def read(index: int) -> str:
        payload = bounded(
            f"https://api.github.com/repos/example/repo/{index}",
            token=TOKEN,
            timeout=20,
        )
        assert isinstance(payload, dict)
        return str(payload["url"])

    successes = 0
    refusals = 0
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(read, index) for index in range(16)]
        for future in futures:
            try:
                future.result()
                successes += 1
            except module._ReadBudgetExceeded:
                refusals += 1

    assert (successes, refusals, transport.calls) == (8, 8, 8)
    bounded.check()


class MultiOwnedDisjointHTTP(SaturatedDisjointHTTP):
    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        parsed = urlparse(url)
        if parsed.path.endswith(f"/git/trees/{ENGINE_TREE}"):
            self.calls.append(url)
            return _tree(ENGINE_TREE, [
                {
                    "path": "entry_signal.py", "mode": "100644", "type": "blob",
                    "sha": BLOB, "size": 123,
                },
                {
                    "path": "second.py", "mode": "100644", "type": "blob",
                    "sha": "9" * 40, "size": 45,
                },
            ])
        return super().__call__(url, token=token, timeout=timeout)


def test_saturated_tree_objects_are_fetched_once_per_immutable_sha() -> None:
    module = _module()
    http = MultiOwnedDisjointHTTP()
    owned = ("engine/entry_signal.py", "engine/second.py")
    state, numbers, complete, _ = module._collision_census(
        http, TOKEN, REPOSITORY, TARGET_PR, owned
    )
    assert (state, numbers, complete) == (
        module.CollisionState.DISJOINT,
        (),
        True,
    )
    paths = [urlparse(url).path for url in http.calls]
    assert paths.count(f"/repos/{REPOSITORY}/git/commits/{MERGE_BASE}") == 1
    assert paths.count(f"/repos/{REPOSITORY}/git/commits/{HEAD}") == 1
    assert paths.count(f"/repos/{REPOSITORY}/git/trees/{ENGINE_TREE}") == 1


TARGET_BRANCH = "fixture-target"
TARGET_HEAD = "4" * 40
TARGET_BASE_HEAD = "5" * 40
DRIFTED_FOREIGN_HEAD = "6" * 40
DRIFTED_HEAD_ROOT = "7" * 40


def _target_pr_payload() -> dict[str, object]:
    return {
        "state": "open",
        "draft": True,
        "labels": [],
        "head": {
            "ref": TARGET_BRANCH,
            "sha": TARGET_HEAD,
            "repo": {"full_name": REPOSITORY},
        },
        "base": {"ref": "main"},
    }


class SaturatedForeignIdentityDriftHTTP:
    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        parsed = urlparse(url)
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        if parsed.path.endswith(f"/pulls/{TARGET_PR}"):
            return _target_pr_payload()
        if parsed.path.endswith(f"/branches/{TARGET_BRANCH}"):
            return {"commit": {"sha": TARGET_HEAD}}
        if parsed.path.endswith("/branches/main"):
            return {"commit": {"sha": TARGET_BASE_HEAD}}
        if parsed.path.endswith(f"/pulls/{TARGET_PR}/files"):
            return [{"filename": OWNED[0], "status": "modified"}]
        if parsed.path.endswith("/pulls"):
            return [
                {"number": TARGET_PR},
                {
                    "number": FOREIGN_PR,
                    "head": {
                        "sha": DRIFTED_FOREIGN_HEAD,
                        "repo": {"full_name": REPOSITORY},
                    },
                    "base": {
                        "sha": BASE,
                        "repo": {"full_name": REPOSITORY},
                    },
                },
            ]
        if parsed.path.endswith(f"/pulls/{FOREIGN_PR}/files"):
            if page in {1, 30}:
                return _bulk_rows(page)
            raise AssertionError(url)
        if parsed.path.endswith(f"/compare/{BASE}...{DRIFTED_FOREIGN_HEAD}"):
            return {
                "url": url,
                "base_commit": {"sha": BASE},
                "merge_base_commit": {"sha": MERGE_BASE},
            }
        if parsed.path.endswith(f"/git/commits/{MERGE_BASE}"):
            return {"sha": MERGE_BASE, "tree": {"sha": BASE_ROOT}}
        if parsed.path.endswith(f"/git/commits/{DRIFTED_FOREIGN_HEAD}"):
            return {"sha": DRIFTED_FOREIGN_HEAD, "tree": {"sha": DRIFTED_HEAD_ROOT}}
        if parsed.path.endswith(f"/git/trees/{BASE_ROOT}"):
            return _tree(BASE_ROOT, [{
                "path": "engine", "mode": "040000", "type": "tree",
                "sha": ENGINE_TREE,
            }])
        if parsed.path.endswith(f"/git/trees/{DRIFTED_HEAD_ROOT}"):
            return _tree(DRIFTED_HEAD_ROOT, [{
                "path": "engine", "mode": "040000", "type": "tree",
                "sha": ENGINE_TREE,
            }])
        if parsed.path.endswith(f"/git/trees/{ENGINE_TREE}"):
            return _tree(ENGINE_TREE, [{
                "path": "entry_signal.py", "mode": "100644", "type": "blob",
                "sha": BLOB, "size": 123,
            }])
        raise AssertionError(url)


def test_second_observation_rejects_saturated_foreign_identity_drift() -> None:
    module = _module()
    first_http = SaturatedDisjointHTTP()
    first_state, first_numbers, first_complete, first_snapshot = (
        module._collision_census(
            first_http,
            TOKEN,
            REPOSITORY,
            TARGET_PR,
            OWNED,
        )
    )
    assert (first_state, first_numbers, first_complete) == (
        module.CollisionState.DISJOINT,
        (),
        True,
    )
    request = module.SourceContinuityRequest(
        receipt_kind=module.ReceiptKind.CHECKPOINT_VERIFIED,
        operation_key="source-continuity-saturated-foreign-pr-test",
        repository=REPOSITORY,
        pr_number=TARGET_PR,
        branch=TARGET_BRANCH,
        base_ref="main",
        pinned_base_sha=TARGET_BASE_HEAD,
        owned_paths=OWNED,
        verified_at="2026-09-09T00:00:00Z",
    )
    result = module._remote_still_matches(
        SaturatedForeignIdentityDriftHTTP(),
        TOKEN,
        request,
        module._pr_identity(_target_pr_payload()),
        TARGET_HEAD,
        TARGET_BASE_HEAD,
        OWNED,
        True,
        first_state,
        first_numbers,
        first_complete,
        first_snapshot,
    )
    assert result is not None
    assert result.code.value == "REMOTE_PROOF_CHANGED"


@pytest.mark.parametrize("bad_url", [
    None,
    "",
    f"https://api.github.com/repos/{REPOSITORY}/compare/{BASE}...{BASE}",
    f"https://api.github.com/repos/another/repository/compare/{BASE}...{HEAD}",
    f"https://invalid.example/repos/{REPOSITORY}/compare/{BASE}...{HEAD}",
    f"https://api.github.com/repos/{REPOSITORY}/compare/{HEAD}...{BASE}",
])
def test_saturated_compare_representation_binds_exact_requested_url(bad_url) -> None:
    module = _module()

    class MisboundCompareHTTP(SaturatedChangedHTTP):
        def __call__(self, url: str, *, token: str, timeout: float) -> object:
            payload = super().__call__(url, token=token, timeout=timeout)
            if urlparse(url).path.endswith(f"/compare/{BASE}...{HEAD}"):
                if bad_url is None:
                    payload.pop("url")
                else:
                    payload["url"] = bad_url
                payload["merge_base_commit"] = {"sha": HEAD}
            return payload

    control = SaturatedChangedHTTP(base_entry=_entry(), head_entry=_entry("3" * 40))
    state, colliding, complete, _ = module._collision_census(
        control, TOKEN, REPOSITORY, TARGET_PR, OWNED
    )
    assert (state, colliding, complete) == (module.CollisionState.OVERLAP, (FOREIGN_PR,), True)

    hostile = MisboundCompareHTTP(base_entry=_entry(), head_entry=_entry("3" * 40))
    with pytest.raises(module._RemoteProbeError):
        module._collision_census(hostile, TOKEN, REPOSITORY, TARGET_PR, OWNED)
    assert not any("/git/commits/" in url for url in hostile.calls)
