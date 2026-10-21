"""Validate this static handoff's structure, never its execution authority.

Run from any directory. Emits a bounded JSON summary; writes no canonical data.
Use --write to save verification/package-checks.json in this package.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

BASE = Path(__file__).resolve().parents[1]
errors: list[str] = []
checks: dict[str, object] = {}


def require(value: bool, message: str) -> None:
    if not value:
        errors.append(message)


required = ['README.md','MASTERPLAN.md','FABLE_START_HERE.md','WORK_PACKAGES.md',
    'WORK_PACKAGES.json','ACCEPTANCE_MATRIX.md','PLAN_AND_PR_CROSSWALK.md','SOURCE_REGISTER.md',
    'fabric/README.md','verification/README.md','verification/brief-compilation.json',
    'verification/handoff-selector-fixture.json','verification/handoff-selector-result.json',
    'audit/agent-os-audit.md','audit/executive-audit.md','audit/mastermind-os-audit.md','audit/pr-snapshot.json']
for name in required:
    require((BASE/name).is_file(), 'missing file: '+name)
checks['required_files'] = len(required)

data = json.loads((BASE/'WORK_PACKAGES.json').read_text())
work = data['work_packages']; ids = {w['id'] for w in work}
require(len(ids)==len(work)==43,'expected43 unique planning packages')
require(data['execution_authority'] is False,'planning metadata must not claim authority')
graph = {w['id']: w['dependencies'] for w in work}
for w in work:
    require(w['owner'] in {'Fable','O1','O2','O3','O4','O5','O6'},'unknown domain '+w['id'])
    require(w['status']=='PLANNING_ONLY_NOT_ADMITTED','wrong planning state '+w['id'])
    require(all(v is None for v in w['runtime_binding'].values()),'fabricated runtime binding '+w['id'])
    require(bool(w['outcome'] and w['acceptance'] and w['independent_review'] and w['budget']),'incomplete package '+w['id'])
    for d in w['dependencies']:
        require(d in ids and d!=w['id'],'invalid dependency '+w['id']+' -> '+d)

visiting=set(); visited=set(); order=[]
def visit(k: str) -> None:
    if k in visiting:
        errors.append('dependency cycle at '+k); return
    if k in visited: return
    visiting.add(k)
    for d in graph.get(k,[]): visit(d)
    visiting.remove(k); visited.add(k); order.append(k)
for k in graph: visit(k)
checks['work_packages']=len(work); checks['topological_order']=order
checks['owner_counts']={o:sum(w['owner']==o for w in work) for o in ['Fable','O1','O2','O3','O4','O5','O6']}

registry=(BASE/'SOURCE_REGISTER.md').read_text()
source_ids=set(re.findall(r'^## (S\d{2})\b',registry,re.M))
require(source_ids=={f'S{i:02}' for i in range(1,27)},'source register IDs incomplete')
for w in work:
    require(set(w['source_ids'])<=source_ids,'unresolved source ID '+w['id'])
checks['source_id_count']=len(source_ids)

comp=json.loads((BASE/'verification/brief-compilation.json').read_text())
require(len(comp['results'])==7,'expected seven compiled briefs')
for r in comp['results']:
    inp=BASE/r['input']; out=BASE/r['output']
    require(hashlib.sha256(inp.read_bytes()).hexdigest()==r['input_sha256'],'brief input drift '+r['input'])
    require(hashlib.sha256(out.read_bytes()).hexdigest()==r['output_sha256'],'brief output drift '+r['output'])
    b=json.loads(inp.read_text())
    require(b['assignment_ref'] is None and all(v is None for v in b['workspace'].values()),'unbound brief lost '+r['input'])
    require(r['compiler_returncode']==0 and r['execution_authority'] is False,'wrong compilation claim')
    for ref in b['source_refs']:
        require(bool(re.fullmatch('[a-f0-9]{40}',ref['commit'])),'unqualified source revision')
checks['compiled_briefs']=len(comp['results'])

source_check=json.loads((BASE/'verification/source-reference-checks.json').read_text())
require(source_check['status']=='PASS' and all(r['exists_at_reference'] for r in source_check['references']), 'source path check failed')
checks['verified_brief_source_paths']=len(source_check['references'])

spec=importlib.util.spec_from_file_location('selector_reproduce',BASE/'verification/handoff-selector-reproduce.py')
module=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
reproduced=json.loads(json.dumps(module.reproduce()))
recorded=json.loads((BASE/'verification/handoff-selector-result.json').read_text())
require(reproduced==recorded,'portable reproducer result differs from recorded evidence')
require(reproduced['correct'] is False,'expected current-defect counterexample not reproduced')
require(all(i['association_selected'] for i in reproduced['inputs']),'association premise failed')
checks['selector_counterexample']='CONFIRMED: earlier record selected; not a fixed-implementation pass'

bad_links=[]
for p in BASE.rglob('*.md'):
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',p.read_text()):
        if '://' in target or target.startswith(('mailto:','#','sandbox:')): continue
        target=target.split('#',1)[0]
        if target and not (p.parent/target).exists(): bad_links.append(str(p.relative_to(BASE))+': '+target)
require(not bad_links,'unresolved local Markdown links: '+repr(bad_links))
checks['local_markdown_links']='all file targets resolve' if not bad_links else bad_links

result={'status':'PASS' if not errors else 'FAIL','scope':'Static package/brief consistency and one isolated confirmed source defect. No production/runtime acceptance.',
    'checks':checks,'errors':errors}
if '--write' in sys.argv:
    (BASE/'verification/package-checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(1 if errors else 0)
