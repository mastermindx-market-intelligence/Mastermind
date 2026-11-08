"""Behavioral qualification for the portable Hermes Design Director documents.

No live inference, Paper mutation, Slack send or runtime acceptance is simulated.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import unittest
import io
from PIL import Image
import tempfile
from contextlib import contextmanager

SCRIPT = Path(__file__).resolve().parents[1] / "skills/mastermind-design-director/scripts/director.py"
spec = importlib.util.spec_from_file_location("design_director", SCRIPT)
director = importlib.util.module_from_spec(spec)
spec.loader.exec_module(director)


@contextmanager
def documents():
    with tempfile.TemporaryDirectory() as name:
        yield make_documents(Path(name))


def make_documents(tmp_path):
    # A decoded image fixture tests transport integrity, never visual quality.
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
    data = buffer.getvalue()
    (tmp_path / "screen.png").write_bytes(data)
    image = {"file_id":"file-a","page_id":"page-a","node_id":"node-a","path":"screen.png",
             "sha256":hashlib.sha256(data).hexdigest(),"observed_at":"2026-11-08T00:00:00Z",
             "source_ref":"fixture://paper/screen"}
    a = {"schema":"mastermind.design.assignment.v1","operation_id":"op-a","assignment_id":"design-a",
         "issued_at":"2026-11-07T23:59:00Z","source_ref":"fixture://source/assignment","product":"Mastermind OS","persona":"Chairman",
         "objective":"Clarify the project decision and evidence path","user_question":"What needs my decision?",
         "useful_next_step":"Open the original project decision","shell_ref":"fixture://shell",
         "token_ref":"fixture://tokens","paper":{"file_id":"file-a","page_id":"page-a",
         "scope_node_ids":["node-a"],"allow_new_artboards":False},"preserve":["Original conversation"],
         "states":["ready","loading","error"],"viewports":["390","1440"],"acceptance":["Original task identity"],
         "constraints":[],"non_goals":["New queue"],"session_ref":"fixture://session/original"}
    r = {"schema":"mastermind.design.completion.v1","operation_id":"op-a","assignment_id":"design-a",
         "assignment_sha256":director.digest(a),"session_ref":a["session_ref"],"account_alias":"C1",
         "summary":"Refined the existing decision surface","continuation":"Review current Paper",
         "status":"complete","reported_at":"2026-11-08T00:01:00Z","decisions":["One primary action"],
         "interactions":["Open original project"],"gaps":[],"limitations":["Design only"],
         "checks":["Screenshot inspected"],"screens":[{"file_id":"file-a","page_id":"page-a",
         "node_id":"node-a","name":"Today","change":"changed","screenshot":image}]}
    r["coverage"] = {group:[{"requirement":requirement,"status":"observed","evidence":"Fixture observation",
        "screenshot_sha256":[image["sha256"]]} for requirement in a[group]] for group in ("preserve","states","viewports","acceptance")}
    q = {"schema":"mastermind.design.critique.v1","completion_sha256":director.digest(r),
         "reviewer":"Test reviewer","evidence_ref":"fixture://review","observed_at":"2026-11-08T00:02:00Z",
         "viewed_screenshot_sha256":[image["sha256"]],"dimensions":{k:{"rating":"adequate","evidence":"Fixture observation"}
         for k in director.REVIEW_DIMENSIONS},"issues":[]}
    c = {"schema":"mastermind.design.corpus.v1","references":[{"id":"os-today","title":"Today decision surface",
         "product":"Mastermind OS","source_ref":"fixture://paper/today","tags":["decision","project"],
         "principles":["One clear next step"],"limitations":["Fixture"],"reuse_contexts":["Project decision"],
         "why_it_works":"Direct next action","approval":{"classification":"unknown"},"screenshot":image}]}
    return a,r,q,c,tmp_path


def check_brief_preserves_scope_revision_and_creative_freedom(documents):
    a,r,q,c,root=documents
    output=director.brief(a,c)
    assert director.digest(a) in output
    assert "file-a" in output and "page-a" in output and "Original conversation" in output
    assert "creative principal" in output and "[unknown]" in output


def check_retrieval_does_not_turn_unknown_into_approval(documents):
    a,r,q,c,root=documents
    director.corpus(c,root)
    assert director.retrieve(c,"project decision",product=a["product"])[0]["id"]=="os-today"
    assert director.retrieve(c,"project decision",approved_only=True)==[]
    assert director.retrieve(c,"unrelated weather")==[]
    c["references"][0]["approval"]["classification"]="chairman_approved"
    with unittest.TestCase().assertRaisesRegex(director.DesignError,"approval.actor"):
        director.corpus(c,root)


def check_negative_examples_cannot_be_positive_references(documents):
    a,r,q,c,root=documents
    c["references"][0]["approval"]["classification"]="superseded"
    assert director.retrieve(c,"project decision")==[]
    a["reference_ids"]=["os-today"]
    with unittest.TestCase().assertRaisesRegex(director.DesignError,"Negative examples"):
        director.brief(a,c)


def check_return_rejects_cross_assignment_and_target_drift(documents,change):
    a,r,q,c,root=documents
    if change=="operation": r["operation_id"]="another"
    elif change=="revision": a["preserve"].append("A new requirement")
    elif change=="file": r["screens"][0]["file_id"]="another"
    elif change=="page": r["screens"][0]["page_id"]="another"
    elif change=="session": r["session_ref"]="fixture://session/new"
    elif change=="node": r["screens"][0]["node_id"]="outside"
    else: r["screens"][0]["screenshot"]["node_id"]="outside"
    with unittest.TestCase().assertRaises(director.DesignError): director.completion(a,r,root)


def check_completion_is_evidence_validation_never_acceptance(documents):
    a,r,q,c,root=documents
    result=director.completion(a,r,root)
    assert result["document_valid"]
    assert not result["design_accepted"] and not result["production_proven"]


def check_untrusted_evidence_cannot_escape_or_substitute_bytes(documents,attack):
    a,r,q,c,root=documents
    e=r["screens"][0]["screenshot"]
    if attack=="changed_bytes": (root/"screen.png").write_bytes(b"\x89PNG\r\n\x1a\nchanged")
    elif attack=="traversal": e["path"]="../screen.png"
    elif attack=="symlink":
        (root/"alias.png").symlink_to(root/"screen.png"); e["path"]="alias.png"
    elif attack=="not_image":
        (root/"screen.png").write_bytes(b"not an image");e["sha256"]=hashlib.sha256(b"not an image").hexdigest()
    else:
        with (root/"screen.png").open("wb") as f: f.truncate(director.MAX_IMAGE_BYTES+1)
    with unittest.TestCase().assertRaises(director.DesignError): director.completion(a,r,root)


def check_critique_binds_exact_completion_and_screenshot(documents):
    a,r,q,c,root=documents
    assert director.critique(a,r,q,root)["action"]=="candidate_for_design_acceptance"
    q["viewed_screenshot_sha256"]=["0"*64]
    with unittest.TestCase().assertRaisesRegex(director.DesignError,"unknown screenshot"):
        director.critique(a,r,q,root)


def check_unobserved_workflow_requires_evidence(documents):
    a,r,q,c,root=documents
    q["dimensions"]["workflow"]["rating"]="not_observed"
    assert director.critique(a,r,q,root)["action"]=="gather_missing_evidence"


def check_revision_keeps_original_assignment_and_session(documents):
    a,r,q,c,root=documents
    q["issues"]=[{"priority":"material","dimension":"workflow","finding":"Ambiguous next action",
                  "evidence":"Fixture screen","requested_change":"Clarify the decision label"}]
    output=director.continuation(a,r,q,root)
    assert "fixture://session/original" in output and "design-a" in output
    assert "Clarify the decision label" in output and "Original conversation" in output
    a["effect_state"]="unknown"; r["assignment_sha256"]=director.digest(a);q["completion_sha256"]=director.digest(r)
    with unittest.TestCase().assertRaisesRegex(director.DesignError,"original effect"):
        director.continuation(a,r,q,root)


def check_polish_alone_does_not_force_revision(documents):
    a,r,q,c,root=documents
    q["issues"]=[{"priority":"polish","dimension":"spacing","finding":"Optional rhythm adjustment",
                  "evidence":"Fixture screen","requested_change":"Consider two more pixels"}]
    assert director.critique(a,r,q,root)["action"]=="candidate_for_design_acceptance"
    with unittest.TestCase().assertRaisesRegex(director.DesignError,"No material revision"):
        director.continuation(a,r,q,root)


def check_bounded_observation_advice_never_resubmits(documents,state,minutes,expected):
    a,r,q,c,root=documents
    receipt={"schema":"mastermind.design.observation.v1","operation_id":a["operation_id"],
             "assignment_id":a["assignment_id"],"source_ref":"fixture://original-receipt", "state":state,
             "observed_at":"2026-11-08T00:00:00Z"}
    now=datetime.fromtimestamp(datetime(2026,11,8,tzinfo=timezone.utc).timestamp()+minutes*60,timezone.utc)
    result=director.status_advice(a,receipt,now)
    assert result["action"]==expected and not result["automatic_resubmit"] and not result["scheduler_created"]
    if state=="delivered": assert not result["worker_start_reported"]


def check_notification_is_a_draft_on_an_explicit_original_thread(documents):
    a,r,q,c,root=documents
    n=director.notification(a,r,root,channel="CEXAMPLE",thread="1.0",canonical_ref="fixture://return")
    assert n["channel"]=="CEXAMPLE" and n["thread_ts"]=="1.0"
    assert not n["sent"] and not n["design_accepted"]
    with unittest.TestCase().assertRaises(director.DesignError): director.notification(a,r,root,channel="",thread="1.0",canonical_ref="fixture://return")


def check_handoff_requires_real_spec_and_cited_design_decision(documents):
    a,r,q,c,root=documents
    fields=("decision_ref","decision_actor","implementation_repo","target_paths","component_mapping","tokens",
            "interactions","data_contracts","responsive","accessibility","verification","known_gaps")
    s={"schema":"mastermind.design.handoff.v1","completion_sha256":director.digest(r),**{k:f"Fixture {k}" for k in fields}}
    out=director.handoff(a,r,q,s,root)
    assert "Data contracts" in out and "does not prove implementation" in out
    del s["decision_ref"]
    with unittest.TestCase().assertRaises(director.DesignError): director.handoff(a,r,q,s,root)


def check_cli_consumes_documents_and_returns_errors_without_effects(documents):
    a,r,q,c,root=documents
    for name,value in (("assignment",a),("completion",r)):
        (root/f"{name}.json").write_text(json.dumps(value))
    command=[sys.executable,str(SCRIPT),"validate-completion","--assignment",str(root/"assignment.json"),
             "--completion",str(root/"completion.json"),"--evidence-root",str(root)]
    good=subprocess.run(command,capture_output=True,text=True,check=False)
    assert good.returncode==0 and json.loads(good.stdout)["document_valid"]
    (root/"screen.png").unlink()
    bad=subprocess.run(command,capture_output=True,text=True,check=False)
    assert bad.returncode==2 and json.loads(bad.stderr)["effect"]=="none"


class DesignDirectorTests(unittest.TestCase):
    def test_document_journeys(self):
        checks=[value for name,value in globals().items() if name.startswith("check_") and name not in {
            "check_return_rejects_cross_assignment_and_target_drift",
            "check_untrusted_evidence_cannot_escape_or_substitute_bytes",
            "check_bounded_observation_advice_never_resubmits"}]
        for check in checks:
            with self.subTest(scenario=check.__name__), documents() as docs:
                check(docs)

    def test_return_identity_and_target_fences(self):
        for change in ("operation","revision","file","page","session","node","image_target"):
            with self.subTest(change=change), documents() as docs:
                check_return_rejects_cross_assignment_and_target_drift(docs,change)

    def test_evidence_integrity(self):
        for attack in ("changed_bytes","traversal","symlink","not_image","oversize"):
            with self.subTest(attack=attack), documents() as docs:
                check_untrusted_evidence_cannot_escape_or_substitute_bytes(docs,attack)

    def test_original_status_boundaries(self):
        cases=[("prepared",0,"attended_dispatch_if_eligible"),
               ("delivered",44,"await_existing_return"),
               ("delivered",45,"read_official_status_or_canonical_return"),
               ("running",90,"reconcile_with_existing_owner_no_resubmit"),
               ("effect_unknown",100,"reconcile_original_effect"),
               ("completed",1,"verify_completion_and_live_paper"),
               ("failed",1,"diagnose_original_failure")]
        for state,minutes,expected in cases:
            with self.subTest(state=state,minutes=minutes), documents() as docs:
                check_bounded_observation_advice_never_resubmits(docs,state,minutes,expected)


if __name__=="__main__":
    unittest.main()


def check_coverage_and_chronology_fences(documents):
    import copy
    a,r,q,c,root=documents
    for mutate in (lambda x:x.pop("coverage"), lambda x:x["coverage"]["states"].pop(),
                   lambda x:x.update(reported_at="2026-11-07T00:00:00Z"),
                   lambda x:x["screens"][0]["screenshot"].update(observed_at="2026-11-07T00:00:00Z")):
        changed=copy.deepcopy(r);mutate(changed)
        with unittest.TestCase().assertRaises(director.DesignError): director.completion(a,changed,root)
    changed=copy.deepcopy(q);changed["dimensions"]["responsive"]["rating"]="not_observed"
    assert director.critique(a,r,changed,root)["action"]=="gather_missing_evidence"
    changed=copy.deepcopy(a);changed["effect_state"]="unknown"
    returned=copy.deepcopy(r);returned["assignment_sha256"]=director.digest(changed)
    reviewed=copy.deepcopy(q);reviewed["completion_sha256"]=director.digest(returned)
    assert director.critique(changed,returned,reviewed,root)["action"]=="reconcile_original_effect"
    (root/"screen.png").write_bytes(b"\x89PNG\r\n\x1a\nnot-a-complete-image")
    r["screens"][0]["screenshot"]["sha256"]=hashlib.sha256((root/"screen.png").read_bytes()).hexdigest()
    with unittest.TestCase().assertRaisesRegex(director.DesignError,"decodable"):
        director.completion(a,r,root)
