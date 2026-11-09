import copy
import json
from pathlib import Path
import tempfile
import unittest
from replay_reader import Replay,ORIGIN,replay,from_file,exact


def frame(kind,t,symbol='SYN-A',session='one',**extra):
    return {'origin':ORIGIN,'kind':kind,'observed_ns':str(t),'symbol':symbol,'session':session,**extra}

def event(seq,t,kind,oid=1,side=1,price=100,quantity=0):
    return {'sequence':str(seq),'received_ns':str(t),'kind':kind,'order_id':str(oid),'side':side,'price':price,'quantity':quantity}

def fixture(symbol='SYN-A'):
    return [frame('START',0,symbol),
            frame('BATCH',1,symbol,complete=True,events=[event(1,1,'ADD',quantity=100)]),
            frame('BATCH',2,symbol,complete=True,events=[event(2,2,'EXECUTE',quantity=60)])]


class ReplayTests(unittest.TestCase):
    def test_no_coverage_extrapolation(self):
        r=replay(fixture(),15)['records'][0]
        self.assertIn('COVERAGE_NOT_PROVEN',r['state'])
        self.assertEqual(r['measurement_cutoff_ns'],'2')
        self.assertEqual(r['recovery']['sides']['bid']['elapsed_ns'],0)
        self.assertEqual(r['descriptive_competing_outcomes']['bid']['followup_end_ns'],0)

    def test_watermark_allows_elapsed_observation(self):
        f=fixture()+[frame('WATERMARK',5,complete_through_ns='5',last_sequence='2')]
        r=replay(f,5)['records'][0]
        self.assertEqual(r['state'],'SYNTHETIC_PREFIX_OBSERVED_TO_CUTOFF')
        self.assertEqual(r['recovery']['sides']['bid']['elapsed_ns'],3)

    def test_delayed_watermark_cannot_appear_early(self):
        f=fixture()+[frame('WATERMARK',10,complete_through_ns='8',last_sequence='2')]
        self.assertEqual(replay(f,8)['records'][0]['measurement_cutoff_ns'],'2')
        r=replay(f,10)['records'][0]
        self.assertEqual(r['measurement_cutoff_ns'],'8')
        self.assertEqual(r['observation_age_ns'],2)

    def test_batch_not_published_before_final_receipt(self):
        f=fixture()+[frame('WATERMARK',4,complete_through_ns='4',last_sequence='2'),
                     frame('BATCH',6,complete=True,events=[event(3,5,'DELETE'),event(4,5,'ADD',oid=2,quantity=100)])]
        self.assertEqual(replay(f,4)['records'][0]['recovery']['sides']['bid']['past_recoveries'],0)
        r=replay(f,6)['records'][0]
        self.assertEqual(r['recovery']['sides']['bid']['past_recoveries'],1)
        self.assertEqual(r['recovery']['sides']['bid']['past_level_depletions'],0)
        self.assertEqual(r['recovery']['sides']['bid']['median_completed_recovery_ns'],4)

    def test_bad_tail_leaves_frame_state_unchanged(self):
        b=Replay()
        for f in fixture():b.apply_frame(f)
        before=json.dumps(b.snapshot(2),sort_keys=True)
        with self.assertRaises(ValueError):b.apply_frame(frame('BATCH',5,complete=True,events=[event(3,4,'ADD',oid=2,quantity=60),event(4,5,'DELETE',oid=999)]))
        self.assertEqual(json.dumps(b.snapshot(2),sort_keys=True),before)

    def test_partial_batch_refused(self):
        b=Replay();b.apply_frame(frame('START',0))
        with self.assertRaises(ValueError):b.apply_frame(frame('BATCH',1,complete=False,events=[event(1,1,'ADD',quantity=10)]))
        self.assertFalse(b.books['SYN-A'].orders)

    def test_event_before_sealed_watermark_refused(self):
        b=Replay()
        for f in fixture()+[frame('WATERMARK',5,complete_through_ns=5,last_sequence=2)]:b.apply_frame(f)
        with self.assertRaises(ValueError):b.apply_frame(frame('BATCH',6,complete=True,events=[event(3,5,'ADD',oid=2,quantity=1)]))

    def test_watermark_wrong_sequence_refused(self):
        b=Replay()
        for f in fixture():b.apply_frame(f)
        with self.assertRaises(ValueError):b.apply_frame(frame('WATERMARK',3,complete_through_ns=3,last_sequence=3))

    def test_watermark_future_coverage_refused(self):
        b=Replay()
        for f in fixture():b.apply_frame(f)
        with self.assertRaises(ValueError):b.apply_frame(frame('WATERMARK',3,complete_through_ns=4,last_sequence=2))

    def test_gap_censors_at_last_proven_coverage_not_detection(self):
        f=fixture()+[frame('WATERMARK',5,complete_through_ns=5,last_sequence=2),frame('GAP',10)]
        r=replay(f,10)['records'][0]
        self.assertEqual(r['state'],'SOURCE_GAP_CENSORED')
        self.assertEqual(r['descriptive_competing_outcomes']['bid']['followup_end_ns'],3)
        self.assertFalse(r['recovery']['source_integrity'])

    def test_gap_does_not_allow_new_event(self):
        b=Replay()
        for f in fixture()+[frame('GAP',3)]:b.apply_frame(f)
        with self.assertRaises(ValueError):b.apply_frame(frame('BATCH',4,complete=True,events=[event(3,4,'ADD',oid=2,quantity=10)]))

    def test_reset_censors_old_session_and_isolates_id_reuse(self):
        f=fixture()+[frame('RESET',5,session='two'),frame('BATCH',6,session='two',complete=True,events=[event(1,6,'ADD',quantity=9)])]
        r=replay(f,6)
        self.assertEqual(r['records'][0]['session'],'two')
        self.assertEqual(r['records'][0]['descriptive_competing_outcomes']['bid']['n'],0)
        self.assertEqual(r['retired_sessions'][0]['responses'][0]['state'],'SOURCE_GAP_CENSORED')

    def test_reset_retains_proven_followup_until_last_watermark(self):
        f=fixture()+[frame('WATERMARK',5,complete_through_ns='5',last_sequence='2'),frame('RESET',10,session='two')]
        r=replay(f,10)
        old=r['retired_sessions'][0]['responses'][0]
        self.assertEqual(old['completed_ns'],5)
        self.assertEqual(old['state'],'SOURCE_GAP_CENSORED')

    def test_empty_started_book_has_no_forecast_or_negative_followup(self):
        r=replay([frame('START',0)],0)['records'][0]
        self.assertEqual(r['descriptive_competing_outcomes']['bid']['n'],0)
        self.assertIsNone(r['forecast_probability'])

    def test_large_half_integer_medians_are_not_rounded(self):
        from book_recovery import median_duration_ns
        from recovery_incidence import Episode,competing_incidence
        n=2**60
        self.assertEqual(median_duration_ns([n,n+1]),str(n)+'.5')
        self.assertEqual(competing_incidence([Episode(n,'RECOVERED'),Episode(n+1,'RECOVERED')])['median_completed_recovery_ns'],str(n)+'.5')
        self.assertEqual(median_duration_ns([1,8]),4.5)
        self.assertEqual(median_duration_ns([1,9]),5)

    def test_same_session_reset_refused(self):
        b=Replay();b.apply_frame(frame('START',0))
        with self.assertRaises(ValueError):b.apply_frame(frame('RESET',1))

    def test_silent_session_change_refused(self):
        b=Replay();b.apply_frame(frame('START',0))
        with self.assertRaises(ValueError):b.apply_frame(frame('BATCH',1,session='other',complete=True,events=[event(1,1,'ADD',quantity=1)]))

    def test_multi_symbol_order_id_isolation(self):
        f=sorted(fixture('SYN-A')+fixture('SYN-B'),key=lambda f:int(f['observed_ns']))
        r=replay(f,2)
        self.assertEqual(len(r['records']),2)
        self.assertTrue(all(x['recovery']['sides']['bid']['current_level_depth']==40 for x in r['records']))

    def test_declared_real_origin_or_symbol_rejected(self):
        for bad in [dict(frame('START',0),origin='IEX'),frame('START',0,symbol='AAPL')]:
            with self.assertRaises(ValueError):replay([bad],0)

    def test_future_events_not_read_for_past_answer(self):
        f=fixture();prefix=replay(f,2)
        future=frame('BATCH',100,events='intentionally malformed future payload')
        self.assertEqual(replay(f+[future],2),prefix)

    def test_original_prefix_required_for_past_query(self):
        b=Replay()
        for f in fixture():b.apply_frame(f)
        with self.assertRaises(ValueError):b.snapshot(1)

    def test_invalid_last_frame_does_not_advance_cutoff(self):
        b=Replay()
        for f in fixture():b.apply_frame(f)
        with self.assertRaises(ValueError):b.apply_frame(frame('BOGUS',100))
        self.assertEqual(b.observed_ns,2)

    def test_canonical_integer_inputs_only(self):
        for value in [True,1.0,'1e3','01','+1','-1',' 1']:
            with self.assertRaises(ValueError):exact(value,'test')
        self.assertEqual(exact(str(2**60),'test'),2**60)

    def test_nested_json_large_clocks_survive(self):
        n=2**60;f=fixture()
        for a in f:
            a['observed_ns']=str(n+int(a['observed_ns']))
            for e in a.get('events',[]):e['received_ns']=str(n+int(e['received_ns']))
        r=json.loads(json.dumps(replay(f,n+2)))['records'][0]
        self.assertEqual(r['recovery']['sides']['bid']['pending']['start_ns'],str(n+2))

    def test_real_decoder_remains_disabled(self):
        from book_recovery import decode_iex_book_event
        with self.assertRaises(NotImplementedError):decode_iex_book_event(b'not-qualified')

    def test_no_forecast_or_action_authority(self):
        r=replay(fixture(),2)
        self.assertFalse(any(r['authority'].values()))
        self.assertIsNone(r['records'][0]['forecast_probability'])
        self.assertIsNone(r['records'][0]['pressure_direction'])

    def test_local_file_end_to_end_and_input_unchanged(self):
        payload={'origin':ORIGIN,'frames':fixture()}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.json';p.write_text(json.dumps(payload));before=p.read_bytes()
            r=from_file(p,2)
            self.assertEqual(before,p.read_bytes());self.assertEqual(r['frames_received'],3)
            self.assertEqual(len(r['fixture_sha256']),64)

    def test_empty_prefix_is_explicitly_empty(self):
        r=replay([frame('START',10)],0)
        self.assertEqual(r['records'],[]);self.assertEqual(r['frames_received'],0)

if __name__=='__main__':unittest.main(verbosity=2)
