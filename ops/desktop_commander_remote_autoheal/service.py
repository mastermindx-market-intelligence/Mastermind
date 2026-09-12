#!/usr/bin/python3
"""launchd entry: one OS-owned singleton lock, then exec the pinned Node host.
No fork, request queue, polling loop, credential copying or shell expansion.
"""
import fcntl
import json
import os
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1]).resolve(strict=True)
root = config_path.parent
config = json.loads(config_path.read_text())
if os.getuid() != config['uid'] or str(root) != config['root']:
    raise SystemExit('service_identity_mismatch')
for file in [root, config_path, root / 'runtime.mjs', root / 'monitor.mjs', root / 'safety.mjs']:
    stat = file.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o022:
        raise SystemExit('service_permissions_unsafe')
os.umask(0o077)
fd = os.open(root / 'service.lock', os.O_CREAT | os.O_RDWR, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit(0)
os.set_inheritable(fd, True)
env = {key: value for key, value in config['environment'].items()}
env['DC_SERVICE_LOCK_FD'] = str(fd)
os.execve(config['node'], [config['node'], str(root / 'runtime.mjs'), str(config_path)], env)
