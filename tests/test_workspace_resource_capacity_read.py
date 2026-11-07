"""Real inert Runtime claim + independently enrolled COO/Workspace source owners."""
import asyncio
import copy
from contextlib import contextmanager
import pytest
from common import workspace_resource_capacity_contract as capacity
from common import executive_workspace_contract as wire
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_workspace_resource_capacity import setup as claim_setup, claim
from tests.test_workspace_retained_activity_read import owner_fixture as coo_fixture
from tests.test_runtime_admitted_plan_read import _bound


@contextmanager
def resource_owner(tmp_path, monkeypatch):
    with coo_fixture(tmp_path / "coo", monkeypatch) as original:
        generator = claim_setup.__wrapped__(tmp_path / "finite", monkeypatch)
        try:
            s = next(generator)
            lease = claim(s)
            with _bound(s.runtime) as (reader, namespace, binding):
                owner = dict(original)
                selected = dict(work_ref="WS:ONE", root_job_id=s.job.root_job_id,
                                job_id=s.job.job_id, attempt_id=lease.attempt.attempt_id)
                service = WorkspaceReadService(cache=original["cache"], runtime=s.runtime,
                    authorize=original["service"].authorize, armed={}, runtime_identity={"db_present": True},
                    bounded_runtime=lambda runtime: reader if runtime is s.runtime else pytest.fail("wrong Runtime"),
                    activity_membership=original["coo"].source.for_workspace_read_principal)
                owner.update(writer=s.runtime, reader=reader, namespace=namespace, binding=binding,
                    service=service, selected=selected, claim_state=s)
                owner["request"] = {"schema": capacity.FRAME_SCHEMA, "operation": capacity.OPERATION,
                    "selection": selected, "principal": owner["principal"]}
                yield owner
        finally:
            generator.close()


@pytest.fixture
def owner(tmp_path, monkeypatch):
    with resource_owner(tmp_path, monkeypatch) as value:
        yield value


def run(owner, **changes):
    return asyncio.run(owner["service"].handle_frame({**owner["request"], **changes}))


def test_original_claim_to_safe_qualified_capacity_body(owner):
    before = owner["namespace"].entries
    result = run(owner)
    assert result["ok"] is True, result
    body = result["result"]
    assert body["availability"] == "AVAILABLE", body
    assert capacity.validate_result(body, owner["selected"]) is body
    assert body["provider_capacity"]["claim_event_id"] > 0
    assert body["provider_capacity"]["current_eligibility"] == "NOT_EVALUATED"
    assert body["source_observation"]["state"] == "SAME"
    assert owner["namespace"].entries == before + 1 == owner["namespace"].exits


@pytest.mark.parametrize("case", ["no_coo", "disabled_coo", "wrong_principal", "no_binding_stamp"])
def test_missing_permission_or_original_membership_never_touches_runtime(owner, case):
    principal = copy.deepcopy(owner["principal"])
    if case == "no_coo": owner["service"]._activity_membership = None
    elif case == "disabled_coo": owner["mutable"]["missions"][0]["enabled"] = False
    elif case == "wrong_principal": principal["subject_digest"] = "3" * 64
    else: owner["service"].authorize.binding_digest = lambda _: None
    before = owner["namespace"].entries
    assert run(owner, principal=principal) == wire.error("access_denied", 403)
    assert owner["namespace"].entries == before


def test_wrong_catalog_root_refuses_before_runtime(owner):
    before = owner["namespace"].entries
    assert run(owner, selection={**owner["selected"], "root_job_id": "JOB-987"}) == wire.error("selection_not_found", 404)
    assert owner["namespace"].entries == before


def test_wrong_current_attempt_is_closed_unavailable_without_receipts(owner):
    selected = {**owner["selected"], "attempt_id": "ATT-" + "9" * 32}
    assert run(owner, selection=selected) == capacity.unavailable(selected, "SOURCE_UNAVAILABLE")


@pytest.mark.parametrize("field,value", [("host_ref", "host-" + "a" * 64), ("clock", 1), ("attempt_id", "../private")])
def test_no_host_clock_or_path_selectors_are_accepted(owner, field, value):
    before = owner["namespace"].entries
    assert run(owner, selection={**owner["selected"], field: value}) == wire.error("invalid_input", 400)
    assert owner["namespace"].entries == before


@pytest.mark.parametrize("change", ["membership", "permission", "replace_source"])
def test_permission_and_membership_are_rechecked_after_source_read(owner, monkeypatch, change):
    from control_plane import workspace_resource_capacity_read as source
    original = source.read_capacity
    def revoke(service, frame):
        response = original(service, frame)
        assert response["result"]["availability"] == "AVAILABLE"
        if change == "membership": owner["mutable"]["missions"][0]["enabled"] = False
        elif change == "permission": service.authorize.binding_digest = lambda _: "e" * 64
        else: service._activity_membership = lambda *args: None
        return response
    monkeypatch.setattr(source, "read_capacity", revoke)
    assert run(owner) == wire.error("access_denied", 403)


@pytest.mark.parametrize("field", ["owner", "publication", "document", "validity", "currentness"])
def test_catalog_publication_and_source_changes_discard_every_receipt(owner, field):
    from dataclasses import replace
    original = owner["cache"].snapshot
    count = [0]
    def changed():
        value = original(); count[0] += 1
        if count[0] == 2:
            if field == "owner": value = replace(value, owner=object())
            elif field == "publication": value = replace(value, publication=value.publication + 1)
            elif field == "document": value.document["source_changed"] = True
            elif field == "validity": value.validity["publication_seq"] = int(value.validity.get("publication_seq", 1)) + 1
            else: value.currentness["source_changed"] = True
        return value
    owner["cache"].snapshot = changed
    assert run(owner) == capacity.unavailable(owner["selected"], "SOURCE_CHANGED")
