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
# Reuse installed App's original signed-token and network-profile fixtures.
from tests.test_executive_mcp_installed_fabric_composition import (
    settings, rsa_key,
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


def test_signed_installed_v2_app_reads_partial_historical_root_without_503(
    tmp_path, short_socket_root, monkeypatch, settings, rsa_key,
):
    """Same authenticated App/Unix/Runtime owner as production, temp data only."""
    import asyncio
    import dataclasses

    import httpx
    from tests.test_executive_mcp_installed_fabric_composition import (
        factory_service, _selected_builder, call, mcp, fixture,
    )

    async def exercise():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile="web_ceo_v2"
        ) as (service, raw, _chain):
            await service.start()
            original=service._require_runtime().jobs.create_job(
                "Temporary unjoined historical Job with no CEO provenance"
            )
            bound=dataclasses.replace(
                settings,
                read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-network-checkout",
                macro_root_flag=None,
                ceo_ingress_socket_path=str(raw["ceo_ingress_socket_path"]),
            )
            app=_selected_builder("web_ceo_v2")(bound,audit_sink=mcp.Sink())
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                ) as client:
                    _job_wire,job_body=await call(
                        client,fixture._read_token(rsa_key),
                        "executive_job",{"job_id":original.job_id},
                    )
                    _raw,body=await call(
                        client,fixture._read_token(rsa_key),
                        "executive_fabric",
                        {"view":"root","root_job_id":original.job_id},
                    )
            # The historical queued Job detail is checked by its existing
            # strict owner, separately from the bounded PARTIAL Fabric root.
            assert job_body["ok"] is True,job_body.get("error")
            assert job_body["data"]["job"]["job_id"]==original.job_id
            assert job_body["data"]["job"]["status"]=="QUEUED"
            assert job_body["data"]["attempt_count"]==0
            assert body["ok"] is True,body.get("error")
            data=body["data"]
            assert data["root"]["job_id"]==original.job_id
            assert data["capability"]["state"]=="PARTIAL"
            assert data["runtime"]["acquisition"]["provenance"]=={
                "state":"PARTIAL","unjoined_job_ids":[original.job_id],
            }
            assert data["runtime"]["acquisition"]["generation"]["state"]=="SAME"
            assert any(
                fact["target_field"]=="runtime.acquisition.provenance"
                and fact["reason"]==UNJOINED_REASON
                for fact in data["missingness"]
            )
            assert body["mode"]=="readonly"
    asyncio.run(exercise())
