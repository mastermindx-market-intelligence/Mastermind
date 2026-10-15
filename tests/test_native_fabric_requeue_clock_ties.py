"""Changed request demand must lose its old FIFO rank even if the clock ties."""
from pathlib import Path
import runpy

import pytest

DATA = runpy.run_path(str(Path(__file__).with_name('test_native_fabric_request_waiters.py')))


@pytest.mark.parametrize('changed', ['priority', 'host'])
def test_requeued_demand_loses_old_fifo_position_even_at_same_clock_tick(changed):
    broker = DATA['Broker']()
    broker.now = lambda: 1000.0
    broker.provider_name = lambda value: value
    broker.pool_cap = lambda _: 12
    conn = DATA['database']()
    state = (broker, conn, [1000.0])
    enqueue, front, rows = DATA['enqueue'], DATA['front'], DATA['rows']
    try:
        # Both initial requests and the later requeue deliberately share a clock
        # value. Changing resource/priority demand must refresh FIFO insertion.
        first_job = 'heal' if changed == 'priority' else 'review'
        enqueue(state, 'a', first_job, host='old-host')
        enqueue(state, 'b', 'review', root='root-b')
        enqueue(state, 'a', 'review', host='new-host' if changed == 'host' else 'old-host')
        assert not front(state, 'a', 'review')
        assert front(state, 'b', 'review', root='root-b')
        assert len(rows(state)) == 2
    finally:
        conn.close()
