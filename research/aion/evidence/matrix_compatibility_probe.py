"""Throwaway source-compatibility proof; no network or real publication."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

network_events = []
def deny_network(event, args):
    if event == 'socket.connect':
        network_events.append(event)
        raise AssertionError('No network allowed in compatibility proof')
sys.addaudithook(deny_network)

from scripts.build_options_structure_intraday import Artifact, _put_immutable, ImmutableCollisionError
from tests.test_build_options_structure_intraday import FakeR2

root = Path(__file__).resolve().parent
fixture_bytes = (root / 'matrix_fixture.json').read_bytes()
fixtures = json.loads(fixture_bytes)
remote = FakeR2()
results = []
for symbol in ('SPY', 'QQQ'):
    payload = fixtures[symbol]
    before = deepcopy(payload)
    artifact = Artifact.from_payload('fixture-only/' + symbol + '.json', payload)
    _put_immutable(remote, 'fake-bucket', artifact)
    assert remote.objects[artifact.key][0] == artifact.body
    assert json.loads(artifact.body) == payload
    assert payload == before
    puts_before = len(remote.puts)
    _put_immutable(remote, 'fake-bucket', artifact)
    assert len(remote.puts) == puts_before
    modified = deepcopy(payload)
    modified['spot'] = float(payload['spot']) + 1
    conflict = Artifact.from_payload(artifact.key, modified)
    try:
        _put_immutable(remote, 'fake-bucket', conflict)
    except ImmutableCollisionError:
        pass
    else:
        raise AssertionError('Changed observation overwrote the original')
    assert remote.objects[artifact.key][0] == artifact.body
    assert remote.delete_calls == 0
    path = root / (symbol + '-roundtrip.json')
    path.write_bytes(remote.objects[artifact.key][0])
    results.append({'root':symbol,'sha256':artifact.sha256,
                    'source_asof':payload.get('asof'),'cells':len(payload['cells']),
                    'roundtrip_equal':True,'duplicate_idempotent':True,'collision_refused':True})
assert network_events == []
result = {'evidence_class':'exact_existing_modules_synthetic_matrix_fixture_compatibility',
          'macro_source':'e729d0fd9d48868b49a1911d4098c689b3d373bd',
          'terminal_source':'87969fb4aff5836410ffd166cc39289b562a41bc',
          'fixture_sha256':sha256(fixture_bytes).hexdigest(), 'cases':results,
          'network_events':0,'remote_writes':0,'production_proof':False,
          'historical_index_or_correction_contract_proven':False}
(root / 'matrix_compatibility_result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
