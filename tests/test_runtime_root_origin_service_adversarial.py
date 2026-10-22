"""Closed registered service root classification never upgrades malformed roots.

All mutations are local disposable SQLite fixture writes. Neither the canonical
Runtime schema nor the immutable production Event ledger is modified.
"""
import json
import sqlite3

import pytest

from control_plane import workspace_source_join as join
from tests.test_runtime_root_origin_bounded import (
    _admit_registered_inference_fixture, corrupt_creation, unavailable,
)
from tests.test_workspace_source_join import actual


@pytest.mark.parametrize("field,value", [
    ("task_kind", "judgment"),
    ("workstream", "CEO:ILLEGAL"),
    ("grounding", {"mastermind_sha": "1"*40, "macro_sha": "2"*40}),
    ("grounding", {"mastermind_sha": "1"*40, "macro_sha": "2"*40,
                    "boot_packet_schema": "mastermind.ceo_boot_packet.v2"}),
    ("requested_authorities", ["READ"]),
    ("effective_authorities", ["EXECUTE"]),
    ("write_authorities", ["WRITE"]),
    ("inference_request", {"schema": "unexpected"}),
    ("unreviewed_extension", {"elevate": True}),
])
def test_corrupted_inference_origin_cannot_hide_inside_generic_roots(
    actual, tmp_path, field, value
):
    writer, bound, namespace, original = actual
    service = _admit_registered_inference_fixture(
        writer, tmp_path, operation="adversarial-origin-"+field.replace("_", "-")
    )
    corrupt_creation(writer, service,
        payload=lambda body:body["provenance"].update({field:value}))
    result = unavailable(bound, namespace)
    assert original != service and result[0] is None


@pytest.mark.parametrize("column,value", [
    ("requested_authorities_json", '["READ","EXECUTE"]'),
    ("authority_level", "A5"),
    ("owner_seat", "ceo"),
    ("escalation_target", "chairman"),
    ("allowed_write_paths_json", '["/tmp/outside"]'),
    ("validation_commands_json", '[["curl", "http://unsafe.example"]]'),
])
def test_job_authority_tamper_blocks_origin_mapping(actual,tmp_path,column,value):
    writer,bound,namespace,original=actual
    service=_admit_registered_inference_fixture(
        writer,tmp_path,operation="authority-tamper-"+column.replace("_", "-")
    )
    # Update only the disposable test database's job row; original Event
    # provenance remains unchanged so cross-store consistency is tested.
    with sqlite3.connect(writer.store.path) as db:
        assert column in {
            "requested_authorities_json", "authority_level", "owner_seat",
            "escalation_target", "allowed_write_paths_json", "validation_commands_json",
        }
        db.execute(f"UPDATE jobs SET {column}=? WHERE job_id=?", (value,service))
    result=unavailable(bound,namespace)
    assert result[0] is None


def test_valid_registered_service_still_excluded_from_ceo_candidates(actual,tmp_path):
    writer,bound,namespace,original=actual
    service=_admit_registered_inference_fixture(
        writer,tmp_path,operation="known-enrolled-control"
    )
    result=join._bounded_runtime_inputs(bound())
    assert result[0] is not None,result[4]
    assert {x["job_id"] for x in result[0]}=={original}
    assert service not in {x["job_id"] for x in result[0]}
