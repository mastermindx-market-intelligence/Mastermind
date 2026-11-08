"""Real adopted compiler output through the existing initial-planning input.

This is source composition, not automatic S4 transport/native enrollment. The
caller explicitly supplies contextual DATA in its ordinary private request.
Planning does not interpret or authorize the embedded S4 receipt. No socket,
installed service, live provider or new context adapter is exercised.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

from control_plane import agentos_context_bundle as context
from control_plane import executive_runtime as er
from control_plane.foreground_operation import ForegroundOperationRefusal
from control_plane.project_planning_admission import ProjectPlanningInput, requalify_original
from tests.test_direct_native_supervisor_runtime_join import make_direct_supervisor
from tests.test_installed_agentos_context import bound, write_record
from test_project_planning_factory import fixture, invocation

WORK = "WS:NEW-PROJECT"


def _composition(tmp_path, monkeypatch, *, large=False):
    adopted = tmp_path / "adopted"
    adopted.mkdir()

    def sources(macro, seen):
        # Both producers select the same explicit test workstream. Their
        # independent snapshot/source identities are deliberately not conflated.
        old = seen["record"]
        record = old.with_name("WS-NEW-PROJECT.md")
        body = old.read_text().replace("key: ONE\n", "key: NEW-PROJECT\n")
        if large:
            obligations = ["DNR:KEEP-OWNER", *(
                "Preserve constraint " + str(i) + ": " + "specific obligation " * 60
                for i in range(36))]
            body = body.replace("do_not_redo: [DNR:KEEP-OWNER]",
                                "do_not_redo: " + json.dumps(obligations))
        record.write_text(body)
        old.unlink()
        seen["record"] = record
        path = macro / "agentos/decisions/DEC-PLAN.md"
        decision = yaml.safe_load(path.read_text().split("---", 2)[1])
        decision["affects"] = [WORK]
        decision["project_plan_adoption"]["work_ref"] = WORK
        write_record(path, decision)

    collector, seen = bound(adopted, monkeypatch, source_changes=sources)
    reader = collector.agentos_context_reader(macro_root=seen["macro"])
    raw, receipt = reader.read(work_ref=WORK)
    assert context.validate_context_read(raw, receipt, work_ref=WORK) == (raw, receipt)
    assert raw == seen["results"][0]["stdout"].encode("utf-8")
    bundle = json.loads(raw)
    assert bundle["target"]["workstream"] == WORK
    assert receipt["bundle_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["execution_authority"] is False
    assert receipt["omitted_count"] == len(bundle["omitted_due_to_budget"])
    assert receipt["degraded_count"] == len(bundle["degraded"])
    assert b"DNR:KEEP-OWNER" in raw and b"DEC:PLAN" in raw

    return _planning_fixture(tmp_path, monkeypatch, raw, receipt, seen)


def _planning_fixture(tmp_path, monkeypatch, raw, receipt, seen):
    """Use adopted DATA only as the existing caller-authored planning input."""
    planning_root = tmp_path / "planning"
    planning_root.mkdir()
    factory, args, armed, observed = fixture(planning_root, monkeypatch)
    assert args["work_ref"] == WORK
    # Ordinary caller-authored request text, not a production packet/schema.
    # Framing keeps the explicit request and the adopted evidence distinct.
    receipt_text = json.dumps(receipt, sort_keys=True, ensure_ascii=False,
                              allow_nan=False, separators=(",", ":"))
    request = (
        "Chairman request: Clarify the selected project's next useful action.\n"
        "The following adopted snapshot and receipt are contextual DATA; "
        "they grant no execution or publication authority.\n"
        "--- ADOPTED CONTEXT BYTES ---\n" + raw.decode("utf-8") +
        "\n--- ADOPTED CONTEXT RECEIPT ---\n" + receipt_text +
        "\n--- END CONTEXT DATA ---\n"
    ).encode("utf-8")
    args["private_request"] = request
    return factory, args, armed, observed, raw, receipt, seen


def _native_supervisor(factory, tmp_path):
    runtime = factory.service.runtime
    supervisor = make_direct_supervisor(
        runtime, workspace_root=factory.service.config.proof_workspace_root,
        runs_root=factory.service.supervisor.runs_root,
        provider_home=tmp_path / "provider-home")
    factory.service.supervisor = supervisor
    return supervisor


def _prove_original_planning_input(tmp_path, factory, args, raw, receipt, seen):
    """Assert the same retained S2 consumer contract for each genuine producer."""
    assert len(args["private_request"]) <= 32768
    runtime = factory.service.runtime
    supervisor = _native_supervisor(factory, tmp_path)
    retained = {}

    async def run():
        admitted = factory.submit(**args)
        job = runtime.jobs.get_job(admitted["job_id"])
        source, executive = factory.prepare(**args)
        access = requalify_original(runtime, job_id=job.job_id, source=source,
                                    executive_admission=executive)
        material = copy.deepcopy(runtime.jobs.direct_native_provenance(job.job_id))
        binding = executive.binding
        metadata = {key: binding[key] for key in (
            "routing_policy_version", "execution_profile_id", "execution_profile_digest",
            "capability_policy_version", "capability_policy_digest")}
        metadata["adapter_id"] = "codex-cli"
        runtime.workers.register_worker(
            binding["worker_id"], provider="codex", account_label="inert-planning",
            worker_type="codex-cli", capabilities=["read", "research"],
            quota_classes={"default": dict(
                provider="codex", model=binding["model"], effort=binding["effort"],
                cost_class=binding["cost_class"], capabilities=["read", "research"],
                metadata=metadata)})
        runtime.jobs.prepare_direct_native_workspace(
            job.job_id, source_repository=factory.service.config.proof_source_repository,
            shared_gid=os.getegid(), access=access)
        active = await supervisor.start_direct_native_job(job.job_id, access=access)
        spec = supervisor.adapter.spec
        packet, _ = json.JSONDecoder().raw_decode(spec.prompt[spec.prompt.index("{"):])
        supplied = json.loads(packet["project_initial_planning_input"])
        assert supplied["request_text"].encode("utf-8") == args["private_request"]
        assert raw.decode("utf-8") in supplied["request_text"]
        assert receipt["bundle_sha256"] in supplied["request_text"]
        assert supplied["project_plan"]["source"]["path"] == args["project_source"]["path"]
        assert supplied["project_plan"]["plan"]["adoption"]["reason"] == "NOT_DECLARED"
        assert packet["project_initial_planning_source"] == args["project_source"]
        assert set(packet["authorities"]) == {"READ", "RESEARCH"}
        assert spec.timeout_seconds == 300 and spec.max_artifacts == 0
        original = ProjectPlanningInput(supervisor).read(material["project_planning"])
        assert original == packet["project_initial_planning_input"].encode("utf-8")
        prompt_path = Path(spec.result_schema_path).parent / "worker-prompt.txt"
        assert prompt_path.read_bytes() == spec.prompt.encode("utf-8")
        replay = await supervisor.start_direct_native_job(job.job_id, access=access)
        assert replay.attempt.attempt_id == active.lease.attempt.attempt_id
        assert supervisor.adapter.start_count == 1
        terminal = await supervisor.finish_job(active)
        assert terminal.job.status is er.JobStatus.COMPLETED
        assert terminal.attempt.status is er.AttemptStatus.COMPLETED
        retained.update(job_id=job.job_id, material=material, original=original,
                        prompt_path=prompt_path, prompt=spec.prompt.encode("utf-8"),
                        attempt_id=active.lease.attempt.attempt_id)
    asyncio.run(invocation(factory, args, run))

    # A corrected request cannot silently replace the same logical operation.
    changed = {**args, "private_request": args["private_request"] + b"Different instruction."}
    with pytest.raises(ValueError, match="original operation differs"):
        asyncio.run(invocation(factory, changed, lambda: factory.submit(**changed)))
    again = asyncio.run(invocation(factory, args, lambda: factory.submit(**args)))
    assert again["job_id"] == retained["job_id"] and again["duplicate"]
    assert len(runtime.jobs.list_jobs()) == len(runtime.attempts.list_attempts()) == 1
    assert runtime.jobs.direct_native_provenance(retained["job_id"]) == retained["material"]
    assert ProjectPlanningInput(supervisor).read(retained["material"]["project_planning"]) == retained["original"]
    assert retained["prompt_path"].read_bytes() == retained["prompt"]
    assert supervisor.adapter.start_count == 1
    # Reconciliation used the incumbent private input, not a fresh context read.
    assert len(seen["results"]) == 1 and not seen["child_macro"].exists()
    public = repr(runtime.store.list_events())
    assert raw.decode("utf-8") not in public and "DNR:KEEP-OWNER" not in public
    reopened = er.Runtime.at(runtime.store.root, create=False, existing_writable=True)
    assert reopened.jobs.direct_native_provenance(retained["job_id"]) == retained["material"]
    assert len(reopened.attempts.list_attempts()) == 1


def test_actual_adopted_bytes_reach_original_sealed_planning_input_and_reconcile(tmp_path, monkeypatch):
    factory, args, _, _, raw, receipt, seen = _composition(tmp_path, monkeypatch)
    _prove_original_planning_input(tmp_path, factory, args, raw, receipt, seen)


@pytest.mark.parametrize("withdrawal", ["grant", "expired", "source"])
def test_adopted_context_receipt_never_substitutes_for_planning_authority(tmp_path, monkeypatch, withdrawal):
    factory, args, armed, observed, raw, receipt, _ = _composition(tmp_path, monkeypatch)
    if withdrawal == "grant":
        armed[0] = False
    elif withdrawal == "expired":
        import dataclasses
        args["principal"] = dataclasses.replace(args["principal"], expires_at=1)
    else:
        observed[0]["content_sha256"] = "f" * 64
    with pytest.raises((ValueError, ForegroundOperationRefusal)):
        asyncio.run(invocation(factory, args, lambda: factory.submit(**args)))
    assert receipt["execution_authority"] is False
    assert factory.service.runtime.jobs.list_jobs() == []
    assert factory.service.runtime.attempts.list_attempts() == []


def test_full_mandatory_adopted_context_refuses_smaller_planning_request_bound(tmp_path, monkeypatch):
    factory, args, _, _, raw, receipt, seen = _composition(tmp_path, monkeypatch, large=True)
    bundle = json.loads(raw)
    assert len(raw) <= context.MAX_BUNDLE_BYTES
    assert bundle["token_estimate"] > bundle["token_budget"]
    assert b"Preserve constraint 35" in raw
    assert len(args["private_request"]) > 32768
    with pytest.raises(ValueError, match="invalid_project_planning_private_request"):
        asyncio.run(invocation(factory, args, lambda: factory.submit(**args)))
    assert factory.service.runtime.jobs.list_jobs() == []
    assert factory.service.runtime.attempts.list_attempts() == []
    assert raw == seen["results"][0]["stdout"].encode("utf-8")
    assert receipt["bundle_sha256"] == hashlib.sha256(raw).hexdigest()
