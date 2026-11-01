"""Explicit code-closure tests only; never install/select a native generation."""
from pathlib import Path
import hashlib
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
DRAFT=ROOT/'ops/native_fabric/quota_continuity/rollout'


def builder():
    spec=importlib.util.spec_from_file_location('inert_native100_builder',DRAFT/'build_review_stage.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_explicit_new_pair_in_native100_and_all_old_base_checks_retained():
    m=builder()
    assert {'paid_provider_entry.py','paid_host_readiness.py'}<=m.ADDITIONS
    assert len(m.GROK47_MERGED_SOURCE_DIGESTS)==9
    assert {'remote_sub.sh','remote_sub_exec.py','pick.py'}<=set(m.GROK47_MERGED_SOURCE_DIGESTS)
    for name,expected in m.GROK47_MERGED_SOURCE_DIGESTS.items():
        assert hashlib.sha256((ROOT/'ops/native_fabric/grok47/overlay'/name).read_bytes()).hexdigest()==expected


def test_four_exact_forward_compositions_include_actual_executor():
    m=builder()
    assert set(m.GROK47_CANDIDATE_COMPOSITION_DIGESTS)=={'pick.py','remote_sub.sh','remote_sub_exec.py','remote_sub_helpers.py'}
    for name,expected in m.GROK47_CANDIDATE_COMPOSITION_DIGESTS.items():
        assert hashlib.sha256((DRAFT.parent/'candidate'/name).read_bytes()).hexdigest()==expected


def test_generated_manifest_covers_actual_new_entry_and_readiness_graph(tmp_path):
    import json,subprocess,sys
    m=builder()
    candidate=DRAFT.parent/'candidate'
    def load(name):
        spec=importlib.util.spec_from_file_location('packaging_'+name,candidate/(name+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    support=load('support_bundle');entry=load('paid_provider_entry')
    namespace=m.BASE_FILES|m.ADDITIONS
    assert entry.SUPPORT_FILES==support.PAID_INITIALIZED_SOURCE_FILES
    assert entry.SOURCE_NAMES<=namespace
    assert support.PAID_INITIALIZED_PHYSICAL_ROOT_SOURCE_FILES-{'pools.yaml'}<=namespace
    expected={'ext/'+name for name in namespace}|{'pool'}
    built=subprocess.run([sys.executable,str(DRAFT/'build_review_stage.py'),'--output',str(tmp_path)],capture_output=True,text=True,timeout=25)
    assert built.returncode==0,built.stderr
    manifest=json.loads((tmp_path/'native-manifest.json').read_bytes())
    inventory=json.loads((tmp_path/'native-source-inventory.json').read_bytes())
    assert set(manifest)==set(inventory['files'])==expected
    assert inventory['native_code_files']==len(expected)
    for name in ('paid_provider_entry.py','paid_host_readiness.py','paid_initializer.py',
                 'paid_initializer_token_data.py','paid_initializer_nested_data.py'):
        key='ext/'+name
        assert manifest[key]==hashlib.sha256((candidate/name).read_bytes()).hexdigest()
        assert inventory['files'][key]['source']=='candidate/'+name


def test_exact_new_template_publisher_is_not_old_launcher_ingress(tmp_path):
    import json,pytest
    path=DRAFT/'native_generation.py';current=path.read_bytes()
    added=(b'    # One vetted flat plist. Not a suffix rule and not a directory walk.\n'
           b'    if relative == "ext/host_pull_launchd.plist.template":\n'
           b'        return\n')
    assert hashlib.sha256(current).hexdigest()=='43e814339a16582e2205f12117e1f17c40dce2e42a9c52d815a37c043e772e1b'
    assert current.count(added)==1
    old=current.replace(added,b'',1)
    assert hashlib.sha256(old).hexdigest()=='d044c24940df13d24ff6241f0da9cec3dc24d90dd60604a08c82e0ad8613586c'
    def load(name,raw):
        source=tmp_path/(name+'.py');source.write_bytes(raw)
        spec=importlib.util.spec_from_file_location(name,source)
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner);return owner
    before=load('old_ingress',old);after=load('new_publisher',current)
    manifest=json.loads((DRAFT/'native-manifest.json').read_bytes())
    assert 'ext/host_pull_launchd.plist.template' in manifest
    with pytest.raises(ValueError,match='flat code files'):before.manifest_files(manifest)
    assert after.manifest_files(manifest)==manifest
    for name in ('ext/other.plist.template','ext/nested/host_pull_launchd.plist.template'):
        with pytest.raises(ValueError):after.file_name(name)
