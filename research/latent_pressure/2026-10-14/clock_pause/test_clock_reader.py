import copy
from pathlib import Path
import tempfile
import unittest
from test_clock_study import fixture,append_at
from clock_study import clock,SECOND,load
from clock_reader import asof_ns,observe_frame


class ReaderTests(unittest.TestCase):
    def test_active_standard_subset(self):
        r=observe_frame(fixture(),clock('10:00'))[0]
        self.assertEqual(r['activity_state'],'STANDARD_SUBSET_ACTIVE')

    def test_other_activity_not_quiet_market(self):
        x=fixture();t=clock('10:01');x=append_at(x,t-SECOND,flag=128)
        r=observe_frame(x,t)[0]
        self.assertEqual(r['activity_state'],'STANDARD_SUBSET_QUIET_OTHER_DISPLAYED_EXECUTIONS')
        self.assertEqual(r['other_flag_L_count_last60s'],1)
        self.assertIsNone(r['pressure_direction'])
        self.assertIsNone(r['withdrawal_of_selling'])

    def test_no_L_is_not_empty_book(self):
        r=observe_frame(fixture(),clock('10:02'))[0]
        self.assertEqual(r['activity_state'],'NO_DISPLAYED_EXECUTION_RECORDS_IN_LAST60S')
        self.assertIsNone(r['quote_recovery'])
        self.assertIsNone(r['forecast_probability'])

    def test_future_event_one_ns_later_cannot_leak(self):
        x=fixture();t=clock('10:01');a=observe_frame(x,t)
        b=observe_frame(append_at(x,t+1,flag=128),t)
        self.assertEqual(a,b)

    def test_inclusive_lookback_exact_ns(self):
        x=fixture();t=clock('10:01')
        x=append_at(x,t-60*SECOND,flag=128)
        r=observe_frame(x,t)[0]
        self.assertEqual(r['other_flag_L_count_last60s'],1)
        self.assertEqual(observe_frame(x,t+1)[0]['other_flag_L_count_last60s'],0)

    def test_other_activity_still_visible_without_enough_standard_history(self):
        x=fixture().iloc[:5].copy();t=clock('10:01');x=append_at(x,t-SECOND,flag=128)
        r=observe_frame(x,t)[0]
        self.assertEqual(r['feature_status'],'INSUFFICIENT_STANDARD_HISTORY')
        self.assertEqual(r['other_flag_L_count_last60s'],1)

    def test_no_data_preserved_per_ticker(self):
        records=observe_frame(fixture(),clock('10:00'))
        self.assertEqual(len(records),8)
        self.assertIsNone(records[1]['last_observed_L_send_ns'])

    def test_all_forecasts_remain_null(self):
        for r in observe_frame(fixture(),clock('10:00')):
            self.assertIsNone(r['forecast_probability']);self.assertIsNone(r['institutional_inventory'])

    def test_naive_wrong_date_outside_refused(self):
        for t in ['2026-10-05T14:00:00','2026-10-06T14:00:00-04:00','2026-10-05T16:00:00-04:00','NaT']:
            with self.assertRaises(ValueError): asof_ns(t)

    def test_exact_string_id_and_nonmutation(self):
        x=fixture();before=x.copy(deep=True);r=observe_frame(x,clock('10:00'))[0]
        self.assertIsInstance(r['last_observed_L_sequence'],str)
        self.assertTrue(x.equals(before))

    def test_unqualified_bytes_refused_before_parsing(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.csv';p.write_text('not an admitted input')
            with self.assertRaisesRegex(ValueError,'UNQUALIFIED_INPUT_IDENTITY'): load(p)


if __name__=='__main__':unittest.main(verbosity=2)
