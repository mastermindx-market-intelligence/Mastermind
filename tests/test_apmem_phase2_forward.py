import unittest
from datetime import datetime,timezone
import pandas as pd
from research.apmem_shadow.phase2.forward import validate_capture


class ForwardCaptureTests(unittest.TestCase):
    def inputs(self):
        p=pd.DataFrame(index=pd.to_datetime(['2026-11-12','2026-11-13']))
        rec={'instrument':'QQQ','sha256':'a'*64,'captured_at':'2026-11-14T01:00:00+00:00','historical_first_availability':None}
        return p,rec,datetime(2026,11,14,1,10,tzinfo=timezone.utc)
    def test_actual_capture(self):
        p,r,now=self.inputs();validate_capture(p,r,'QQQ','2026-11-13',now,'a'*64)
    def test_future_capture_refused(self):
        p,r,now=self.inputs();r['captured_at']='2026-11-15T00:00:00+00:00'
        with self.assertRaises(ValueError):validate_capture(p,r,'QQQ','2026-11-13',now,'a'*64)
    def test_forming_bar_refused(self):
        p,r,now=self.inputs();r['captured_at']='2026-11-13T19:00:00+00:00'
        with self.assertRaises(ValueError):validate_capture(p,r,'QQQ','2026-11-13',now,'a'*64)
    def test_wrong_origin_refused(self):
        p,r,now=self.inputs()
        with self.assertRaises(ValueError):validate_capture(p,r,'QQQ','2026-11-12',now,'a'*64)
    def test_wrong_digest_refused(self):
        p,r,now=self.inputs()
        with self.assertRaises(ValueError):validate_capture(p,r,'QQQ','2026-11-13',now,'b'*64)
    def test_fake_historical_clock_refused(self):
        p,r,now=self.inputs();r['historical_first_availability']='2010-01-01'
        with self.assertRaises(ValueError):validate_capture(p,r,'QQQ','2026-11-13',now,'a'*64)


if __name__=='__main__':unittest.main()
