"""Finite enrollment source closure through the real held importer.

Root UID/GID, outside-fixture ancestor modes and ACL absence are explicit test
edges. This does not install/enroll a host, open credentials, sockets or models.
"""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

from tests.test_hermes_isolated_entry import manifest

ROOT = Path(__file__).resolve().parents[1]


def test_finite_enrollment_paths_import_v4_through_held_source_owner(tmp_path):
    spec = importlib.util.spec_from_file_location("discovery_enrollment", ROOT / "scripts/enroll_linux_secondary_worker.py")
    enrollment = importlib.util.module_from_spec(spec); sys.modules[spec.name] = enrollment
    spec.loader.exec_module(enrollment)
    root = tmp_path / "releases" / ("a" * 40)
    root.mkdir(parents=True)
    for relative in enrollment.RELEASE_PATHS:
        source, target = ROOT / relative, root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, target)
    manifest(root)
    driver = r'''
import importlib.util,os,pathlib,sys,types
root=pathlib.Path(sys.argv[1]); entry=root/'ops/executive_os/release_manifest.py'
spec=importlib.util.spec_from_file_location('_discovery_held_owner',entry)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ancestors={(p.stat().st_dev,p.stat().st_ino) for p in root.parents}
def owned(raw):
    data={k:getattr(raw,k) for k in dir(raw) if k.startswith('st_')}
    data.update(st_uid=0,st_gid=0)
    if (raw.st_dev,raw.st_ino) in ancestors:data['st_mode'] &= ~0o022
    return types.SimpleNamespace(**data)
class Proxy:
    def __init__(self,target,**values):self.target=target;self.values=values
    def __getattr__(self,name):return self.values.get(name,getattr(self.target,name))
m.os=Proxy(os,stat=lambda *a,**k:owned(os.stat(*a,**k)),fstat=lambda fd:owned(os.fstat(fd)))
m.sys=Proxy(sys,platform='linux');m._LINUX_RELEASES=root.parent
m._linux_source_acl=lambda fd,directory:None
owner=m._HeldReleaseSources(root)
try:
    with m._held_release_imports(owner) as finder:
        from integrations.hermes_harness.native_discovery_tools import schemas
        from integrations.hermes_runtime.native_agentos_memory import validate_consumer_readback
        assert len(schemas()) == 2
        finder.check()
        assert all(str(root) in str(getattr(v,'__file__','')) or getattr(v,'__file__',None) is None
                   for v in finder.owned.values())
finally:owner.close()
assert str(root) not in sys.path
print('HELD_DISCOVERY_CLOSURE_OK')
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", driver, str(root)],
        cwd=tmp_path, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout[-1000:] + result.stderr[-3000:]
    assert result.stdout.strip() == "HELD_DISCOVERY_CLOSURE_OK"
