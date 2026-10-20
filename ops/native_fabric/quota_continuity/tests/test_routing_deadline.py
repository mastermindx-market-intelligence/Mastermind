"""Real bounded picker subprocess; no provider, packet or task dispatch."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_commission_deadline import PYTHON_FIXTURE
from lane_runtime import cleanup_receipt_is_proven

ROOT = Path(__file__).resolve().parents[1]

ROUTE_SOURCE = '''import json,os,time
from pathlib import Path
def format_pick(task, **options):
    Path(os.environ['ROUTING_INPUT_RECORD']).write_text(json.dumps({'task_class':task,**options}))
    if os.environ['ROUTING_DELAY'] == '1':
        time.sleep(10)
    return 'POOL=minimax MODEL=MiniMax-M2.7 HOST=fixture MODE=minimax'
'''

PROGRAM = '''import json,os,sys,time
from pathlib import Path
from types import ModuleType,SimpleNamespace
for name in ('a04_terminal_reconcile','native_completion_reconcile','native_prestart_reconcile',
             'native_preexec_reconcile','native_host_review_controller_reconcile'):
    module=ModuleType(name);module.RUN=module.RUN_ID='unavailable-historical-fixture';module.KNOWN_RUNS=()
    sys.modules[name]=module
import fabric_task
from commission_deadline import CommissionDeadlineExpired
root=Path(os.environ['ROUTING_FIXTURE_ROOT'])
fabric_task.pick=SimpleNamespace(__file__=str(root/'picker/pick.py'))
deadline=time.monotonic_ns()+int(float(os.environ['ROUTING_BUDGET'])*1e9)
started=time.monotonic()
try:
    result=fabric_task._route_with_deadline('mechanical',{'pool':None,'host':'auto',
        'route_key':'routing-only','task_complexity':'C0_MECHANICAL'},deadline,
        dict(os.environ),root,'routing-only')
    value={'state':'route','route':result}
except CommissionDeadlineExpired:
    value={'state':'deadline'}
value['elapsed']=time.monotonic()-started
print(json.dumps(value))
'''


class RoutingDeadline(unittest.TestCase):
    def run_picker(self, *, slow):
        with tempfile.TemporaryDirectory(prefix="fabric-routing-deadline-") as raw:
            root = Path(raw)
            (root / "picker").mkdir()
            (root / "picker/pick.py").write_text(ROUTE_SOURCE)
            wrapper = root / "fixture-python"
            wrapper.write_text("#!" + sys.executable + "\n" + PYTHON_FIXTURE)
            wrapper.chmod(0o700)
            program = root / "invoke.py"
            program.write_text(PROGRAM)
            env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": os.pathsep.join((str(ROOT / "candidate"), str(ROOT / "source"))),
                "DEADLINE_FIXTURE_ROOT": str(root), "ROUTING_FIXTURE_ROOT": str(root),
                "ROUTING_INPUT_RECORD": str(root / "input.json"),
                "ROUTING_DELAY": "1" if slow else "0",
                "ROUTING_BUDGET": "0.35" if slow else "3"}
            result = subprocess.run([str(wrapper), str(program)], env=env,
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((root / "input.json").read_text())
            value = json.loads(result.stdout)
            receipt = json.loads((root / "routing-only.routing-process.jsonl").read_text().splitlines()[-1])
            self.assertEqual(record, {"task_class": "mechanical", "pool": None,
                "host": "auto", "route_key": "routing-only", "task_complexity": "C0_MECHANICAL"})
            self.assertTrue(receipt["cleanup"]["census_proven"])
            self.assertTrue(cleanup_receipt_is_proven(receipt["cleanup"]))
            self.assertFalse(any(root.glob("*.request-launch.json")))
            self.assertFalse(any(root.glob("*.provider.json")))
            return value, receipt

    def test_blocked_existing_picker_expires_without_task_launch(self):
        value, receipt = self.run_picker(slow=True)
        self.assertEqual(value["state"], "deadline")
        self.assertLess(value["elapsed"], 3)
        self.assertTrue(receipt["timed_out"])

    def test_successful_existing_picker_preserves_route_and_metadata(self):
        value, receipt = self.run_picker(slow=False)
        self.assertEqual(value["state"], "route")
        self.assertEqual(value["route"], "POOL=minimax MODEL=MiniMax-M2.7 HOST=fixture MODE=minimax")
        self.assertFalse(receipt["timed_out"])


if __name__ == "__main__":
    unittest.main()
