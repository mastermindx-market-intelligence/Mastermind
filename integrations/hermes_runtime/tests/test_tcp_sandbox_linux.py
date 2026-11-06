"""Actual Linux child-process enforcement, with synthetic loopback listeners.

No provider, service installation, credential, root, or external request.
A skip is explicitly NOT kernel enforcement acceptance. On the target host,
require this case to pass without skips before any production credential use.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
CHILD = r'''
import errno, json, socket, subprocess, sys
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.tcp_sandbox import apply_tcp_port_policy
host, allowed, denied, bind_port = sys.argv[1], *map(int, sys.argv[2:])
try:
    apply_tcp_port_policy(frozenset({bind_port}), frozenset({allowed}))
except RuntimeRefusal as exc:
    print(json.dumps({"sandbox": "UNAVAILABLE", "code": exc.code}))
    sys.exit(77)
def connection(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port))
allowed_rc, denied_rc = connection(allowed), connection(denied)
with socket.socket() as sock:
    sock.bind((host, bind_port))
    bound = sock.getsockname()[1] == bind_port
with socket.socket() as sock:
    try:
        sock.bind((host, 0))
        forbidden_bind = False
    except OSError as exc:
        forbidden_bind = exc.errno == errno.EACCES
# An exec'd descendant must inherit the denial rather than escape it.
grandchild = subprocess.run([sys.executable, "-c",
    "import socket,sys; s=socket.socket(); s.settimeout(1); "
    "print(s.connect_ex((sys.argv[1],int(sys.argv[2])))); s.close()",
    host, str(denied)], capture_output=True, text=True, timeout=5, close_fds=True)
child_denied = grandchild.returncode == 0 and grandchild.stdout.strip() == str(errno.EACCES)
result = {"sandbox": "APPLIED", "allowed_connect": allowed_rc,
          "wildcard_own_alias_denied": denied_rc == errno.EACCES,
          "fixed_bind_allowed": bound, "ephemeral_bind_denied": forbidden_bind,
          "exec_child_inherits_denial": child_denied}
print(json.dumps(result, sort_keys=True))
sys.exit(0 if allowed_rc == 0 and denied_rc == errno.EACCES and bound
         and forbidden_bind and child_denied else 1)
'''


@unittest.skipUnless(sys.platform == "linux", "real Landlock requires Linux; not host acceptance")
class LinuxTcpEnforcementTests(unittest.TestCase):
    def test_unrelated_wildcard_port_is_denied_on_both_own_aliases(self):
        with socket.socket() as allowed, socket.socket() as denied:
            allowed.bind(("0.0.0.0", 0))
            denied.bind(("0.0.0.0", 0))
            allowed.listen(8)
            denied.listen(8)
            ports = (allowed.getsockname()[1], denied.getsockname()[1])
            # Positively establish the denied service is listening on both
            # aliases before sandboxing; ECONNREFUSED can never count as proof.
            for host in ("127.0.0.2", "127.0.0.3"):
                with socket.create_connection((host, ports[1]), timeout=1):
                    connection, _ = denied.accept()
                    connection.close()
                with socket.socket() as reserve:
                    reserve.bind((host, 0))
                    bind_port = reserve.getsockname()[1]
                completed = subprocess.run(
                    [sys.executable, "-c", CHILD, host, str(ports[0]), str(ports[1]), str(bind_port)],
                    cwd=ROOT, env={"PATH": os.defpath, "PYTHONPATH": str(ROOT),
                                   "PYTHONDONTWRITEBYTECODE": "1"},
                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                    timeout=15, close_fds=True,
                )
                if completed.returncode == 77:
                    self.skipTest("kernel sandbox unavailable: " + completed.stdout.strip())
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                report = json.loads(completed.stdout)
                self.assertEqual(report["allowed_connect"], 0)
                self.assertTrue(report["wildcard_own_alias_denied"])
                self.assertTrue(report["fixed_bind_allowed"])
                self.assertTrue(report["ephemeral_bind_denied"])
                self.assertTrue(report["exec_child_inherits_denial"])


if __name__ == "__main__":
    unittest.main()
