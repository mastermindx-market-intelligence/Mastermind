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
