"""Closed request-local project DATA metadata; syntax never grants READ."""
import json
import re
from datetime import datetime, timezone
from common.workspace_project_plan_contract import validate_source, validate_selection

RECORD_SCHEMA = 'mastermind.project_discovery_record.v1'
MAX_RECORD_BYTES = 262144


def validate_record(value, *, work_ref, code_commit, data_commit):
    try:
        validate_selection({'work_ref': work_ref})
        if (type(value) is not dict or set(value) != {'schema', 'selection', 'source', 'code_source', 'observed_at_ms', 'agent_os_state'}
                or value['schema'] != RECORD_SCHEMA or value['selection'] != {'work_ref': work_ref}):
            raise ValueError()
        source = validate_source(value['source'], work_ref)
        code = value['code_source']
        if (source['commit'] != data_commit or type(code) is not dict
                or set(code) != {'repository', 'commit', 'path', 'content_sha256'}
                or code['repository'] != source['repository'] or code['commit'] != code_commit
                or code['path'] != 'scripts/agentos.py' or type(code['content_sha256']) is not str
                or re.fullmatch(r'[a-f0-9]{64}', code['content_sha256']) is None):
            raise ValueError()
        stamp = value['observed_at_ms']
        state = value['agent_os_state']
        if (type(stamp) is not int or not 0 < stamp <= 9007199254740991
                or type(state) is not dict or state.get('schema') != 'agent_os_state.v1'
                or type(state.get('workstreams')) is not list or len(state['workstreams']) != 1
                or type(state['workstreams'][0]) is not dict or state['workstreams'][0].get('key') != work_ref[3:]):
            raise ValueError()
        generated = datetime.fromisoformat(state['generated_at'].replace('Z', '+00:00'))
        if generated.utcoffset() is None or abs(generated.timestamp() * 1000 - stamp) >= 1000:
            raise ValueError()
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8', errors='strict')
        if len(encoded) + 1 > MAX_RECORD_BYTES:
            raise ValueError()
        return json.loads(encoded)
    except Exception:
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE') from None
