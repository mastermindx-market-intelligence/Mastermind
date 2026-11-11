"""Closed syntax/binding for request-local DATA observations, no authority."""
from datetime import datetime
import re

from common.executive_workspace_contract import digest
from common.canonical_project_data_observation_contract import validate as data_observation
from common.workspace_project_plan_contract import validate_source

_HASH = re.compile(r'[a-f0-9]{64}')


def validate_observation(value, *, work_ref, root_job_id, document, validity, currentness, fabric=None):
    def fail():
        raise ValueError('PROJECT_DISCOVERY_OBSERVATION_INVALID')
    if (type(value) is not dict or set(value) != {'schema', 'state', 'selection', 'control_room', 'runtime', 'project_data'}
            or value['schema'] != 'mastermind.workspace_source_observation.v2' or value['state'] != 'SAME'
            or value['selection'] != (None if root_job_id is None else dict(work_ref=work_ref, root_job_id=root_job_id))):
        fail()
    c, p, runtime = value['control_room'], value['project_data'], value['runtime']
    if (type(c) is not dict or set(c) != {'instance_before', 'instance_after', 'publication_before', 'publication_after',
            'document_digest', 'source_validity_digest', 'cache_currentness_digest'}
            or type(c['instance_before']) is not str or not c['instance_before'] or c['instance_before'] != c['instance_after']
            or type(c['publication_before']) is not int or c['publication_before'] <= 0 or c['publication_before'] != c['publication_after']
            or any(type(c[key]) is not str or _HASH.fullmatch(c[key]) is None
                for key in ('document_digest', 'source_validity_digest', 'cache_currentness_digest'))):
        fail()
    if (type(p) is not dict or set(p) != {'source', 'code_source', 'data_observation', 'creation_publication',
            'source_generation', 'document_digest', 'source_validity_digest', 'cache_currentness_digest'}
            or type(p['source_generation']) is not str or _HASH.fullmatch(p['source_generation']) is None):
        fail()
    witness = data_observation(p['data_observation'])
    source = validate_source(p['source'], work_ref)
    code = p['code_source']
    if (source['commit'] != witness['canonical_data_commit'] or type(code) is not dict
            or set(code) != {'repository', 'commit', 'path', 'content_sha256'}
            or code['repository'] != source['repository'] or code['commit'] != witness['executable_macro_commit']
            or code['path'] != 'scripts/agentos.py' or type(code['content_sha256']) is not str
            or _HASH.fullmatch(code['content_sha256']) is None):
        fail()
    creation = p['creation_publication']
    if (type(creation) is not dict or set(creation) != {'selection', 'principal_scope', 'request_sha256',
            'recipe_fingerprint_sha256', 'event_id', 'receipt_sha256', 'recorded_at_ms', 'sources'}
            or type(creation['selection']) is not dict or set(creation['selection']) != {'action', 'request_id', 'work_ref'}
            or creation['selection']['action'] != 'publish_project_proposal' or creation['selection']['work_ref'] != work_ref
            or type(creation['selection']['request_id']) is not str
            or re.fullmatch(r'mmos-project-create-[a-f0-9]{40}', creation['selection']['request_id']) is None
            or any(type(creation[key]) is not str or _HASH.fullmatch(creation[key]) is None
                for key in ('principal_scope', 'request_sha256', 'recipe_fingerprint_sha256', 'receipt_sha256'))
            or any(type(creation[key]) is not int or creation[key] <= 0 for key in ('event_id', 'recorded_at_ms'))
            or type(creation['sources']) is not list or not 1 <= len(creation['sources']) <= 4):
        fail()
    sources = creation['sources']
    if not any(item.get('path') == source['path'] for item in sources if type(item) is dict):
        fail()
    for item in sources:
        if (type(item) is not dict or set(item) != {'repository', 'commit', 'path', 'content_sha256'}
                or item['repository'] != 'macro' or type(item['commit']) is not str or re.fullmatch(r'[a-f0-9]{40}', item['commit']) is None
                or type(item['path']) is not str or not item['path'].startswith('agentos/')
                or type(item['content_sha256']) is not str or _HASH.fullmatch(item['content_sha256']) is None):
            fail()
    operation = witness['source_operation']
    if operation is not None and (operation['principal_scope'] != creation['principal_scope'] or operation['selection']['work_ref'] != work_ref):
        fail()
    if (validity.get('schema') != 'mastermind.project_data_source_validity.v1'
            or validity.get('profile') != 'workspace_project_data_read.v1'
            or validity.get('source_generation') != p['source_generation']
            or currentness != dict(state='fresh', source_generation=p['source_generation'])):
        fail()
    for key, body in (('document_digest', document), ('source_validity_digest', validity), ('cache_currentness_digest', currentness)):
        if p[key] != digest(body):
            fail()
    generated = datetime.fromisoformat(document['generated_at'].replace('Z', '+00:00'))
    if (generated.utcoffset() is None or document.get('schema') != 'mastermind.chairman_control_room.v1'
            or abs(generated.timestamp() * 1000 - witness['canonical_observed_at_ms']) >= 1000
            or document['autonomy']['generated_at'] != document['generated_at']
            or [row.get('work_ref') for row in document['work']] != [work_ref]
            or type(runtime) is not dict or set(runtime) != {'schema', 'state', 'source_identity', 'before', 'after', 'snapshot_digest'}
            or runtime['schema'] != 'mastermind.runtime_read_observation.v1' or runtime['state'] != 'SAME'
            or type(runtime['source_identity']) is not str or not runtime['source_identity']
            or type(runtime['before']) is not int or runtime['before'] < 0 or runtime['before'] != runtime['after']
            or type(runtime['snapshot_digest']) is not str or _HASH.fullmatch(runtime['snapshot_digest']) is None):
        fail()
    if fabric is not None:
        acquisition = fabric.get('runtime', {}).get('acquisition', {})
        if (acquisition.get('schema') != 'mastermind.fabric_runtime_acquisition.v1'
                or acquisition.get('owner') != 'executive_runtime'
                or acquisition.get('query') != dict(kind='root_detail', root_job_id=root_job_id)
                or acquisition.get('snapshot_digest') != runtime['snapshot_digest']
                or acquisition.get('generation') != {key: val for key, val in runtime.items() if key != 'snapshot_digest'}):
            fail()
    return value


def card_is_current(validity, currentness, responsibility, *, work_ref, root_job_id, generated_at):
    """READ currency only. Dispatch and saved target eligibility stay separate."""
    if (validity.get('schema') != 'mastermind.project_data_source_validity.v1'
            or currentness != dict(state='fresh', source_generation=validity.get('source_generation'))):
        return False
    rows = [item for item in validity.get('cards', []) if item.get('responsibility_ref') == work_ref and item.get('root_job_id') == root_job_id]
    if len(rows) != 1:
        return False
    meta = responsibility.get('validity', {}).get('card', {})
    receipt = rows[0].get('components', {}).get('card', {})
    budget, remaining = meta.get('valid_for_ms'), receipt.get('remaining_ms')
    return (meta.get('schema') == 'mastermind.autonomy_validity.v1'
        and meta.get('policy') == 'mapper-inclusive-48h-future-1h.v1'
        and meta.get('qualified_at') == generated_at == receipt.get('qualified_at')
        and meta.get('proof_ref') == receipt.get('proof_ref')
        and type(meta.get('proof_ref')) is str and _HASH.fullmatch(meta['proof_ref']) is not None
        and type(budget) is int and type(remaining) is int and 0 < remaining <= min(budget, 15000)
        and receipt.get('state') == 'current')
