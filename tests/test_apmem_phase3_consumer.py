from copy import deepcopy
import unittest
from research.apmem_shadow.phase3.consumer import attach,CONTRACT


def fixture():
    report={'ticker':'TEST','as_of':'2026-05-01','buyable':False,'verdict':'chase','entry_score':32.}
    payload={'instrument':'TEST','origin_session':'2026-05-01','captured_at':'2026-11-14T00:00:00Z',
             'computed_at':'2026-11-14T01:00:00Z','historical_first_availability':None,
             'lineage':{'raw_capture_sha256':'a'*64,'prefix_sha256':'b'*64,
                        'native_source_commit':'c'*40,'research_source_commit':'d'*40},
             'forecast':{'model':'delta1_MEM','unit':'mean_daily_variance','h1':.0004,'h5':.0003,'h20':.0002,'fit_cutoff':'2026-04-01'},
             'native':{'eligible':True,'tier':'T2','provisional':False},
             'conditional':{'contract':CONTRACT,'model':'risk','training_n':500,'fit_origin':'2026-04-20',
                            'latest_training_label_end':'2026-04-20','fit_age_sessions':9,
                            'p_stop':.4,'p_target':.3,'p_timeout':.3}}
    args={'instrument':'TEST','origin':'2026-05-01','now':'2026-11-14T02:00:00Z','expected_lineage':deepcopy(payload['lineage'])}
    return report,payload,args

class ConsumerTests(unittest.TestCase):
    def test_real_context_does_not_overrule_entry(self):
        r,p,a=fixture();old=deepcopy(r);out=attach(r,p,**a)
        self.assertEqual(r,old);self.assertFalse(out['buyable']);self.assertEqual(out['entry_score'],32.)
        c=out['entry_risk_research'];self.assertEqual(c['status'],'RESEARCH_ONLY')
        self.assertTrue(c['capture_utc_date_after_origin']);self.assertFalse(any(c['authority'].values()))
        self.assertAlmostEqual(c['conditional']['p_target_given_activity'],3/7)
    def test_missing_context_does_not_block_incumbent(self):
        r,p,a=fixture();r['buyable']=True;out=attach(r,{},**a)
        self.assertTrue(out['buyable']);self.assertEqual(out['entry_risk_research']['status'],'ABSTAIN')
    def test_wrong_instrument(self):
        r,p,a=fixture();p['instrument']='OTHER'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['WRONG_INSTRUMENT'])
    def test_stale_origin(self):
        r,p,a=fixture();p['origin_session']='2026-04-30'
        self.assertIn('WRONG_OR_STALE_ORIGIN',attach(r,p,**a)['entry_risk_research']['reason_codes'])
    def test_naive_clock_refused(self):
        r,p,a=fixture();p['captured_at']='2026-11-14T00:00:00'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['status'],'ABSTAIN')
    def test_future_computation_refused(self):
        r,p,a=fixture();p['computed_at']='2026-11-15T00:00:00Z'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['status'],'ABSTAIN')
    def test_digest_required(self):
        r,p,a=fixture();p['lineage']['prefix_sha256']='bad'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['INVALID_INPUT_DIGEST'])
    def test_wrong_forecast_unit(self):
        r,p,a=fixture();p['forecast']['unit']='annual_percent'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['INVALID_FORECAST_UNIT'])
    def test_zero_risk_not_valid(self):
        r,p,a=fixture();p['forecast']['h5']=0.
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['status'],'ABSTAIN')
    def test_future_forecast_fit(self):
        r,p,a=fixture();p['forecast']['fit_cutoff']='2026-05-04'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['FUTURE_FORECAST_FIT'])
    def test_probabilities_not_reused_for_long_hold(self):
        r,p,a=fixture();a['intended_contract']='trailing63'
        c=attach(r,p,**a)['entry_risk_research']
        self.assertEqual(c['forecast_status'],'AVAILABLE_RESEARCH');self.assertEqual(c['conditional_status'],'ABSTAIN_CONTRACT_MISMATCH')
    def test_provisional_not_confirmed(self):
        r,p,a=fixture();p['native']['provisional']=True
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['conditional_status'],'ABSTAIN_NO_CONFIRMED_ENTRY')
    def test_future_label_refused(self):
        r,p,a=fixture();p['conditional']['latest_training_label_end']='2026-04-21'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['conditional_status'],'ABSTAIN_TRAINING_CLOCK')
    def test_stale_classifier_refused(self):
        r,p,a=fixture();p['conditional']['fit_age_sessions']=63
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['conditional_status'],'ABSTAIN_TRAINING_CLOCK')
    def test_probability_sum_refused(self):
        r,p,a=fixture();p['conditional']['p_target']=.8
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['conditional_status'],'ABSTAIN_INVALID_PROBABILITY')
    def test_future_outcome_never_projected(self):
        r,p,a=fixture();p['actual_outcome']='target'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['FUTURE_OUTCOME_IN_CONSUMER_INPUT'])
    def test_incompatible_authority_claim_refused(self):
        r,p,a=fixture();p['may_trade']=True
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['INCOMPATIBLE_AUTHORITY_CLAIM'])
    def test_unbound_source_cannot_be_trusted(self):
        r,p,a=fixture();a.pop('expected_lineage')
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['UNBOUND_OR_MISMATCHED_SOURCE_LINEAGE'])
    def test_well_formed_but_wrong_source_refused(self):
        r,p,a=fixture();p['lineage']['research_source_commit']='e'*40
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['UNBOUND_OR_MISMATCHED_SOURCE_LINEAGE'])
    def test_invented_historical_availability_refused(self):
        r,p,a=fixture();p['historical_first_availability']='2020-01-01'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['reason_codes'],['UNVERIFIED_HISTORICAL_PUBLICATION_CLAIM'])
    def test_string_eligibility_not_a_confirmed_event(self):
        r,p,a=fixture();p['native']['eligible']='false'
        self.assertEqual(attach(r,p,**a)['entry_risk_research']['conditional_status'],'ABSTAIN_NO_CONFIRMED_ENTRY')
    def test_duplicate_projection_refused(self):
        r,p,a=fixture();r['entry_risk_research']={}
        with self.assertRaises(ValueError):attach(r,p,**a)

if __name__=='__main__':unittest.main()
