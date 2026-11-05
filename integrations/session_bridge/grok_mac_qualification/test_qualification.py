import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
EXT=Path.home()/".claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext"
sys.path[:0]=[str(HERE),str(EXT)]
import fabric_host_qualification as q

@pytest.fixture
def case(tmp_path,monkeypatch):
    now=datetime.now(timezone.utc)
    host={"platform":"darwin","local":False,"roles":["lanes"],"allowed_modes":["grok"],"qualification_only_modes":["grok"],"max_active":3,"lane_ceiling":3,"cores":12,"load_gate":8,"min_free_gb":30,"require_ac":True,"windows":[]}
    state={"ts":now.timestamp(),"host":"mb","reachable":True,"disk_free_gb":135,"on_ac":True,"tools":["grok","node","python3"],"load1":1,"ncpu":12,"active_lanes":0,"active_lanes_status":"known"}
    monkeypatch.setattr(q.pick,"format_pick",lambda *a,**kw:"POOL=grok MODEL=grok-4.6")
    def run(host_changes=None,state_changes=None,which="mb"):
        h={**host,**(host_changes or {})};s={**state,**(state_changes or {})}
        (tmp_path/"mb.json").write_text(json.dumps(s))
        reg={"mb":h}
        result=q.qualification_route(which,task_class="review",complexity="C1_ROUTINE_BOUNDED",reason="",root="root",parent="root",registry=reg,state_dir=str(tmp_path),now=now)
        assert reg["mb"]["qualification_only_modes"]==["grok"]
        return result
    return run,now

def test_explicit_pending_mac_has_one_transient_route(case):
    run,_=case
    assert run()=="POOL=grok MODEL=grok-4.6 HOST=mb MODE=grok"

@pytest.mark.parametrize("host,state",[
    ({"roles":["candidate"]},{}),({"allowed_modes":[]},{}),
    ({"platform":"linux"},{}),({"local":True},{}),
    ({}, {"on_ac":False}), ({}, {"load1":99}),
    ({}, {"active_lanes":3}), ({}, {"disk_free_gb":1}),
    ({}, {"tools":[]}), ({}, {"reachable":False}),
    ({}, {"ts":0}),
])
def test_all_existing_host_gates_still_apply(case,host,state):
    run,_=case
    with pytest.raises(ValueError):run(host,state)

def test_wrong_host_and_provider_refused(case,monkeypatch):
    run,_=case
    with pytest.raises(ValueError):run(which="m2")
    monkeypatch.setattr(q.pick,"format_pick",lambda *a,**kw:"NONE reason=exhausted")
    with pytest.raises(ValueError,match="PROVIDER_REFUSED"):run()

def test_inventory_selection_only_grok(monkeypatch):
    import types
    from importlib.machinery import SourceFileLoader
    m=SourceFileLoader("selected_bootstrap",str(HERE/"bootstrap_clis.py.candidate")).load_module()
    original=Path.read_text
    monkeypatch.setattr(Path,"read_text",lambda p,*a,**kw: json.dumps({"m1":{"ssh_alias":"m1"}}) if p.name=="hosts.json" else original(p,*a,**kw))
    scripts=[]
    monkeypatch.setattr(m.subprocess,"run",lambda *a,**kw:(scripts.append(kw["input"]) or types.SimpleNamespace(stdout="grok=installed\n",returncode=0)))
    monkeypatch.setattr(sys,"argv",["bootstrap","m1","--install-missing","--tool","grok"])
    assert m.main()==0
    assert "@xai-official/grok@" in scripts[0]
    assert "opencode" not in scripts[0] and "cursor.com" not in scripts[0] and "@openai" not in scripts[0]
