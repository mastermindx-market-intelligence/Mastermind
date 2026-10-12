import json,subprocess,sys,tempfile,unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).parent
ET=ZoneInfo('America/New_York')

class CLIEndToEnd(unittest.TestCase):
    def fixture(self, tmp):
        start=datetime(2026,10,6,20,tzinfo=ET).astimezone(timezone.utc)
        overnight=[];day=[]
        for i in range(48):
            ts=(start+timedelta(minutes=30*i))
            local=ts.astimezone(ET)
            if local.hour>=20 or local.hour<4:
                overnight.append({'t':ts.isoformat(),'o':100,'h':101,'l':99,'c':100.5,'v':10})
            else:
                fake=int(datetime(local.year,local.month,local.day,local.hour,local.minute,tzinfo=timezone.utc).timestamp())
                day.append([fake,100,101,99,100.5,100])
        p=tmp/'night.json';p.write_text(json.dumps({'bars':{'SOXX':overnight}}))
        q=tmp/'day.json';q.write_text(json.dumps({'bars':day}))
        return p,q
    def call(self, tmp,night=True):
        p,q=self.fixture(tmp)
        out=tmp/'out'
        argv=[sys.executable,str(ROOT/'ingest_v12.py'),
            '--symbol','SOXX','--daytime-file',str(q),
            '--overnight-evidence','available' if night else 'not_configured',
            '--daytime-format','terminal','--interval','30','--basis','split','--out',str(out)]
        if night:argv+=['--overnight-file',str(p),'--overnight-format','alpaca']
        result=subprocess.run(argv,capture_output=True,text=True)
        return result,out
    def test_full_fixture_has_24h_2h_3h_4h_no_backdating(self):
        with tempfile.TemporaryDirectory() as d:
            result,out=self.call(Path(d),True)
            self.assertEqual(result.returncode,0,result.stderr)
            r=json.loads((out/'report.json').read_text())
            self.assertEqual(r['coverage']['overnight_bars'],16)
            self.assertEqual(r['coverage']['daytime_bars'],32)
            self.assertEqual(r['coverage']['complete_full_trading_days'],1)
            self.assertTrue(r['full_session_research_ready'])
            self.assertFalse(r['backtest_eligible_full_year'])
            self.assertFalse(r['quote_execution_replay_ready'])
            self.assertEqual(r['complete_aggregate_bars'],{'120':12,'180':8,'240':6})
            self.assertEqual(r['historical_quote_fills_claimed'],0)
    def test_absent_night_does_not_fabricate_24h(self):
        with tempfile.TemporaryDirectory() as d:
            result,out=self.call(Path(d),False)
            self.assertEqual(result.returncode,0,result.stderr)
            r=json.loads((out/'report.json').read_text())
            self.assertFalse(r['full_session_research_ready'])
            self.assertEqual(r['coverage']['complete_full_trading_days'],0)
            self.assertEqual(r['complete_aggregate_bars'],{'120':0,'180':0,'240':0})
    def test_unentitled_or_unavailable_night_cannot_be_labeled_available(self):
        with tempfile.TemporaryDirectory() as d:
            p,q=self.fixture(Path(d));out=Path(d)/'out'
            cmd=[sys.executable,str(ROOT/'ingest_v12.py'),'--symbol','SOXX',
                 '--daytime-file',str(q),'--daytime-format','terminal',
                 '--overnight-file',str(p),'--overnight-format','alpaca',
                 '--overnight-evidence','not_configured','--interval','30',
                 '--basis','split','--out',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse((out/'report.json').exists())

if __name__=='__main__':unittest.main()