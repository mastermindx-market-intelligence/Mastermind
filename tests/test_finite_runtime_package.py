"""Real isolated import closure, no injected modules or provider effects."""
import os
from pathlib import Path
import subprocess
import sys


def test_isolated_release_resolves_actual_owner_dependencies():
    root=Path(__file__).resolve().parents[1]
    source='''import sys
sys.path.insert(0,ROOT)
from integrations.session_bridge.bound_launch_capture.runtime import lane_runtime, remote_sub_exec
from integrations.session_bridge.bound_launch_capture import fabric_reserved_attended_launch, fabric_attended_backend
assert remote_sub_exec.LaneLease is lane_runtime.LaneLease
assert callable(remote_sub_exec._begin_reserved_attended_under_lease)
assert callable(fabric_reserved_attended_launch.prepare_reserved_attended_launch)
assert 'native_remote' not in sys.modules
assert 'fabric_client_projection' not in sys.modules
print('ISOLATED_OWNER_CLOSURE_PASS')
'''.replace('ROOT',repr(str(root)))
    result=subprocess.run([sys.executable,'-I','-S','-B','-c',source],capture_output=True,text=True,timeout=20,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','PYTHONPATH':'/untrusted/ignored'})
    assert result.returncode==0,result.stderr
    assert result.stdout=='ISOLATED_OWNER_CLOSURE_PASS\n'
