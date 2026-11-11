"""Exact scope adoption; existing collector behavior stays unchanged."""
import ast
import hashlib
import json
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent
BASE = PACKAGE.parent / 'r2_plain_review_scopes/candidate/original_delivery_collector.py'
RUN = 'rv-original-tail-risk-review-01a13301-r1'
ROOT = '01a13301-995f-7631-8cee-d675d7de5671'


def scopes_and_rest(path):
    tree = ast.parse(path.read_text())
    scopes = {}
    rest = []
    for node in tree.body:
        if (isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'PLAIN_SCOPES' for t in node.targets)):
            scopes.update(ast.literal_eval(node.value))
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)
              and isinstance(node.value.func.value, ast.Name)
              and node.value.func.value.id == 'PLAIN_SCOPES'):
            assert node.value.func.attr == 'update' and not node.value.keywords
            scopes.update(ast.literal_eval(node.value.args[0]))
        else:
            rest.append(ast.dump(node))
    return scopes, rest


def test_only_exact_scope_added_all_existing_behavior_unchanged():
    before, old_ast = scopes_and_rest(BASE)
    after, new_ast = scopes_and_rest(PACKAGE / 'original_delivery_collector.py')
    expected = json.loads((PACKAGE / 'SCOPES.json').read_text())
    assert old_ast == new_ast
    assert set(after) - set(before) == {RUN}
    assert {k: after[k] for k in before} == before
    assert after[RUN] == expected[RUN]
    assert after[RUN]['root'] == after[RUN]['parent'] == ROOT
    assert after[RUN]['host'] == 'ubuntu0'
    assert after[RUN]['mode'] == 'qwen'
    assert after[RUN]['requested_model'] == 'qwen3.8-max'


def test_binding_matches_fixed_scope_and_current_source_pins():
    scope = json.loads((PACKAGE / 'SCOPES.json').read_text())[RUN]
    binding = json.loads((PACKAGE / (RUN + '.binding.json')).read_text())
    assert binding['run_id'] == RUN and binding['artifact_names'] == []
    for key in ('root', 'parent', 'host', 'mode', 'requested_model'):
        assert binding[key] == scope[key]
    assert binding['sources']['packet'] == {
        'path': scope['packet_path'], 'sha256': scope['packet_sha256']}
    assert {k: binding['sources'][k]['sha256'] for k in ('log', 'support')} == scope['source_pins']
    assert scope['lease_witness']['path'].endswith('/' + RUN + '.lease.qyAasS')
    assert scope['destination'].endswith('/' + RUN + '-collection-v1')


def test_provenance_states_its_limits_and_reconstruction_matches():
    record = json.loads((PACKAGE / 'PROVENANCE.json').read_text())
    scope = json.loads((PACKAGE / 'SCOPES.json').read_text())[RUN]
    assert record['byte_match'] is True
    assert record['retained_bytes'] == record['reconstructed_bytes'] == 115515
    assert record['reconstructed_sha256'] == record['retained_sha256'] == scope['packet_sha256']
    assert 'uncommitted' in record['limitations']
    assert 'no historical producer-root authentication' in record['limitations']


def test_exact_candidate_manifest():
    manifest = json.loads((PACKAGE / 'SOURCE.json').read_text())
    assert hashlib.sha256(BASE.read_bytes()).hexdigest() == manifest['base_sha256']
    assert hashlib.sha256((PACKAGE / 'original_delivery_collector.py').read_bytes()).hexdigest() == manifest['candidate_sha256']
