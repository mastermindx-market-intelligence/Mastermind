"""Closed public journey values; no I/O, Runtime, identity or grant issuance."""
import json
import re


def proposal_request(value):
    def fail(): raise ValueError('PROJECT_PLAN_PROPOSAL_REQUEST_INVALID')
    def obj(item,keys):
        if type(item) is not dict or any(type(k) is not str for k in item) or set(item)!=set(keys):fail()
    def match(item,pattern):
        if type(item) is not str or re.fullmatch(pattern,item) is None:fail()
    obj(value,{'schema','request_id','work_ref','expected_commit','expected_adoption','base_source','selection','result_digest'})
    if value['schema']!='mastermind.project_plan_proposal_request.v1':fail()
    match(value['request_id'],r'mmos-project-plan-proposal-[a-f0-9]{40}')
    match(value['work_ref'],r'WS:[A-Z0-9]+(?:-[A-Z0-9]+)*')
    if not 5<=len(value['work_ref'])<=67:fail()
    match(value['expected_commit'],r'[a-f0-9]{40}');match(value['result_digest'],r'[a-f0-9]{64}')
    if value['expected_adoption'] is not None:match(value['expected_adoption'],r'DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*')
    source=value['base_source'];obj(source,{'repository','commit','path','content_sha256'})
    if source['repository']!='mastermindx-market-intelligence/macro':fail()
    match(source['commit'],r'[a-f0-9]{40}');match(source['content_sha256'],r'[a-f0-9]{64}')
    match(source['path'],r'(?:agentos/workstreams/WS-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md|research/project-plans/[A-Za-z0-9._-]+\.md)')
    selection=value['selection'];obj(selection,{'work_ref','job_id','attempt_id'})
    if selection['work_ref']!=value['work_ref']:fail()
    for key in ('job_id','attempt_id'):match(selection[key],r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    if len(raw.encode())>16384:fail()
    return json.loads(raw)
