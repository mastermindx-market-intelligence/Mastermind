"""Preserve frozen research economics while making data/clock types explicit.

These tests use published derived evidence and synthetic clock/CSV fixtures only.
No historical strategy, private price source, provider, or security guard is changed.
Pins below were recorded from PR1338 at 7ec0207a before the representation repair.
"""
from __future__ import annotations
import ast
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parents[1]
STUDY = ROOT / "research/soxx-multitimeframe-cycle-2026-10-11/terminal_finepivot_v14"
PAIR_SEMANTIC_SHA = "ab43a602f08358ecbd9fbd7d53372a48f99779be9d4b54618d800936816f1c30"
METADATA_SHA = "3a243907f89b3930357987086303080fd5abad1e2c79fd58da01a4d8850702c8"


def _isolated_function(name, **namespace):
    # Extract the pure helper, not the research module's private-data imports.
    tree = ast.parse((STUDY / "peer_v14.py").read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1, f"explicit research helper missing: {name}"
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, "peer_v14.py", "exec"), namespace)
    return namespace[name]


def test_asset_metadata_retains_identical_frozen_bytes():
    path = STUDY / "ASSET_SOURCE_METADATA.json"
    assert path.is_file(), "financial-asset metadata must have an unambiguous domain name"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == METADATA_SHA


def test_pair_rows_and_order_are_unchanged_and_episode_keys_are_strings():
    path = STUDY / "peer_pairs_v14.csv"
    with path.open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) - 1 == 176
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    assert digest == PAIR_SEMANTIC_SHA
    episode_col = rows[0].index("episode")
    for record, physical_line in zip(rows[1:], path.read_text().splitlines()[1:]):
        assert '"' + record[episode_col] + '"' in physical_line


def test_clock_expression_is_equivalent_at_every_minute_and_subminute_boundary():
    predicate = _isolated_function("_is_rth_15m_start", dt=dt)
    tz = ZoneInfo("America/New_York")
    for month, day in ((1, 15), (3, 8), (11, 1)):
        for minute in range(24 * 60):
            for second in (0, 29, 59):
                stamp = dt.datetime(2026, month, day, minute // 60, minute % 60,
                                    second, 123456, tzinfo=tz)
                prior = 570 <= stamp.hour * 60 + stamp.minute < 960 and stamp.minute % 15 == 0
                assert predicate(stamp) is prior


def test_pair_writer_quotes_strings_but_retains_numeric_types(tmp_path):
    save = _isolated_function("_save_episode_pairs", csv=csv, BASE=tmp_path)
    rows = [{"episode": "3h_medium:1:468:470", "baseline": -1.25, "test": 2.5,
             "lift": 3.75, "saved_loser": True}]
    save("pairs.csv", rows)
    text = (tmp_path / "pairs.csv").read_text()
    assert '"3h_medium:1:468:470"' in text
    assert ",3.75," in text
    with (tmp_path / "pairs.csv").open(newline="") as stream:
        parsed = list(csv.DictReader(stream))
    assert parsed == [{k: str(v) for k, v in rows[0].items()}]
    save("empty.csv", [])
    assert not (tmp_path / "empty.csv").exists()
