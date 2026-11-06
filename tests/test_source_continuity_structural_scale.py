"""Structural Source Continuity scale: resources, not PR cardinality, bound proof."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

import test_source_continuity as fx
import test_source_continuity_census_budget as budget


class IdentityEstateHTTP(budget.EstateHTTP):
    """Budget fixture whose foreign roster rows carry immutable GitHub identity."""

    @staticmethod
    def _foreign_row(number: int) -> dict[str, object]:
        return {
            "number": number,
            "state": "open",
            "head": {
                "sha": f"{number:040x}",
                "repo": {"full_name": fx.REPOSITORY},
            },
            "base": {
                "sha": fx.CURRENT_BASE_SHA,
                "repo": {"full_name": fx.REPOSITORY},
            },
        }

    @staticmethod
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

    def __call__(self, url, *, token, timeout):
        parsed = urlparse(url)
        if parsed.path.endswith("/pulls"):
            page = int(parse_qs(parsed.query).get("page", ["1"])[0])
            self.calls.append((url, token, timeout))
            if page == 1:
                self.passes += 1
            rows = [self._target_row()] + [
                self._foreign_row(1000 + i) for i in range(self.count - 1)
            ]
            result = rows[(page - 1) * 100:page * 100]
            if self.after_read:
                self.after_read(url, result)
            return result
        return super().__call__(url, token=token, timeout=timeout)


def test_complete_identity_estate_above_490_is_bounded_by_existing_resources(
    capsys, monkeypatch
) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock(), raising=False)
    http = IdentityEstateHTTP(500)

    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 0, payload
    assert payload["collision_state"] == "DISJOINT"
    assert payload["authority_effect"] == "NONE"
    assert payload["merge_authorized"] is False
    assert payload["writer_release_authorized"] is False
    assert http.passes == 2
    assert len(http.calls) < module._MAX_HTTP_CALLS
    assert module._MAX_HTTP_CALLS == 1152
    assert module._MAX_HTTP_NORMALIZED_BYTES == 128 * 1024 * 1024
    assert module._HTTP_READ_BUDGET_SECONDS == 300.0


def test_full_ten_page_roster_still_refuses_before_foreign_file_enumeration(
    capsys, monkeypatch
) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock(), raising=False)
    http = IdentityEstateHTTP(1000)

    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 2
    assert payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert not any(
        "/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
        for url, _, _ in http.calls
    )


CURRENT_BASE_SHA = "e" * 40
FOREIGN_HEAD_SHA = "f" * 40
FOREIGN_BASE_SHA = "d" * 40
CURRENT_BASE_ROOT = "1" * 40
FOREIGN_HEAD_ROOT = "2" * 40
CURRENT_BASE_ENGINE = "3" * 40
FOREIGN_HEAD_ENGINE = "4" * 40
SAME_BLOB = "5" * 40
OTHER_BLOB = "6" * 40
FOREIGN_PR = 991
MATERIAL_OWNED = ("engine/entry_signal.py",)


def _tree(sha: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {"sha": sha, "truncated": False, "tree": rows}


def _foreign_row() -> dict[str, object]:
    return {
        "number": FOREIGN_PR,
        "state": "open",
        "head": {
            "sha": FOREIGN_HEAD_SHA,
            "repo": {"full_name": fx.REPOSITORY},
        },
        "base": {
            "sha": FOREIGN_BASE_SHA,
            "repo": {"full_name": fx.REPOSITORY},
        },
    }


def _blob_entry(sha: str = SAME_BLOB, *, mode: str = "100644") -> dict[str, object]:
    return {
        "path": "entry_signal.py",
        "mode": mode,
        "type": "blob",
        "sha": sha,
        "size": 123,
    }


class CurrentBaseOverlapHTTP:
    """One ordinary roster overlap with exact current-base/head tree evidence."""

    def __init__(self, foreign_entry: dict[str, object] | None) -> None:
        self.foreign_entry = foreign_entry
        self.calls: list[str] = []

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == fx.TOKEN and timeout > 0
        self.calls.append(url)
        parsed = urlparse(url)

        if parsed.path.endswith(f"/pulls/{FOREIGN_PR}/files"):
            return [{"filename": MATERIAL_OWNED[0], "status": "modified"}]

        if parsed.path.endswith(f"/git/commits/{CURRENT_BASE_SHA}"):
            return {"sha": CURRENT_BASE_SHA, "tree": {"sha": CURRENT_BASE_ROOT}}
        if parsed.path.endswith(f"/git/commits/{FOREIGN_HEAD_SHA}"):
            return {"sha": FOREIGN_HEAD_SHA, "tree": {"sha": FOREIGN_HEAD_ROOT}}

        if parsed.path.endswith(f"/git/trees/{CURRENT_BASE_ROOT}"):
            return _tree(CURRENT_BASE_ROOT, [{
                "path": "engine",
                "mode": "040000",
                "type": "tree",
                "sha": CURRENT_BASE_ENGINE,
            }])
        if parsed.path.endswith(f"/git/trees/{FOREIGN_HEAD_ROOT}"):
            return _tree(FOREIGN_HEAD_ROOT, [{
                "path": "engine",
                "mode": "040000",
                "type": "tree",
                "sha": FOREIGN_HEAD_ENGINE,
            }])
        if parsed.path.endswith(f"/git/trees/{CURRENT_BASE_ENGINE}"):
            return _tree(CURRENT_BASE_ENGINE, [_blob_entry()])
        if parsed.path.endswith(f"/git/trees/{FOREIGN_HEAD_ENGINE}"):
            rows = [] if self.foreign_entry is None else [self.foreign_entry]
            return _tree(FOREIGN_HEAD_ENGINE, rows)

        raise AssertionError(url)


def test_ordinary_roster_overlap_equal_to_current_target_base_is_history_only() -> None:
    module = fx._cli_module()
    http = CurrentBaseOverlapHTTP(_blob_entry())

    evidence, overlaps = module._foreign_collision_evidence(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        _foreign_row(),
        FOREIGN_PR,
        MATERIAL_OWNED,
        current_base_head=CURRENT_BASE_SHA,
    )

    assert overlaps is False
    assert evidence.proof_method == "CURRENT_TARGET_BASE_TREE_EQUALITY"
    assert evidence.target_base_sha == CURRENT_BASE_SHA
    assert evidence.head_sha == FOREIGN_HEAD_SHA
    assert evidence.owned_path_entries[0][0] == MATERIAL_OWNED[0]
    assert evidence.owned_path_entries[0][1] == evidence.owned_path_entries[0][2]


def test_ordinary_roster_overlap_with_different_head_entry_remains_collision() -> None:
    module = fx._cli_module()
    http = CurrentBaseOverlapHTTP(_blob_entry(OTHER_BLOB))

    evidence, overlaps = module._foreign_collision_evidence(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        _foreign_row(),
        FOREIGN_PR,
        MATERIAL_OWNED,
        current_base_head=CURRENT_BASE_SHA,
    )

    assert overlaps is True
    assert evidence.owned_path_entries[0][1] != evidence.owned_path_entries[0][2]


def test_ordinary_roster_overlap_with_missing_head_entry_remains_collision() -> None:
    module = fx._cli_module()
    http = CurrentBaseOverlapHTTP(None)

    evidence, overlaps = module._foreign_collision_evidence(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        _foreign_row(),
        FOREIGN_PR,
        MATERIAL_OWNED,
        current_base_head=CURRENT_BASE_SHA,
    )

    assert overlaps is True
    assert evidence.owned_path_entries[0][2] is None


class CurrentBaseCensusHTTP(CurrentBaseOverlapHTTP):
    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        parsed = urlparse(url)
        if parsed.path.endswith("/pulls"):
            self.calls.append(url)
            return [
                {"number": fx.PR_NUMBER, "state": "open"},
                _foreign_row(),
            ]
        return super().__call__(url, token=token, timeout=timeout)


def test_collision_census_uses_current_target_base_materiality() -> None:
    module = fx._cli_module()

    equal_http = CurrentBaseCensusHTTP(_blob_entry())
    state, numbers, complete, _snapshot = module._collision_census(
        equal_http,
        fx.TOKEN,
        fx.REPOSITORY,
        fx.PR_NUMBER,
        MATERIAL_OWNED,
        current_base_head=CURRENT_BASE_SHA,
    )
    assert (state, numbers, complete) == (
        module.CollisionState.DISJOINT,
        (),
        True,
    )

    changed_http = CurrentBaseCensusHTTP(_blob_entry(OTHER_BLOB))
    state, numbers, complete, _snapshot = module._collision_census(
        changed_http,
        fx.TOKEN,
        fx.REPOSITORY,
        fx.PR_NUMBER,
        MATERIAL_OWNED,
        current_base_head=CURRENT_BASE_SHA,
    )
    assert (state, numbers, complete) == (
        module.CollisionState.OVERLAP,
        (FOREIGN_PR,),
        True,
    )


class SaturatedCurrentBaseHTTP(CurrentBaseOverlapHTTP):
    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        parsed = urlparse(url)
        if parsed.path.endswith(f"/pulls/{FOREIGN_PR}/files"):
            self.calls.append(url)
            page = int(parse_qs(parsed.query).get("page", ["1"])[0])
            if page in {1, 30}:
                return [
                    {
                        "filename": f"bulk/page-{page:02d}-{i:03d}.dat",
                        "status": "modified",
                    }
                    for i in range(100)
                ]
            raise AssertionError(url)
        return super().__call__(url, token=token, timeout=timeout)


def test_saturated_foreign_pr_uses_current_target_base_for_owned_paths() -> None:
    module = fx._cli_module()
    http = SaturatedCurrentBaseHTTP(_blob_entry())

    evidence, overlaps = module._foreign_collision_evidence(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        _foreign_row(),
        FOREIGN_PR,
        MATERIAL_OWNED,
        current_base_head=CURRENT_BASE_SHA,
    )

    assert overlaps is False
    assert evidence.proof_method == "CURRENT_TARGET_BASE_TREE_EQUALITY"
    assert evidence.target_base_sha == CURRENT_BASE_SHA
    assert evidence.owned_path_entries[0][1] == evidence.owned_path_entries[0][2]


def test_remote_prefix_binds_observed_current_base_into_collision_census(
    monkeypatch
) -> None:
    module = fx._cli_module()
    observed: dict[str, object] = {}
    original = module._collision_census_details

    def capture(*args, **kwargs):
        observed["current_base_head"] = kwargs.get("current_base_head")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "_collision_census_details", capture)
    result = module._probe_remote_prefix(
        fx._ProbeHTTP(),
        fx.TOKEN,
        fx._request(module),
    )

    assert not isinstance(result, module.SourceContinuityRefusal)
    assert observed["current_base_head"] == fx.CURRENT_BASE_SHA


def test_identity_estate_600_reuses_first_pass_evidence_within_existing_call_budget(
    capsys, monkeypatch
) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock(), raising=False)
    http = IdentityEstateHTTP(600)

    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 0, payload
    assert payload["collision_state"] == "DISJOINT"
    assert http.passes == 2
    foreign_file_calls = [
        url for url, _, _ in http.calls
        if "/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
    ]
    assert len(foreign_file_calls) == 599
    assert len(http.calls) < module._MAX_HTTP_CALLS == 1152


MOVED_HEAD_SHA = "7" * 40
MOVED_HEAD_ROOT = "8" * 40
MOVED_HEAD_ENGINE = "9" * 40


def _moved_foreign_row() -> dict[str, object]:
    row = _foreign_row()
    row["head"] = {
        "sha": MOVED_HEAD_SHA,
        "repo": {"full_name": fx.REPOSITORY},
    }
    return row


class MovedColliderHTTP(CurrentBaseOverlapHTTP):
    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        parsed = urlparse(url)
        if parsed.path.endswith("/pulls"):
            self.calls.append(url)
            return [
                {"number": fx.PR_NUMBER, "state": "open"},
                _moved_foreign_row(),
            ]
        if parsed.path.endswith(f"/git/commits/{MOVED_HEAD_SHA}"):
            self.calls.append(url)
            return {"sha": MOVED_HEAD_SHA, "tree": {"sha": MOVED_HEAD_ROOT}}
        if parsed.path.endswith(f"/git/trees/{MOVED_HEAD_ROOT}"):
            self.calls.append(url)
            return _tree(MOVED_HEAD_ROOT, [{
                "path": "engine",
                "mode": "040000",
                "type": "tree",
                "sha": MOVED_HEAD_ENGINE,
            }])
        if parsed.path.endswith(f"/git/trees/{MOVED_HEAD_ENGINE}"):
            self.calls.append(url)
            return _tree(MOVED_HEAD_ENGINE, [_blob_entry(OTHER_BLOB)])
        return super().__call__(url, token=token, timeout=timeout)


def test_moved_collider_with_same_exact_overlap_projection_is_reproved() -> None:
    module = fx._cli_module()
    target_entry = module._GitTreeEntry("100644", "blob", SAME_BLOB)
    first_head_entry = module._GitTreeEntry("100644", "blob", OTHER_BLOB)
    first_identity = module._ForeignPullIdentity(
        FOREIGN_PR,
        fx.REPOSITORY,
        FOREIGN_HEAD_SHA,
        fx.REPOSITORY,
        FOREIGN_BASE_SHA,
    )
    first_evidence = module._CurrentBaseCollisionEvidence(
        pr_number=FOREIGN_PR,
        proof_method="CURRENT_TARGET_BASE_TREE_EQUALITY",
        head_repository=fx.REPOSITORY,
        head_sha=FOREIGN_HEAD_SHA,
        target_repository=fx.REPOSITORY,
        target_base_sha=CURRENT_BASE_SHA,
        owned_path_entries=((MATERIAL_OWNED[0], target_entry, first_head_entry),),
    )
    first_record = module._ForeignCollisionRecord(
        pr_number=FOREIGN_PR,
        identity=first_identity,
        evidence=first_evidence,
        overlaps=True,
    )

    matches, complete, final_records = module._revalidate_collision_census(
        MovedColliderHTTP(_blob_entry(OTHER_BLOB)),
        fx.TOKEN,
        fx.REPOSITORY,
        fx.PR_NUMBER,
        MATERIAL_OWNED,
        (first_record,),
        (FOREIGN_PR,),
        current_base_head=CURRENT_BASE_SHA,
    )

    assert (matches, complete) == (True, True)
    assert len(final_records) == 1
    assert final_records[0].pr_number == FOREIGN_PR


def test_receipt_binds_final_collision_evidence_with_v2_digest(
    capsys, monkeypatch
) -> None:
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock(), raising=False)
    http = IdentityEstateHTTP(2)

    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 0, payload
    assert payload["receipt_version"] == "v2"
    assert len(payload["collision_evidence_fingerprint"]) == 64


import subprocess
import test_source_continuity_r3_hardening as r3


def _subject_materiality_repo(tmp_path, *, current_base_has_historical: bool):
    repo = tmp_path / "subject-materiality"
    r3.init_repo(repo, "seed")
    (repo / "owned.txt").write_text("base-owned\n", encoding="utf-8")
    (repo / "historical.txt").write_text("base-historical\n", encoding="utf-8")
    r3.git(repo, "add", "owned.txt", "historical.txt")
    r3.git(repo, "commit", "-qm", "subject merge base")
    merge_base = r3.git(repo, "rev-parse", "HEAD")

    if current_base_has_historical:
        r3.git(repo, "checkout", "-qb", "current-base")
        (repo / "historical.txt").write_text("shared-historical\n", encoding="utf-8")
        r3.git(repo, "add", "historical.txt")
        r3.git(repo, "commit", "-qm", "current base carries historical row")
        current_base = r3.git(repo, "rev-parse", "HEAD")
    else:
        current_base = merge_base

    r3.git(repo, "checkout", "-qb", "subject", merge_base)
    (repo / "historical.txt").write_text("shared-historical\n", encoding="utf-8")
    (repo / "owned.txt").write_text("subject-owned\n", encoding="utf-8")
    r3.git(repo, "add", "historical.txt", "owned.txt")
    r3.git(repo, "commit", "-qm", "subject candidate")
    remote_head = r3.git(repo, "rev-parse", "HEAD")
    return repo, merge_base, current_base, remote_head


def test_subject_effective_delta_drops_historical_row_already_in_current_base(
    tmp_path
) -> None:
    module = fx._cli_module()
    repo, merge_base, current_base, remote_head = _subject_materiality_repo(
        tmp_path,
        current_base_has_historical=True,
    )
    request = fx._request(
        module,
        branch="subject",
        owned_paths=("owned.txt",),
    )

    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        request,
        remote_head,
        merge_base,
        ("historical.txt", "owned.txt"),
        current_base_head=current_base,
    )

    assert not isinstance(result, module.SourceContinuityRefusal)
    local_facts, path_entries, effective_paths = result
    assert local_facts.head_sha == remote_head
    assert effective_paths == ("owned.txt",)
    assert tuple(entry.path for entry in path_entries) == ("owned.txt",)


def test_subject_effective_delta_still_refuses_real_out_of_scope_current_path(
    tmp_path
) -> None:
    module = fx._cli_module()
    repo, merge_base, current_base, remote_head = _subject_materiality_repo(
        tmp_path,
        current_base_has_historical=False,
    )
    request = fx._request(
        module,
        branch="subject",
        owned_paths=("owned.txt",),
    )

    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        request,
        remote_head,
        merge_base,
        ("historical.txt", "owned.txt"),
        current_base_head=current_base,
    )

    assert isinstance(result, module.SourceContinuityRefusal)
    assert result.code is module.RefusalCode.PATH_OUTSIDE_OWNERSHIP


def test_main_receipt_uses_effective_current_subject_delta_not_historical_roster(
    monkeypatch
) -> None:
    module = fx._cli_module()
    effective_path = fx.FINAL_OWNED_PATHS[0]
    historical_path = "docs/history-only.md"
    observed: dict[str, object] = {}

    first_identity = (
        "open",
        True,
        fx.BRANCH,
        fx.HEAD_SHA,
        fx.REPOSITORY,
        "master",
    )
    remote_prefix = (
        first_identity,
        fx.REPOSITORY,
        fx.BRANCH,
        "master",
        fx.HEAD_SHA,
        fx.TREE_SHA,
        fx.BASE_SHA,
        fx.CURRENT_BASE_SHA,
        (historical_path, effective_path),
        True,
        module.CollisionState.NONE,
        (),
        True,
        ((fx.PR_NUMBER, ()),),
        (),
    )

    monkeypatch.setattr(
        module,
        "_probe_remote_prefix",
        lambda *_args, **_kwargs: remote_prefix,
    )

    local = module.LocalGitFacts(
        branch=fx.BRANCH,
        head_sha=fx.HEAD_SHA,
        tree_sha=fx.TREE_SHA,
        remote_head_object_exists=True,
        remote_head_is_ancestor_of_local=True,
        unpushed_commit_count=0,
        uncommitted_in_scope_count=0,
        untracked_in_scope_count=0,
        uncommitted_out_of_scope_count=0,
        untracked_out_of_scope_count=0,
    )
    entry = module.RemotePathEntry(
        path=effective_path,
        mode="100644",
        object_type="blob",
        object_sha=fx.BLOB_A,
        size=123,
    )

    def local_probe(*_args, **kwargs):
        observed["local_current_base"] = kwargs.get("current_base_head")
        return local, (entry,), (effective_path,)

    monkeypatch.setattr(module, "_probe_local_and_entries", local_probe)
    monkeypatch.setattr(
        module,
        "_remote_still_matches",
        lambda *_args, **_kwargs: module._RemoteRevalidation(
            fx.CURRENT_BASE_SHA, fx.BASE_SHA, ()
        ),
    )

    def verify(_request, _local, remote, _external):
        observed["receipt_changed_paths"] = remote.changed_paths
        return object()

    monkeypatch.setattr(module, "verify_source_continuity", verify)
    monkeypatch.setattr(module, "_emit", lambda _result: 0)

    rc = module.main(
        fx._cli_argv(),
        runner=lambda *_args, **_kwargs: None,
        http_get=lambda *_args, **_kwargs: None,
        environ={"GITHUB_TOKEN": fx.TOKEN},
        clock=lambda: fx.VERIFIED_AT,
    )

    assert rc == 0
    assert observed["local_current_base"] == fx.CURRENT_BASE_SHA
    assert observed["receipt_changed_paths"] == (effective_path,)


def test_main_recomputes_effective_subject_delta_after_accepted_base_move(monkeypatch) -> None:
    module = fx._cli_module()
    old_base = fx.CURRENT_BASE_SHA
    new_base = "4" * 40
    first_path, refreshed_path = fx.FINAL_OWNED_PATHS[:2]
    observed: dict[str, object] = {"probe_bases": []}

    first_identity = (
        "open",
        True,
        fx.BRANCH,
        fx.HEAD_SHA,
        fx.REPOSITORY,
        "master",
    )
    remote_prefix = (
        first_identity,
        fx.REPOSITORY,
        fx.BRANCH,
        "master",
        fx.HEAD_SHA,
        fx.TREE_SHA,
        fx.BASE_SHA,
        old_base,
        (first_path, refreshed_path),
        True,
        module.CollisionState.NONE,
        (),
        True,
        ((fx.PR_NUMBER, ()),),
        (),
    )
    monkeypatch.setattr(module, "_probe_remote_prefix", lambda *_args, **_kwargs: remote_prefix)

    local = module.LocalGitFacts(
        branch=fx.BRANCH,
        head_sha=fx.HEAD_SHA,
        tree_sha=fx.TREE_SHA,
        remote_head_object_exists=True,
        remote_head_is_ancestor_of_local=True,
        unpushed_commit_count=0,
        uncommitted_in_scope_count=0,
        untracked_in_scope_count=0,
        uncommitted_out_of_scope_count=0,
        untracked_out_of_scope_count=0,
    )

    def entry(path: str, sha: str) -> object:
        return module.RemotePathEntry(
            path=path,
            mode="100644",
            object_type="blob",
            object_sha=sha,
            size=123,
        )

    def local_probe(*_args, **kwargs):
        base = kwargs.get("current_base_head")
        observed["probe_bases"].append(base)
        if base == old_base:
            return local, (entry(first_path, fx.BLOB_A),), (first_path,)
        if base == new_base:
            return local, (entry(refreshed_path, fx.BLOB_B),), (refreshed_path,)
        raise AssertionError(base)

    monkeypatch.setattr(module, "_probe_local_and_entries", local_probe)
    monkeypatch.setattr(
        module,
        "_remote_still_matches",
        lambda *_args, **_kwargs: module._RemoteRevalidation(
            new_base,
            fx.BASE_SHA,
            (),
        ),
    )

    def verify(_request, _local, remote, _external):
        observed["receipt_base"] = remote.current_base_head_sha
        observed["receipt_paths"] = remote.changed_paths
        observed["entry_paths"] = tuple(item.path for item in remote.path_entries)
        return object()

    monkeypatch.setattr(module, "verify_source_continuity", verify)
    monkeypatch.setattr(module, "_emit", lambda _result: 0)

    rc = module.main(
        fx._cli_argv(),
        runner=lambda *_args, **_kwargs: None,
        http_get=lambda *_args, **_kwargs: None,
        environ={"GITHUB_TOKEN": fx.TOKEN},
        clock=lambda: fx.VERIFIED_AT,
    )

    assert rc == 0
    assert observed["probe_bases"] == [old_base, new_base]
    assert observed["receipt_base"] == new_base
    assert observed["receipt_paths"] == (refreshed_path,)
    assert observed["entry_paths"] == (refreshed_path,)


MULTI_FOREIGN_PRS = (991, 992)
MULTI_FOREIGN_ROOT = "a" * 40
MULTI_FOREIGN_ENGINE = "b" * 40


def _multi_foreign_row(number: int) -> dict[str, object]:
    return {
        "number": number,
        "state": "open",
        "head": {
            "sha": f"{number:040x}",
            "repo": {"full_name": fx.REPOSITORY},
        },
        "base": {
            "sha": FOREIGN_BASE_SHA,
            "repo": {"full_name": fx.REPOSITORY},
        },
    }


class MultipleCurrentBaseOverlapHTTP:
    """Two historical overlaps must share one immutable target-base lookup."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == fx.TOKEN and timeout > 0
        self.calls.append(url)
        parsed = urlparse(url)

        if parsed.path.endswith("/pulls"):
            return [
                {"number": fx.PR_NUMBER, "state": "open"},
                *[_multi_foreign_row(number) for number in MULTI_FOREIGN_PRS],
            ]

        for number in MULTI_FOREIGN_PRS:
            if parsed.path.endswith(f"/pulls/{number}/files"):
                return [{"filename": MATERIAL_OWNED[0], "status": "modified"}]
            if parsed.path.endswith(f"/git/commits/{number:040x}"):
                return {
                    "sha": f"{number:040x}",
                    "tree": {"sha": MULTI_FOREIGN_ROOT},
                }

        if parsed.path.endswith(f"/git/commits/{CURRENT_BASE_SHA}"):
            return {
                "sha": CURRENT_BASE_SHA,
                "tree": {"sha": CURRENT_BASE_ROOT},
            }
        if parsed.path.endswith(f"/git/trees/{CURRENT_BASE_ROOT}"):
            return _tree(
                CURRENT_BASE_ROOT,
                [{
                    "path": "engine",
                    "mode": "040000",
                    "type": "tree",
                    "sha": CURRENT_BASE_ENGINE,
                }],
            )
        if parsed.path.endswith(f"/git/trees/{CURRENT_BASE_ENGINE}"):
            return _tree(CURRENT_BASE_ENGINE, [_blob_entry()])
        if parsed.path.endswith(f"/git/trees/{MULTI_FOREIGN_ROOT}"):
            return _tree(
                MULTI_FOREIGN_ROOT,
                [{
                    "path": "engine",
                    "mode": "040000",
                    "type": "tree",
                    "sha": MULTI_FOREIGN_ENGINE,
                }],
            )
        if parsed.path.endswith(f"/git/trees/{MULTI_FOREIGN_ENGINE}"):
            return _tree(MULTI_FOREIGN_ENGINE, [_blob_entry()])

        raise AssertionError(url)


def test_current_target_base_entries_are_resolved_once_per_collision_census() -> None:
    module = fx._cli_module()
    http = MultipleCurrentBaseOverlapHTTP()

    details = module._collision_census_details(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        fx.PR_NUMBER,
        MATERIAL_OWNED,
        current_base_head=CURRENT_BASE_SHA,
    )

    assert details.state is module.CollisionState.DISJOINT
    assert details.colliding_pr_numbers == ()
    assert len(details.foreign_records) == len(MULTI_FOREIGN_PRS)
    assert sum(
        urlparse(url).path.endswith(f"/git/commits/{CURRENT_BASE_SHA}")
        for url in http.calls
    ) == 1
    assert sum(
        urlparse(url).path.endswith(f"/git/trees/{CURRENT_BASE_ROOT}")
        for url in http.calls
    ) == 1
    assert sum(
        urlparse(url).path.endswith(f"/git/trees/{CURRENT_BASE_ENGINE}")
        for url in http.calls
    ) == 1


def _compact_files_payload(
    rows: list[tuple[str, str]],
    *,
    changed_files: int | None = None,
    has_next: bool = False,
    end_cursor: str | None = None,
    files_null: bool = False,
    head_sha: str = FOREIGN_HEAD_SHA,
) -> dict[str, object]:
    total = len(rows) if changed_files is None else changed_files
    files: object = None
    if not files_null:
        files = {
            "totalCount": total,
            "nodes": [
                {"path": path, "changeType": change_type}
                for path, change_type in rows
            ],
            "pageInfo": {
                "hasNextPage": has_next,
                "endCursor": end_cursor,
            },
        }
    return {
        "data": {
            "rateLimit": {"cost": 1, "remaining": 4000},
            "repository": {
                "pullRequest": {
                    "number": FOREIGN_PR,
                    "state": "OPEN",
                    "headRefOid": head_sha,
                    "baseRefOid": FOREIGN_BASE_SHA,
                    "headRepository": {"nameWithOwner": fx.REPOSITORY},
                    "baseRepository": {"nameWithOwner": fx.REPOSITORY},
                    "changedFiles": total,
                    "files": files,
                }
            },
        }
    }


class CompactFilesHTTP:
    compact_foreign_files_available = True

    def __init__(
        self,
        pages: dict[str | None, dict[str, object]],
        *,
        rest_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.pages = pages
        self.rest_rows = rest_rows
        self.compact_calls: list[str | None] = []
        self.rest_file_calls = 0
        self.identity_reads = 0

    def compact_pull_files_page(
        self,
        repository: str,
        pr_number: int,
        *,
        cursor: str | None,
        token: str,
        timeout: float,
    ) -> object:
        assert repository == fx.REPOSITORY
        assert pr_number == FOREIGN_PR
        assert token == fx.TOKEN and timeout > 0
        self.compact_calls.append(cursor)
        return self.pages[cursor]

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == fx.TOKEN and timeout > 0
        parsed = urlparse(url)
        if parsed.path.endswith(f"/pulls/{FOREIGN_PR}/files"):
            self.rest_file_calls += 1
            assert self.rest_rows is not None
            return self.rest_rows
        if parsed.path.endswith(f"/pulls/{FOREIGN_PR}"):
            self.identity_reads += 1
            return _foreign_row()
        raise AssertionError(url)


def test_compact_foreign_files_avoid_patch_heavy_rest_rows() -> None:
    module = fx._cli_module()
    http = CompactFilesHTTP(
        {
            None: _compact_files_payload(
                [("docs/compact.md", "MODIFIED")],
            )
        }
    )

    observation = module._foreign_files_observation(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        FOREIGN_PR,
        raw_pr=_foreign_row(),
    )

    assert observation.paths == ("docs/compact.md",)
    assert observation.saturated is False
    assert http.compact_calls == [None]
    assert http.rest_file_calls == 0
    assert http.identity_reads == 0


@pytest.mark.parametrize("changed_files", [0, 1])
def test_compact_null_file_connection_promotes_to_exact_owned_tree_proof(
    changed_files: int,
) -> None:
    # A null connection is not evidence of empty changes. Live REST metadata
    # reports 0 changes while serving a 100-row file page for some open PRs.
    module = fx._cli_module()
    http = CompactFilesHTTP({
        None: _compact_files_payload([], changed_files=changed_files, files_null=True)
    })
    observation = module._foreign_files_observation(
        http, fx.TOKEN, fx.REPOSITORY, FOREIGN_PR, raw_pr=_foreign_row()
    )
    assert observation == module._ForeignFilesObservation((), True)
    assert http.compact_calls == [None]
    assert http.rest_file_calls == 0
    assert http.identity_reads == 0


def test_compact_rename_promotes_to_owned_path_tree_proof() -> None:
    module = fx._cli_module()
    outside = "docs/renamed-away.md"
    http = CompactFilesHTTP(
        {
            None: _compact_files_payload(
                [(outside, "RENAMED")],
            )
        },
    )

    observation = module._foreign_files_observation(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        FOREIGN_PR,
        raw_pr=_foreign_row(),
    )

    assert observation == module._ForeignFilesObservation((), True)
    assert http.compact_calls == [None]
    assert http.rest_file_calls == 0
    assert http.identity_reads == 0


def test_compact_files_are_bound_to_the_roster_identity() -> None:
    module = fx._cli_module()
    http = CompactFilesHTTP(
        {
            None: _compact_files_payload(
                [("docs/compact.md", "MODIFIED")],
                head_sha=MOVED_HEAD_SHA,
            )
        }
    )

    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http,
            fx.TOKEN,
            fx.REPOSITORY,
            FOREIGN_PR,
            raw_pr=_foreign_row(),
        )

    assert http.rest_file_calls == 0


def test_compact_files_paginate_without_rest_fallback() -> None:
    module = fx._cli_module()
    first_rows = [
        (f"docs/page-1-{index:03d}.md", "MODIFIED")
        for index in range(100)
    ]
    second_rows = [("docs/page-2-final.md", "ADDED")]
    http = CompactFilesHTTP(
        {
            None: _compact_files_payload(
                first_rows,
                changed_files=101,
                has_next=True,
                end_cursor="cursor-100",
            ),
            "cursor-100": _compact_files_payload(
                second_rows,
                changed_files=101,
            ),
        }
    )

    observation = module._foreign_files_observation(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        FOREIGN_PR,
        raw_pr=_foreign_row(),
    )

    assert len(observation.paths) == 101
    assert observation.paths[-1] == "docs/page-2-final.md"
    assert http.compact_calls == [None, "cursor-100"]
    assert http.rest_file_calls == 0


def test_compact_three_thousand_file_pr_uses_existing_saturated_tree_proof() -> None:
    module = fx._cli_module()
    http = CompactFilesHTTP(
        {
            None: _compact_files_payload(
                [("bulk/first.md", "MODIFIED")],
                changed_files=3000,
                has_next=True,
                end_cursor="unused",
            )
        }
    )

    observation = module._foreign_files_observation(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        FOREIGN_PR,
        raw_pr=_foreign_row(),
    )

    assert observation == module._ForeignFilesObservation((), True)
    assert http.compact_calls == [None]
    assert http.rest_file_calls == 0


def test_compact_unknown_change_type_refuses() -> None:
    module = fx._cli_module()
    http = CompactFilesHTTP(
        {
            None: _compact_files_payload(
                [("docs/unknown.md", "FUTURE_STATUS")],
            )
        }
    )

    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http,
            fx.TOKEN,
            fx.REPOSITORY,
            FOREIGN_PR,
            raw_pr=_foreign_row(),
        )


@pytest.mark.parametrize("defect", ["errors", "cost", "remaining"])
def test_compact_graphql_control_plane_defects_refuse(defect: str) -> None:
    module = fx._cli_module()
    payload = _compact_files_payload([("docs/compact.md", "MODIFIED")])
    if defect == "errors":
        payload["errors"] = [{"message": "partial response"}]
    elif defect == "cost":
        payload["data"]["rateLimit"]["cost"] = 2
    else:
        payload["data"]["rateLimit"]["remaining"] = -1
    http = CompactFilesHTTP({None: payload})

    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http,
            fx.TOKEN,
            fx.REPOSITORY,
            FOREIGN_PR,
            raw_pr=_foreign_row(),
        )


def test_compact_duplicate_path_across_pages_refuses() -> None:
    module = fx._cli_module()
    first_rows = [
        (f"docs/page-1-{index:03d}.md", "MODIFIED")
        for index in range(100)
    ]
    http = CompactFilesHTTP(
        {
            None: _compact_files_payload(
                first_rows,
                changed_files=101,
                has_next=True,
                end_cursor="cursor-100",
            ),
            "cursor-100": _compact_files_payload(
                [(first_rows[0][0], "MODIFIED")],
                changed_files=101,
            ),
        }
    )

    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http,
            fx.TOKEN,
            fx.REPOSITORY,
            FOREIGN_PR,
            raw_pr=_foreign_row(),
        )


def test_compact_repeated_cursor_refuses() -> None:
    module = fx._cli_module()
    first_rows = [
        (f"docs/page-1-{index:03d}.md", "MODIFIED")
        for index in range(100)
    ]
    second_rows = [
        (f"docs/page-2-{index:03d}.md", "MODIFIED")
        for index in range(100)
    ]
    http = CompactFilesHTTP(
        {
            None: _compact_files_payload(
                first_rows,
                changed_files=201,
                has_next=True,
                end_cursor="repeat",
            ),
            "repeat": _compact_files_payload(
                second_rows,
                changed_files=201,
                has_next=True,
                end_cursor="repeat",
            ),
        }
    )

    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http,
            fx.TOKEN,
            fx.REPOSITORY,
            FOREIGN_PR,
            raw_pr=_foreign_row(),
        )


def test_compact_pages_share_the_existing_http_call_and_byte_budget(
    monkeypatch,
) -> None:
    module = fx._cli_module()
    clock = budget.Clock()
    monkeypatch.setattr(module, "monotonic", clock)
    payload = _compact_files_payload([("docs/compact.md", "MODIFIED")])

    class Transport:
        compact_foreign_files_available = True

        def __call__(self, _url, *, token, timeout, **_kwargs):
            raise AssertionError("REST path is not part of this proof")

        def compact_pull_files_page(
            self,
            repository,
            pr_number,
            *,
            cursor,
            token,
            timeout,
        ):
            assert repository == fx.REPOSITORY
            assert pr_number == FOREIGN_PR
            assert cursor is None
            assert token == fx.TOKEN and timeout > 0
            return payload

    bounded = module._BoundedHTTPGet(Transport())
    observed = bounded.compact_pull_files_page(
        fx.REPOSITORY,
        FOREIGN_PR,
        cursor=None,
        token=fx.TOKEN,
        timeout=20.0,
    )

    assert observed == payload
    assert bounded._calls == 1
    assert bounded._bytes == len(
        module.canonical_json(payload).encode("utf-8", "backslashreplace")
    )



@pytest.mark.parametrize("change_type", ("RENAMED", "COPIED"))
def test_compact_rename_or_copy_unknown_source_routes_to_exact_tree_proof(
    change_type: str,
) -> None:
    """A copied/renamed source is absent from the GraphQL path-only page."""
    module = fx._cli_module()
    http = CompactFilesHTTP(
        {None: _compact_files_payload([("docs/new-location.md", change_type)])}
    )
    observed = module._foreign_files_observation(
        http, fx.TOKEN, fx.REPOSITORY, FOREIGN_PR, raw_pr=_foreign_row(),
    )
    assert observed == module._ForeignFilesObservation((), True)
    assert http.rest_file_calls == 0



@pytest.mark.parametrize("field,malformed", [
    ("number", True),
    ("number", float(FOREIGN_PR)),
    ("totalCount", True),
    ("totalCount", 1.0),
])
def test_compact_graphql_identity_fields_refuse_bool_or_float(
    field: str, malformed: object,
) -> None:
    module = fx._cli_module()
    payload = _compact_files_payload([("docs/changed.md", "MODIFIED")])
    pull = payload["data"]["repository"]["pullRequest"]
    if field == "totalCount":
        pull["files"]["totalCount"] = malformed
    else:
        pull["number"] = malformed
    http = CompactFilesHTTP({None: payload})
    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http, fx.TOKEN, fx.REPOSITORY, FOREIGN_PR, raw_pr=_foreign_row(),
        )


def test_compact_oversized_cursor_refuses_before_post_replay() -> None:
    module = fx._cli_module()
    items = [(f"docs/page-one-{i:03d}.md", "MODIFIED") for i in range(100)]
    http = CompactFilesHTTP({
        None: _compact_files_payload(
            items, changed_files=101, has_next=True,
            end_cursor="X" * 4097,
        )
    })
    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http, fx.TOKEN, fx.REPOSITORY, FOREIGN_PR, raw_pr=_foreign_row(),
        )
    assert http.compact_calls == [None]
    assert http.rest_file_calls == 0


def test_compact_real_wire_post_uses_fixed_github_endpoint_and_pinned_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The readonly POST endpoint and protocol version are source constants."""
    module = fx._cli_module()
    seen = []
    payload = _compact_files_payload([("docs/changed.md", "MODIFIED")])

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self, _cap: int): return __import__("json").dumps(payload).encode()

    def urlopen(req, *, timeout):
        seen.append(req)
        assert req.full_url == module._GRAPHQL_ROOT
        assert req.get_method() == "POST"
        assert req.get_header("X-github-api-version") == module._API_VERSION
        assert req.get_header("Authorization") == "Bearer local-test-token"
        assert timeout > 0
        body = __import__("json").loads(req.data)
        assert body["query"] == module._GRAPHQL_PULL_FILES_QUERY
        assert body["variables"] == {
            "owner": fx.REPOSITORY.split("/", 1)[0],
            "name": fx.REPOSITORY.split("/", 1)[1],
            "number": FOREIGN_PR,
            "cursor": None,
        }
        return Response()

    monkeypatch.setattr(module, "urlopen", urlopen)
    assert module._stdlib_compact_pull_files_page(
        fx.REPOSITORY, FOREIGN_PR, cursor=None,
        token="local-test-token", timeout=4.0
    ) == payload
    assert len(seen) == 1


def test_compact_real_empty_connection_does_not_override_immutable_tree_proof() -> None:
    module = fx._cli_module()
    http = CompactFilesHTTP({
        None: _compact_files_payload([], changed_files=0)
    })
    assert module._foreign_files_observation(
        http, fx.TOKEN, fx.REPOSITORY, FOREIGN_PR,
        raw_pr=_foreign_row()
    ) == module._ForeignFilesObservation((), True)



class NullCompactCurrentBaseHTTP(CurrentBaseOverlapHTTP):
    compact_foreign_files_available = True

    def compact_pull_files_page(
        self, repository, pr_number, *, cursor, token, timeout,
    ):
        assert repository == fx.REPOSITORY and pr_number == FOREIGN_PR
        assert cursor is None and token == fx.TOKEN and timeout > 0
        return _compact_files_payload([], changed_files=0, files_null=True)


@pytest.mark.parametrize(
    ("foreign_sha", "missing_foreign", "expected_overlap"),
    [
        (SAME_BLOB, False, False),
        (OTHER_BLOB, False, True),
        (SAME_BLOB, True, True),
    ],
)
def test_compact_null_file_connection_requires_real_immutable_owned_tree_proof(
    foreign_sha: str, missing_foreign: bool, expected_overlap: bool,
) -> None:
    """GraphQL-null can never waive material differences on owned paths."""
    module = fx._cli_module()
    entry = None if missing_foreign else _blob_entry(foreign_sha)
    http = NullCompactCurrentBaseHTTP(entry)
    proof, overlaps = module._foreign_collision_evidence(
        http, fx.TOKEN, fx.REPOSITORY, _foreign_row(),
        FOREIGN_PR, MATERIAL_OWNED, current_base_head=CURRENT_BASE_SHA,
    )
    assert overlaps is expected_overlap
    assert proof.proof_method == "CURRENT_TARGET_BASE_TREE_EQUALITY"
    assert proof.target_base_sha == CURRENT_BASE_SHA
    assert proof.head_sha == FOREIGN_HEAD_SHA
    assert tuple(x[0] for x in proof.owned_path_entries) == MATERIAL_OWNED
    assert not any("/files" in url for url in http.calls)


def test_compact_present_zero_connection_routes_to_exact_tree_proof() -> None:
    """A present but empty GraphQL list is not proof when zero-count metadata lies."""
    module = fx._cli_module()
    http = CompactFilesHTTP({
        None: _compact_files_payload([], changed_files=0)
    })
    seen = module._foreign_files_observation(
        http, fx.TOKEN, fx.REPOSITORY, FOREIGN_PR, raw_pr=_foreign_row()
    )
    assert seen == module._ForeignFilesObservation((), True)
    assert http.compact_calls == [None]


@pytest.mark.parametrize("foreign_entry, expected_overlap", [
    (_blob_entry(), False),
    (_blob_entry(OTHER_BLOB), True),
    (None, True),
])
def test_compact_present_zero_connection_uses_actual_owned_tree(
    foreign_entry, expected_overlap: bool,
) -> None:
    module = fx._cli_module()
    class PresentEmptyCurrentBase(CurrentBaseOverlapHTTP):
        compact_foreign_files_available = True
        def compact_pull_files_page(self, repository, pr_number, *, cursor, token, timeout):
            assert repository == fx.REPOSITORY
            return _compact_files_payload([], changed_files=0)
    http = PresentEmptyCurrentBase(foreign_entry)
    proof, overlap = module._foreign_collision_evidence(
        http, fx.TOKEN, fx.REPOSITORY, _foreign_row(), FOREIGN_PR,
        MATERIAL_OWNED, current_base_head=CURRENT_BASE_SHA
    )
    assert overlap is expected_overlap
    assert proof.proof_method == "CURRENT_TARGET_BASE_TREE_EQUALITY"


def test_compact_unicode_surrogate_cursor_refuses_as_remote_not_internal_error() -> None:
    module = fx._cli_module()
    rows = [(f"docs/p{i:03d}.md", "MODIFIED") for i in range(100)]
    http = CompactFilesHTTP({
        None: _compact_files_payload(rows, changed_files=101, has_next=True, end_cursor="\ud800")
    })
    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http, fx.TOKEN, fx.REPOSITORY, FOREIGN_PR, raw_pr=_foreign_row()
        )
    assert http.compact_calls == [None]


def test_compact_changed_files_boolean_is_refused() -> None:
    module = fx._cli_module()
    payload = _compact_files_payload([("docs/p0.md","MODIFIED")])
    payload["data"]["repository"]["pullRequest"]["changedFiles"] = True
    http = CompactFilesHTTP({None:payload})
    with pytest.raises(module._RemoteProbeError):
        module._foreign_files_observation(
            http,fx.TOKEN,fx.REPOSITORY,FOREIGN_PR,raw_pr=_foreign_row()
        )
