from __future__ import annotations
import copy
import math
import numpy as np
import pandas as pd
import pytest
from research.grey_rotation_context.core import (
    AUTHORITY, ContractError, SeriesInput, attach_context, cohort_snapshot,
    digest, event_context, index_context, paired_breadth_change, recovery_context,
)
from research.grey_rotation_context.decomposition import decompose, mature_episode_training
from research.grey_rotation_context.risk_axis import features, fit_log_ridge, holm, mean_future, paired_block_summary, walk_forward


def index_fixture():
    dates = pd.bdate_range('2017-01-02', periods=330)
    values = pd.Series(15+np.arange(330)*.02, index=dates)
    known = pd.Series([str(d.date())+'T21:15:00Z' for d in dates], index=dates)
    return dates, SeriesInput('VIX', values, 'a'*64, known)


def event_fixture():
    identity = {'source_hash':'source', 'signal_era':'gc_v2_wo2', 'detector_spec_hash':'spec'}
    event = {'event_id':'fixture-id','ticker':'TEST','detector_id':'G0_GREY_DOT@1',
             'family':'grey_dot','signal_ts':'2018-03-05','signal_known_ts':'2018-03-07',
             'source_identity':identity, 'bar_state':'closed', 'final':True,
             'pre_channel_reconstruction':False}
    args = dict(expected_identity=identity, source_observed_at='2018-03-08T13:00:00Z',
                decision_at='2018-03-08T14:00:00Z', decision_session='2018-03-08')
    return event,args


def members(origin='2018-03-08'):
    return [{'ticker':f'S{i}','issuer_id':f'I{i}','group_id':'SECTOR',
             'membership_vintage':'frozen-v1','start_session':'2010-01-01',
             'end_session':None,'membership_available_at':'2010-01-01T00:00:00Z',
             'has_close':True,'observation_session':origin,'available_at':origin+'T21:00:00Z',
             'd_known':10. if i < 3 else 40.,'n_bars_known':100,'dot_recent5':i == 0}
            for i in range(6)]


def cohort(rows,origin='2018-03-08',**kwargs):
    return cohort_snapshot(rows,origin=origin,decision_at=origin+'T22:00:00Z',**kwargs)


@pytest.mark.parametrize('name',['VIX','VVIX'])
def test_market_names_and_explicit_lag(name):
    dates,src=index_fixture();src=SeriesInput(name,src.values,src.receipt_sha256,src.available_at)
    row=index_context(src,dates,str(dates[-1].date()),str(dates[-1].date())+'T21:00:00Z')
    assert row['source_session'] == str(dates[-2].date())
    assert row['latest'] == src.values.iloc[-2]
    assert row['mean20_log_change5'] > 0
    assert row['authority'] == AUTHORITY


def test_realized_vol_of_vix_cannot_impersonate_vvix():
    dates,src=index_fixture();bad=SeriesInput('realized_vix_changes',src.values,'a'*64)
    with pytest.raises(ContractError):index_context(bad,dates,str(dates[-1].date()),'2019-01-01T22:00:00Z')


@pytest.mark.parametrize('lag',[0,-1,True,1.5])
def test_bad_lag_rejected(lag):
    dates,src=index_fixture()
    with pytest.raises(ContractError):index_context(src,dates,str(dates[-1].date()),'2019-01-01T22:00:00Z',lag=lag)


def test_missing_publication_not_silently_backdated():
    dates,src=index_fixture();src=SeriesInput('VIX',src.values,'a'*64)
    a=index_context(src,dates,str(dates[-1].date()),'2019-01-01T22:00:00Z')
    b=index_context(src,dates,str(dates[-1].date()),'2019-01-01T22:00:00Z',allow_assumed_availability=True)
    assert a['status']=='UNAVAILABLE'
    assert 'assumption' in b['availability_basis']


def test_late_publication_is_unavailable_not_forward_filled():
    dates,src=index_fixture();known=src.available_at.copy();known.iloc[-2]='2030-01-01T00:00:00Z'
    row=index_context(SeriesInput('VIX',src.values,'a'*64,known),dates,str(dates[-1].date()),'2019-01-01T22:00:00Z')
    assert row['latest'] is None and row['mean20'] is None


def test_future_prices_and_missing_values_do_not_change_old_market_context():
    dates,src=index_fixture();t=dates[-10];clock=str(t.date())+'T21:00:00Z'
    a=index_context(src,dates,str(t.date()),clock)
    changed=src.values.copy();changed.loc[changed.index>t]=1e9
    b=index_context(SeriesInput('VIX',changed,'a'*64,src.available_at),dates,str(t.date()),clock)
    assert a==b
    changed=src.values.copy();changed.loc[dates[-11]]=np.nan
    z=index_context(SeriesInput('VIX',changed,'a'*64,src.available_at),dates,str(t.date()),clock)
    assert z['latest'] is None


def test_vvix_acceleration_does_not_imply_direction():
    dates,src=index_fixture()
    row=index_context(SeriesInput('VVIX',src.values,'a'*64,src.available_at),dates,str(dates[-1].date()),'2019-01-01T22:00:00Z')
    assert 'buy' not in row and 'risk_on' not in row and 'win_probability' not in row


def test_canonical_shape_fixture_consumed_without_mutation():
    event,args=event_fixture();old=copy.deepcopy(event)
    row=event_context(event,**args)
    assert row['status']=='RECORDED_CONTEXT' and event==old


@pytest.mark.parametrize('key',['source_hash','signal_era','detector_spec_hash'])
def test_event_identity_is_a_three_part_binding(key):
    event,args=event_fixture();args['expected_identity']=dict(args['expected_identity']);args['expected_identity'][key]='different'
    with pytest.raises(ContractError):event_context(event,**args)


def test_unknown_dot_clock_remains_unknown_even_when_final():
    event,args=event_fixture();event['signal_known_ts']=None
    row=event_context(event,**args)
    assert row['status']=='TIMING_UNQUALIFIED'
    assert row['signal_known_session'] is None


@pytest.mark.parametrize('change',[{'final':False},{'pre_channel_reconstruction':True}])
def test_provisional_and_backcast_not_promoted(change):
    event,args=event_fixture();event.update(change)
    assert event_context(event,**args)['status'] in ('PROVISIONAL','BACKCAST_ONLY')


def test_future_event_refused():
    event,args=event_fixture();event['signal_known_ts']='2018-03-09'
    with pytest.raises(ContractError):event_context(event,**args)


def test_later_artifact_refused():
    event,args=event_fixture();args['source_observed_at']='2018-03-09T00:00:00Z'
    with pytest.raises(ContractError):event_context(event,**args)


def test_macro_early_is_not_terminal_g0():
    event,args=event_fixture();event['detector_id']='macro_early'
    with pytest.raises(ContractError):event_context(event,**args)


def test_complete_roster_denominator_keeps_missing_names():
    rows=members();rows[-1]['has_close']=False
    out=cohort(rows)
    assert (out['n_expected'],out['n_defined'],out['n_missing_or_unresolved'])==(6,5,1)
    assert out['coverage']==5/6 and out['floor_share']==3/5


def test_leave_focal_issuer_out_of_all_share_classes():
    rows=members();extra=copy.deepcopy(rows[0]);extra['ticker']='S0_SECOND';rows.append(extra)
    out=cohort(rows,focal_issuer='I0')
    assert out['n_expected']==5 and 'I0' not in out['issuer_states']
    assert out['floor_share']==2/5


def test_unresolved_share_class_not_chosen_alphabetically():
    rows=members();extra=copy.deepcopy(rows[0]);extra['ticker']='S0_SECOND';rows.append(extra)
    out=cohort(rows)
    assert out['status']=='SHARE_CLASS_UNRESOLVED' and out['unresolved_issuers']==['I0']
    fixed=cohort(rows,representative={'I0':'S0'})
    assert fixed['status']=='CONTEXT_ONLY' and fixed['n_expected']==6


def test_membership_end_is_exclusive():
    rows=members();rows[0]['end_session']='2018-03-08'
    assert cohort(rows)['n_expected']==5


def test_future_membership_vintage_not_known_in_past():
    rows=members();rows[0]['membership_available_at']='2026-11-14T00:00:00Z'
    with pytest.raises(ContractError):cohort(rows)


def test_reconstructed_membership_does_not_claim_original_vintage():
    rows=members();rows[0]['membership_available_at']=None
    with pytest.raises(ContractError):cohort(rows)
    out=cohort(rows,allow_reconstructed_membership=True)
    assert 'not_original' in out['membership_basis']


def test_thin_undefined_and_partial_observations_do_not_count_as_no_washout():
    rows=members();rows[0]['n_bars_known']=89;rows[1]['d_known']=None;rows[2]['available_at']='2030-01-01T00:00:00Z'
    out=cohort(rows)
    assert out['status']=='THIN' and out['n_defined']==3 and out['floor_share']==0
    assert out['n_expected']==6


def test_missing_dot_not_false_dot():
    rows=members();rows[0]['dot_recent5']=None
    out=cohort(rows)
    assert out['n_dot_defined']==5 and out['dot_share5']==0


def test_composition_artifact_is_separated_from_paired_recovery():
    old=members('2018-03-08');new=members('2018-03-09')
    new[-1]['has_close']=False;new[-2]['has_close']=False
    result=paired_breadth_change(cohort(old),cohort(new,origin='2018-03-09'))
    assert result['raw_floor_change']>.2
    assert result['paired_floor_change']==0
    assert result['roster_or_definition_changed']


def test_beta_only_move_is_not_sector_alpha():
    dates=pd.bdate_range('2013-01-02',periods=220)
    m=pd.Series(np.sin(np.arange(220))*.01,index=dates);g=2*m;r=.5*m
    out=recovery_context(g,m,r)
    assert np.nanmax(abs(out.market_adjusted_move.to_numpy()))<1e-12


def test_relative_strength_can_mean_falling_less():
    dates=pd.bdate_range('2013-01-02',periods=160)
    m=pd.Series(np.sin(np.arange(160))*.001-.002,index=dates)
    out=recovery_context(m,2*m,3*m)
    assert out.iloc[-1].both_falling and out.iloc[-1].relative_gain_without_absolute_gain


def test_beta_excludes_current_recovery_window():
    dates=pd.bdate_range('2013-01-02',periods=200)
    m=pd.Series(np.sin(np.arange(200))*.01,index=dates);g=m.copy()
    a=recovery_context(g,m,m)
    g.iloc[-5:]=10
    b=recovery_context(g,m,m)
    assert a.pre_window_market_beta.iloc[-1]==b.pre_window_market_beta.iloc[-1]


def toy(delta=0.):
    rows=[]
    for state,day,p,n1,n0 in [('good','2018-01-02',.72,77,40),('bad','2018-01-03',.52,23,60)]:
        for arm,n in [(True,n1),(False,n0)]:
            for i in range(n):
                rows.append({'event_id':f'{state}-{arm}-{i}','origin':day,'label_end':'2018-02-01',
                             'treated':arm,'outcome':p+(delta if arm else 0.)})
    return pd.DataFrame(rows)


def test_common_tape_world_separates_7_4_percentage_points_with_zero_stock_effect():
    out=decompose(toy(),permitted_end='2019-12-31')
    assert abs(out['pooled_gap']-.074)<1e-12
    assert abs(out['within_date_gap'])<1e-12
    assert abs(out['date_composition_component']-.074)<1e-12
    assert not out['causal_effect_established']


@pytest.mark.parametrize('effect',[.05,-.03])
def test_real_same_day_component_survives_standardization(effect):
    out=decompose(toy(effect),permitted_end='2019-12-31')
    assert abs(out['within_date_gap']-effect)<1e-12
    assert abs(out['within_date_gap']+out['date_composition_component']-out['common_date_pooled_gap'])<1e-12


def test_unpaired_dates_not_silently_invented():
    f=toy();f.loc[f.origin.eq('2018-01-03'),'treated']=True
    out=decompose(f,permitted_end='2019-12-31')
    assert out['paired_dates']==1 and out['all_dates']==2
    assert out['paired_events']<out['available_events']


@pytest.mark.parametrize('bad',['duplicate','unmatured','sealed','nonbool','bad_label_clock','nooutcome'])
def test_bad_evaluation_contracts(bad):
    f=toy()
    if bad=='duplicate':f.loc[1,'event_id']=f.loc[0,'event_id']
    if bad=='unmatured':f.loc[0,'label_end']='2021-01-01'
    if bad=='sealed':f.loc[0,['origin','label_end']]=['2020-01-02','2020-02-01']
    if bad=='nonbool':f['treated']=f.treated.astype(str)
    if bad=='bad_label_clock':f.loc[0,'label_end']='2017-01-01'
    if bad=='nooutcome':f['outcome']=np.nan
    with pytest.raises(ContractError):decompose(f,permitted_end='2019-12-31')


def test_historical_personality_cannot_use_unfinished_episodes():
    f=toy();f['label_available_session']=f.label_end
    assert mature_episode_training(f,origin='2018-01-20',minimum_events=1).empty
    assert len(mature_episode_training(f,origin='2018-02-02',minimum_events=1))==len(f)
    assert mature_episode_training(f,origin='2018-02-02',minimum_events=1000).empty


def test_sidecar_preserves_original_fields_and_never_promotes():
    original={'buyable':False,'entry_score':10,'verdict':'knife','nested':{'a':1}}
    old=copy.deepcopy(original)
    out=attach_context(original,{'market':{'VIX':30},'limitations':['unqualified forecast']})
    with pytest.raises(ContractError):attach_context(original,{'buy_probability':.99})
    assert {k:v for k,v in out.items() if k!='grey_rotation_research'}==old
    out['nested']['a']=2
    assert original==old and not out['grey_rotation_research']['authority']['may_trade']
    with pytest.raises(ContractError):attach_context(out,{})


def price_fixture():
    dates=pd.bdate_range('2010-01-04',periods=1050)
    r=.01*np.sin(np.arange(len(dates))*.15)
    v=.00015+abs(r)*.01
    p=pd.DataFrame({'variance':v,'return_log':r},index=dates)
    ix=pd.Series(20+np.sin(np.arange(len(dates))*.03),index=dates)
    return p,ix,ix*4


def test_future_labels_and_index_lags():
    a=np.arange(1,30,dtype=float)
    assert mean_future(a,5)[0]==4.
    assert np.isnan(mean_future(a,5)[-5:]).all()
    p,ix,vx=price_fixture();old=features(p,ix,vx)
    vx.iloc[-1]=1e10
    assert np.array_equal(features(p,ix,vx)['plus_vvix_trend'],old['plus_vvix_trend'],equal_nan=True)


def test_regression_smearing_intercept_and_training_only_scale():
    x=np.zeros((100,2));y=np.full(100,.001)
    fit=fit_log_ridge(x,y)
    assert np.allclose(fit.predict(x),.001)
    with pytest.raises(ContractError):fit_log_ridge(x,y*0)


def test_sealed_future_input_is_rejected_before_feature_work():
    p,ix,vx=price_fixture();p.index=pd.bdate_range('2018-01-02',periods=len(p))
    with pytest.raises(ContractError):features(p,ix,vx)


def test_chronological_fits_have_only_matured_labels_and_prediction_parity():
    p,ix,vx=price_fixture()
    result,logs=walk_forward(p,ix,vx,minimum=100,window=300,refit=63)
    assert not result.empty
    assert all(x['latest_training_label_end']<=x['origin'] for x in logs if x['status']=='FITTED')
    cut=p.index[-100]
    shorter,_=walk_forward(p.loc[:cut],ix.loc[:cut],vx.loc[:cut],minimum=100,window=300,refit=63)
    keys=['origin','horizon','model','target']
    paired=shorter.merge(result,on=keys,suffixes=('_a','_b'))
    assert len(paired)==len(shorter)
    assert np.allclose(paired.forecast_a,paired.forecast_b,rtol=1e-13,atol=1e-15)


def test_block_and_multiplicity_rulers():
    a=paired_block_summary(np.zeros(400),draws=100)
    assert a['mean_loss_difference']==0 and a['centered_bootstrap_p']==1
    assert holm([.01,.03,.5])==pytest.approx([.03,.06,.5])
    with pytest.raises(ContractError):paired_block_summary(np.ones(12))


def test_same_day_final_dot_requires_actual_exchange_close():
    event,args=event_fixture();args['decision_session']='2018-03-07'
    args['decision_at']='2018-03-07T22:00:00Z';args['source_observed_at']='2018-03-07T21:10:00Z'
    assert event_context(event,**args)['status']=='CLOSE_TIME_UNQUALIFIED'
    assert event_context(event,**args,signal_close_at='2018-03-07T21:00:00Z')['status']=='RECORDED_CONTEXT'
    args['decision_at']='2018-03-07T19:00:00Z';args['source_observed_at']='2018-03-07T18:30:00Z'
    with pytest.raises(ContractError):event_context(event,**args,signal_close_at='2018-03-07T21:00:00Z')


def test_numpy_member_scalars_keep_their_real_boolean_meaning():
    rows=members()
    for r in rows:r['has_close']=np.bool_(True);r['n_bars_known']=np.int64(100);r['dot_recent5']=np.bool_(False)
    assert cohort(rows)['n_defined']==6


def test_known_timestamp_provenance_conflict_rejected():
    event,args=event_fixture();event['field_origin']={'signal_known_ts':'artifact_absent'}
    with pytest.raises(ContractError):event_context(event,**args)


def test_missing_outcomes_are_not_negative_labels():
    f=toy();f.loc[0,'outcome']=np.nan
    out=decompose(f,permitted_end='2019-12-31')
    assert out['missing_outcomes']==1 and out['available_events']==len(f)-1


def test_regression_cannot_generate_false_volatility_from_nonfinite_input():
    x=np.ones((40,3));x[0,0]=np.inf
    with pytest.raises(ContractError):fit_log_ridge(x,np.ones(40))


def test_duplicate_publication_dates_refused():
    dates,src=index_fixture();bad=src.values.copy();bad.index=[dates[0]]*len(bad)
    with pytest.raises(ContractError):index_context(SeriesInput('VIX',bad,'a'*64),dates,str(dates[-1].date()),'2019-01-01T22:00:00Z')


@pytest.mark.parametrize('index_name',['date','Date'])
def test_filtered_parquet_reader_respects_index_metadata(tmp_path,index_name):
    pytest.importorskip('pyarrow')
    from research.grey_rotation_context.run_risk_axis import _load
    index=pd.DatetimeIndex(['2019-12-30','2019-12-31','2020-01-02'],name=index_name)
    frame=pd.DataFrame({'variance':[.01,.02,99.]},index=index)
    path=tmp_path/'fixture.parquet';frame.to_parquet(path)
    out=_load(path,['variance'],'date')
    assert len(out)==2 and out.variance.max()==.02


def test_parquet_reader_refuses_a_different_semantic_index(tmp_path):
    pytest.importorskip('pyarrow')
    from research.grey_rotation_context.run_risk_axis import _load
    frame=pd.DataFrame({'variance':[.01]},index=pd.DatetimeIndex(['2019-12-31'],name='publication_time'))
    path=tmp_path/'fixture.parquet';frame.to_parquet(path)
    with pytest.raises(ContractError):_load(path,['variance'],'date')


def test_representative_change_is_not_called_paired_breadth_recovery():
    before=cohort(members())
    rows=members('2018-03-09');rows[0]['ticker']='S0_SECOND';rows[0]['d_known']=50.
    after=cohort(rows,origin='2018-03-09')
    out=paired_breadth_change(before,after)
    assert out['representative_changed_issuers']==['I0']
    assert out['common_defined_issuers']==5 and out['paired_floor_change']==0
    assert out['roster_or_definition_changed']


def test_provisional_bar_cannot_also_be_a_final_record():
    event,args=event_fixture();event['bar_state']='provisional'
    with pytest.raises(ContractError):event_context(event,**args)


@pytest.mark.parametrize('bad',[True,0,1.5])
def test_cohort_minimum_is_an_explicit_positive_count(bad):
    with pytest.raises(ContractError):cohort(members(),minimum_peers=bad)
