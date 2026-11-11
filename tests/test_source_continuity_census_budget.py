"""Actual Source Continuity CLI budget regressions; no real HTTP or token."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

import test_source_continuity as fx


class EstateHTTP(fx._ProbeHTTP):
    """Existing identity fixture plus a paginated, changing foreign PR estate."""

    def __init__(
        self,
        count=143,
        *,
        files_per_pr=1,
        file_counts=None,
        change=None,
        overlap=False,
        opened_between=0,
        identity_complete=False,
        move_overlap=False,
    ):
        super().__init__()
        self.count = count
        self.opened_between = opened_between
        self.files_per_pr = files_per_pr
        self.file_counts = {} if file_counts is None else dict(file_counts)
        self.change = change
        self.overlap = overlap
        self.identity_complete = identity_complete
        self.move_overlap = move_overlap
        self.passes = 0
        self.after_read = None

    def _foreign_row(self, number):
        head_sha = f"{number:040x}"[-40:]
        if (
            self.move_overlap
            and self.passes > 1
            and number == 1000 + self.count - 2
        ):
            head_sha = "e" * 40
        return {
            "number": number,
            "state": "open",
            "head": {
                "sha": head_sha,
                "repo": {"full_name": fx.REPOSITORY},
            },
            "base": {
                "sha": "f" * 40,
                "repo": {"full_name": fx.REPOSITORY},
            },
        }

    def __call__(self, url, *, token, timeout):
        parsed = urlparse(url)
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        tail = parse_qs(parsed.query).get("direction") == ["desc"]
        if parsed.path.endswith("/pulls"):
            self.calls.append((url, token, timeout))
            if page == 1 and not tail:
                self.passes += 1
            foreign_rows = []
            for i in range(self.count - 1):
                number = 1000 + i
                if self.identity_complete:
                    foreign_rows.append(self._foreign_row(number))
                else:
                    foreign_rows.append({"number": number})
            rows = [{"number": fx.PR_NUMBER}] + foreign_rows
            if self.change == "membership" and self.passes > 1:
                rows[-1] = {"number": 9000}
            if self.passes > 1:
                rows += [{"number": 9000 + i} for i in range(self.opened_between)]
            if self.change == "duplicate" and page == 1:
                rows[1] = rows[0]
            if tail:
                result = rows[::-1][:100]
            else:
                result = rows[(page - 1) * 100:page * 100]
        elif parsed.path.endswith("/files") and (
                f"/pulls/{fx.PR_NUMBER}/" not in parsed.path):
            self.calls.append((url, token, timeout))
            number = int(parsed.path.split("/")[-2])
            file_count = self.file_counts.get(number, self.files_per_pr)
            rows = [{"filename": f"docs/foreign-{number}-{i}.md", "status": "modified"}
                    for i in range(file_count)]
            if self.overlap and number == 1000 + self.count - 2:
                rows[-1]["filename"] = fx.FINAL_OWNED_PATHS[0]
            if self.change == "paths" and self.passes > 1:
                rows[-1]["filename"] += ".changed"
            result = rows[(page - 1) * 100:page * 100]
        elif (
            self.identity_complete
            and parsed.path.startswith(f"/repos/{fx.REPOSITORY}/pulls/")
            and parsed.path.rsplit("/", 1)[-1].isdigit()
            and 1000 <= int(parsed.path.rsplit("/", 1)[-1]) < 1000 + self.count - 1
        ):
            self.calls.append((url, token, timeout))
            result = self._foreign_row(int(parsed.path.rsplit("/", 1)[-1]))
        else:
            result = super().__call__(url, token=token, timeout=timeout)
        if self.after_read:
            self.after_read(url, result)
        return result


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def run_cli(module, capsys, http, *, kind="checkpoint", runner=None, read_failure=None):
    exit_code = fx._run_cli(module, fx._cli_argv(kind), http=http, runner=runner)
    captured = capsys.readouterr()
    if read_failure is None:
        assert captured.err == ""
    else:
        assert json.loads(captured.err) == {"diagnostic": "READ_FAILED", **read_failure}
    assert captured.out.count("\n") == 1
    return exit_code, json.loads(captured.out)


@pytest.mark.parametrize("count", [1, 2, 99, 100, 143, 200, 256, 409, 419, 450, 451, 457, 458, 465, 470, 475, 476, 477, 478, 479, 480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 903, 907, 999, 1000, 1001, 1499, 1500])
@pytest.mark.parametrize("kind", ["checkpoint", "remote-complete"])
def test_real_main_reports_the_qualified_coverage_boundary(count, kind, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(count)
    rc, payload = run_cli(module, capsys, http, kind=kind)
    if count >= 100:
        assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
        assert http.passes == 1
        assert not any("/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
                       for url, _, _ in http.calls)
        return
    assert rc == 0, payload
    assert payload["authority_effect"] == "NONE"
    assert payload["merge_authorized"] is False
    assert payload["writer_release_authorized"] is False
    assert http.passes == 2
    assert payload["collision_state"] == ("NONE" if count == 1 else "DISJOINT")


@pytest.mark.parametrize("count", [1501, 1600, 1601, 2000])
def test_over_ceiling_refuses_before_foreign_files(count, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(count)
    rc, payload = run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert not any("/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
                   for url, _, _ in http.calls)
    roster_pages = [int(parse_qs(urlparse(url).query)["page"][0])
                    for url, _, _ in http.calls if urlparse(url).path.endswith("/pulls")]
    assert roster_pages == [1]
    assert module._MAX_ROSTER_PAGES == 16


@pytest.mark.parametrize("change,code", [
    ("membership", "REMOTE_PROOF_CHANGED"),
    ("paths", "REMOTE_PROOF_CHANGED"),
    ("duplicate", "REMOTE_PROBE_FAILED"),
])
def test_single_page_estate_still_requires_stable_complete_observations(
        change, code, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    rc, payload = run_cli(module, capsys, EstateHTTP(99, change=change))
    assert rc != 0 and payload["code"] == code


def _foreign_file_call_count(http: EstateHTTP) -> int:
    return sum(
        1
        for url, _token, _timeout in http.calls
        if "/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
    )


def _foreign_detail_call_count(http: EstateHTTP) -> int:
    return sum(
        1
        for url, _token, _timeout in http.calls
        if urlparse(url).path.rsplit("/", 1)[0].endswith("/pulls")
        and urlparse(url).path.rsplit("/", 1)[-1].isdigit()
        and urlparse(url).path.rsplit("/", 1)[-1] != str(fx.PR_NUMBER)
    )


def test_single_page_selective_revalidation_reuses_stable_foreign_evidence(monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    estate_size = 99
    http = EstateHTTP(
        estate_size,
        overlap=True,
        identity_complete=True,
    )

    first = module._collision_census_details(
        http, fx.TOKEN, fx.REPOSITORY, fx.PR_NUMBER, fx.FINAL_OWNED_PATHS
    )
    assert first.complete is True
    assert first.state is module.CollisionState.OVERLAP
    first_file_calls = _foreign_file_call_count(http)
    assert first_file_calls == estate_size - 1

    matched, complete, final_records = module._revalidate_collision_census(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        fx.PR_NUMBER,
        fx.FINAL_OWNED_PATHS,
        first.foreign_records,
        first.colliding_pr_numbers,
    )

    assert (matched, complete) == (True, True)
    assert len(final_records) == estate_size - 1
    assert _foreign_file_call_count(http) == first_file_calls
    assert _foreign_detail_call_count(http) == 1
    assert http.passes == 2


def test_single_page_selective_revalidation_reproves_only_moved_foreign_identity(monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    estate_size = 99
    http = EstateHTTP(
        estate_size,
        overlap=True,
        identity_complete=True,
        move_overlap=True,
    )

    first = module._collision_census_details(
        http, fx.TOKEN, fx.REPOSITORY, fx.PR_NUMBER, fx.FINAL_OWNED_PATHS
    )
    first_file_calls = _foreign_file_call_count(http)

    matched, complete, final_records = module._revalidate_collision_census(
        http,
        fx.TOKEN,
        fx.REPOSITORY,
        fx.PR_NUMBER,
        fx.FINAL_OWNED_PATHS,
        first.foreign_records,
        first.colliding_pr_numbers,
    )

    assert (matched, complete) == (True, True)
    assert len(final_records) == estate_size - 1
    assert _foreign_file_call_count(http) == first_file_calls + 1
    assert _foreign_detail_call_count(http) == 2
    assert http.passes == 2


def test_single_page_estate_moved_collider_same_projection_stays_within_closed_budget(
        capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    estate_size = 99
    http = EstateHTTP(
        estate_size,
        overlap=True,
        identity_complete=True,
        move_overlap=True,
    )
    rc, payload = run_cli(module, capsys, http)
    assert rc == 0, payload
    assert payload["collision_state"] == "OVERLAP"
    assert payload["colliding_pr_numbers"] == [1000 + estate_size - 2]
    assert payload["receipt_version"] == "v2"
    assert len(payload["collision_evidence_fingerprint"]) == 64
    assert len(http.calls) < module._MAX_HTTP_CALLS
    assert _foreign_detail_call_count(http) == 2
    assert http.passes == 2


def test_490_estate_refuses_before_selective_revalidation(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(490, overlap=True, identity_complete=True, move_overlap=True)

    rc, payload = run_cli(module, capsys, http)

    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert _foreign_file_call_count(http) == 0
    assert _foreign_detail_call_count(http) == 0
    assert http.passes == 1


def test_last_foreign_pr_overlap_is_preserved(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    rc, payload = run_cli(module, capsys, EstateHTTP(99, overlap=True))
    assert rc == 0
    assert payload["collision_state"] == "OVERLAP"
    assert payload["colliding_pr_numbers"] == [1097]
    assert payload["merge_authorized"] is False


def test_logical_call_budget_is_shared_across_both_passes(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    control = EstateHTTP(10)
    assert run_cli(module, capsys, control)[0] == 0
    limit = len(control.calls) - 1
    monkeypatch.setattr(module, "_MAX_HTTP_CALLS", limit, raising=False)
    http = EstateHTTP(10)
    rc, payload = run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert len(http.calls) == limit
    assert http.passes == 2


def test_normalized_byte_budget_is_shared(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    sizes = []
    control = EstateHTTP(10)
    control.after_read = lambda _url, result: sizes.append(
        len(module.canonical_json(result).encode("utf-8", "backslashreplace")))
    assert run_cli(module, capsys, control)[0] == 0
    monkeypatch.setattr(module, "_MAX_HTTP_NORMALIZED_BYTES", sum(sizes) - 1,
                        raising=False)
    http = EstateHTTP(10)
    rc, payload = run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert http.passes == 2


@pytest.mark.parametrize("defect", ["late", "backwards", "nan", "infinity"])
def test_invalid_or_expired_clock_never_emits_receipt(defect, capsys, monkeypatch):
    module = fx._cli_module()
    clock = Clock()
    monkeypatch.setattr(module, "monotonic", clock, raising=False)
    http = EstateHTTP(1)
    def advance(_url, _result):
        clock.now = {"late": 1000.0, "backwards": -1.0,
                     "nan": float("nan"), "infinity": float("inf")}[defect]
    http.after_read = advance
    rc, payload = run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert len(http.calls) == 1


def test_auth_failure_is_not_relabeled_budget_or_retried(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    calls = []
    def denied(url, **kwargs):
        calls.append(url)
        raise module._AuthProbeError()
    rc, payload = run_cli(module, capsys, denied, read_failure={
        "endpoint": "repos/mastermindx-market-intelligence/Mastermind/pulls/410",
        "cause": "unclassified",
        "attempts": 1,
        "retryable": False,
        "failed_reads": 1,
        "recovered_reads": 0,
    })
    assert rc == 2 and payload["code"] == "AUTH_UNAVAILABLE"
    assert len(calls) == 1


@pytest.mark.parametrize("files", [2000, 2100])
def test_large_foreign_file_fanout_remains_bounded(files, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(99, files_per_pr=files)
    rc, payload = run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    # The call budget binds: admission refuses the 4,097th read before transport.
    assert len(http.calls) == 4096


def test_accounting_preserves_unconsumed_unicode_metadata(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(2)
    def metadata(_url, result):
        if isinstance(result, dict):
            result["unconsumed_note"] = "Chinese 中文 with escaped surrogate \ud800"
    http.after_read = metadata
    rc, payload = run_cli(module, capsys, http)
    assert rc == 0 and payload["authority_effect"] == "NONE"


def test_deadline_is_rechecked_after_json_accounting(capsys, monkeypatch):
    module = fx._cli_module()
    clock = Clock()
    monkeypatch.setattr(module, "monotonic", clock, raising=False)
    original = module.canonical_json
    def slow_account(value):
        result = original(value)
        if isinstance(value, dict) and "state" in value and "head" in value:
            clock.now = 901.0
        return result
    monkeypatch.setattr(module, "canonical_json", slow_account)
    rc, payload = run_cli(module, capsys, EstateHTTP(1))
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


@pytest.mark.parametrize("count", [2, 50, 99])
def test_complete_cli_uses_real_git_with_single_response_estate(
        count, tmp_path, capsys, monkeypatch):
    import subprocess
    import test_source_continuity_r3_hardening as r3

    repo = tmp_path / "fixture"
    base = r3.init_repo(repo, "base")
    r3.git(repo, "checkout", "-qb", "fixture/census")
    (repo / "value.txt").write_text("changed\n", encoding="utf-8")
    r3.git(repo, "add", "value.txt")
    r3.git(repo, "commit", "-qm", "candidate")
    head = r3.git(repo, "rev-parse", "HEAD")
    for key, value in {
        "WORKSPACE": str(repo), "BASE_SHA": base, "CURRENT_BASE_SHA": base,
        "HEAD_SHA": head, "TREE_SHA": r3.git(repo, "rev-parse", "HEAD^{tree}"),
        "BRANCH": "fixture/census", "FINAL_OWNED_PATHS": ("value.txt",),
        "REPOSITORY": "example/source-continuity-fixture",
    }.items():
        monkeypatch.setattr(fx, key, value)
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(count)
    rc, payload = run_cli(module, capsys, http, runner=subprocess.run)
    assert rc == 0, payload
    assert payload["remote_head_sha"] == payload["local_head_sha"] == head
    assert payload["repository"] == "example/source-continuity-fixture"
    assert payload["local_equals_remote"] is True and http.passes == 2
    assert payload["merge_authorized"] is False


def test_deadline_is_rechecked_after_pure_verification(capsys, monkeypatch):
    module = fx._cli_module()
    clock = Clock()
    monkeypatch.setattr(module, "monotonic", clock)
    original = module.verify_source_continuity
    def slow_verify(*args):
        result = original(*args)
        clock.now = 901.0
        return result
    monkeypatch.setattr(module, "verify_source_continuity", slow_verify)
    rc, payload = run_cli(module, capsys, EstateHTTP(1))
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


def test_transport_timeout_is_clipped_to_remaining_budget(capsys, monkeypatch):
    module = fx._cli_module()
    clock = Clock()
    monkeypatch.setattr(module, "monotonic", clock)
    http = EstateHTTP(1)
    def advance(_url, _result):
        clock.now = 890.0
    http.after_read = advance
    assert run_cli(module, capsys, http)[0] == 0
    assert http.calls[0][2] == 20.0
    assert all(timeout == 10.0 for _, _, timeout in http.calls[1:])


@pytest.mark.parametrize("now", [True, "0", float("nan"), float("inf"), 1e308])
def test_invalid_initial_clock_refuses_before_any_http(now, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", lambda: now)
    http = EstateHTTP(1)
    rc, payload = run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert http.calls == []


def test_exact_call_and_byte_limit_remains_successful(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock())
    sizes = []
    control = EstateHTTP(3)
    control.after_read = lambda _url, result: sizes.append(
        len(module.canonical_json(result).encode("utf-8", "backslashreplace")))
    assert run_cli(module, capsys, control)[0] == 0
    monkeypatch.setattr(module, "_MAX_HTTP_CALLS", len(control.calls))
    monkeypatch.setattr(module, "_MAX_HTTP_NORMALIZED_BYTES", sum(sizes))
    http = EstateHTTP(3)
    assert run_cli(module, capsys, http)[0] == 0
    assert len(http.calls) == len(control.calls) and http.passes == 2


def test_budget_constants_are_closed_and_raw_response_cap_is_unchanged():
    module = fx._cli_module()
    assert (module._MAX_COLLISION_PRS, module._MAX_HTTP_CALLS) == (1500, 4096)
    assert module._MAX_ROSTER_PAGES == 16
    assert module._MAX_HTTP_NORMALIZED_BYTES == 768 * 1024 * 1024
    assert module._HTTP_READ_BUDGET_SECONDS == 900.0
    assert module._MAX_HTTP_BODY_BYTES == 5_000_000
    assert module._FOREIGN_PR_WORKERS == 4


# Live production census of macro#7870 on 2026-11-02 (stdlib transport, four
# workers, conditional roster revalidation): 903 open PRs, 106 owned paths.
MEASURED_OPEN_PRS = 903
MEASURED_CALLS = 1_537
MEASURED_NORMALIZED_BYTES = 286_139_447
MEASURED_SECONDS = 286.0


def test_current_macro_estate_payload_fits_successor_byte_budget(monkeypatch):
    """Measured current census payload must fit without changing any other ceiling."""
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock())
    bounded = module._BoundedHTTPGet(lambda *_args, **_kwargs: None)
    bounded._bytes = MEASURED_NORMALIZED_BYTES

    assert bounded._bytes > 128 * 1024 * 1024
    assert bounded._bytes < 768 * 1024 * 1024
    bounded.check()


def test_retained_resource_projection_fits_without_proving_coverage():
    """Retain the historical capacity estimate, not an enumeration certificate.

    Resource headroom cannot qualify the now-refused multi-page coverage.
    """
    module = fx._cli_module()
    assert MEASURED_CALLS > 1152
    assert MEASURED_NORMALIZED_BYTES > 128 * 1024 * 1024
    assert MEASURED_OPEN_PRS > 490

    scale = module._MAX_COLLISION_PRS / MEASURED_OPEN_PRS
    for measured, budget in (
        (MEASURED_CALLS, module._MAX_HTTP_CALLS),
        (MEASURED_NORMALIZED_BYTES, module._MAX_HTTP_NORMALIZED_BYTES),
        (MEASURED_SECONDS, module._HTTP_READ_BUDGET_SECONDS),
    ):
        assert budget / (measured * scale) >= 1.6


def test_normalized_byte_budget_accepts_exact_768_mib_and_refuses_one_over(monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock())
    bounded = module._BoundedHTTPGet(lambda *_args, **_kwargs: None)

    bounded._bytes = 768 * 1024 * 1024
    bounded.check()

    bounded._bytes += 1
    with pytest.raises(module._ReadBudgetExceeded):
        bounded.check()


def test_single_get_rejects_accounting_overrun_before_return(monkeypatch):
    """No later GET may be needed to reject the just-accounted late result."""
    module = fx._cli_module()
    clock = Clock()
    monkeypatch.setattr(module, "monotonic", clock)
    original = module.canonical_json
    def slow_account(payload):
        result = original(payload)
        clock.now = 901.0
        return result
    monkeypatch.setattr(module, "canonical_json", slow_account)
    calls = []
    def transport(url, **_kwargs):
        calls.append(url)
        return {"observed": "one finite fixture response"}
    bounded = module._BoundedHTTPGet(transport)
    with pytest.raises(module._ReadBudgetExceeded):
        bounded("https://api.github.com/repos/example/fixture", token="fixture", timeout=20)
    assert len(calls) == 1
