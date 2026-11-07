"""End-to-end synthetic fixture: CLI I/O, not empirical performance proof."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run import main
from test_engine import bar_rows, pattern


class Pipeline(unittest.TestCase):
    def test_run_with_qualified_shape_synthetic_data(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            days = list(pd.bdate_range(end="2026-10-30", periods=75).date)
            rows = []
            for i, date in enumerate(days):
                for name, slope, price in (("SPY", .0005, 500), ("A", .005, 60),
                                           ("B", -.0001, 50), ("C", .002, 55)):
                    rows.append({"date": str(date), "symbol": name,
                                 "close": price*(1+slope)**i, "volume": 1000000})
            pd.DataFrame(rows).to_csv(base / "daily.csv", index=False)
            pd.DataFrame([{"symbol": s, "start_date": str(days[0]), "end_date": ""}
                          for s in ("A", "B", "C")]).to_csv(base / "membership.csv", index=False)
            bar_rows(pattern()).to_csv(base / "bars.csv", index=False)
            status = main(["--daily", str(base/"daily.csv"),
                           "--membership", str(base/"membership.csv"),
                           "--bars", str(base/"bars.csv"),
                           "--out", str(base/"report.json"),
                           "--min-universe", "3", "--min-adv", "1", "--rs-top", "0.34"])
            self.assertEqual(status, 0)
            report = json.loads((base / "report.json").read_text())
            self.assertEqual(report["metrics"]["pivot"]["resolved"], 1)
            self.assertEqual(report["empirical_strategy_edge_verdict"], "NOT_ESTABLISHED")
            self.assertFalse(report["performance_is_empirically_validated"])
            self.assertEqual(len(report["input_sha256"]["bars"]), 64)


if __name__ == "__main__":
    unittest.main()
