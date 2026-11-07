"""Exact compiler edits in temporary Git -> actual fixed READ; no publisher proof."""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import types
import zlib

from tests.test_agentos_plan_continuity_capture import repository, read


def compiler():
    fixture = json.loads((Path(__file__).parent / 'fixtures/agentos-plan-adoption-compiler-a5cb.json').read_bytes())
    assert fixture['commit'] == 'a5cbff6352a8c20849a2ad99b601cb1530afc138'
    raw = zlib.decompress(base64.b64decode(fixture['zlib_base64'], validate=True))
    assert hashlib.sha256(raw).hexdigest() == fixture['sha256']
    assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == fixture['blob']
    module = types.ModuleType('exact_adoption_compiler_fixture')
    exec(compile(raw, fixture['path'], 'exec'), module.__dict__)
    return module


def test_actual_candidate_then_decision_edits_become_truthful_read(repository):
    repo = repository; owner = repo['owner']; module = compiler()
    work = 'WS:PLAN-TEST'; ws_path = 'agentos/workstreams/WS-PLAN-TEST.md'
    proposed_ws = deepcopy(repo['ws']); proposed_ws['objective'] = 'A genuine proposed workstream objective.'
    candidate = owner._yaml_frontmatter(proposed_ws).encode() + b'\nExact candidate body\r\n'
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    header = dict(repo['header'], candidate_sha256=candidate_sha)
    proposal_raw = owner._yaml_frontmatter(header).encode() + candidate
    repo['write']('planning/proposal.md', proposal_raw)
    initial_head = repo['commit'](); repo['head'] = initial_head
    def capture(path, raw, commit):
        return {'source': {'repository': module.MACRO, 'path': path, 'commit': commit,
                           'content_sha256': hashlib.sha256(raw).hexdigest()}, 'raw_bytes': raw}
    proposal = capture('planning/proposal.md', proposal_raw, initial_head)
    request_id = 'mmos-project-adopt-' + '7' * 40
    candidate_path = 'planning/proposal.candidate-' + candidate_sha[:20] + '.md'
    decision_path = 'agentos/decisions/DEC-PLAN-ADOPTION-' + '7' * 40 + '.md'
    def snapshot(head, candidate_exists):
        result = {'schema': 'agentos.plan_adoption_snapshot.v1', 'repository': module.MACRO,
            'commit': head, 'workstream': capture(ws_path, repo['git']('show', head + ':' + ws_path), head),
            'decisions': [capture('agentos/decisions/DEC-PLAN-FIRST.md',
                repo['git']('show', head + ':agentos/decisions/DEC-PLAN-FIRST.md'), head)],
            'proposal': capture('planning/proposal.md', repo['git']('show', head + ':planning/proposal.md'), head),
            'base': repo['baseline'], 'candidate_target': {'path': candidate_path, 'state': 'ABSENT'},
            'decision_target': {'path': decision_path, 'state': 'ABSENT'}}
        if candidate_exists:
            result['candidate_target'] = {'path': candidate_path, 'state': 'CAPTURED',
                'capture': capture(candidate_path, repo['git']('show', head + ':' + candidate_path), head)}
        return result
    initial = snapshot(initial_head, False)
    request = {'schema': 'agentos.plan_adoption_request.v1', 'request_id': request_id, 'work_ref': work,
        'expected_commit': initial_head, 'expected_adoption': 'DEC:PLAN-FIRST',
        'proposal_source': proposal['source'], 'base_source': repo['baseline']['source'], 'candidate_sha256': candidate_sha}
    actor = {'principal_id': 'isolated-fixture-principal', 'decided_by': 'fixture-owner',
        'decided_at': '2026-11-04', 'decision_rationale': 'Synthetic recipe/read integration only.'}
    first = module.compile_candidate_recipe(request=request, snapshot=initial, actor=actor, owner=owner)
    assert first['status'] == 'PREVIEW_ONLY' and len(first['edits']) == 1
    def apply_recipe_edits(edits):
        # A temporary fixture applies exact bytes; this is NOT a production publisher/CAS substitute.
        for edit in edits:
            target = repo['root'] / edit['path']
            if edit['expected_sha256'] is None:
                assert not target.exists()
            else:
                assert hashlib.sha256(target.read_bytes()).hexdigest() == edit['expected_sha256']
            raw = edit['content_utf8'].encode()
            assert hashlib.sha256(raw).hexdigest() == edit['content_sha256']
            repo['write'](edit['path'], raw)
        repo['head'] = repo['commit']()
        return repo['head']
    candidate_head = apply_recipe_edits(first['edits'])
    after_candidate, _ = read(repo)
    assert after_candidate['continuity']['adoption']['decision_ref'] == 'DEC:PLAN-FIRST'
    assert after_candidate['continuity']['adoption']['content'].encode() == repo['baseline_bytes']
    assert after_candidate['plan']['objective'] != proposed_ws['objective']
    current = snapshot(candidate_head, True)
    publication = {'schema': 'agentos.plan_candidate_publication.v1', 'state': 'VERIFIED_DEFAULT',
        'request_id': request_id, 'request_sha256': first['request_sha256'],
        **current['candidate_target']['capture']}
    # This proof object is fixture input only. It establishes no upstream/default/permission claim.
    second = module.compile_adoption_recipe(request=request, initial_snapshot=initial, current_snapshot=current,
        actor=actor, candidate_publication=publication, owner=owner)
    assert second['request_sha256'] == first['request_sha256'] and second['status'] == 'PREVIEW_ONLY'
    final_head = apply_recipe_edits(second['edits'])
    result, calls = read(repo)
    assert result['schema'] == 'mastermind.workspace_project_plan.v2'
    assert result['source']['commit'] == final_head
    assert result['plan']['objective'] == proposed_ws['objective']
    assert result['plan']['adoption']['matches_authored_record'] is True
    adopted = result['continuity']['adoption']
    assert adopted['state'] == 'AVAILABLE' and adopted['decision_ref'] == second['decision_ref']
    assert adopted['adoption']['predecessor'] == 'DEC:PLAN-FIRST'
    assert adopted['adoption']['adopted_source']['commit'] == candidate_head
    assert adopted['content'].encode() == candidate
    item = result['continuity']['proposals']['items'][0]
    assert item['proposal_source'] == proposal['source']
    assert item['adoption_relation'] == 'CURRENT_DECISION_REFERENCES_PROPOSAL'
    assert item['comparison_basis'] == 'RECORDED_PREDECESSOR'
    assert item['comparison']['base_text'].encode() == repo['baseline_bytes']
    assert item['comparison']['candidate_text'].encode() == candidate
    assert not any('fetch' in call for call in calls)
