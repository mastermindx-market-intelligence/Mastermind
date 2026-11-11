"""Real held YAML supplies the unchanged no-site routing policy implementation."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DRIVER = r'''
import hashlib,importlib.util,json,sys
from pathlib import Path
candidate,policy_path,workspace=map(Path,sys.argv[1:])
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
runtime=load('held_policy_runtime',candidate/'paid_yaml_runtime.py')
policy=load('held_real_policy',policy_path)
assert importlib.util.find_spec('yaml') is None
archive=(candidate/'paid_pyyaml_6_0_3.zip').read_bytes()
provenance=(candidate/'paid_pyyaml_provenance.json').read_bytes()
raw=b'{"routing":{},"pools":{"grok":{"windows":{"weekly":{}}}}}\n'
# A guard callback has no truthy return and never substitutes admission.
calls=[]
def check():calls.append(1)
with runtime.held_yaml(archive,provenance,check):
    assert policy.parse_policy(raw)['routing']=={}
    fingerprint=policy.critical_fingerprint(raw)
    assert len(fingerprint)==64
    for bad in (b'routing: {}\nrouting: {}\n',b'1: value\n'):
        try:policy.parse_policy(bad)
        except ValueError as error:assert str(error)=='ROUTING_POLICY_DUPLICATE_OR_NONSTRING_KEY'
        else:raise AssertionError('ambiguous policy accepted')
    stable=workspace/'lanes/ext';(stable/'active').mkdir(parents=True)
    data=stable.parent/'orch/fabric';data.mkdir(parents=True)
    (data/'pools.yaml').write_bytes(raw)
    snapshot=workspace/'snapshot.yaml';snapshot.write_bytes(raw)
    result=policy.validate_publication(snapshot,stable)
    assert result['snapshot_sha256']==result['stable_sha256']==hashlib.sha256(raw).hexdigest()
    (data/'pools.yaml').write_bytes(b'{"routing":{"changed":true},"pools":{"grok":{"windows":{"weekly":{}}}}}\n')
    try:policy.validate_publication(snapshot,stable)
    except ValueError as error:assert str(error)=='ROUTING_CRITICAL_POLICY_MISMATCH'
    else:raise AssertionError('critical mismatch admitted')
    (data/'pools.yaml').unlink()
    try:policy.validate_publication(snapshot,stable)
    except FileNotFoundError:pass
    else:raise AssertionError('missing stable policy admitted')
assert len(calls)==20
assert not any(n=='yaml' or n.startswith('yaml.') or n=='_yaml' for n in sys.modules)
print('HELD_REAL_POLICY_POSITIVE_AND_NEGATIVES_OK')
'''


def test_real_policy_positive_and_refusals_in_no_site_interpreter(tmp_path):
    completed=subprocess.run([sys.executable,'-I','-S','-B','-c',DRIVER,
        str(ROOT/'ops/native_fabric/quota_continuity/candidate'),
        str(ROOT/'ops/native_fabric/quota_continuity/source/fabric_policy_snapshot.py'),
        str(tmp_path)],capture_output=True,timeout=20)
    assert completed.returncode==0, 'isolated real policy proof refused'
    assert completed.stdout==b'HELD_REAL_POLICY_POSITIVE_AND_NEGATIVES_OK\n'
    assert not completed.stderr


COMPOSITION_DRIVER = r'''
import importlib.util,sys
from pathlib import Path
from types import SimpleNamespace
candidate=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('fixture_entry',candidate/'paid_provider_entry.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
sources={name:(candidate/name).read_bytes() for name in entry.YAML_NAMES}
checks=[]
owner=SimpleNamespace(sources=sources,here=candidate,check=lambda:checks.append(1))
class ForeignFinder:
    def __eq__(self,other):return True
    def find_spec(self,fullname,path=None,target=None):return None
foreign=ForeignFinder();before=list(sys.meta_path)
try:
    with entry._support_imports(owner):
        import yaml
        assert yaml.__version__=='6.0.3'
        sys.meta_path.insert(0,foreign)
except entry.ProviderEntryRefused:pass
else:raise AssertionError('composed finder drift accepted')
assert sys.meta_path[0] is foreign
assert len(sys.meta_path)==len(before)+1
assert all(a is b for a,b in zip(sys.meta_path[1:],before))
assert 'paid_yaml_runtime' not in sys.modules
assert not any(n=='yaml' or n.startswith('yaml.') or n=='_yaml' for n in sys.modules)
assert checks
print('HELD_COMPOSITION_FOREIGN_FINDER_PRESERVED_AND_REFUSED')
'''


def test_composed_support_context_preserves_foreign_equal_comparing_finder():
    completed=subprocess.run([sys.executable,'-I','-S','-B','-c',COMPOSITION_DRIVER,
        str(ROOT/'ops/native_fabric/quota_continuity/candidate')],capture_output=True,timeout=20)
    assert completed.returncode==0, 'composed held import cleanup proof refused'
    assert completed.stdout==b'HELD_COMPOSITION_FOREIGN_FINDER_PRESERVED_AND_REFUSED\n'
    assert not completed.stderr
