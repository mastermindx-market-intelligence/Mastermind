"""The recovered L0 binding admits one original read, before any filesystem IO."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUN = "mm-l0-price-metadata-review-20261015-01a1333c-v1"
OWNER = "01a1333c-a475-7052-95a8-72c623fb12e1"
PACKET = "baf0b1e363b85a22796086029202e6b2e8330d21f4caa6b78a02d40c2916d197"
SUPPORT = "8172955c737b6f55f83aaebcdea5c22566f06a14320bd3fd967054da0fd6c51c"


@pytest.fixture(scope="module")
def staged_ext(tmp_path_factory):
    stage = tmp_path_factory.mktemp("l0-original-read")
    subprocess.run(
        [sys.executable, str(ROOT / "ops/native_fabric/quota_continuity/rollout/build_review_stage.py"),
         "--output", str(stage)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return stage / "native-code-stage/ext"


def test_generated_reader_requires_exact_original_scope_before_any_io(staged_ext):
    request = {
        "schema": "mastermind.original_delivery_read.v1", "run_id": RUN,
        "root": OWNER, "parent": OWNER, "host": "ubuntu1",
        "contract": {"schema": "mastermind.original_plain_result_contract.v1",
                     "run_id": RUN, "root": OWNER, "parent": OWNER, "names": [],
                     "packet_sha256": PACKET, "support_digest": SUPPORT},
    }
    program = f"""
import copy
import sys
sys.path.insert(0, {str(staged_ext)!r})
import original_delivery_collector as collector
request = {request!r}
code = collector.code_for_request(request)
namespace = {{}}
exec(compile(code[:code.rfind('\\ntry:\\n raw=')], 'generated-reader', 'exec'), namespace)
visited = []
class OriginalPathReached(Exception):
    pass
def directory_probe(path):
    visited.append(str(path))
    raise OriginalPathReached()
namespace['DirectoryChain'] = directory_probe
try:
    namespace['remote_read'](request, home='/inert-owner')
except OriginalPathReached:
    pass
else:
    raise AssertionError('exact original request never reached its original packet path')
assert visited == ['/inert-owner/lanes/tmp']
changes = [
    ('root', 'another-root'), ('parent', 'another-parent'), ('host', 'ubuntu0'),
    ('run_id', request['run_id'] + '-replacement'),
    ('contract.root', 'another-root'), ('contract.parent', 'another-parent'),
    ('contract.run_id', request['run_id'] + '-replacement'),
    ('contract.packet_sha256', '0' * 64), ('contract.support_digest', '0' * 64),
    ('contract.names', ['replacement.patch']),
    ('contract.schema', 'mastermind.fabric_artifact_production.v1'),
]
for field, value in changes:
    candidate = copy.deepcopy(request)
    if field.startswith('contract.'):
        candidate['contract'][field.split('.')[1]] = value
    else:
        candidate[field] = value
    visited.clear()
    try:
        namespace['remote_read'](candidate, home='/inert-owner')
    except ValueError as error:
        assert str(error) == 'read_contract_invalid', (field, str(error))
    else:
        raise AssertionError('accepted changed original scope: ' + field)
    assert not visited, field
"""
    result = subprocess.run([sys.executable, "-B", "-c", program],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_scope_provenance_preserves_original_dispatch_and_lease():
    proof = json.loads((ROOT / "ops/native_fabric/quota_continuity/rollout/market_memory_l0_original_scope.json").read_text())
    assert proof["original_session_id"] == OWNER
    assert proof["run_id"] == RUN
    assert proof["scope"]["packet_sha256"] == PACKET
    assert proof["scope"]["support_digest"] == SUPPORT
    assert proof["scope"]["lease_witness"]["sha256"] == "70ba6a698a49d7401611ef5ab5cf6f2f64f10355329d6593f38a76b3d3f5887b"
    assert proof["witnesses"][1]["call_id"] == "call_d7cb5da6dc124cc293b2519cb7d9763b"
    assert proof["effect"] == "LOCAL_SOURCE_QUALIFICATION_ONLY_NO_REMOTE_READ_NO_LEASE_MUTATION"


def test_sealed_generation_uses_original_state_owner_and_keeps_custody_checks(staged_ext):
    # Every byte and path below belongs to this inert kit. No real run, host,
    # credential, lease or selection pointer is read or changed.
    with tempfile.TemporaryDirectory(prefix="l0-native-state-", dir=Path.home()) as directory:
        base = Path(directory)
        program = f"""
import copy
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, {str(ROOT / 'ops/native_fabric/quota_continuity/rollout')!r})
import native_generation
base = Path({str(base)!r})
owner = base/'kit/ext'
state = owner/'state/remote_sub'
state.mkdir(parents=True, mode=0o700)
stage = Path({str(staged_ext.parent)!r})
manifest = json.loads((stage.parent/'native-manifest.json').read_text())
generation = native_generation.publish(stage, owner, manifest)
sys.path.insert(0, str(generation/'ext'))
import original_delivery_collector as collector
rid = 'inert-original-l0'
root = 'inert-parent'
os.environ['CODEX_THREAD_ID'] = root
packet = base/'packet.txt'
packet.write_bytes(b'inert review text without an artifact contract')
lease = state/(rid+'.lease.fixture')
lease.write_bytes(b'inert lease witness')
manifest = {{name: collector.sha((generation/'ext'/name).read_bytes())
            for name in ('artifact_production.py', 'artifact_reader.py')}}
support = state/(rid+'.support.json')
support.write_bytes(collector.canonical(manifest))
support_digest = collector.sha(collector.canonical({{'schema':'remote-support-code.v1','files':manifest}}))
log = state/(rid+'.log')
events = ['LEASE_OK pool=minimax',
          'SUPPORT_VERSION_READY digest='+support_digest+' policy='+'1'*64,
          'LAUNCH stdout=lanes_'+rid+'.stdout rc_file=ext/lanes_'+rid+'.rc cwd=~',
          'LAUNCH_ATTEMPT attempt=1']
log.write_text(''.join('2026-10-19T00:00Z [remote_sub id='+rid+' host=inert-host] '+event+'\\n' for event in events))
(owner/'hosts.json').write_text(json.dumps({{'inert-host':{{'allowed_modes':['minimax'],'ssh_alias':'inert-host'}}}}))
scope = {{'root':root,'parent':root,'host':'inert-host','packet_path':str(packet),
         'packet_sha256':collector.sha(packet.read_bytes()),'support_digest':support_digest,
         'source_pins':{{'log':collector.sha(log.read_bytes()),'support':collector.sha(support.read_bytes())}},
         'lease_witness':{{'path':str(lease),'sha256':collector.sha(lease.read_bytes())}}}}
collector.PLAIN_SCOPES[rid] = scope
binding = {{'schema':collector.BINDING_SCHEMA,'run_id':rid,'root':root,'parent':root,
           'host':'inert-host','mode':'minimax','requested_model':'MiniMax-M3','cwd':'~',
           'artifact_names':[], 'sources':{{name:{{'path':str(path),'sha256':collector.sha(path.read_bytes())}}
                    for name,path in [('packet',packet),('log',log),('support',support)]}}}}
binding_path = base/'binding.json'
def qualify(value):
    binding_path.write_bytes(collector.canonical(value))
    return collector.load_binding(binding_path, run_id=rid, root=root, parent=root)
assert qualify(binding)[3]['run_id'] == rid
alias_binding = copy.deepcopy(binding)
for name in ('log','support'):
    alias_binding['sources'][name]['path'] = str(generation/'ext/state/remote_sub'/Path(binding['sources'][name]['path']).name)
assert qualify(alias_binding)[3]['run_id'] == rid
outside = copy.deepcopy(binding)
outside['sources']['log']['path'] = str(base/log.name)
try:
    qualify(outside)
except ValueError as error:
    assert str(error) == 'original_source_path_invalid'
else:
    raise AssertionError('accepted a log outside the original state owner')
lease.write_bytes(b'changed inert witness')
try:
    qualify(binding)
except ValueError as error:
    assert str(error) == 'plain_original_lease_witness_changed'
else:
    raise AssertionError('accepted changed original lease witness')
lease.unlink()
lease.symlink_to(packet)
try:
    qualify(binding)
except (ValueError, OSError):
    pass
else:
    raise AssertionError('followed a lease symlink')
"""
        try:
            result = subprocess.run([sys.executable, "-B", "-c", program],
                                    capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            # Only this test's inert generation is unsealed for cleanup; never
            # follow its aliases or touch the installed runtime generation.
            for path, _directories, _files in os.walk(base, followlinks=False):
                os.chmod(path, 0o700)
