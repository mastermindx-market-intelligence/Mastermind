import hashlib
import json
import unittest
from research.apmem_shadow.phase2.tiingo_adapter import adapt_eod_capture


def source():
    rows=[{'date':f'2026-11-{d:02d}T00:00:00.000Z','open':100.,'high':101.,'low':99.,
           'close':100.,'divCash':0.,'splitFactor':1.,'volume':1000} for d in (11,12,13)]
    return rows


def capture(rows):
    raw=json.dumps(rows).encode()
    rec={'instrument':'QQQ','raw_sha256':hashlib.sha256(raw).hexdigest(),'rows':len(rows),
         'captured_at':'2026-11-14T01:50:00+00:00','historical_first_availability':None,
         'request_path':'/tiingo/daily/QQQ/prices?endDate=2026-11-13&startDate=2010-01-01'}
    return raw,rec


class TiingoAdapterTests(unittest.TestCase):
    def test_exact_raw_prices_and_cash(self):
        rows=source();rows[1]['divCash']=.5;raw,rec=capture(rows)
        p,r=adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
        self.assertEqual(p.close.tolist(),[100.]*3);self.assertEqual(p.dividends.tolist(),[0,.5,0])
        self.assertFalse(r['price_or_distribution_imputation']);self.assertEqual(p.stock_splits.sum(),0)
    def test_digest_refused(self):
        raw,rec=capture(source());rec['raw_sha256']='a'*64
        with self.assertRaises(ValueError):adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
    def test_source_identity_refused(self):
        raw,rec=capture(source());rec['instrument']='SPY'
        with self.assertRaises(ValueError):adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
    def test_origin_request_refused(self):
        raw,rec=capture(source());rec['request_path']=rec['request_path'].replace('2026-11-13','2026-11-12')
        with self.assertRaises(ValueError):adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
    def test_nan_close_refused(self):
        rows=source();rows[-1]['close']=float('nan');raw,rec=capture(rows)
        with self.assertRaises(ValueError):adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
    def test_split_refused(self):
        rows=source();rows[-1]['splitFactor']=2.;raw,rec=capture(rows)
        with self.assertRaises(ValueError):adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
    def test_duplicate_date_refused(self):
        rows=source();rows[1]['date']=rows[0]['date'];raw,rec=capture(rows)
        with self.assertRaises(ValueError):adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
    def test_forming_timestamp_refused(self):
        rows=source();rows[-1]['date']='2026-11-13T15:00:00Z';raw,rec=capture(rows)
        with self.assertRaises(ValueError):adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
    def test_future_revision_does_not_use_adj_fields(self):
        rows=source()
        for r in rows:r['adjClose']=1000000.
        raw,rec=capture(rows);p,_=adapt_eod_capture(raw,rec,'QQQ','2026-11-13')
        self.assertEqual(p.close.tolist(),[100.]*3)
    def test_boolean_numeric_refused(self):
        rows=source();rows[-1]['close']=True;raw,rec=capture(rows)
        with self.assertRaises(ValueError):adapt_eod_capture(raw,rec,'QQQ','2026-11-13')


if __name__=='__main__':unittest.main()
