"""Actual original COO membership and inert captured Runtime source."""
import asyncio
import copy
from contextlib import contextmanager
import pytest
from common import workspace_host_observation_contract as wire
from common.executive_workspace_contract import error
from control_plane.workspace_host_observation_read import handle_host_observation_frame
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_workspace_host_observation import setup as claim_setup
from tests.test_finite_initial_transaction import claim, snap
from tests.test_workspace_retained_activity_read import owner_fixture as coo_fixture
from tests.test_runtime_admitted_plan_read import _bound


@contextmanager
def host_owner(tmp_path, monkeypatch):
    with coo_fixture(tmp_path / "coo", monkeypatch) as original:
        generator = claim_setup.__wrapped__(tmp_path / "finite", monkeypatch)
        try:
            s = next(generator)
            lease = claim(s)
            with _bound(s.runtime) as (reader, namespace, binding):
                selected = dict(work_ref="WS:ONE", root_job_id=s.job.root_job_id, job_id=s.job.job_id, attempt_id=lease.attempt.attempt_id)
                service = WorkspaceReadService(cache=original["cache"], runtime=s.runtime,
                    authorize=original["service"].authorize, armed={}, runtime_identity={"db_present": True},
                    bounded_runtime=lambda actual: reader if actual is s.runtime else pytest.fail("wrong Runtime"),
                    activity_membership=original["coo"].source.for_workspace_read_principal)
                owner = {**original, "service": service, "writer": s.runtime, "reader": reader, "namespace": namespace,
                    "binding": binding, "selected": selected, "claim_state": s}
                owner["request"] = {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION, "selection": selected, "principal": owner["principal"]}
                yield owner
        finally:
            generator.close()


@pytest.fixture
def owner(tmp_path, monkeypatch):
    with host_owner(tmp_path, monkeypatch) as value: yield value


def run(owner, **changes):
    return asyncio.run(handle_host_observation_frame(owner["service"], {**owner["request"], **changes}))


def test_current_original_owner_returns_only_recorded_host_and_unchanged_runtime(owner):
    before = snap(owner["claim_state"])
    result = run(owner)
    assert result["ok"] is True and result["result"]["availability"] == "AVAILABLE", result
    wire.validate_result(result["result"], owner["selected"])
    assert result["result"]["observation"]["observed_host_role"] == "PHYSICAL_RESOURCE_HOST"
    assert owner["namespace"].entries == owner["namespace"].exits == 1
    assert snap(owner["claim_state"]) == before


@pytest.mark.parametrize("case", ["no_coo", "disabled_coo", "wrong_principal", "no_stamp"])
def test_foreign_or_revoked_owner_never_reads_runtime(owner, case):
    principal = copy.deepcopy(owner["principal"])
    if case == "no_coo": owner["service"]._activity_membership = None
    elif case == "disabled_coo": owner["mutable"]["missions"][0]["enabled"] = False
    elif case == "wrong_principal": principal["subject_digest"] = "3" * 64
    else: owner["service"].authorize.binding_digest = lambda _: None
    assert run(owner, principal=principal) == error("access_denied", 403)
    assert owner["namespace"].entries == 0


@pytest.mark.parametrize("field", ["host_ref", "clock", "snapshot", "path"])
def test_selection_does_not_accept_host_clock_metrics_or_path(owner, field):
    assert run(owner, selection={**owner["selected"], field: "foreign"}) == error("invalid_input", 400)
    assert owner["namespace"].entries == 0


@pytest.mark.parametrize("case", ["permission", "membership", "owner"])
def test_post_read_permission_or_original_owner_change_withholds_every_fact(owner, monkeypatch, case):
    from control_plane import workspace_host_observation_read as read
    original = read.read_host_observation
    def changed(service, frame):
        result = original(service, frame)
        assert result["result"]["availability"] == "AVAILABLE"
        if case == "permission": service.authorize.binding_digest = lambda _: "e" * 64
        elif case == "membership": owner["mutable"]["missions"][0]["enabled"] = False
        else: service._activity_membership = lambda *args: None
        return result
    monkeypatch.setattr(read, "read_host_observation", changed)
    assert run(owner) == error("access_denied", 403)


@pytest.mark.parametrize("field", ["owner", "publication", "document", "validity", "currentness"])
def test_source_publication_change_discards_recorded_metrics(owner, field):
    from dataclasses import replace
    original = owner["cache"].snapshot
    count = [0]
    def changed():
        value = original(); count[0] += 1
        if count[0] == 2:
            if field == "owner": value = replace(value, owner=object())
            elif field == "publication": value = replace(value, publication=value.publication + 1)
            elif field == "document": value.document["changed"] = True
            elif field == "validity": value.validity["publication_seq"] = int(value.validity.get("publication_seq", 1)) + 1
            else: value.currentness["changed"] = True
        return value
    owner["cache"].snapshot = changed
    assert run(owner) == wire.unavailable(owner["selected"], "SOURCE_CHANGED")
