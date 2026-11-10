"""Ticker-derived path safety in portfolio.self_directed (CodeQL py/path-injection #23/#24).

The stockdata mark loader used to interpolate the operator-supplied ticker straight into
``vendor/macro/site/stockdata/<TICKER>.json``. These tests pin the allowlist that now guards that
interpolation, and prove the loader itself degrades to None (its pre-existing "no data" contract)
on traversal payloads instead of touching the filesystem.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio import self_directed as sd


# ---------------------------------------------------------------------------
# the sanitizer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("AAPL", "AAPL"),
        ("aapl", "AAPL"),          # normalized
        ("  AAPL  ", "AAPL"),      # stripped
        ("BRK.B", "BRK.B"),        # dotted class shares are legal
        ("BRK-B", "BRK-B"),        # dashed class shares are legal
        ("SPY", "SPY"),
        ("AAPL\n", "AAPL"),        # whitespace edges are normalized away, not rejected
        ("A", "A"),                # 1 char is the floor
        ("ABCDEFGHIJKL", "ABCDEFGHIJKL"),   # 12 chars is the ceiling
    ],
)
def test_safe_ticker_accepts_real_symbols(raw: str, expected: str) -> None:
    assert sd._safe_ticker(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "../../etc/passwd",
        "../../../etc/passwd",
        "a/b.json",
        "a/b",
        "",
        "   ",
        "ABCDEFGHIJKLM",           # 13 chars, over the cap
        "AAPL\x00",                # NUL
        "/etc/passwd",
        "..\\..\\windows",
        "~/.ssh/id_rsa",
        "AAPL;rm -rf /",
        ".",                       # directory component, not a symbol
        "..",
        "AAPL US",                 # internal space
        None,
        123,                       # type confusion
    ],
)
def test_safe_ticker_rejects_everything_else(bad) -> None:
    assert sd._safe_ticker(bad) is None


# ---------------------------------------------------------------------------
# the loader seam — traversal payloads must return None without side effects
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    ["../../etc/passwd", "../../../etc/passwd", "a/b.json", "", "ABCDEFGHIJKLM", ".."],
)
def test_stockdata_price_returns_none_on_traversal_payloads(payload: str) -> None:
    assert sd._stockdata_price(payload) is None


def test_stockdata_price_still_reads_a_valid_ticker(tmp_path: Path, monkeypatch) -> None:
    """The allowlist must not break the legitimate read path."""
    (tmp_path / "AAPL.json").write_text(json.dumps({"tech": {"price": 191.25}}))
    monkeypatch.setattr(sd, "_STOCKDATA_DIR", tmp_path)
    assert sd._stockdata_price("aapl") == pytest.approx(191.25)


def test_stockdata_price_rejects_escape_from_patched_dir(tmp_path: Path, monkeypatch) -> None:
    """A traversal payload can never resolve to a file that lives beside the stockdata dir."""
    secret = tmp_path.parent / "secret.json"
    secret.write_text(json.dumps({"tech": {"price": 42.0}}))
    stockdir = tmp_path / "stockdata"
    stockdir.mkdir()
    monkeypatch.setattr(sd, "_STOCKDATA_DIR", stockdir)
    assert sd._stockdata_price("../secret") is None
    assert sd._stockdata_price("../secret.json") is None
