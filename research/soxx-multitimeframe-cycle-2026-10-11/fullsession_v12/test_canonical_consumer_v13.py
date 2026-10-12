"""CLI containment tests: never authorize a new vendor fetch or market publication."""
import contextlib,io,types,sys,unittest
from pathlib import Path
from unittest.mock import patch
from test_tiingo_l1_v13 import projection,RAW_SHA,RECEIPT_ID,CUTOFF
from tiingo_canonical_consumer_v13 import parser,run,main

def args(**extras):
    base=["--archive-root","/Volumes/Mastermind/market-data/tiingo",
      "--source-day","2026-10-11","--source-sha",RAW_SHA,
      "--symbol","AMD","--observed-before-utc",CUTOFF,
      "--night-start-et","2026-10-08"]
    namespace=parser().parse_args(base)
    for name,value in extras.items():setattr(namespace,name,value)
    return namespace

class SourceCLI(unittest.TestCase):
    def test_bad_sha_refused_before_importing_data_owner(self):
        with self.assertRaises(ValueError):run(args(source_sha="invalid"))
    def test_lowercase_symbol_refused_before_import(self):
        with self.assertRaises(ValueError):run(args(symbol="amd"))
    def test_unbounded_night_list_refused(self):
        with self.assertRaises(ValueError):run(args(night_start_et=["2026-10-08"]*15))
    def test_non_authenticating_reader_is_exact_owner(self):
        calls=[]
        reader=types.ModuleType("lib.dataos.tiingo_reader")
        def read(source,day,sha,**kwargs):
            calls.append((source,day,sha,kwargs))
            return types.SimpleNamespace(source="boats-bars",rows=(projection(),))
        reader.read_research_view=read
        lib=types.ModuleType("lib");lib.__path__=[]
        dataos=types.ModuleType("lib.dataos");dataos.__path__=[]
        with patch.dict(sys.modules,{"lib":lib,"lib.dataos":dataos,"lib.dataos.tiingo_reader":reader}):
            report=run(args())
        self.assertEqual(report["source_rows"],1)
        self.assertEqual(report["market_data_rows_emitted"],0)
        self.assertFalse(report["actual_quote_fills_proven"])
        self.assertFalse(report["point_in_time_eligible"])
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0],"boats-bars")
        self.assertEqual(calls[0][3]["purpose"],"INSPECTION")
        self.assertTrue(calls[0][3]["check_mount"])
        self.assertEqual(calls[0][3]["max_rows"],2000)

if __name__=="__main__":unittest.main(verbosity=2)