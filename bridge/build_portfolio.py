"""The write-back bridge (bot side): emit the portfolio.v1 contract.

Writes data/portfolio/latest.json (machine hub) + site/portfolio.json (page-facing).
In production a macro-repo build_portfolio.py (cloned from build_transmission.py)
renders site/portfolio.html from this same JSON; here we own the contract.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import bot  # noqa: F401

_ROOT = Path(__file__).resolve().parent.parent


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Durably replace one published contract without exposing a partial document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # Atomic replacement still prevents a partial contract where dir fsync is unavailable.
            pass
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def prepare(payload: dict, portfolio_id: str | None = None) -> tuple[dict, bytes]:
    """Return the incumbent contract's exact paths/bytes without filesystem effects."""
    from portfolio import registry
    pid = portfolio_id or registry.DEFAULT_ID
    payload = {"schema": "portfolio.v1", "is_paper": True, "portfolio_id": pid, **payload,
               "disclaimer": "Paper-only / display-only. Accountability, not alpha. Not investment advice.",
               "zh": {"disclaimer": "仅纸面/仅展示；从不自动执行。"}}
    base = registry.data_dir(portfolio_id)
    paths = {"hub": str(base / "latest.json"), "site": str(base / "portfolio.json")}
    encoded = json.dumps(payload, indent=2, default=str, ensure_ascii=False).encode("utf-8")
    return paths, encoded


def write(payload: dict, portfolio_id: str | None = None) -> dict:
    """Write both existing portfolio contracts and return their paths."""
    paths, encoded = prepare(payload, portfolio_id)
    for path in paths.values():
        _atomic_write_bytes(Path(path), encoded)
    return paths
