"""Real three-book callers retain an existing run through a local refusal.

Synthetic transport, research, quotes and clock; actual submission allocator,
packet gate, closed-session queue, account and decision-journal owners.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from test_provider_start_run_binding import RunBindingHarness, CANDIDATES, AUTH_FAILURE, BOOKS, FIXED_REFUSAL

ASOF="2026-10-16"
STAMP="2026-10-16T22:30:00+00:00"
BOOK_INFO={
    "autonomous": ("AAPL", "SPY", "USD"),
    "china": ("600519.SS", "000300.SS", "CNY"),
    "hk": ("0700.HK", "^HSI", "HKD"),
}
RATES={"USD":1.0,"CNY":7.0,"HKD":7.8}
PRICES_USD={"AAPL":200.0,"SPY":500.0,"600519.SS":200.0,"000300.SS":500.0,"0700.HK":50.0,"^HSI":2500.0}

class FrozenClock(datetime):
    @classmethod
    def now(cls,tz=None):
        value=cls(2026,10,16,22,30,tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)

def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []

def submission_args(book, *, valid=True):
    ticker=BOOK_INFO[book][0]
    return {
        "holdings":[{"ticker":ticker,"action":"add","conviction":"high",
            "rationale":"Retain this fixture company for its durable earnings growth.",
            "evidence":["Synthetic audited earnings evidence for the offline comparison."],
            "why_now":"The synthetic earnings catalyst is now within the decision horizon."}],
        "summary":"One qualified fixture company merits a deterministic portfolio allocation.",
        "mandate":"Manage this simulated equity book within its permitted venue.",
        "falsifiers":["Exit if the recorded earnings thesis deteriorates materially."] if valid else [],
        "evidence_planes":["fundamentals","technicals"],
        "source_provenance":["synthetic offline fixture evidence"],
        "liquidity_notes":"Synthetic quotes are fixed for this offline comparison.",
        "expected_failure_mode":"An adverse earnings revision reduces the expected investment return.",
        "risk_posture":"normal",
        "cash_rationale":"Retain residual cash because the fixture contains one qualified addition.",
        "exit_decisions":[], "decision_memo":{},
    }

class BookRunHarness(RunBindingHarness):
    def __init__(self,monkeypatch,root,book,*,mode="shadow",binding=True,seed=True):
        super().__init__(monkeypatch,root)
        from bot import settle
        from brain import cost_guard,decision_submission,portfolio_learning,self_mirror,risk_lens,student
        from bridge import build_portfolio
        from control_plane import packet_gate,decision_packet,run_events
        from data_layer import feed_health
        from portfolio import advisor_trade,firm_exposure,fx,mandate_packet,paper_account,registry,safety
        self.book=book
        self.module=importlib.import_module("bot."+book)
        self.mcp=importlib.import_module("brain."+book+"_mcp")
        self.pa,self.registry=paper_account,registry
        self.submitted,self.calls,self.gates=[],[],[]
        self.governance=root/"packet-governance"
        self.binding_enabled=binding
        monkeypatch.setenv("MASTERMIND_PACKET_GATE",mode)
        monkeypatch.setattr(registry,"_ROOT",root)
        monkeypatch.setattr(fx,"rate_per_usd",lambda currency:RATES[currency])
        self.fx_values=[]
        actual_fx=fx.usd_to
        def convert(value,currency):
            result=actual_fx(value,currency)
            self.fx_values.append((value,currency,result))
            return result
        monkeypatch.setattr(fx,"usd_to",convert)
        monkeypatch.setattr(paper_account,"_current_price",lambda ticker:PRICES_USD.get(ticker))
        for module in (self.module,paper_account,decision_packet,run_events,decision_submission):
            monkeypatch.setattr(module,"datetime",FrozenClock)
        monkeypatch.setattr(cost_guard,"over_budget",lambda *a,**kw:False)
        monkeypatch.setattr(cost_guard,"record",lambda *a,**kw:None)
        monkeypatch.setattr(advisor_trade,"pending_proposals",lambda **kw:[])
        monkeypatch.setattr(decision_submission,"_instrument_identity",lambda ticker:{
            "kind":"common_stock","status":"synthetic_common_stock","verified":True,
        })
        monkeypatch.setattr(settle,"is_open",lambda portfolio_id:False)
        monkeypatch.setattr(feed_health,"status",lambda *a,**kw:{"status":"ok"})
        if hasattr(self.module,"_warm_live"):
            monkeypatch.setattr(self.module,"_warm_live",lambda *a,**kw:None)
        if hasattr(self.module,"_translate_report"):
            monkeypatch.setattr(self.module,"_translate_report",lambda *a,**kw:False)
        monkeypatch.setattr(build_portfolio,"write",lambda *a,**kw:{})
        monkeypatch.setattr(mandate_packet,"build",lambda *a,**kw:{})
        monkeypatch.setattr(mandate_packet,"write_packet",lambda *a,**kw:None)
        monkeypatch.setattr(mandate_packet,"emit_run_event",lambda *a,**kw:None)
        monkeypatch.setattr(portfolio_learning,"attach_lesson_trace",lambda *a,**kw:{"ok":True,"cited_ids":[]})
        monkeypatch.setattr(portfolio_learning,"record_application",lambda *a,**kw:{"ok":True,"recorded":False})
        monkeypatch.setattr(portfolio_learning,"refresh_post_sell",lambda *a,**kw:{"summary":{}})
        monkeypatch.setattr(portfolio_learning,"derive_lessons",lambda *a,**kw:{"lessons":[]})
        monkeypatch.setattr(firm_exposure,"caps_enabled",lambda:False)
        monkeypatch.setattr(safety,"compute_safety",lambda *a,**kw:{})
        monkeypatch.setattr(safety,"gross_overlay",lambda *a,**kw:{"gross_mult":1.0})
        monkeypatch.setattr(safety,"persist",lambda *a,**kw:None)
        monkeypatch.setattr(self.module,"_build_prompt",lambda *a,**kw:"Synthetic bounded book research")
        monkeypatch.setattr(self_mirror,"inject",lambda value,*a,**kw:value)
        monkeypatch.setattr(risk_lens,"govern_persona",lambda value,*a,**kw:value)
        monkeypatch.setattr(student,"inject",lambda value,*a,**kw:value)
        monkeypatch.setattr(self.mcp,"build_servers",lambda:{})
        monkeypatch.setattr(self.mcp,"allowed_tools",lambda:[])
        monkeypatch.setattr(self.kr,"candidates",lambda:CANDIDATES)
        monkeypatch.setattr(self.cb,"_selected_backend",lambda *_:"cli")
        original_reason=self.cb.reason
        async def forward(prompt,**kwargs):
            self.calls.append(copy.deepcopy(kwargs))
            assert kwargs["book"]==self.book and kwargs["role"]=="deep" and kwargs["arm"] is True
            # Retain the real public bridge and actual caller book/role. Only
            # transport selection, provider guard and optional logging are fixture inputs.
            kwargs["model"]="synthetic-model"
            kwargs["before_provider_start"]=self.guard
            kwargs["log_run"]=self.log_run
            if self.wrong_book is not None:
                kwargs["book"]=self.wrong_book
            return await original_reason(prompt,**kwargs)
        monkeypatch.setattr(self.cb,"reason",forward)
        if not binding:
            monkeypatch.setattr(self.cb,"provider_refusal_run_id",lambda *a,**kw:None,raising=False)
        actual_gate=packet_gate.process
        def gate(book,submission,prior,**kwargs):
            result=actual_gate(book,submission,prior,run_events_root=self.governance,
                               rejections_root=self.governance,**kwargs)
            self.gates.append({"extras":copy.deepcopy(kwargs.get("extras")),
                "packet":result.packet.to_dict() if result.packet else None,
                "meta":copy.deepcopy(result.to_meta())})
            return result
        monkeypatch.setattr(packet_gate,"process",gate)
        if seed:
            paper_account._save_account({
                "inception_date":ASOF,"starting_nav":1_000_000.0,"cash":1_000_000.0,
                "positions":{},"spy_shares":None,"spy_inception_price":None,
            },book)
        self.guard=None
        self.log_run=True
        self.wrong_book=None

    def configure(self,*,accepted=True,valid=True,log_run=True,wrong_book=None):
        self.log_run,self.wrong_book=log_run,wrong_book
        calls=[]
        def guard():
            calls.append(1)
            return None if accepted and len(calls)==1 else False
        self.guard=guard
        if accepted:
            async def submit():
                response=await self.mcp.submit_book.handler(submission_args(self.book,valid=valid))
                actual=self.mcp.read_submission()
                assert actual and len(actual["holdings"])==1
                assert "SUBMISSION REJECTED" not in json.dumps(response)
                assert actual["falsifiers"]==submission_args(self.book,valid=valid)["falsifiers"]
                expected_policy,expected_weight=(
                    ("deterministic_conviction_allocator.v2",0.15)
                    if self.book=="autonomous" else
                    ("deterministic_incremental_regional_allocator.v1",0.18)
                )
                assert actual["holdings"][0]["weight_source"]==expected_policy
                assert actual["holdings"][0]["weight"]==expected_weight
                self.submitted.append(copy.deepcopy(actual))
            self.plans.append([submit,RuntimeError(AUTH_FAILURE)])
        self.turn_guard_calls=calls

    def run_book(self,**kwargs):
        self.configure(**kwargs)
        return getattr(self.module,"run_"+self.book)(ASOF,armed=True,force=True)

    def capture(self,out):
        base=self.registry.data_dir(self.book)
        pending_path=self.pa._pending_target_path(self.book)
        return {
            "out":copy.deepcopy(out),"row":copy.deepcopy(self.module.load_decisions()[0]),
            "pending":json.loads(pending_path.read_text()) if pending_path.exists() else None,
            "account":copy.deepcopy(self.pa._load_account(self.book)),
            "fills":read_rows(base/"fills.jsonl"),
            "submissions":copy.deepcopy(self.submitted),"gates":copy.deepcopy(self.gates),
            "events":read_rows(self.governance/"data"/"governance"/"run_events.jsonl"),
            "rejections":read_rows(self.governance/"data"/"governance"/"packet_rejections.jsonl"),
        }

def without_correlation(value):
    """Only enumerated lineage/correlation fields may differ."""
    value=copy.deepcopy(value)
    value["out"]["brain"].pop("run_id",None)
    value["out"].pop("packet_id",None)
    for field in ("packet_id","rejection_id"):
        value["out"].get("packet_meta",{}).pop(field,None)
    for field in ("run_id","packet_id"):
        value["row"].pop(field,None)
    for gate in value["gates"]:
        gate["extras"].pop("run_id",None)
        if gate["packet"] is not None:
            gate["packet"].pop("run_id",None)
        for field in ("packet_id","rejection_id"):
            gate["meta"].pop(field,None)
    for event in value["events"]:
        for field in ("run_id","packet_id","rejection_id"):
            event.get("extra",{}).pop(field,None)
    for rejection in value["rejections"]:
        for field in ("run_id","rejection_id"):
            rejection.pop(field,None)
        rejection["packet"].pop("run_id",None)
    return value

def assert_correlations(capture,run_id,mode,valid):
    gate=capture["gates"][0]
    assert gate["extras"]["run_id"]==run_id
    meta_copies=(gate["meta"],capture["out"]["packet_meta"])
    if mode=="off":
        assert capture["events"]==capture["rejections"]==[]
        assert gate["packet"] is None
        assert capture["out"]["packet_id"] is None and capture["row"]["packet_id"] is None
        for meta in meta_copies:
            assert meta["packet_id"] is None and meta["rejection_id"] is None
        return
    packet=gate["packet"]
    assert packet["run_id"]==(run_id or "")
    raw="|".join([packet["book"],packet["asof"],packet["submitted_at"],run_id or ""])
    expected=hashlib.sha256(raw.encode()).hexdigest()[:16]
    assert capture["out"]["packet_id"]==expected
    assert capture["row"]["packet_id"]==expected
    for meta in meta_copies:
        assert meta["packet_id"]==expected
    event=capture["events"][0]
    assert event["extra"]["packet_id"]==expected and event["extra"]["run_id"]==(run_id or "")
    if valid:
        assert capture["rejections"]==[]
        assert event["kind"]=="packet_accepted"
        assert event["extra"].get("rejection_id") is None
        for meta in meta_copies:
            assert meta["rejection_id"] is None
    else:
        rejection=capture["rejections"][0]
        assert rejection["run_id"]==(run_id or "")
        assert rejection["packet"]["run_id"]==(run_id or "")
        raw="|".join([rejection["ts"],packet["book"],packet["asof"],run_id or ""])
        rejection_id=hashlib.sha256(raw.encode()).hexdigest()[:16]
        assert rejection["rejection_id"]==rejection_id
        for meta in meta_copies:
            assert meta["rejection_id"]==rejection_id
        assert event["extra"]["rejection_id"]==rejection_id

@pytest.mark.parametrize("book",BOOKS)
@pytest.mark.parametrize("mode,valid",[("off",True),("shadow",True),("shadow",False),("enforce",True),("enforce",False)])
def test_real_book_refusal_binding_changes_only_provenance(monkeypatch,tmp_path,book,mode,valid):
    outcomes=[]
    for binding in (False,True):
        with monkeypatch.context() as mp:
            h=BookRunHarness(mp,tmp_path/str(binding),book,mode=mode,binding=binding)
            out=h.run_book(accepted=True,valid=valid)
            capture=h.capture(out)
            assert len(h.created)==len(h.calls)==len(h.submitted)==1
            assert len(h.providers)==1 and len(h.turn_guard_calls)==2
            assert len(h.classifications)==len(h.cooling)==1 and h.sessions==[]
            assert out["brain"]["ok"] is False and FIXED_REFUSAL in out["brain"]["error"]
            assert capture["fills"]==[] and capture["account"]["positions"]=={}
            assert capture["account"]["cash"]==1_000_000.0
            accepted=mode!="enforce" or valid
            if book!="autonomous":
                ticker,benchmark,currency=BOOK_INFO[book]
                benchmark_value=(PRICES_USD[benchmark],currency,PRICES_USD[benchmark]*RATES[currency])
                target_value=(PRICES_USD[ticker],currency,PRICES_USD[ticker]*RATES[currency])
                assert benchmark_value in h.fx_values
                # A gate-rejected target never advances to target price/FX preparation.
                assert (target_value in h.fx_values) is accepted
            assert out["decided"] is accepted and out["decision_effective"] is accepted
            assert out["target_status"]==("queued" if accepted else "rejected_packet_gate")
            if accepted:
                target={row["ticker"]:row["weight"] for row in h.submitted[0]["holdings"]}
                assert capture["pending"]["target"]==target and target
                for field in ("decision_id","submission_sha256","target_sha256"):
                    assert capture["row"][field]
            else:
                assert capture["pending"] is None
            run_id=h.created[0] if binding else None
            assert out["brain"]["run_id"]==run_id
            assert capture["row"]["run_id"]==run_id
            assert h.rl.read_run(h.created[0])["ts"] is not None
            assert_correlations(capture,run_id,mode,valid)
            outcomes.append(capture)
    assert without_correlation(outcomes[0])==without_correlation(outcomes[1])
    if mode!="off":
        assert outcomes[0]["out"]["packet_id"]!=outcomes[1]["out"]["packet_id"]
        assert outcomes[0]["events"][0]["event_id"]==outcomes[1]["events"][0]["event_id"]

@pytest.mark.parametrize("book",BOOKS)
@pytest.mark.parametrize("identity",["created","logging-off","wrong-book"])
def test_real_book_no_submission_keeps_failure_and_exact_availability(monkeypatch,tmp_path,book,identity):
    h=BookRunHarness(monkeypatch,tmp_path,book,mode="enforce")
    wrong=next(b for b in BOOKS if b!=book) if identity=="wrong-book" else None
    out=h.run_book(accepted=False,log_run=identity!="logging-off",wrong_book=wrong)
    capture=h.capture(out)
    expected=h.created[0] if identity=="created" else None
    assert out["brain"]["run_id"]==expected and capture["row"]["run_id"]==expected
    assert out["decided"] is False and out["decision_effective"] is False
    assert out["target_status"]=="rejected_no_submission"
    assert capture["pending"] is None and capture["fills"]==[]
    assert h.providers==h.classifications==h.cooling==h.sessions==[]
    assert h.gates==[] and len(h.turn_guard_calls)==1
    assert capture["account"]["cash"]==1_000_000.0 and capture["account"]["positions"]=={}

@pytest.mark.parametrize("book",BOOKS)
def test_same_day_barren_refusal_does_not_replace_accepted_row_or_run(monkeypatch,tmp_path,book):
    h=BookRunHarness(monkeypatch,tmp_path,book,mode="shadow")
    first=h.run_book(accepted=True)
    path=h.registry.data_dir(book)/"decisions.jsonl"
    before=path.read_bytes()
    pending_path=h.pa._pending_target_path(book)
    pending_before=pending_path.read_bytes()
    first_row=h.module.load_decisions()[0]
    assert first_row["run_id"]==h.created[0]
    assert first_row["decision_effective"] is True
    second=h.run_book(accepted=False)
    assert len(h.created)==2 and h.created[0]!=h.created[1]
    assert second["brain"]["run_id"]==h.created[1]
    assert path.read_bytes()==before
    assert pending_path.read_bytes()==pending_before
    assert h.module.load_decisions()[0]==first_row
    assert h.rl.read_run(h.created[1])["ts"] is not None
    assert len(h.submitted)==1 and len(h.providers)==1
