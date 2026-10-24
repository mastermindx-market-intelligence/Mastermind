"""Independent function-level proof; no host, provider, or installed broker I/O."""
from pathlib import Path
import os
import sqlite3
from typing import Optional
import types

import pytest

import subprocess
import tempfile
import textwrap

BUNDLE = (Path(__file__).resolve().parents[1] /
          "ops/native_fabric/routing_audit_20261013/queue_priority")
PREIMAGE = BUNDLE / "queue_front_reference.py.txt"
PATCH = BUNDLE / "queue_priority_isolation.patch"

def reviewed_source():
    original = ("class BrokerQueueReference:\n" +
                textwrap.indent(PREIMAGE.read_text(), "    ")).encode("utf-8")
    if os.environ.get("FABRIC_QUEUE_TEST_PREIMAGE") == "1":
        return original.decode("utf-8")
    # Apply the actual published follow-on patch to the exact function excerpt.
    # This proves the changed decision function, not full native integration.
    with tempfile.TemporaryDirectory(prefix="fabric-queue-source-") as temporary:
        root = Path(temporary)
        (root / "ext").mkdir()
        target = root / "ext/lease_broker.py"
        target.write_bytes(original)
        applied = subprocess.run(["git", "apply", str(PATCH)], cwd=root,
                                 capture_output=True, text=True, check=False)
        if applied.returncode != 0:
            raise RuntimeError("queue patch failed against reference: " + applied.stderr)
        return target.read_text()

SOURCE = reviewed_source()
PRIORITIES = {"heal": 0, "build": 1, "review": 2, "mechanical": 3}

def class_priority(task_class, job_class=None):
    logical = str(job_class or "").strip()
    return PRIORITIES.get((logical or task_class or "unknown").strip().lower(), 4)

namespace = {"sqlite3": sqlite3, "Optional": Optional,
             "_class_priority": class_priority}
exec(compile(SOURCE, "<reviewed-queue-decision-excerpt>", "exec"), namespace)
choose = namespace["BrokerQueueReference"]._front_of_queue

def decide(rows, current, job_class=None):
    # The incumbent query already orders by priority then enqueue time.
    waiters = [{"orchestrator_id": root, "priority": priority, "enqueued_at": age}
               for root, priority, age in rows]
    waiters.sort(key=lambda row: (row["priority"], row["enqueued_at"]))
    owner = types.SimpleNamespace(_waiters=lambda conn, pool: waiters)
    return choose(owner, None, "synthetic", "root-a", current, job_class)

@pytest.mark.parametrize("own_priority,other_priority,current", [
    (0, 1, "mechanical"), (0, 2, "mechanical"),
    (1, 2, "mechanical"), (0, 1, "review"),
    (0, 2, "review"), (1, 3, "mechanical"),
])
def test_cannot_borrow_sibling_urgency(own_priority, other_priority, current):
    rows = [("root-a", own_priority, 10), ("root-b", other_priority, 20)]
    assert decide(rows, current) is False

@pytest.mark.parametrize("current", ["heal", "build", "review", "mechanical", "unknown"])
def test_no_waiters_remains_available(current):
    assert decide([], current) is True

@pytest.mark.parametrize("current,priority", list(PRIORITIES.items()))
def test_existing_same_class_fifo_position_preserved(current, priority):
    assert decide([("root-a", priority, 10), ("root-b", priority, 20)], current) is True
    assert decide([("root-b", priority, 10), ("root-a", priority, 20)], current) is False

@pytest.mark.parametrize("other_priority", [1, 2, 3, 4])
def test_new_genuinely_urgent_work_can_outrank_old_lower_priority(other_priority):
    assert decide([("root-b", other_priority, 10), ("root-a", 4, 20)], "heal") is True

@pytest.mark.parametrize("current", ["build", "review", "mechanical", "unknown"])
def test_other_root_higher_priority_still_blocks(current):
    assert decide([("root-b", 0, 10)], current) is False

@pytest.mark.parametrize("logical", ["mechanical", "review"])
def test_remote_transport_priority_is_logical_not_siblings(logical):
    rows = [("root-a", 0, 10), ("root-b", 1, 20)]
    assert decide(rows, "remote-glm", logical) is False

@pytest.mark.parametrize("current", ["heal", "build", "review", "mechanical"])
def test_same_root_only_no_competitor_does_not_deadlock(current):
    assert decide([("root-a", 0, 10)], current) is True


def test_exhaustive_priority_and_fifo_reference():
    from itertools import permutations, product
    # Three original roots, all 125 priority assignments, six arrival orders,
    # five current priorities: 3,750 distinct decision cases.
    for priorities in product(range(5), repeat=3):
        for arrivals in permutations(range(3)):
            rows = list(zip(("root-a", "root-b", "root-c"), priorities, arrivals))
            for current_priority, current in enumerate(("heal", "build", "review", "mechanical", "unknown")):
                own = arrivals[0] if priorities[0] == current_priority else float("inf")
                blocked = any(root != "root-a" and
                              (priority < current_priority or
                               (priority == current_priority and arrival < own))
                              for root, priority, arrival in rows)
                assert decide(rows, current) is not blocked, (rows, current)


def test_patch_applies_with_real_method_indentation_and_offset():
    import textwrap
    # Native Broker methods are nested, unlike a dedented function excerpt.
    # The source patch must work in that structure and at a nonzero file offset.
    real_shape = ("# unrelated source\n" * 740 +
                  "class BrokerQueueReference:\n" +
                  textwrap.indent(PREIMAGE.read_text(), "    "))
    with tempfile.TemporaryDirectory(prefix="fabric-queue-offset-") as temporary:
        root = Path(temporary)
        (root / "ext").mkdir()
        target = root / "ext/lease_broker.py"
        target.write_text(real_shape)
        answer = subprocess.run(["git", "apply", str(PATCH)], cwd=root,
                                capture_output=True, text=True, check=False)
        assert answer.returncode == 0, answer.stderr
