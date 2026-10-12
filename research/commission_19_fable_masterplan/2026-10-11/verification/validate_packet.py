"""Offline authoring checks only: no execution admission or source verification."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]

def main():
    work=json.loads((ROOT/'WORK_PACKAGES.json').read_text())['packages']
    reports=json.loads((ROOT/'RESEARCH_MANIFEST.json').read_text())
    sources=json.loads((ROOT/'SOURCE_REGISTER.json').read_text())['sources']
    issues=json.loads((ROOT/'ISSUE_CROSSWALK.json').read_text())['observed_2026_10_11']
    acceptance=json.loads((ROOT/'ACCEPTANCE_MATRIX.json').read_text())['cases']
    checks=[]
    def require(name, ok):
        if not ok: raise AssertionError(name)
        checks.append(name)
    ids={p['id'] for p in work}; src={s['id'] for s in sources}
    require('34_unique_packages',len(work)==34 and len(ids)==34)
    require('36_unique_source_entries',len(sources)==36 and len(src)==36)
    require('19_original_report_carriers',len(reports['reports'])==19)
    topics={r['topic'] for r in reports['reports']} | {r['topic'] for r in reports['missing_topics']}
    require('all_18_intended_topics_accounted_for',topics==set(range(1,19)))
    require('20_existing_issue_ids',len(issues)==20 and len({i['id'] for i in issues})==20)
    require('all_issues_mapped_to_work',set(i['id'] for i in issues)<=set(i for p in work for i in p['issues']))
    require('all_dependencies_resolve',all(d in ids for p in work for d in p['depends_on']))
    require('all_package_sources_resolve',all(s in src for p in work for s in p['source_refs']))
    require('all_report_dossiers_resolve',all(r['dossier_source'] in src for r in reports['reports']))
    require('all_report_sha40',all(re.fullmatch(r'[0-9a-f]{40}',r['commit']) for r in reports['reports']))
    by={p['id']:p for p in work}; done=set(); visiting=set()
    def visit(k):
        if k in visiting: raise AssertionError('dependency cycle: '+k)
        if k in done:return
        visiting.add(k)
        for d in by[k]['depends_on']:visit(d)
        visiting.remove(k);done.add(k)
    for k in ids:visit(k)
    require('acceptance_DAG_acyclic',len(done)==34)
    require('50_unique_supplementary_cases',len(acceptance)==50 and len({c['id'] for c in acceptance})==50)
    require('acceptance_packages_resolve',all(c['package'] in ids for c in acceptance))
    for i in range(1,9):
        text=(ROOT/f'prompts/O{i}_OPUS_ORCHESTRATOR.md').read_text()
        for label in ['ROUTE: orchestration','MISSION:','WHY:','SCOPE:','OUT OF SCOPE:','NOT DONE UNLESS:','RETURN:']:
            require(f'O{i}_header_{label}',bool(re.search(r'^'+re.escape(label),text,re.M)))
        require(f'O{i}_explicit_opus_method',('model: opus' in text and 'fable-mode' in text))
        require(f'O{i}_fabric_operator',('Fabric operators' in text and 'task operators' in text))
    broken=[];local_links=0
    for f in ROOT.rglob('*.md'):
        # The complete reference preserves component-relative links, all of which
        # resolve at packet root except prompts' relative-context prose (no links).
        for href in re.findall(r'\]\(([^)]+)\)',f.read_text()):
            if '://' in href or href.startswith('#') or href.startswith('mailto:'):continue
            href=href.split('#')[0]
            if not href:continue
            local_links+=1
            if not (f.parent/href).exists():broken.append((str(f.relative_to(ROOT)),href))
    require('internal_markdown_links_resolve',not broken)
    probe=json.loads((ROOT/'verification/composer_excerpt_probe_result.json').read_text())
    require('8_bounded_probe_cases',probe['case_count']==8 and probe['assertions_passed'] is True)
    require('probe_scope_not_inflated',probe['full_application_imported'] is False and probe['real_producer_or_browser_tested'] is False and probe['full_file_hash_verified_locally'] is False)
    require('probe_script_hash_matches',hashlib.sha256((ROOT/'verification/composer_excerpt_probe.py').read_bytes()).hexdigest()==probe['script_sha256'])
    toy=json.loads((ROOT/'verification/toy_scenario_arithmetic.json').read_text())
    require('toy_arithmetic_labeled',toy['classification']=='invented_toy_example_not_market_evidence' and toy['assertions_passed'] is True)
    brief=json.loads((ROOT/'verification/craft_brief.json').read_text())
    require('craft_no_fake_runtime_binding',brief['assignment_ref'] is None and all(v is None for v in brief['workspace'].values()))
    compiled=(ROOT/'verification/COMPILED_CRAFT_BRIEF.md').read_text()
    require('craft_compiler_output_present','authoring only' in compiled and 'grants no execution' in compiled)
    report={'classification':'offline_packet_structural_validation_not_product_acceptance','passed':True,'check_count':len(checks),'checks':checks,'local_markdown_links_checked':local_links,'package_count':len(work),'coordinator_count':8,'case_count':len(acceptance),'report_carriers':len(reports['reports']),'source_entries':len(sources),'scope_exclusions':['No network/source-truth validation','No product execution','No live runtime or permissions test','No production or scientific acceptance']}
    (ROOT/'verification/packet_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','check_count','local_markdown_links_checked','package_count','coordinator_count','case_count']}))

if __name__=='__main__':main()
