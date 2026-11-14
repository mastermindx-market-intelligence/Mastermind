import importlib.util
from unittest.mock import patch
from pathlib import Path
import pytest

@pytest.fixture
def feed():
    spec = importlib.util.spec_from_file_location("isolated_yahoo_feed", Path(__file__).resolve().parents[1] / "data_layer" / "yahoo_feed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_failed_start_leaves_background_refresh_retryable(feed):
    with patch.object(feed.threading.Thread, "start", side_effect=RuntimeError("can't start new thread")):
        feed.warm(["AAPL"], background=True)
    assert feed._INFLIGHT == set()
    with patch.object(feed.threading, "Thread") as thread:
        feed.warm(["AAPL"], background=True)
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

def test_failed_start_preserves_other_pending_symbols(feed):
    feed._INFLIGHT.add("MSFT")
    with patch.object(feed.threading.Thread, "start", side_effect=RuntimeError("can't start new thread")):
        feed.warm(["AAPL", "MSFT"], background=True)
    assert feed._INFLIGHT == {"MSFT"}

def test_success_still_deduplicates_before_worker_runs(feed):
    with patch.object(feed.threading, "Thread") as thread:
        feed.warm(["AAPL"], background=True)
        feed.warm(["AAPL"], background=True)
        thread.assert_called_once()
    assert feed._INFLIGHT == {"AAPL"}

@pytest.mark.parametrize('sibling_kind', ['background', 'synchronous'])
def test_failed_start_cannot_wait_behind_sibling_download(feed, sibling_kind):
    import threading
    from types import SimpleNamespace

    attempting = threading.Event()
    downloading = threading.Event()
    release_download = threading.Event()
    returned = threading.Event()
    errors = []
    fetched = []
    feed._reset_if_stale()
    feed._INFLIGHT.add('MSFT')

    def fetch(want):
        fetched.append(want)
        downloading.set()
        assert release_download.wait(3)
        feed._CACHE['MSFT'] = 100.0

    feed._fetch_and_cache = fetch

    def sibling_call():
        attempting.set()
        if sibling_kind == 'background':
            feed._bg_fetch(['MSFT'])
        else:
            feed.warm(['MSFT'])

    sibling = threading.Thread(target=sibling_call)

    class RefusedStart:
        def start(self):
            sibling.start()
            assert attempting.wait(1)
            # The old implementation permits the sibling to enter provider I/O
            # here. The repair keeps it outside until rollback is complete.
            downloading.wait(0.1)
            raise RuntimeError("can't start new thread")

    feed.threading = SimpleNamespace(Thread=lambda **kwargs: RefusedStart())

    def caller():
        try:
            feed.warm(['AAPL'], background=True)
        except Exception as exc:
            errors.append(exc)
        finally:
            returned.set()

    first = threading.Thread(target=caller)
    first.start()
    try:
        assert downloading.wait(2)
        assert returned.wait(0.2), 'background caller waited behind sibling I/O'
        assert not errors
        assert 'AAPL' not in feed._INFLIGHT
        assert 'MSFT' in feed._INFLIGHT
    finally:
        release_download.set()
        first.join(3)
        sibling.join(3)
    assert not first.is_alive() and not sibling.is_alive()
    assert fetched == [['MSFT']]
    assert feed._CACHE['MSFT'] == 100.0
    with patch.object(feed.threading, 'Thread') as thread:
        feed.warm(['AAPL'], background=True)
        thread.return_value.start.assert_called_once()


def test_background_lock_miss_never_starts_or_reserves(feed):
    feed._LOCK.acquire()
    try:
        with patch.object(feed.threading, 'Thread') as thread:
            feed.warm(['AAPL'], background=True)
            thread.assert_not_called()
        assert not feed._INFLIGHT
    finally:
        feed._LOCK.release()


def test_real_successful_worker_runs_after_launch_lock_release(feed):
    import threading
    import time
    from types import SimpleNamespace

    downloaded = threading.Event()
    workers = []

    def fetch(want):
        assert want == ['AAPL']
        feed._CACHE['AAPL'] = 100.0
        feed._TS['AAPL'] = time.monotonic()
        downloaded.set()

    def factory(**kwargs):
        worker = threading.Thread(**kwargs)
        workers.append(worker)
        return worker

    feed._fetch_and_cache = fetch
    feed.threading = SimpleNamespace(Thread=factory)
    feed.warm(['AAPL'], background=True)
    try:
        assert downloaded.wait(2)
    finally:
        for worker in workers:
            worker.join(3)
    assert all(not worker.is_alive() for worker in workers)
    assert not feed._INFLIGHT
    assert feed.price_cached('AAPL') == 100.0
    feed.warm(['AAPL'], background=True)
    assert len(workers) == 1
