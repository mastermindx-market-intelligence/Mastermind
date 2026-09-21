from __future__ import annotations

import json
from urllib.parse import quote

import pytest

import test_source_continuity as fx


NEW_BASE_SHA = "7" * 40
DIVERGED_MERGE_BASE = "8" * 40
MOVED_TARGET_MERGE_BASE = "9" * 40
SECOND_MOVED_BASE_SHA = "a" * 40


def _branch_url() -> str:
    return (
        f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/branches/"
        f"{quote('master', safe='')}"
    )


def _compare_url(base: str, head: str) -> str:
    return f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/compare/{base}...{head}"


def _compare_payload(
    url: str,
    *,
    base_sha: str,
    merge_base_sha: str,
    head_sha: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "url": url,
        "base_commit": {"sha": base_sha},
        "merge_base_commit": {"sha": merge_base_sha},
    }
    if head_sha is not None:
        payload["commits"] = [{"sha": head_sha}]
    return payload


class MovingBaseHTTP(fx._ProbeHTTP):
    def __init__(
        self,
        *,
        ff_merge_base: str = fx.CURRENT_BASE_SHA,
        refreshed_merge_base: str = fx.BASE_SHA,
        final_base_sha: str = NEW_BASE_SHA,
        malformed_second_base: bool = False,
        omit_forward_url: bool = False,
        omit_refreshed_base: bool = False,
    ) -> None:
        super().__init__()
        self.base_reads = 0
        self.ff_merge_base = ff_merge_base
        self.refreshed_merge_base = refreshed_merge_base
        self.final_base_sha = final_base_sha
        self.malformed_second_base = malformed_second_base
        self.omit_forward_url = omit_forward_url
        self.omit_refreshed_base = omit_refreshed_base

    def __call__(self, url: str, *, token: str, timeout: float):
        self.calls.append((url, token, timeout))
        assert token == fx.TOKEN
        assert timeout > 0
        endpoint = url.removeprefix(fx.API_ROOT + "/")
        base_endpoint = f"repos/{fx.REPOSITORY}/branches/master"
        if endpoint == base_endpoint:
            self.base_reads += 1
            if self.base_reads == 1:
                return {"commit": {"sha": fx.CURRENT_BASE_SHA}}
            if self.base_reads == 2 and self.malformed_second_base:
                return {"commit": {}}
            if self.base_reads == 2:
                return {"commit": {"sha": NEW_BASE_SHA}}
            return {"commit": {"sha": self.final_base_sha}}

        ff_endpoint = (
            f"repos/{fx.REPOSITORY}/compare/"
            f"{fx.CURRENT_BASE_SHA}...{NEW_BASE_SHA}"
        )
        if endpoint == ff_endpoint:
            payload = _compare_payload(
                url,
                base_sha=fx.CURRENT_BASE_SHA,
                merge_base_sha=self.ff_merge_base,
                head_sha=NEW_BASE_SHA,
            )
            if self.omit_forward_url:
                payload.pop("url")
            return payload

        refreshed_endpoint = (
            f"repos/{fx.REPOSITORY}/compare/{NEW_BASE_SHA}...{fx.HEAD_SHA}"
        )
        if endpoint == refreshed_endpoint:
            payload = _compare_payload(
                url,
                base_sha=NEW_BASE_SHA,
                merge_base_sha=self.refreshed_merge_base,
            )
            if self.omit_refreshed_base:
                payload.pop("base_commit")
            return payload

        # Avoid double-recording ordinary calls: fx._ProbeHTTP records them too.
        self.calls.pop()
        return super().__call__(url, token=token, timeout=timeout)


class ConditionalMovingBaseHTTP:
    _source_continuity_conditional = True

    def __init__(
        self,
        module,
        *,
        changed_base_sha: str,
        final_base_sha: str | None = None,
    ) -> None:
        self.module = module
        self.base = fx._ProbeHTTP()
        self.changed_base_sha = changed_base_sha
        self.final_base_sha = final_base_sha or changed_base_sha
        self.base_plain_reads = 0
        self.calls: list[tuple[str, str | None]] = []

    @staticmethod
    def etag(url: str) -> str:
        import hashlib

        return 'W/"' + hashlib.sha256(url.encode("utf-8")).hexdigest() + '"'

    def _plain_payload(self, url: str) -> object:
        endpoint = url.removeprefix(fx.API_ROOT + "/")
        if endpoint == f"repos/{fx.REPOSITORY}/branches/master":
            self.base_plain_reads += 1
            sha = (
                fx.CURRENT_BASE_SHA
                if self.base_plain_reads == 1
                else self.final_base_sha
            )
            return {"commit": {"sha": sha}, "metadata": self.base_plain_reads}

        if endpoint == (
            f"repos/{fx.REPOSITORY}/compare/"
            f"{fx.CURRENT_BASE_SHA}...{NEW_BASE_SHA}"
        ):
            return _compare_payload(
                url,
                base_sha=fx.CURRENT_BASE_SHA,
                merge_base_sha=fx.CURRENT_BASE_SHA,
                head_sha=NEW_BASE_SHA,
            )
        if endpoint == (
            f"repos/{fx.REPOSITORY}/compare/{NEW_BASE_SHA}...{fx.HEAD_SHA}"
        ):
            return _compare_payload(
                url,
                base_sha=NEW_BASE_SHA,
                merge_base_sha=fx.BASE_SHA,
            )
        return self.base(url, token=fx.TOKEN, timeout=20.0)

    def __call__(
        self,
        url: str,
        *,
        token: str,
        timeout: float,
        if_none_match: str | None = None,
    ) -> object:
        assert token == fx.TOKEN and timeout > 0
        self.calls.append((url, if_none_match))
        if if_none_match is None:
            return self.module._HTTPRepresentation(
                payload=self._plain_payload(url),
                etag=self.etag(url),
                not_modified=False,
            )

        if url == _branch_url():
            return self.module._HTTPRepresentation(
                payload={
                    "commit": {"sha": self.changed_base_sha},
                    "metadata": "changed",
                },
                etag='"changed-base"',
                not_modified=False,
            )
        return self.module._HTTPRepresentation(
            payload=None,
            etag=if_none_match.removeprefix("W/"),
            not_modified=True,
        )


def _run(module, http, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, object]]:
    exit_code = fx._run_cli(
        module,
        fx._cli_argv("remote-complete"),
        http=http,
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out)


def _assert_changed(result: tuple[int, dict[str, object]]) -> None:
    exit_code, payload = result
    assert exit_code == 1
    assert payload["code"] == "REMOTE_PROOF_CHANGED"


def test_nonconditional_safe_base_fast_forward_refreshes_receipt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    http = MovingBaseHTTP()

    exit_code, payload = _run(module, http, capsys)

    assert exit_code == 0
    assert payload["schema"] == "mastermind.source_continuity_receipt/v1"
    assert payload["current_base_head_sha"] == NEW_BASE_SHA
    assert payload["remote_merge_base_sha"] == fx.BASE_SHA
    assert http.base_reads == 3
    assert any(
        url == _compare_url(fx.CURRENT_BASE_SHA, NEW_BASE_SHA)
        for url, _, _ in http.calls
    )
    assert any(
        url == _compare_url(NEW_BASE_SHA, fx.HEAD_SHA)
        for url, _, _ in http.calls
    )


def test_nonconditional_divergent_base_refuses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    http = MovingBaseHTTP(ff_merge_base=DIVERGED_MERGE_BASE)
    _assert_changed(_run(module, http, capsys))


def test_nonconditional_refreshed_target_merge_base_movement_refuses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    http = MovingBaseHTTP(refreshed_merge_base=MOVED_TARGET_MERGE_BASE)
    _assert_changed(_run(module, http, capsys))


def test_nonconditional_second_base_move_during_refresh_refuses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    http = MovingBaseHTTP(final_base_sha=SECOND_MOVED_BASE_SHA)
    _assert_changed(_run(module, http, capsys))


def test_moved_base_compare_must_bind_exact_requested_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    exit_code, payload = _run(
        module,
        MovingBaseHTTP(omit_forward_url=True),
        capsys,
    )
    assert exit_code != 0
    assert payload["schema"] == "mastermind.source_continuity_refusal/v1"


def test_refreshed_target_compare_must_bind_new_base_commit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    exit_code, payload = _run(
        module,
        MovingBaseHTTP(omit_refreshed_base=True),
        capsys,
    )
    assert exit_code != 0
    assert payload["schema"] == "mastermind.source_continuity_refusal/v1"


def test_nonconditional_malformed_moved_base_payload_fails_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    exit_code, payload = _run(
        module,
        MovingBaseHTTP(malformed_second_base=True),
        capsys,
    )
    assert exit_code != 0
    assert payload["schema"] == "mastermind.source_continuity_refusal/v1"


def test_conditional_safe_base_fast_forward_refreshes_receipt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    http = ConditionalMovingBaseHTTP(module, changed_base_sha=NEW_BASE_SHA)

    exit_code, payload = _run(module, http, capsys)

    assert exit_code == 0
    assert payload["current_base_head_sha"] == NEW_BASE_SHA
    assert payload["remote_merge_base_sha"] == fx.BASE_SHA
    assert http.base_plain_reads == 2
    assert (_branch_url(), http.etag(_branch_url())) in http.calls


def test_conditional_same_head_metadata_churn_remains_acceptable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = fx._cli_module()
    http = ConditionalMovingBaseHTTP(
        module,
        changed_base_sha=fx.CURRENT_BASE_SHA,
        final_base_sha=fx.CURRENT_BASE_SHA,
    )

    exit_code, payload = _run(module, http, capsys)

    assert exit_code == 0
    assert payload["current_base_head_sha"] == fx.CURRENT_BASE_SHA
    assert payload["remote_merge_base_sha"] == fx.BASE_SHA


def test_closed_invocation_budgets_remain_unchanged() -> None:
    module = fx._cli_module()
    assert module._MAX_COLLISION_PRS == 400
    assert module._MAX_HTTP_CALLS == 1152
    assert module._MAX_HTTP_NORMALIZED_BYTES == 96 * 1024 * 1024
    assert module._HTTP_READ_BUDGET_SECONDS == 300.0
