"""Adversarial first tests for Data OS BOATS L1 read-only research consumption."""
import unittest
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from fullsession import Bar,classify_session,stitch,aggregates
from tiingo_l1_v13 import l1_to_bars,audit_overnight_nights,resample_complete_30m

UTC=timezone.utc
ET=ZoneInfo("America/New_York")
RAW_SHA="a"*64
RECEIPT_ID="b"*64
CUTOFF="2026-10-11T22:00:00Z"
START=datetime(2026,10,9,0,0,tzinfo=UTC)  # Thursday Oct 8, 20:00 EDT

def projection(i=0,**overrides):
    at=START+timedelta(minutes=i)
    row={
        "source_vendor":"tiingo","dataset_source":"boats-bars",
        "source_view_schema":"mastermind.tiingo.research_views.v2",
        "source_sha256":RAW_SHA,"source_receipt_id":RECEIPT_ID,
        "source_observed_at_utc":"2026-10-11T12:00:00Z",
        "source_rights_admitted":False,"pit_backtest_eligible":False,
        "canonical_price_basis_admitted":False,"vendor_historical_availability":"UNVERIFIED",
        "venue":"BOATS","venue_scope":"single_ats","session":"overnight",
        "is_nbbo":False,"executable_price_proven":False,
        "ticker_vendor":"AMD","bar_at_vendor":at.isoformat(),
        "source_date_label":at.date().isoformat(),
        "requested_resample_frequency":"1min",
        "vendor_open":100.0+i/10000,"vendor_high":101.0+i/10000,
        "vendor_low":99.0+i/10000,"vendor_close":100.5+i/10000,
        "vendor_volume":10.0,"volume_available":True,
    }
    row.update(overrides)
    return row

def convert(rows):
    return l1_to_bars(rows,symbol="AMD",expected_sha=RAW_SHA,
                      receipt_id=RECEIPT_ID,observed_before_utc=CUTOFF)

class DataOSL1Contract(unittest.TestCase):
    def test_one_verified_bar_and_lineage(self):
        bars,meta=convert([projection()])
        self.assertEqual(len(bars),1)
        self.assertEqual(bars[0].symbol,"AMD")
        self.assertEqual(bars[0].volume,10)
        self.assertEqual(bars[0].basis,"raw")
        self.assertEqual(bars[0].source,"tiingo-boats")
        self.assertEqual(classify_session(bars[0].utc),"overnight")
        self.assertEqual(meta["source_sha256"],RAW_SHA)
        self.assertEqual(meta["receipt_id"],RECEIPT_ID)
        self.assertFalse(meta["pit_backtest_eligible"])
        self.assertFalse(meta["historical_quote_fills_proven"])
        self.assertFalse(meta["redistribution_approved"])

    def test_refuse_alias_mismatch(self):
        with self.assertRaises(ValueError):convert([projection(ticker_vendor="AAPL")])
    def test_refuse_wrong_venue_or_daytime(self):
        with self.assertRaises(ValueError):convert([projection(venue="IEX")])
        with self.assertRaises(ValueError):convert([projection(bar_at_vendor="2026-10-09T14:30:00Z")])
    def test_refuse_wrong_receipt_or_source_sha(self):
        with self.assertRaises(ValueError):convert([projection(source_receipt_id="c"*64)])
        with self.assertRaises(ValueError):convert([projection(source_sha256="c"*64)])
    def test_refuse_pit_or_redistribution_promotions(self):
        with self.assertRaises(ValueError):convert([projection(pit_backtest_eligible=True)])
        with self.assertRaises(ValueError):convert([projection(source_rights_admitted=True)])
        with self.assertRaises(ValueError):convert([projection(executable_price_proven=True)])
    def test_refuse_late_vintage(self):
        with self.assertRaises(ValueError):convert([projection(source_observed_at_utc="2026-10-12T00:00:00Z")])
    def test_refuse_duplicate_timestamps(self):
        with self.assertRaises(ValueError):convert([projection(),projection()])
    def test_refuse_noninteger_volume_and_unrepresentable_amount(self):
        for v in (True,10.1,float(2**53+2),-1.0):
            with self.subTest(v=v):
                with self.assertRaises(ValueError):convert([projection(vendor_volume=v)])
    def test_refuse_mismatched_source_frequency_and_split_basis(self):
        with self.assertRaises(ValueError):convert([projection(requested_resample_frequency="30min")])
        with self.assertRaises(ValueError):l1_to_bars([projection()],symbol="AMD",expected_sha=RAW_SHA,
                                     receipt_id=RECEIPT_ID,observed_before_utc=CUTOFF,basis="split")
    def test_missing_volume_kept_unknown_not_zero(self):
        bars,_=convert([projection(vendor_volume=None,volume_available=False)])
        self.assertIsNone(bars[0].volume)
    def test_complete_genuine_night_480_minutes_to_16_halfhours(self):
        bars,meta=convert([projection(i) for i in range(480)])
        windows=audit_overnight_nights(bars,night_starts_et=["2026-10-08"])
        self.assertEqual(len(windows),1)
        self.assertEqual(windows[0]["observed_minutes"],480)
        self.assertEqual(windows[0]["missing_minutes"],0)
        self.assertTrue(windows[0]["complete_overnight"])
        half,buckets=resample_complete_30m(bars)
        self.assertEqual(len(half),16)
        self.assertEqual(buckets["complete_30m"],16)
        self.assertEqual(buckets["skipped_partial_30m"],0)
        self.assertEqual(half[0].utc,START)
        self.assertEqual(half[0].volume,300)
        self.assertEqual(half[0].basis,"raw")
        self.assertEqual(half[-1].utc,START+timedelta(minutes=450))
        self.assertTrue(all(classify_session(b.utc)=="overnight" for b in half))
        self.assertFalse(meta["full_24h_session_proven"])
    def test_missing_one_minute_refuses_30m_bucket_and_full_night(self):
        bars,_=convert([projection(i) for i in range(480) if i!=100])
        nights=audit_overnight_nights(bars,night_starts_et=["2026-10-08"])
        self.assertFalse(nights[0]["complete_overnight"])
        self.assertEqual(nights[0]["missing_minutes"],1)
        half,counts=resample_complete_30m(bars)
        self.assertEqual(len(half),15)
        self.assertEqual(counts["skipped_partial_30m"],1)
    def test_no_full_session_claim_from_night_only(self):
        bars,_=convert([projection(i) for i in range(480)])
        half,_=resample_complete_30m(bars)
        all_bars=stitch([],half)
        ag=aggregates(all_bars,240)
        self.assertEqual(len(ag),2)
        self.assertTrue(all(z["complete"] for z in ag))
        self.assertEqual(sum(x.minutes for x in all_bars),480)
        self.assertLess(sum(x.minutes for x in all_bars),1440)
    def test_reject_mixed_dates_duplicate_night_requests(self):
        bars,_=convert([projection()])
        with self.assertRaises(ValueError):audit_overnight_nights(bars,night_starts_et=["2026-10-08","2026-10-08"])
    def test_reject_malformed_bar_values(self):
        with self.assertRaises(ValueError):convert([projection(vendor_low=120.0)])
        with self.assertRaises(ValueError):convert([projection(vendor_open=True)])

if __name__=="__main__":unittest.main(verbosity=2)