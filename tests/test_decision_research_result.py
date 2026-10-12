"""Pure single-decision candidate claims, not authenticated provider execution."""
import asyncio
from copy import deepcopy
import json

import pytest

from control_plane.wake_events import canonical_json_bytes
from test_decision_research import prepare


OP_REF = "svc-esp-" + "a" * 32
FP = "b" * 64
REF = {
    "schema": "mastermind.executive_service_inference_result_ref.v2",
    "job_id": "JOB-001",
    "attempt_id": "ATT-" + "c" * 32,
    "worker_id": "fixture-worker",
    "result_sha256": "d" * 64,
    "content_sha256": "e" * 64,
}


def claims(context):
    return {
        "schema": "mastermind.bot_research_claims.v1",
        "context_id": context["context_id"],
        "snapshot_id": context["snapshot_id"],
        "claims": [
            {
                "claim_id": "claim-1",
                "statement": "Synthetic account rows report cash, subject to source verification.",
                "kind": "OBSERVATION",
                "stance": "NEUTRAL",
                "evidence_refs": ["book_truth:0"],
                "contrary_refs": ["risk_truth:0"],
                "uncertainty": "UNQUANTIFIED",
                "falsifier": "A corrected account generation contradicts the preserved cash field.",
            }
        ],
        "unknowns": ["All unselected and incomplete evidence domains remain unresolved."],
        "coverage_ack": {
            "selection_complete": context["selection_complete"],
            "selected_rows": sum(s["selected_rows"] for s in context["sections"].values()),
            "unselected_domains": context["unselected_domains"],
        },
    }


def direct(context, payload=None):
    payload = claims(context) if payload is None else payload
    result = {
        "schema_version": "mastermind.executive_service_inference_worker_result.v1",
        "job_id": REF["job_id"], "run_id": REF["attempt_id"],
        "worker_id": REF["worker_id"], "status": "COMPLETED",
        "answer": json.dumps(payload, sort_keys=True),
    }
    return {
        "schema": "mastermind.fabric_service_inference_result_view.v1",
        "operation_ref": OP_REF,
        "request_fingerprint": FP,
        "reference": deepcopy(REF),
        "generation": {"schema": "mastermind.runtime_read_observation.v1",
                       "state": "SAME", "source_identity": "f" * 32,
                       "before": 1, "after": 1},
        "availability": "AVAILABLE", "execution_status": "COMPLETED",
        "content_complete": True, "acceptance": "NOT_PROJECTED",
        "document": {"schema": "mastermind.executive_service_inference_result_document.v1",
                     "reference": deepcopy(REF), "result": result},
    }


def consume(context=None, response=None):
    from brain.decision_research_result import consume_validated_answer
    c = context or prepare()
    return consume_validated_answer(
        c, response if response is not None else direct(c),
        expected_operation_ref=OP_REF,
        expected_request_fingerprint=FP,
        expected_reference=REF,
    )


def error_type():
    from brain.decision_research_result import ResearchClaimError
    return ResearchClaimError


def test_pure_candidate_claims_bind_original_context_and_never_create_authority():
    context = prepare(); before = deepcopy(context)
    output = consume(context)
    assert context == before
    assert output["schema"] == "mastermind.bot_research_candidate_claim_set.v1"
    assert output["context_id"] == context["context_id"]
    assert output["snapshot_id"] == context["snapshot_id"]
    assert output["authority"] == {"write_permitted": False, "execution_authority": False,
                                   "numeric_target_authority": False}
    assert output["candidate_only"] is True
    assert output["claims"][0]["evidence_refs"] == ["book_truth:0"]
    assert output["claims"][0]["contrary_refs"] == ["risk_truth:0"]
    assert output["claim_set_id"].startswith("sha256:")
    assert "A corrected account" in output["claims"][0]["falsifier"]
    assert "No source" not in output["unknowns"]


def test_identical_verified_input_yields_stable_fingerprint_and_copy_isolated():
    a, b = consume(), consume()
    assert a == b and a is not b
    a["claims"][0]["statement"] = "changed"
    assert consume() == b


@pytest.mark.parametrize("field,new", [
    ("schema", "malformed"),
    ("operation_ref", "svc-esp-" + "f" * 32),
    ("request_fingerprint", "f" * 64),
    ("availability", "UNAVAILABLE"),
    ("execution_status", "RUNNING"),
    ("content_complete", False),
    ("acceptance", "ACCEPTED"),
])
def test_wrong_operation_or_status_cannot_become_a_claim(field, new):
    c = prepare(); view = direct(c); view[field] = new
    with pytest.raises(error_type()): consume(c, view)


@pytest.mark.parametrize("change", [
    {"job_id": "JOB-999"}, {"attempt_id": "ATT-" + "a" * 32},
    {"content_sha256": "f" * 64}, {"result_sha256": "f" * 64},
])
def test_foreign_or_substituted_reference_is_rejected(change):
    c = prepare(); d = direct(c); d["reference"].update(change)
    with pytest.raises(error_type()):consume(c,d)


@pytest.mark.parametrize("patch", [
    {"context_id": "sha256:" + "f" * 64},
    {"snapshot_id": "sha256:" + "f" * 64},
    {"schema": "forged"}, {"extra_authority": {"trade": True}},
])
def test_claim_schema_and_original_context_are_closed(patch):
    c=prepare(); p=claims(c); p.update(patch)
    with pytest.raises(error_type()):consume(c,direct(c,p))


@pytest.mark.parametrize("field,value", [
    ("claim_id", "claim 1"),
    ("statement", ""),
    ("kind", "TRADING_SIGNAL"),
    ("stance", "BUY_NOW"),
    ("uncertainty", 0.99),
    ("falsifier", ""),
    ("evidence_refs", ["outside:0"]),
    ("evidence_refs", ["book_truth:200"]),
    ("evidence_refs", ["book_truth:0", "book_truth:0"]),
    ("contrary_refs", ["outside:0"]),
])
def test_claims_demand_selected_citations_and_explicit_falsifiers(field,value):
    c=prepare();p=claims(c);p["claims"][0][field]=value
    with pytest.raises(error_type()):consume(c,direct(c,p))


def test_duplicate_claim_ids_or_more_than_twelve_claims_refuse():
    c=prepare();p=claims(c);p["claims"].append(deepcopy(p["claims"][0]))
    with pytest.raises(error_type()):consume(c,direct(c,p))
    p=claims(c);p["claims"]=p["claims"]*13
    with pytest.raises(error_type()):consume(c,direct(c,p))


def test_partial_context_cannot_discard_unknowns_or_coverage_ack():
    c=prepare()
    for change in [
        ("unknowns", []),
        ("coverage_ack", {"selection_complete":True, "selected_rows":999, "unselected_domains":[]}),
    ]:
        p=claims(c);p[change[0]]=change[1]
        with pytest.raises(error_type()):consume(c,direct(c,p))


def test_model_cannot_add_numeric_target_or_order_authority():
    c=prepare();p=claims(c)
    for key in ["target_weight", "order", "trade_size", "execution_authority", "calibrated_confidence"]:
        forged=deepcopy(p);forged["claims"][0][key]=5
        with pytest.raises(error_type()):consume(c,direct(c,forged))


def test_unselected_section_cannot_be_cited_even_if_snapshot_contains_it():
    c=prepare(section_ids=["book_truth"])
    p=claims(c);p["claims"][0]["contrary_refs"]=["risk_truth:0"]
    with pytest.raises(error_type()):consume(c,direct(c,p))


def test_corrupt_or_unqualified_original_context_is_rejected():
    c=prepare();c["context_id"]="sha256:"+"f"*64
    with pytest.raises(error_type()):consume(c,direct(c))


def test_invalid_json_duplicates_nonfinite_and_oversized_answers_refuse():
    c=prepare();d=direct(c)
    for invalid in [
        '{"schema":"x","schema":"y"}',
        '{"claims":[NaN]}',
        '{"claims":"'+("x"*14000)+'"}',
        "not-json",
    ]:
        view=deepcopy(d);view["document"]["result"]["answer"]=invalid
        with pytest.raises(error_type()):consume(c,view)


def test_one_selected_source_artifact_is_not_multiple_independent_confirmations():
    c=prepare(); p=claims(c)
    p["claims"][0]["evidence_refs"]=["book_truth:0","book_truth:1"]
    out=consume(c,direct(c,p))
    assert len(out["claims"][0]["artifact_identities"]) == 1
    assert out["artifact_independence"] == "NOT_ESTABLISHED"


def test_no_runtime_provider_or_account_write_dependency():
    from brain import decision_research_result as module
    source=__import__("pathlib").Path(module.__file__).read_text()
    for forbidden in ["subprocess", "httpx", "requests.", "paper_account", "create_job",
                      "submit_service_intent", "open(", "write_text", "datetime.now"]:
        assert forbidden not in source


@pytest.mark.parametrize("field,bad", [
    ("kind", []), ("kind", {}),
    ("stance", []), ("stance", {"buy": True}),
    ("uncertainty", []), ("uncertainty", {"calibrated": 0.99}),
])
def test_wrong_llm_enum_types_refuse_with_typed_claim_error(field,bad):
    c=prepare(); p=claims(c); p["claims"][0][field]=bad
    with pytest.raises(error_type()):consume(c,direct(c,p))


def test_ambiguous_multi_source_row_cannot_invent_artifact_provenance():
    from portfolio import decision_snapshot_contracts as snapshots
    c=prepare()
    section=c["sections"]["book_truth"]
    section["source_ids"]=["book.account","macro.risk"]
    c["context_id"]=snapshots.content_digest({k:v for k,v in c.items() if k!="context_id"})
    p=claims(c)
    with pytest.raises(error_type(),match="source"):
        consume(c,direct(c,p))


def test_candidate_output_cannot_expose_full_input_artifacts_or_secret_paths():
    c=prepare()
    out=consume(c)
    serialized=json.dumps(out)
    assert "data/portfolios/" not in serialized
    assert "account.json" not in serialized
    assert out["uncertainty_calibration"]=="NOT_CALIBRATED"


def test_raw_row_cannot_choose_its_own_source_artifact_in_multi_source_section():
    from portfolio import decision_snapshot_contracts as snapshots
    c=prepare()
    s=c["sections"]["book_truth"]
    s["source_ids"]=["book.account","macro.risk"]
    s["rows"][0]["value"]["source_id"]="macro.risk"
    c["context_id"]=snapshots.content_digest({k:v for k,v in c.items() if k!="context_id"})
    p=claims(c)
    with pytest.raises(error_type(),match="provenance"):
        consume(c,direct(c,p))


def test_structural_coverage_and_omissions_survive_false_model_unknowns():
    from portfolio import decision_snapshot_contracts as snapshots
    c=prepare()
    section=c["sections"]["book_truth"]
    section["source_omitted_rows"]=7
    section["rows_total"]+=7
    c["context_id"]=snapshots.content_digest({k:v for k,v in c.items() if k!="context_id"})
    p=claims(c)
    p["unknowns"]=["No source or coverage gaps exist."]
    output=consume(c,direct(c,p))
    coverage=output["coverage"]
    assert coverage["snapshot_coverage"]==c["snapshot_coverage"]
    assert coverage["snapshot_state"]==c["snapshot_state"]
    assert coverage["domain_coverage"]==c["domain_coverage"]
    assert coverage["source_omitted_rows"]["book_truth"]==7
    assert coverage["snapshot_gap_count"]==c["snapshot_gap_count"]
    assert coverage["selection_omitted_rows"]["book_truth"]==section["selection_omitted_rows"]
    assert coverage["selection_complete"]==c["selection_complete"]


def test_huge_integer_is_a_typed_refusal_not_uncaught_python_error():
    c=prepare();d=direct(c)
    d["document"]["result"]["answer"]='{"n":'+("9"*4301)+'}'
    with pytest.raises(error_type()):
        consume(c,d)


def test_readonly_candidate_consumer_uses_original_client_answer_only():
    from brain.decision_research_result import read_original_candidate_claims
    from brain.decision_research import inference_request
    c=prepare();ref=deepcopy(REF)
    class Client:
        calls=[]
        async def answer(self, operation, objective, wire):
            self.calls.append((operation,objective,wire))
            return direct(c)
        async def submit(self,*a):raise AssertionError("read-only consumer submitted")
        async def reconcile(self,*a):raise AssertionError("extra status read")
    client=Client()
    output=asyncio.run(read_original_candidate_claims(
        client, original_context=c,
        operation_key="candidate-example-1", objective="Inspect the original preserved evidence.",
        original_operation_ref=OP_REF, original_request_fingerprint=FP,
        original_inference_request=inference_request(c,task_aware=True),
    ))
    assert len(client.calls)==1
    operation,objective,wire=client.calls[0]
    assert operation=="candidate-example-1" and objective=="Inspect the original preserved evidence."
    assert wire==inference_request(c,task_aware=True)
    # Caller-retained operation identity is explicit. The actual service
    # client owns operation-key equality before candidate projection.
    assert output["candidate_only"] is True


def test_readonly_candidate_consumer_rejects_foreign_result_and_never_retries():
    from brain.decision_research_result import read_original_candidate_claims
    from brain.decision_research import inference_request
    c=prepare()
    class Client:
        calls=0
        async def answer(self,*args):
            self.calls+=1
            return direct(c)
    client=Client()
    with pytest.raises(error_type()):
        asyncio.run(read_original_candidate_claims(client,original_context=c,
             operation_key="different-operation",objective="Inspect evidence.",
             original_operation_ref="svc-esp-"+"f"*32,original_request_fingerprint=FP,
             original_inference_request=inference_request(c)))
    assert client.calls==1


def test_original_nondefault_wire_must_survive_read_only_claim_consumer():
    from brain.decision_research_result import read_original_candidate_claims
    from brain.decision_research import inference_request
    c=prepare()
    wire=inference_request(c,max_output_chars=2000,task_aware=True)
    class Client:
        calls=0
        async def answer(self,key,objective,received):
            self.calls+=1
            assert received==wire
            return direct(c)
    client=Client()
    returned=asyncio.run(read_original_candidate_claims(
        client,original_context=c,operation_key="nondefault-output-limit",
        objective="Inspect original evidence.", original_operation_ref=OP_REF,
        original_request_fingerprint=FP,
        original_inference_request=wire,
    ))
    assert returned["candidate_only"] is True and client.calls==1


def test_inflight_mutation_cannot_substitute_another_context_after_request():
    from brain.decision_research_result import read_original_candidate_claims
    from brain.decision_research import inference_request
    c=prepare()
    original=deepcopy(c)
    different=prepare(question="This is a different question and evidence context.")
    wire=inference_request(c,task_aware=True)
    class Client:
        calls=0
        async def answer(self,key,objective,received):
            self.calls+=1
            assert received==wire
            c.clear();c.update(deepcopy(different))
            return direct(different)
    client=Client()
    with pytest.raises(error_type()):
        asyncio.run(read_original_candidate_claims(
            client,original_context=c,operation_key="mutating-context",
            objective="Inspect original evidence.", original_operation_ref=OP_REF,
            original_request_fingerprint=FP,
            original_inference_request=wire,
        ))
    assert client.calls==1 and c!=original
