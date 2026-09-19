"""Subject-PR semantic revalidation regressions."""
from __future__ import annotations

import copy
import json

import pytest

import test_source_continuity as fx
import test_source_continuity_saturated_foreign_pr as sf


def _bounded(module, transport):
    bounded = module._BoundedHTTPGet(
        transport,
        subject_pull_url=sf.TARGET_PULL_URL,
    )
    for url in transport.first:
        bounded(url, token=sf.TOKEN, timeout=20.0)
    return bounded


def _noisy_subject() -> dict[str, object]:
    changed = copy.deepcopy(sf._target_pr_payload())
    changed.update(
        {
            "title": "representation-only churn",
            "updated_at": "2026-09-17T04:00:00Z",
            "merge_commit_sha": "9" * 40,
            "mergeable": True,
            "rebaseable": False,
            "mergeable_state": "unstable",
            "comments": 17,
        }
    )
    changed["head"]["repo"].update(  # type: ignore[index]
        {"updated_at": "2026-09-17T04:00:00Z", "pushed_at": "2026-09-17T04:00:01Z"}
    )
    return changed


def test_subject_pr_changed_200_with_same_canonical_identity_does_not_starve() -> None:
    module = sf._module()
    transport = sf.SemanticRevalidationTransport(
        module,
        {sf.TARGET_PULL_URL: sf._target_pr_payload()},
        changed={sf.TARGET_PULL_URL: _noisy_subject()},
    )
    bounded = _bounded(module, transport)
    initial_bytes = bounded._bytes

    assert bounded.validate_unchanged(token=sf.TOKEN) is True
    assert bounded._semantic_revalidations == [sf.TARGET_PULL_URL]
    assert bounded._bytes > initial_bytes
    assert bounded._calls == 2


@pytest.mark.parametrize(
    "mutator",
    [
        lambda row: row.update(state="closed"),
        lambda row: row.update(draft=False),
        lambda row: row["head"].update(ref="other-branch"),
        lambda row: row["head"].update(sha="8" * 40),
        lambda row: row["head"]["repo"].update(full_name="other/repository"),
        lambda row: row["base"].update(ref="other-base"),
        lambda row: row.pop("head"),
    ],
)
def test_subject_pr_source_or_hold_identity_movement_still_refuses(mutator) -> None:
    module = sf._module()
    changed = copy.deepcopy(sf._target_pr_payload())
    mutator(changed)
    transport = sf.SemanticRevalidationTransport(
        module,
        {sf.TARGET_PULL_URL: sf._target_pr_payload()},
        changed={sf.TARGET_PULL_URL: changed},
    )
    bounded = _bounded(module, transport)

    assert bounded.validate_unchanged(token=sf.TOKEN) is False


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
def test_subject_pr_malformed_hold_projection_still_refuses(mutator) -> None:
    module = sf._module()
    changed = copy.deepcopy(sf._target_pr_payload())
    mutator(changed)
    transport = sf.SemanticRevalidationTransport(
        module,
        {sf.TARGET_PULL_URL: sf._target_pr_payload()},
        changed={sf.TARGET_PULL_URL: changed},
    )
    bounded = _bounded(module, transport)

    assert bounded.validate_unchanged(token=sf.TOKEN) is False


def test_unassigned_pull_detail_endpoint_remains_unconditionally_strict() -> None:
    module = sf._module()
    other_url = sf.TARGET_PULL_URL.rsplit("/", 1)[0] + "/999"
    payload = sf._target_pr_payload()
    transport = sf.SemanticRevalidationTransport(
        module,
        {other_url: payload},
        changed={other_url: copy.deepcopy(payload)},
    )
    bounded = _bounded(module, transport)

    assert bounded.validate_unchanged(token=sf.TOKEN) is False


def test_main_issues_receipt_when_only_subject_pr_representation_changes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sf._module()
    target = f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/pulls/{fx.PR_NUMBER}"
    changed = {
        "state": "open",
        "draft": True,
        "labels": [],
        "title": "advisory churn",
        "merge_commit_sha": "9" * 40,
        "mergeable": True,
        "head": {
            "ref": fx.BRANCH,
            "sha": fx.HEAD_SHA,
            "repo": {
                "full_name": fx.REPOSITORY,
                "pushed_at": "2026-09-17T04:00:00Z",
            },
        },
        "base": {"ref": "master"},
    }
    first = copy.deepcopy(changed)
    first.pop("title")
    first.pop("mergeable")
    first["head"]["repo"].pop("pushed_at")
    http = sf.MainSemanticConditionalHTTP(
        module,
        {target: changed},
        first_overrides={target: first},
    )

    exit_code = fx._run_cli(module, fx._cli_argv(), http=http)
    captured = capsys.readouterr()

    assert exit_code == 0
    receipt = json.loads(captured.out)
    assert receipt["schema"] == "mastermind.source_continuity_receipt/v1"
    assert receipt["local_equals_remote"] is True


def test_main_still_refuses_subject_pr_head_movement(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sf._module()
    target = f"{fx.API_ROOT}/repos/{fx.REPOSITORY}/pulls/{fx.PR_NUMBER}"
    first = {
        "state": "open",
        "draft": True,
        "labels": [],
        "head": {"ref": fx.BRANCH, "sha": fx.HEAD_SHA, "repo": {"full_name": fx.REPOSITORY}},
        "base": {"ref": "master"},
    }
    changed = copy.deepcopy(first)
    changed["head"]["sha"] = "8" * 40
    http = sf.MainSemanticConditionalHTTP(
        module,
        {target: changed},
        first_overrides={target: first},
    )

    exit_code = fx._run_cli(module, fx._cli_argv(), http=http)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out)["code"] == "REMOTE_PROOF_CHANGED"
