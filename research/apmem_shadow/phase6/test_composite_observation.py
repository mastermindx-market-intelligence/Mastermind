import copy,unittest
import consumer
import test_forward as fixtures

class CompositeObservationTests(unittest.TestCase):
    def support(self):
        return {'observed_session':'2026-11-13','state':'SLOW_AND_COHORT_SUPPORTED',
                'slow_known':True,'slow_supported':True,'cohort_known':True,'cohort_supported':True,
                'phase_disagreement':True,'new_trigger_on_origin':False}
    def context(self):
        return consumer.make_context('MCD','2026-11-13','REPAIR_WITH_RELATIVE_RESILIENCE',{},source_hash='a'*64,
            research_revision='b'*40,peer_basis='fixed_economic_diagnostic',risk_forecast=fixtures.RiskContractTests().record(),support_context=self.support())
    def test_risk_and_state_are_attached_without_new_signal(self):
        c=self.context();inc={'ticker':'MCD','verdict':'wait','buyable':False,'entry_score':17.}
        out=consumer.attach(inc,c,instrument='MCD',expected_session='2026-11-13',expected_source_hash='a'*64)
        self.assertFalse(out['buyable']);self.assertEqual(out['entry_score'],17.)
        self.assertFalse(out['nested_cycle_research']['support_context']['new_trigger_on_origin'])
        self.assertEqual(out['nested_cycle_research']['risk_forecast']['forecasts']['horizons'],[1,5,20])
    def test_tampered_risk_units_refused_at_consumption(self):
        c=self.context();c['risk_forecast']['variance_units']='annualized_percent'
        with self.assertRaises(ValueError):consumer.attach({'ticker':'MCD'},c,instrument='MCD',expected_session='2026-11-13',expected_source_hash='a'*64)
    def test_unknown_support_cannot_claim_confirmation(self):
        s=self.support();s['cohort_known']=False
        with self.assertRaises(ValueError):consumer.validate_support(s,'2026-11-13')
    def test_state_label_must_match_fields(self):
        s=self.support();s['slow_supported']=False
        with self.assertRaises(ValueError):consumer.validate_support(s,'2026-11-13')
    def test_future_support_clock_refused(self):
        s=self.support();s['observed_session']='2026-11-16'
        with self.assertRaises(ValueError):consumer.validate_support(s,'2026-11-13')
    def test_phase_conflict_not_silently_erased(self):
        c=self.context();self.assertTrue(c['support_context']['phase_disagreement'])
    def test_attached_risk_payload_isolated(self):
        r=fixtures.RiskContractTests().record();s=self.support()
        c=consumer.make_context('MCD','2026-11-13','CONTEXT_INCOMPLETE',{},source_hash='a'*64,research_revision='b'*40,
             peer_basis='fixed_economic_diagnostic',risk_forecast=r,support_context=s)
        c['risk_forecast']['forecasts']['mean_daily_variance'][0]=999.;self.assertNotEqual(r['forecasts']['mean_daily_variance'][0],999.)

if __name__=='__main__':unittest.main()
