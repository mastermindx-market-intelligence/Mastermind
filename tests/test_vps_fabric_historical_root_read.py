"""Canonical V2 Fabric root reads remain truthful for historical non-CEO Jobs.

The existing producer explicitly marks a generic root as PARTIAL with one
unjoined Job. The installed Web-CEO validator must accept the *exact* missing
producer fact instead of reporting a fabricated backend outage. These are
temporary Runtime fixtures; no installed database or worker is accessed.
"""
from __future__ import annotations

import copy

from control_plane import fabric_job_view as producer
from control_plane.executive_runtime import Runtime
from integrations.mastermind_executive_app.gateway import (
    WebCeoV2CeoIngressReadGateway as Reader,
)

UNJOINED_REASON = (
    "durable orchestration-root workstream join unavailable for included Jobs"
)


def historical_root(tmp_path):
    writer=Runtime.at(tmp_path / "runtime")
    job=writer.jobs.create_job("Historical plain queued Job with no orchestration provenance")
    # The installed owner supplies an explicit closed arming source; bare {}
    # is not an installed arming receipt and must never be accepted.
    armed,_notes=producer._read_armed(None)
    document=producer.read_fabric_view_v2_from_runtime(
        writer, job.job_id, armed=armed, runtime_identity={"db_present": True}
    )
    return job, document


def validate_root(job, document):
    return Reader._valid_fabric_data(
        document,
        arguments={"view": "root", "root_job_id": job.job_id},
        bounded=[],
    )


def test_existing_unjoined_generic_root_yields_partial_not_backend_unavailable(tmp_path):
    job,document=historical_root(tmp_path)
    acquisition=document["runtime"]["acquisition"]
    assert acquisition["provenance"] == {
        "state": "PARTIAL", "unjoined_job_ids": [job.job_id]
    }
    assert document["capability"]["state"] == "PARTIAL"
    assert len(document["children"]) == 0
    assert any(
        fact["missingness_class"] == "MISSING_PRODUCER"
        and fact["target_field"] == "runtime.acquisition.provenance"
        and fact["producer_owner"] == "executive_runtime"
        and fact["reason"] == UNJOINED_REASON
        for fact in document["missingness"]
    )
    assert validate_root(job,document)


def test_changed_or_removed_historical_missingness_is_not_authenticated(tmp_path):
    job,document=historical_root(tmp_path)
    assert validate_root(job,document)
    wrong=copy.deepcopy(document)
    for fact in wrong["missingness"]:
        if fact["target_field"]=="runtime.acquisition.provenance":
            fact["reason"]="unknown provenance therefore fully accepted"
    assert not validate_root(job,wrong)
    omitted=copy.deepcopy(document)
    omitted["missingness"]=[
        fact for fact in omitted["missingness"]
        if fact["target_field"]!="runtime.acquisition.provenance"
    ]
    assert not validate_root(job,omitted)


def test_old_ceo_only_missingness_phrase_is_not_an_accepted_alias(tmp_path):
    job,document=historical_root(tmp_path)
    assert validate_root(job,document)
    old=copy.deepcopy(document)
    for fact in old["missingness"]:
        if fact["target_field"]=="runtime.acquisition.provenance":
            fact["reason"]="durable CEO-intent workstream join unavailable for included Jobs"
    # Historical vocabulary is not a second accepted source contract.
    assert not validate_root(job,old)


def test_known_durable_ceo_provenance_retains_full_read_contract(tmp_path):
    from tests.test_fabric_job_view_bounded import _root
    writer,job=_root(tmp_path / "admitted-ceo")
    armed,_notes=producer._read_armed(None)
    document=producer.read_fabric_view_v2_from_runtime(
        writer,job.job_id,armed=armed,runtime_identity={"db_present":True}
    )
    provenance=document["runtime"]["acquisition"]["provenance"]
    assert provenance["state"]=="COMPLETE"
    assert provenance["unjoined_job_ids"]==[]
    assert document["capability"]["state"]=="PROVEN"
    assert validate_root(job,document)
