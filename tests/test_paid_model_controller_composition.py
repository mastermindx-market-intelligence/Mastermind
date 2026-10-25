import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).parents[1]
QUOTA = ROOT / 'ops/native_fabric/quota_continuity'


def test_actual_staged_candidate_requires_original_context_before_model_entry(tmp_path):
    built = subprocess.run([sys.executable, str(QUOTA/'rollout/build_review_stage.py'),
                            '--output',str(tmp_path)],capture_output=True,text=True)
    assert built.returncode == 0, built.stderr
    stage = tmp_path/'native-code-stage/ext'
    code = '''
import os,hashlib
from pathlib import Path
import remote_sub_exec as remote
root=Path(os.environ['FIXTURE_SUPPORT'])
lanes=Path('/inert/lanes')
env={'FABRIC_CANONICAL_PAID_MODE':'sealed-model-only-v1',
 'REMOTE_SUB_LANES':str(lanes),'GLM_REMOTE_CAPABILITY_FILE':str(lanes/'tmp/a.glm-cap.json')}
try:remote._canonical_model_command(root,lanes/'tmp/a.txt','a','glm','glm-5.3',env)
except ValueError:pass
else:raise AssertionError('environment labels manufactured original source custody')
import paid_initializer
for name,expected in paid_initializer._CANONICAL_ENTRY_SOURCES.items():
 assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
assert remote._canonical_model_command(root,lanes/'tmp/a.txt','a','glm','glm-5.3',{}) is None
for extra in ({'FABRIC_OPERATOR_CAPSULE':'fake'},{'FABRIC_NEW_MACRO_COMMIT':'f'*40},
              {'FABRIC_CANONICAL_PAID_MODE':'other'},{'GLM_REMOTE_CAPABILITY_FILE':'/private/credential'}):
 try:remote._canonical_model_command(root,lanes/'tmp/a.txt','a','glm','glm-5.3',{**env,**extra})
 except ValueError:pass
 else:raise AssertionError('unsupported scope entered model client')
print('staged_model_only_selection_pass')
'''
    checked = subprocess.run([sys.executable,'-B','-c',code],cwd=stage,
        env={**os.environ,'PYTHONPATH':str(stage),'FIXTURE_SUPPORT':str(stage)},
        capture_output=True,text=True)
    assert checked.returncode == 0, checked.stderr
    assert checked.stdout == 'staged_model_only_selection_pass\n'
    inventory=json.loads((tmp_path/'native-source-inventory.json').read_text())
    expected_sources = {
        'remote_sub.sh': 'candidate/remote_sub.sh',
        'remote_sub_exec.py': 'candidate/remote_sub_exec.py',
        'support_bundle.py': 'candidate/support_bundle.py',
        'paid_glm_model_client.py': 'candidate/paid_glm_model_client.py',
    }
    for name, expected in expected_sources.items():
        assert inventory['files']['ext/'+name]['source'] == expected
    # The selected overlay must retain protected paid-mode scope refusal
    # as well as its separately reviewed Grok 4.7 safety controls.
    selected_transport = (stage / 'remote_sub.sh').read_text()
    assert 'CANONICAL_PAID_SCOPE_REFUSED before_lease=1' in selected_transport
    assert 'CANONICAL_PAID_STATE_REFUSED before_lease=1' in selected_transport


def test_private_scope_guard_refuses_before_reservation_or_acquire():
    source=(QUOTA/'candidate/remote_sub.sh').read_text()
    guard=source[source.index('CANONICAL_PAID_ACTIVE=0'):source.index('NATIVE_MODE=0')]
    env={**os.environ,'FABRIC_CANONICAL_PAID_MODE':'sealed-model-only-v1',
         'FABRIC_CANONICAL_PAID_NONCE':'a'*64,'FABRIC_CANONICAL_PAID_PAYLOAD_SHA256':'b'*64,
         'FABRIC_CANONICAL_PAID_HOST':'ubuntu0'}
    for setup in ["MODE=glm; HOST_ARG=auto; DRY_RUN=0; MODEL=glm-5.3",
                  "MODE=qwen; HOST_ARG=ubuntu0; DRY_RUN=0; MODEL=glm-5.3",
                  "MODE=glm; HOST_ARG=ubuntu0; DRY_RUN=1; MODEL=glm-5.3"]:
        checked=subprocess.run(['bash','-c','set -u\n'+setup+'\n'+guard],env=env,
                               capture_output=True,text=True)
        assert checked.returncode==78
        assert checked.stdout==''
        assert checked.stderr=='CANONICAL_PAID_SCOPE_REFUSED before_lease=1\n'
    assert source.index('CANONICAL_PAID_REQUIRED schema=1') < source.index('broker acquire ')
    assert source.index('9 "$ID" "$LEASE_ID"') > source.index('LEASE_ID=$(awk')
    assert source.index('exec 9>&-\n  [ "$RC"') < source.index('GLM_ACCOUNT_QUOTED=')


def test_manual_and_paid_support_closures_are_distinct(tmp_path):
    code='''
import support_bundle as support
assert support.PAID_MODEL_SOURCE_FILES-support.SOURCE_FILES=={'paid_glm_model_client.py','paid_model_owner.py','linux_process_identity.py'}
assert support.PAID_INITIALIZED_SOURCE_FILES-support.PAID_MODEL_SOURCE_FILES=={'paid_provider_entry.py','paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py'}
assert support.PAID_MODEL_SOURCE_FILES in support.SOURCE_GENERATIONS
assert support.PAID_INITIALIZED_SOURCE_FILES in support.SOURCE_GENERATIONS
assert 'paid_glm_model_client.py' not in support.PHYSICAL_ROOT_SOURCE_FILES
assert support.SOURCE_FILES in support.SOURCE_GENERATIONS
assert support.PHYSICAL_ROOT_SOURCE_FILES in support.SOURCE_GENERATIONS
'''
    stage=tmp_path/'support';stage.mkdir()
    (stage/'support_bundle.py').write_bytes((QUOTA/'candidate/support_bundle.py').read_bytes())
    checked=subprocess.run([sys.executable,'-B','-c',code],cwd=stage,
                           capture_output=True,text=True)
    assert checked.returncode==0,checked.stderr
