"""Actual Source Continuity CLI budget regressions; no real HTTP or token."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

import test_source_continuity as fx


class EstateHTTP(fx._ProbeHTTP):
    """Existing identity fixture plus a paginated, changing foreign PR estate."""

    def __init__(self, count=143, *, files_per_pr=1, change=None, overlap=False):
        super().__init__()
        self.count = count
        self.files_per_pr = files_per_pr
        self.change = change
        self.overlap = overlap
        self.passes = 0
        self.after_read = None

    def __call__(self, url, *, token, timeout):
        parsed = urlparse(url)
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        if parsed.path.endswith("/pulls"):
            self.calls.append((url, token, timeout))
            if page == 1:
                self.passes += 1
            rows = [{"number": fx.PR_NUMBER}] + [
                {"number": 1000 + i} for i in range(self.count - 1)]
            if self.change == "membership" and self.passes > 1:
                rows[-1] = {"number": 9000}
            if self.change == "duplicate" and page == 2:
                rows[100] = rows[99]
            result = rows[(page - 1) * 100:page * 100]
        elif parsed.path.endswith("/files") and (
                f"/pulls/{fx.PR_NUMBER}/" not in parsed.path):
            self.calls.append((url, token, timeout))
            number = int(parsed.path.split("/")[-2])
            rows = [{"filename": f"docs/foreign-{number}-{i}.md", "status": "modified"}
                    for i in range(self.files_per_pr)]
            if self.overlap and number == 1000 + self.count - 2:
                rows[-1]["filename"] = fx.FINAL_OWNED_PATHS[0]
            if self.change == "paths" and self.passes > 1:
                rows[-1]["filename"] += ".changed"
            result = rows[(page - 1) * 100:page * 100]
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


def run_cli(module, capsys, http, *, kind="checkpoint", runner=None):
    exit_code = fx._run_cli(module, fx._cli_argv(kind), http=http, runner=runner)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    return exit_code, json.loads(captured.out)


@pytest.mark.parametrize("count", [1, 100, 143, 200, 256])
@pytest.mark.parametrize("kind", ["checkpoint", "remote-complete"])
def test_real_main_completes_bounded_estate(count, kind, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(count)
    rc, payload = run_cli(module, capsys, http, kind=kind)
    assert rc == 0, payload
    assert payload["authority_effect"] == "NONE"
    assert payload["merge_authorized"] is False
    assert payload["writer_release_authorized"] is False
    assert http.passes == 2
    assert payload["collision_state"] == ("NONE" if count == 1 else "DISJOINT")


@pytest.mark.parametrize("count", [257, 1000])
def test_over_ceiling_refuses_before_foreign_files(count, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(count)
    rc, payload = run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert not any("/pulls/1" in url and "/files?" in url
                   for url, _, _ in http.calls)


@pytest.mark.parametrize("change,code", [
    ("membership", "REMOTE_PROOF_CHANGED"),
    ("paths", "REMOTE_PROOF_CHANGED"),
    ("duplicate", "REMOTE_PROBE_FAILED"),
])
def test_large_estate_still_requires_stable_complete_observations(
        change, code, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    rc, payload = run_cli(module, capsys, EstateHTTP(143, change=change))
    assert rc != 0 and payload["code"] == code


def test_last_foreign_pr_overlap_is_preserved(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    rc, payload = run_cli(module, capsys, EstateHTTP(256, overlap=True))
    assert rc == 0
    assert payload["collision_state"] == "OVERLAP"
    assert payload["colliding_pr_numbers"] == [1254]
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
        clock.now = {"late": 500.0, "backwards": -1.0,
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
    rc, payload = run_cli(module, capsys, denied)
    assert rc == 2 and payload["code"] == "AUTH_UNAVAILABLE"
    assert len(calls) == 1


@pytest.mark.parametrize("files", [950, 1000])
def test_large_foreign_file_fanout_remains_bounded(files, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", Clock(), raising=False)
    http = EstateHTTP(90, files_per_pr=files)
    rc, payload = run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert len(http.calls) <= 640


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
            clock.now = 181.0
        return result
    monkeypatch.setattr(module, "canonical_json", slow_account)
    rc, payload = run_cli(module, capsys, EstateHTTP(1))
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


@pytest.mark.parametrize("count", [143, 200, 256])
def test_complete_cli_uses_real_git_with_large_synthetic_estate(
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
        clock.now = 181.0
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
        clock.now = 170.0
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
    assert (module._MAX_COLLISION_PRS, module._MAX_HTTP_CALLS) == (256, 640)
    assert module._MAX_HTTP_NORMALIZED_BYTES == 32 * 1024 * 1024
    assert module._HTTP_READ_BUDGET_SECONDS == 180.0
    assert module._MAX_HTTP_BODY_BYTES == 5_000_000


def test_single_get_rejects_accounting_overrun_before_return(monkeypatch):
    """No later GET may be needed to reject the just-accounted late result."""
    module = fx._cli_module()
    clock = Clock()
    monkeypatch.setattr(module, "monotonic", clock)
    original = module.canonical_json
    def slow_account(payload):
        result = original(payload)
        clock.now = 181.0
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
