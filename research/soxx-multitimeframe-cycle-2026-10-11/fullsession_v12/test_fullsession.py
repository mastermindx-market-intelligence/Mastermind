import unittest
from datetime import datetime, timezone, timedelta
UTC=timezone.utc
from zoneinfo import ZoneInfo
from fullsession import (
    normalize_alpaca, normalize_tiingo, normalize_terminal_display,
    classify_session, trade_date, stitch, aggregates, asof_signal,
    quote_decision, Bar, Quote, provenance_summary, coverage)

ET=ZoneInfo('America/New_York')
def bar(t, source='alpaca-boats',basis='split', minutes=30):
    return Bar(symbol='SOXX',utc=datetime.fromisoformat(t.replace('Z','+00:00')),
        minutes=minutes,open=100.,high=102.,low=99.,close=101.,volume=1,
        source=source,basis=basis)

class FullSessionConformance(unittest.TestCase):
    def test_alpaca_boats_excludes_premarket(self):
        payload={'bars':{'SOXX':[
          {'t':'2026-10-08T02:00:00Z','o':100,'h':101,'l':99,'c':100.5,'v':15},
          {'t':'2026-10-08T08:30:00Z','o':100,'h':101,'l':99,'c':100.5,'v':15} ]}}
        out=normalize_alpaca(payload,'SOXX',30)
        self.assertEqual(len(out),1)
        self.assertEqual(classify_session(out[0].utc),'overnight')
    def test_tiingo_boats_is_not_consolidated_daytime(self):
        payload=[{'date':'2026-10-08T02:00:00Z','open':100,'high':103,'low':99,'close':102},
          {'date':'2026-10-08T08:00:00Z','open':100,'high':103,'low':99,'close':102}]
        out=normalize_tiingo(payload,'SOXX',30)
        self.assertEqual(len(out),1)
        self.assertIsNone(out[0].volume)
    def test_rejects_nonfinite_bad_bar(self):
        payload={'bars':{'SOXX':[{'t':'2026-10-08T02:00:00Z','o':100,'h':101,'l':99,'c':float('nan'),'v':0}]}}
        with self.assertRaises(ValueError):normalize_alpaca(payload,'SOXX',30)
    def test_rejects_pagination_without_complete_history(self):
        with self.assertRaises(ValueError):normalize_alpaca({'bars':{'SOXX':[]},'next_page_token':'next'},'SOXX',30)
    def test_overnight_trade_date_and_sunday(self):
        sunday=datetime(2026,10,11,20,30,tzinfo=ET).astimezone(timezone.utc)
        self.assertEqual(trade_date(sunday).isoformat(),'2026-10-12')
        self.assertEqual(classify_session(sunday),'overnight')
        self.assertEqual(classify_session(datetime(2026,10,10,22,tzinfo=ET)), 'closed')
        self.assertEqual(classify_session(datetime(2026,10,9,23,tzinfo=ET)), 'closed')
    def test_dst_november_overnight(self):
        before=datetime(2026,11,1,1,30,tzinfo=ET,fold=0).astimezone(timezone.utc)
        after=datetime(2026,11,1,1,30,tzinfo=ET,fold=1).astimezone(timezone.utc)
        self.assertNotEqual(before,after)
        self.assertEqual(classify_session(before),'closed')
        self.assertEqual(classify_session(after),'closed')
    def test_early_close_13_becomes_post(self):
        d=datetime(2025,12,24,13,30,tzinfo=ET)
        self.assertEqual(classify_session(d,{'2025-12-24':13*60}),'postmarket')
        self.assertEqual(classify_session(d),'rth')
    def test_terminal_display_epoch_not_utc_price_time(self):
        fake_utc=int(datetime(2026,10,8,9,30,tzinfo=timezone.utc).timestamp())
        out=normalize_terminal_display([[fake_utc,100,102,99,101,1000]],'SOXX',30,basis='split')
        self.assertEqual(out[0].utc.astimezone(ET).hour,9)
        self.assertEqual(out[0].utc.astimezone(ET).minute,30)
        self.assertEqual(classify_session(out[0].utc),'rth')
    def test_rejects_overnight_display_epoch_without_utc(self):
        fake=int(datetime(2026,11,1,1,30,tzinfo=timezone.utc).timestamp())
        with self.assertRaises(ValueError):normalize_terminal_display([[fake,100,101,99,100,1]],'SOXX',30)
    def test_stitch_rejects_mixed_adjustments(self):
        with self.assertRaises(ValueError):stitch([bar('2026-10-08T02:00:00Z')], [bar('2026-10-08T08:00:00Z',basis='raw',source='massive')])
    def test_stitch_rejects_overlap_instead_of_silent_vendor_winner(self):
        with self.assertRaises(ValueError):stitch([bar('2026-10-08T02:00:00Z')],[bar('2026-10-08T02:00:00Z',source='massive')])
    def test_no_bars_cannot_prove_24h_coverage(self):
        self.assertFalse(coverage([],datetime(2026,10,7,20,tzinfo=ET),30,48)['complete'])
    def test_full_4h_overnight_aggregates(self):
        start=datetime(2026,10,7,20,tzinfo=ET).astimezone(timezone.utc)
        b=[]
        for i in range(8):
            stamp=(start+timedelta(minutes=30*i)).isoformat()
            b.append(bar(stamp))
        ag=aggregates(b,240)
        self.assertEqual(len(ag),1)
        self.assertTrue(ag[0]['complete'])
        self.assertEqual(ag[0]['observed'],8)
        self.assertEqual(ag[0]['sessions'],['overnight'])
    def test_one_missing_30m_bar_invalidates_4h_signal(self):
        start=datetime(2026,10,7,20,tzinfo=ET).astimezone(timezone.utc)
        b=[bar((start+timedelta(minutes=30*i)).isoformat()) for i in [0,1,2,3,4,5,7]]
        ag=aggregates(b,240)
        self.assertEqual(len(ag),1)
        self.assertFalse(ag[0]['complete'])
        self.assertEqual(ag[0]['observed'],7)
        self.assertIsNone(asof_signal(ag,start+timedelta(hours=4)))
    def test_mixed_market_sessions_are_flagged(self):
        start=datetime(2026,10,8,8,tzinfo=ET).astimezone(timezone.utc)
        b=[bar((start+timedelta(minutes=30*i)).isoformat(),source='massive') for i in range(6)]
        ag=aggregates(b,180)[0]
        self.assertIn('premarket',ag['sessions'])
        self.assertIn('rth',ag['sessions'])
    def test_terminal_boats_et_wall_epoch_requires_available_venue_evidence(self):
        stamp=int(datetime(2026,10,7,20,30,tzinfo=UTC).timestamp())
        rows=[[stamp,100,101,99,100.5,110]]
        with self.assertRaises(ValueError):normalize_terminal_display(rows,'SOXX',30,source='alpaca-boats')
        data=normalize_terminal_display(rows,'SOXX',30,source='alpaca-boats',overnight_evidence='available')
        self.assertEqual(data[0].utc,datetime(2026,10,8,0,30,tzinfo=UTC))
        self.assertEqual(classify_session(data[0].utc),'overnight')
    def test_asof_rejects_completely_unobserved_four_hour_bucket(self):
        start=datetime(2026,10,7,20,tzinfo=ET).astimezone(UTC)
        # No prints at all in the middle 2-hour aggregate; no empty aggregate was emitted.
        b=[bar((start+timedelta(minutes=30*i)).isoformat()) for i in list(range(0,4))+list(range(8,12))]
        ag=aggregates(b,120)
        self.assertEqual(len(ag),2)
        self.assertIsNone(asof_signal(ag,start+timedelta(hours=6)))
    def test_quote_rejects_crossed_stale_wide(self):
        t=datetime.fromisoformat('2026-10-08T02:00:00Z')
        with self.assertRaises(ValueError):Quote('SOXX',t,101,100,100,100,'boats')
        for q in [Quote('SOXX',t-timedelta(seconds=90),100,100.1,100,100,'boats'),
                  Quote('SOXX',t,100,105,100,100,'boats')]:
            self.assertNotEqual(quote_decision([q],t,'buy',101,10,symbol='SOXX')['status'],'quote_marketable_unfilled')
    def test_quote_marketable_not_proven_fill(self):
        t=datetime.fromisoformat('2026-10-08T02:00:00Z')
        q=Quote('SOXX',t,100.,100.2,100,100,'boats')
        self.assertEqual(quote_decision([q],t,'buy',100.3,10,symbol='SOXX')['status'],'quote_marketable_unfilled')
        self.assertEqual(quote_decision([q],t,'buy',100.1,10,symbol='SOXX')['status'],'limit_not_marketable')
    def test_no_quote_never_invents_execution(self):
        t=datetime.fromisoformat('2026-10-08T02:00:00Z')
        self.assertEqual(quote_decision([],t,'buy',100.3,10,symbol='SOXX')['status'],'quote_unavailable')
    def test_wrong_symbol_quote_is_unavailable(self):
        t=datetime.fromisoformat('2026-10-08T02:00:00Z')
        q=Quote('NVDA',t,100,100.1,100,100,'boats')
        self.assertEqual(quote_decision([q],t,'buy',101,10,symbol='SOXX')['status'],'quote_unavailable')
    def test_asof_does_not_reuse_old_signal_after_missing_session_bar(self):
        start=datetime(2026,10,7,20,tzinfo=ET).astimezone(timezone.utc)
        b=[bar((start+timedelta(minutes=30*i)).isoformat()) for i in range(16) if i!=11]
        ag=aggregates(b,120)
        self.assertTrue(ag[0]['complete'])
        self.assertFalse(ag[2]['complete'])
        self.assertIsNone(asof_signal(ag,start+timedelta(hours=8)))
    def test_provenance_marks_missing_night(self):
        t=datetime.fromisoformat('2026-10-08T02:00:00Z')
        x=provenance_summary([bar('2026-10-08T02:00:00Z')])
        self.assertEqual(x['overnight_rows'],1)
        self.assertFalse(x['whole_24h_proven'])

if __name__=='__main__':unittest.main(verbosity=2)