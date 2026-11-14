"""Exercise the complete native agenda controller; no browser or API requests."""
import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
EMPTY = dict(schema_version="improvement_agenda.v1", as_of="2026-11-14",
             n_items=0, items=[], owners={}, class_counts={})
ROW = dict(rank=1, title="Repair", **{"class":"quality"}, fix_type="code-change",
           owner="opus-session", suggested_fix="Fix", expected_impact="Correct",
           evidence=["Retained evidence"], rank_score=3, age_weeks=0)
VALID_ROW = dict(EMPTY, n_items=1, items=[ROW], owners={"opus-session":1},
                 class_counts={"quality":1})
CASES = [
 ("empty", EMPTY, True),
 ("legacy-row", VALID_ROW, True),
 ("annotated", dict(VALID_ROW, items=[dict(ROW, readiness=dict(state="blocked",depends_on=["A"],unmet_dependencies=["A"]))]), True),
 ("partial", {"schema_version":"improvement_agenda.v1","note":"partial"}, False),
 ("empty-object", {}, False),
 ("null", None, False),
 ("array", [], False),
 ("missing-items", {k:v for k,v in EMPTY.items() if k!="items"}, False),
 ("wrong-items", dict(EMPTY,items={}), False),
 ("mismatch", dict(EMPTY,n_items=1), False),
 ("negative-count", dict(EMPTY,n_items=-1), False),
 ("string-count", dict(EMPTY,n_items="0"), False),
 ("unknown-schema",dict(EMPTY,schema_version="future"),False),
 ("missing-date",dict(EMPTY,as_of=None),False),
 ("wrong-owners",dict(EMPTY,owners=[]),False),
 ("negative-owner-count",dict(EMPTY,owners={"owner":-1}),False),
 ("string-class-count",dict(EMPTY,class_counts={"x":"0"}),False),
 ("bad-row",dict(VALID_ROW,items=[None]),False),
 ("bad-evidence",dict(VALID_ROW,items=[dict(ROW,evidence="text")]),False),
 ("bad-readiness-state",dict(VALID_ROW,items=[dict(ROW,readiness={"state":2})]),False),
 ("bad-dependencies",dict(VALID_ROW,items=[dict(ROW,readiness={"depends_on":"A"})]),False),
 ("bad-readiness-input",dict(EMPTY,readiness_input={"available":"false"}),False),
 ("bad-warnings",dict(EMPTY,readiness_input={"degraded":"warning"}),False),
 ("unavailable",dict(EMPTY,available=False),False),
 ("unavailable-read",dict(EMPTY,read_status="unavailable"),False),
]
NODE = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[1],'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/g).at(-1).replace(/^<script>|<\/script>$/g,'');
const data=JSON.parse(process.argv[2]), expected=process.argv[3]==='true';
const nodes={root:{},sub:{}};
vm.runInNewContext(script,{document:{getElementById:id=>nodes[id]},
 fetch:async()=>({ok:true,status:200,json:async()=>data})});
setImmediate(()=>{
 const available=nodes.sub.textContent!=='unavailable';
 assert.strictEqual(available,expected);
 assert.strictEqual(nodes.root.innerHTML.includes('every accountability source is clean or absent'),expected && data.items.length===0);
 if(!expected) assert(!nodes.root.innerHTML.includes('open items'));
 if(expected && data.items.length) assert(nodes.root.innerHTML.includes('Retained evidence'));
});
"""
@pytest.mark.parametrize("_name,payload,available", CASES, ids=[x[0] for x in CASES])
def test_agenda_display_shape(_name,payload,available):
    node=shutil.which("node")
    assert node, "Node is required to execute the actual agenda controller"
    subprocess.run([node,"-e",NODE,str(ROOT/"app/static/agenda.html"),json.dumps(payload),
                    str(available).lower()],check=True,capture_output=True,text=True,timeout=10)
