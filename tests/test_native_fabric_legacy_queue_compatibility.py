"""The new request-scoped implementation must preserve unscoped queue policy."""
from itertools import permutations, product
from pathlib import Path
import runpy
from types import SimpleNamespace


def test_legacy_priority_fifo_compatibility_all_3750_cases():
    data = runpy.run_path(str(Path(__file__).with_name('test_native_fabric_request_waiters.py')))
    choose = data['Broker']._front_of_queue
    classes = ('heal', 'build', 'review', 'mechanical', 'unknown')
    checked = 0
    for priorities in product(range(5), repeat=3):
        for arrivals in permutations(range(3)):
            rows = [{'id': f'legacy-{i}', 'orchestrator_id': root,
                     'priority': priority, 'enqueued_at': arrival}
                    for i, (root, priority, arrival) in enumerate(
                        zip(('root-a', 'root-b', 'root-c'), priorities, arrivals))]
            rows.sort(key=lambda row: (row['priority'], row['enqueued_at']))
            owner = SimpleNamespace(_waiters=lambda conn, pool: rows)
            for current_priority, current_class in enumerate(classes):
                own_time = arrivals[0] if priorities[0] == current_priority else float('inf')
                blocked = any(row['orchestrator_id'] != 'root-a' and (
                    row['priority'] < current_priority or
                    (row['priority'] == current_priority and row['enqueued_at'] < own_time))
                    for row in rows)
                assert choose(owner, None, 'synthetic', 'root-a', current_class) is not blocked
                checked += 1
    assert checked == 3750
