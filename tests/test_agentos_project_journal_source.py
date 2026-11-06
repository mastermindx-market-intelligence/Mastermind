"""Actual captured Macro parser and source metadata; no host/provider effects."""
import json
from pathlib import Path
import pytest
from control_plane.agentos_project_journal import (AgentOsProjectJournalReader,
    ProjectJournalSourceUnavailable, read_from_macro_owner)
from tests.test_agentos_project_plan_source import source_git, SHA, PATH, WORK

DEC = 'agentos/decisions/DEC-ONE-CHOICE.md'
DSC = 'agentos/discoveries/DSC-ONE-FINDING.md'
HND = 'agentos/handoffs/ONE-2026-11-03.md'
RECORDS = {
DEC: '''---
key: ONE-CHOICE
question: Which current path should be used?
answer: Keep the original source owner.
rationale: Preserve real evidence custody.
alternatives:
  - option: Duplicate source
    why_not: Conflicting truth.
evidence: ['pytest original source']
affects: ['WS:ONE']
confidence: high
reversibility: easy
decided_by: ceo
decided_at: 2026-11-02
---
PRIVATE BODY SHOULD NEVER LEAK
''',
DSC: '''---
key: ONE-FINDING
claim: The source carries its own record dates.
falsifier: pytest tests/test_source.py
so_what: Keep authored and publication dates separate.
kind: architecture
verified_at: 2026-11-01
verified_by: pytest source check
scope: ['WS:ONE']
confidence: verified
---
PRIVATE BODY SHOULD NEVER LEAK
''',
HND: '''---
workstream: WS:ONE
session: historical-source-session
model: codex
ended_because: complete
mission: The original implementation returned.
state_before: The source needed a correction.
changed: [{path: app/source.py, what: Corrected the source.}]
verified: [{claim: Focused check passed., command: pytest test_source, result: PASS}]
unverified: []
unresolved: [None in this fixture.]
next_actions: ['Review the original returned evidence.']
do_not_redo: [Do not replay source evidence.]
danger_areas: [Preserve original scope.]
---
PRIVATE BODY SHOULD NEVER LEAK
'''}

@pytest.fixture
def journal_git(source_git):
    original, calls = source_git
    def runner(argv, **limits):
        cmd = argv[5:]
        if cmd[0] == 'log' and '--name-only' in cmd:
            text = '\n'.join(RECORDS) + '\n'
        elif cmd[0] == 'ls-tree' and cmd[-1] in RECORDS:
            text = '100644 blob ' + 'b'*40 + '\t' + cmd[-1] + '\0'
        elif cmd[0] == 'show' and cmd[-1].startswith(SHA+':') and cmd[-1][41:] in RECORDS:
            text = RECORDS[cmd[-1][41:]]
        elif cmd[0] == 'log' and cmd[-1] in RECORDS:
            text = '2026-11-03T12:00:00+00:00\n'
        else:
            return original(argv, **limits)
        calls.append((argv, limits))
        return dict(code=0, stdout=text, timed_out=False, limit_exceeded=False, invalid_utf8=False)
    return runner, calls


def read(runner):
    return read_from_macro_owner(macro_root=Path('/qualified/macro'),
        expected_macro_sha=SHA, work_ref=WORK, runner=runner)


def test_actual_canonical_parser_produces_record_dates_and_source_tuples(journal_git):
    body = read(journal_git[0])
    assert body['availability'] == 'AVAILABLE', body
    entries = body['journal']['entries']
    assert {r['kind'] for r in entries} == {'DECISION','DISCOVERY','HANDOFF'}
    handoff = next(r for r in entries if r['kind']=='HANDOFF')
    assert handoff['recorded_at']=='2026-11-03T12:00:00+00:00'
    assert handoff['time_basis']=='GIT_RECORD_COMMIT_TIME'
    assert handoff['next_action']=='Review the original returned evidence.'
    decision = next(r for r in entries if r['kind']=='DECISION')
    assert decision['recorded_at']=='2026-11-02'
    assert decision['time_basis']=='DECLARED_DECISION_DATE'
    assert all(r['source']['commit']==SHA for r in entries)
    assert 'PRIVATE BODY' not in json.dumps(body)
    assert body['journal']['coverage']['scanned']==3


@pytest.mark.parametrize('case,reason', [('head','SOURCE_CHANGED'),('after','SOURCE_CHANGED'),
    ('missing','RECORD_NOT_FOUND'),('symlink','RECORD_INVALID')])
def test_source_drift_and_record_absence_are_closed(journal_git,case,reason):
    original,_=journal_git;heads=[0]
    def runner(argv,**limits):
        result=original(argv,**limits);cmd=argv[5:]
        if cmd==['rev-parse','HEAD']:
            heads[0]+=1
            if case=='head' or case=='after' and heads[0]==2:result['stdout']='b'*40
        if cmd[0]=='ls-tree' and cmd[-1]==PATH:
            if case=='missing':result['stdout']=''
            if case=='symlink':result['stdout']=result['stdout'].replace('100644','120000')
        return result
    body=read(runner)
    assert body['reason_codes']==[reason]
    assert body['source'] is None and body['journal'] is None


def test_unrelated_records_and_invalid_source_rows_do_not_become_history(journal_git):
    original,_=journal_git
    def runner(argv,**limits):
        result=original(argv,**limits)
        if argv[5:] == ['show',SHA+':'+DEC]:
            result['stdout']=result['stdout'].replace('WS:ONE','WS:OTHER')
        if argv[5:] == ['show',SHA+':'+DSC]:result['stdout']='---\nkey: BROKEN\n---\n'
        return result
    body=read(runner)
    assert [row['kind'] for row in body['journal']['entries']]==['HANDOFF']
    assert body['journal']['coverage']['invalid']==1


def test_unissued_facade_cannot_borrow_a_source_owner():
    with pytest.raises(ProjectJournalSourceUnavailable):
        AgentOsProjectJournalReader(macro_root=Path('/qualified/macro')).read(work_ref=WORK)


def test_canonical_bare_citations_keep_exact_association(journal_git):
    original,_=journal_git
    def runner(argv,**limits):
        result=original(argv,**limits)
        if argv[5:] in (['show',SHA+':'+DEC],['show',SHA+':'+DSC]):
            result['stdout']=result['stdout'].replace("['WS:ONE']",'WS:ONE')
        return result
    value=read(runner)
    assert {row['kind'] for row in value['journal']['entries']}=={'DECISION','DISCOVERY','HANDOFF'}
