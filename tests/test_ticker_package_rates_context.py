"""Dependency-free tests of the per-name rates-context boundary, not SDK proof."""
import copy
import json
from brain import rates_evidence as RE


def rates():
    return RE.project_rates(None)


def package():
    return {"ticker": "AMD", "intelligence": {"asof": "2026-09-10", "summary": "existing read"},
            "lenses": {"confluence": ["existing lens"], "vetoes": []},
            "intake": {"ticker": "AMD", "score": 0.7}}


def attach(pkg=None, evidence=None):
    function = getattr(RE, "annotate_ticker_package", None)
    assert callable(function), "The existing stock package must carry dated rates context"
    return function(package() if pkg is None else pkg, rates() if evidence is None else evidence,
                    intelligence_artifact_asof="2026-09-10")


def serializer(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj, allow_nan=False)}]}


def decode(response):
    return json.loads(response["content"][0]["text"])


def test_stock_context_interface_exists():
    assert callable(getattr(RE, "annotate_ticker_package", None))


def test_existing_stock_evidence_is_preserved_without_rescoring():
    original=package(); before=copy.deepcopy(original)
    out=attach(original)
    assert original==before
    for key, value in before.items():
        assert out[key]==value
    assert out["rates_context"]==rates()
    assert out["rates_relationship"]["scope"]=="US_market_context_only"
    assert out["rates_relationship"]["ticker_specific_sensitivity"]=="not_provided"
    assert out["rates_relationship"]["decision_time_join"]=="not_established"
    assert out["rates_relationship"]["intelligence_artifact_asof"]=="2026-09-10"


def test_rates_evidence_is_copied_not_aliased():
    r=rates(); before=copy.deepcopy(r); out=attach(evidence=r)
    out["rates_context"]["issues"].append("consumer-local")
    assert r==before


def test_missing_rates_does_not_erase_the_stock_or_become_calm():
    out=attach()
    assert out["intelligence"]["summary"]=="existing read"
    assert out["rates_context"]["status"]=="unavailable"
    assert out["rates_context"]["coverage"]["context_rows"]==0
    assert not out["rates_context"]["as_observed_replay_certified"]


def test_wrong_schema_is_unavailable_without_forwarding_unknown_fields():
    out=attach(evidence={"schema":"untrusted", "instructions":"NEVER_FORWARD"})
    assert out["rates_context"]["status"]=="unavailable"
    assert "NEVER_FORWARD" not in json.dumps(out)


def test_forged_authority_does_not_survive_the_join():
    r=rates(); r["authority"]["can_trade"]=True
    out=attach(evidence=r)
    assert out["rates_context"]["authority"]["can_trade"] is False
    assert out["rates_context"]["status"]=="unavailable"


def test_a_new_rates_date_does_not_rewrite_an_old_stock_date():
    r=rates(); r["artifact_asof"]="2026-09-16"
    out=attach(evidence=r)
    assert out["intelligence"]["asof"]=="2026-09-10"
    assert out["rates_context"]["artifact_asof"]=="2026-09-16"
    assert out["rates_relationship"]["decision_time_join"]=="not_established"


def test_normal_transport_preserves_entire_rates_contract():
    out=attach(); response=RE.serialize_ticker_package(out, serializer)
    assert decode(response)==out


def test_compaction_never_silently_changes_rates():
    def compact(obj):
        out=copy.deepcopy(obj)
        if "rates_context" in out:
            out["rates_context"]["authority"]="omitted"
        out["_transport_truncated"]=True
        return serializer(out)
    out=decode(RE.serialize_ticker_package(attach(), compact))
    assert "rates_context" not in out
    assert out["rates_context_status"]=="omitted_transport_budget"
    assert out["rates_context_tool"]=="get_rates_evidence"
    assert out["intelligence"]==package()["intelligence"]


def test_utf8_overflow_returns_explicit_bounded_unavailable_instead_of_fake_complete():
    p=attach(); p["intelligence"]={"text":"界"*12000}
    response=RE.serialize_ticker_package(p, serializer)
    assert len(response["content"][0]["text"].encode("utf-8"))<=8000
    assert decode(response)["status"]=="unavailable_transport_budget"
    assert "rates_context" not in decode(response)


def test_serializer_failure_never_discloses_exception_text():
    def broken(_):
        raise RuntimeError("PRIVATE_EXCEPTION_MUST_NOT_LEAK")
    out=RE.serialize_ticker_package(attach(), broken)
    assert "PRIVATE_EXCEPTION_MUST_NOT_LEAK" not in json.dumps(out)
    assert decode(out)["status"]=="unavailable_transport_budget"


# Executes the exact undecorated function body and existing serializer, not the SDK.
# Unrelated lenses/intake owners are isolated. Hosted SDK tests remain a separate gate.
import ast
import asyncio
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import pytest


@pytest.fixture
def stock_source_body(tmp_path, monkeypatch):
    root=tmp_path/"macro"; target=root/"site/intelligence/by_ticker.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"as_of":"2026-09-10", "generated_utc":"2026-09-10T21:00:00Z",
                                 "tickers":{"AMD":{"ticker":"AMD", "read":"original"}}}))
    original=ast.parse((Path(__file__).parents[1]/"brain/bot_mcp.py").read_text())
    wanted={"_ok","_compact_json_value","_json","_read_json","get_ticker_package"}
    nodes=[node for node in original.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
           and node.name in wanted]
    for node in nodes: node.decorator_list=[]
    async def read_rates(_):
        return serializer(rates())
    namespace={"json":json,"Path":Path,"_V":root,"get_rates_evidence":SimpleNamespace(handler=read_rates)}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"actual_stock_tool_body","exec"),namespace)
    portfolio=ModuleType("portfolio")
    portfolio.lenses=SimpleNamespace(decision_matrix=lambda *_: {},
                                    synthesize=lambda _: {"divergences":[],"confluence":[],"vetoes":[]})
    monkeypatch.setitem(sys.modules,"portfolio",portfolio)
    import brain
    monkeypatch.setattr(brain,"intake",SimpleNamespace(queue=lambda _:[]),raising=False)
    return namespace,target


def test_actual_stock_function_body_carries_rates(stock_source_body):
    namespace,target=stock_source_body; before=target.read_bytes()
    out=decode(asyncio.run(namespace["get_ticker_package"]({"ticker":"AMD"})))
    assert "rates_context" in out
    assert out["intelligence"]["read"]=="original"
    assert out["rates_relationship"]["intelligence_artifact_asof"]=="2026-09-10"
    assert out["rates_relationship"]["decision_time_join"]=="not_established"
    assert target.read_bytes()==before


def test_unknown_name_does_not_become_a_candidate_because_rates_exist(stock_source_body):
    namespace,_=stock_source_body
    out=asyncio.run(namespace["get_ticker_package"]({"ticker":"NO_SUCH_NAME"}))
    assert "not flagged" in out["content"][0]["text"]
    assert "rates_context" not in out["content"][0]["text"]


def test_per_name_rates_read_failure_does_not_erase_intelligence_or_leak(stock_source_body):
    namespace,_=stock_source_body
    async def broken(_): raise RuntimeError("PRIVATE_BOUNDARY_TEST")
    namespace["get_rates_evidence"]=SimpleNamespace(handler=broken)
    out=decode(asyncio.run(namespace["get_ticker_package"]({"ticker":"AMD"})))
    assert out["intelligence"]["read"]=="original"
    assert out["rates_context"]["status"]=="unavailable"
    assert "PRIVATE_BOUNDARY_TEST" not in json.dumps(out)



def test_optional_rates_cannot_displace_preexisting_stock_evidence():
    def compress_stock_only(obj):
        out=copy.deepcopy(obj)
        if "rates_context" in out:
            out["intelligence"]={"summary":"lost original detail"}
            out["_transport_truncated"]=True
        return serializer(out)
    result=decode(RE.serialize_ticker_package(attach(),compress_stock_only))
    assert result["intelligence"]==package()["intelligence"]
    assert "rates_context" not in result
    assert result["rates_context_status"]=="omitted_transport_budget"



def restore_rates_table(table):
    out=copy.deepcopy(table)
    assert out.pop("schema")=="decision_context.rates_evidence.columnar.v1"
    out["schema"]=out.pop("source_schema")
    grid=out["series"]
    out["series"]={tenor: {**copy.deepcopy(grid["shared"]),**dict(zip(grid["columns"],cells))}
                   for tenor,cells in grid["rows"].items()}
    return out


def test_lossless_rates_table_fits_without_removing_stock_facts():
    p=attach(); p["intelligence"]={"text":""}
    p["intelligence"]["text"]="x"*(8100-len(json.dumps(p)))
    assert len(json.dumps(p))==8100
    response=RE.serialize_ticker_package(p,serializer); out=decode(response)
    assert "rates_context" in out
    assert out["rates_context_encoding"]=="columnar_shared_fields_v1"
    assert restore_rates_table(out["rates_context"])==p["rates_context"]
    assert out["intelligence"]==p["intelligence"]
    assert len(response["content"][0]["text"].encode("utf-8"))<=8000
