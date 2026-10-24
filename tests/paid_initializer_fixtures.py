"""Explicit synthetic commitment DATA, never current host approval."""
from pathlib import Path
from ops.native_fabric.quota_continuity.candidate import paid_initializer as module


def commitment(host='ubuntu2',alias='ubuntu2',python='/usr/bin/python3',capture='/home/worker/lanes/ext/lanes',
               uid=1000,gid=1000,user='worker',home='/home/worker',binary_sha='a'*64,hook_sha='b'*64):
    lane=str(Path(capture).parent.parent)
    return dict(schema_version=module.SCHEMA,host_ref=host,transport_alias=alias,lane_root=lane,
        account=dict(uid=uid,gid=gid,user=user,home=home),
        bootstrap_python=dict(path='/usr/bin/python3',real_path='/usr/bin/python3.12',sha256='a'*64),
        launch_python=dict(path=python,real_path=python,sha256=binary_sha),
        host_env=dict(path=lane+'/ext/HOST_ENV.sh',sha256=hook_sha,size=8,uid=uid,gid=gid,mode=0o600),
        initialized_context=dict(home=home,glm_config=home+'/glm.json'),initialization_contract=module.CONTRACT,purpose=module.PURPOSE,
        startup=dict(profile='cpython-3.12-linux-root-prefix.v1',prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr'))


def witness(req):
    c=req['initializer_commitment']
    return dict(commitment_sha256=req['initializer_commitment_sha256'],snapshot_sha256=c['host_env']['sha256'],snapshot_sealed=True,
        host_env_identity=[1,2,0o100600,c['account']['uid'],c['account']['gid'],1,8,100,100],
        bootstrap_sha256=c['bootstrap_python']['sha256'],launch_sha256=c['launch_python']['sha256'])
