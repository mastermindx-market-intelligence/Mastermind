"""Current inherited launch contracts with temporary Runtime and fake providers.

This covers prompt composition only. Commission verification and provider delivery
remain owned by the existing supervisor and its separate integration tests.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
from types import MappingProxyType

import pytest

from tests.test_chairman_coordination_host import host, supervisor, command
from tests.test_chairman_coordination_review import (
    prepare_review, review_supervisor, exercise_independent_review,
)
from tests.test_chairman_coordination_parent import parent_supervisor, dispatch_command
from control_plane.executive_runtime import AttemptLease
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError


@pytest.fixture(params=["work", "review", "parent"])
def launch_case(host, request):
    kind = request.param
    h = host
    if kind == "work":
        sup = supervisor(h)
        outcome = h["runtime"].attempts.dispatch_cycle_job(
            h["work"].job_id, command_id=command(h),
            worker_id="worker-a", quota_class="default")
        field = "_coordination_job_id"
        marker = "\n\nAdditional task content for this exact admitted work Job:\n"
        module, bound = "chairman_coordination_host", "_MAX_PROMPT_BYTES"
    else:
        h = prepare_review(h)
        if kind == "review":
            sup = review_supervisor(h)
            outcome = h["review_dispatch"]
            field = "_coordination_review_job_id"
            marker = "\n\nAdditional review task for this exact admitted Job:\n"
            module, bound = "chairman_coordination_review", "_MAX_PACKET_BYTES"
        else:
            returned, _, _, handoff = exercise_independent_review(h)
            h = {**h, "review_return": returned, "handoff": handoff}
            sup, _ = parent_supervisor(h)
            outcome = h["runtime"].attempts.dispatch_cycle_job(
                h["root"].job_id, command_id=dispatch_command(h),
                worker_id="worker-b", quota_class="default")
            field = "_coordination_root_job_id"
            marker = "\n\nParent coordination evidence:\n"
            module, bound = "chairman_coordination_parent", "_MAX_PROMPT_BYTES"
    assert outcome.lease_token is not None
    lease = AttemptLease(attempt=outcome.attempt, lease_token=outcome.lease_token)
    job = h["runtime"].jobs.get_job(outcome.job_id)
    schema = sup._write_schema(
        sup._run_dir(lease.attempt.attempt_id), job=job, attempt=lease.attempt,
        effective_grant=lease.attempt.effective_grant)
    assert type(sup)._launch_spec is ExecutiveSupervisor._launch_spec
    return dict(sup=sup, job=job, lease=lease, schema=schema, field=field,
                marker=marker, module=importlib.import_module("control_plane." + module),
                bound=bound, starts=sup.adapter.start_count)


def commission_input(mode):
    if mode == "absent":
        return dict(commission=None, inline_commission=None)
    content = "# Exact commission\nPreserve café, λ, and 観測.\nDo not widen authority.\n"
    reference = MappingProxyType({
        "repository": "mastermindx-market-intelligence/Mastermind",
        "commit": "c" * 40,
        "path": "research/commission.md",
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "verified_local_path": "/fixture/verified/commission-λ.md",
    })
    return dict(commission=reference,
                inline_commission=content if mode == "inline" else None)


def launch(case, **kwargs):
    return case["sup"]._launch_spec(
        case["job"], case["lease"], case["schema"],
        case["lease"].attempt.effective_grant, **kwargs)


@pytest.mark.parametrize("selected", [False, True], ids=["unselected", "selected"])
@pytest.mark.parametrize("mode", ["absent", "reference", "inline"])
def test_inherited_launch_preserves_commission_and_assignment(launch_case, monkeypatch, selected, mode):
    case = launch_case
    sup, job, attempt = case["sup"], case["job"], case["lease"].attempt
    inputs = commission_input(mode)
    grant = copy.deepcopy(attempt.effective_grant)
    reference = dict(inputs["commission"]) if inputs["commission"] is not None else None
    if not selected:
        def forbidden(*args):
            raise AssertionError("unselected launch acquired coordination sources")
        monkeypatch.setattr(sup, case["field"], "JOB-unselected")
        monkeypatch.setattr(sup, "_coordination_sources", forbidden)
    original = ExecutiveSupervisor._prompt(
        sup, job, attempt, grant, **inputs)
    spec = launch(case, **inputs)
    if selected:
        assert spec.prompt.startswith(original)
        assert spec.prompt.count(case["marker"]) == 1
    else:
        assert spec.prompt == original
        assert case["marker"] not in spec.prompt
    packet, _ = json.JSONDecoder().raw_decode(spec.prompt[spec.prompt.index("{"):])
    expected_ref = ({key: reference[key] for key in
                     ("repository", "commit", "path", "content_sha256")}
                    if reference is not None else None)
    assert packet["commission_ref"] == expected_ref
    assert packet["commission_local_path"] == (reference["verified_local_path"] if reference else None)
    if reference is not None:
        assert dict(inputs["commission"]) == reference
        assert ("never widen the authorities, paths, validation, lifecycle, or provider "
                "constraints in the JSON packet above.") in spec.prompt
    if inputs["inline_commission"] is not None:
        assert spec.prompt.count(inputs["inline_commission"]) == 1
        assert spec.prompt.count("--- VERIFIED IMMUTABLE COMMISSION BYTES ---") == 1
    else:
        assert "--- VERIFIED IMMUTABLE COMMISSION BYTES ---" not in spec.prompt
    assert attempt.effective_grant == grant
    assert spec.effective_grant_digest == attempt.effective_grant_digest
    assert sup.adapter.start_count == case["starts"]


def test_complete_launch_bound_includes_exact_inline_utf8(launch_case, monkeypatch):
    case = launch_case
    inputs = commission_input("inline")
    # Keep the outer prompt larger than the review packet's separate bound.
    # The immutable inline bytes must count toward the complete launch limit.
    inputs["inline_commission"] += "\n" + "\u03bb" * 65536
    reference = dict(inputs["commission"])
    reference["content_sha256"] = hashlib.sha256(
        inputs["inline_commission"].encode("utf-8")).hexdigest()
    inputs["commission"] = MappingProxyType(reference)
    expected = launch(case, **inputs).prompt
    size = len(expected.encode("utf-8"))
    assert size > len(expected)
    monkeypatch.setattr(case["module"], case["bound"], size)
    accepted = launch(case, **inputs).prompt
    # Fresh bounded Runtime observations may legitimately change their digests.
    assert len(accepted.encode("utf-8")) == size
    assert accepted.count(inputs["inline_commission"]) == 1
    monkeypatch.setattr(case["module"], case["bound"], size - 1)
    with pytest.raises(SupervisorError, match="composition refused"):
        launch(case, **inputs)
    assert case["sup"].adapter.start_count == case["starts"]
