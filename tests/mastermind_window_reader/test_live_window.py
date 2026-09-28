"""Consumer tests on exact upstream owner; events/classification are synthetic."""
import asyncio, dataclasses, importlib.util, json
import pytest
from control_plane.visible_turn_projection import VisibleTurnProjection, TurnKey, ReadResult
from integrations.mastermind_window_reader.live_window_read import WindowReader, ContentDecision, WindowError, project_window

SPEC=importlib.util.find_spec('integrations.mastermind_window_reader.live_window_read')

def test_window_connection_exists():
    assert SPEC is not None, 'Missing live-window read connection'

REF='managed-window:fixture-visible-turn'
KEY=TurnKey('fixture-attempt','fixture-session','fixture-generation',1,'fixture-worker','fixture-local','fixture-native')
NOW='2026-09-16T20:00:00+00:00'

class Source:
    def __init__(self):
        self.owner=VisibleTurnProjection();self.grant=self.owner.mint_grant(KEY);self.reads=0
    def publish(self,id,text,state='partial',position=1):
        self.owner.publish(KEY,method='item/updated' if state=='partial' else 'item/completed',
          params={'item':{'type':'agentMessage','id':id,'sequence':position,'text':text}},native_turn_id=KEY.native_turn_id)
    def terminal(self):
        self.owner.publish(KEY,method='turn/completed',params={},native_turn_id=KEY.native_turn_id)
    async def read(self,cursor,limit):
        self.reads+=1
        return self.owner.read(KEY,reader_grant=self.grant,cursor=cursor,max_items=limit)

def build(source,**kw):
    opts=dict(read_page=source.read,source_ref=REF,expected_scope=(KEY.process_generation_id,KEY.native_turn_id),
      classify=lambda i:ContentDecision('visible-response',i.text,'VISIBLE_TEXT'),now=lambda:NOW,page_size=1,max_pages=8)
    opts.update(kw);return WindowReader(**opts)

def capture(reader):return json.loads(asyncio.run(reader.read()))

@pytest.mark.skipif(not SPEC,reason='consumer not implemented yet')
class TestWindow:
    def test_partial_then_completion_same_identity(self):
        s=Source();s.publish('a','Draft');r=build(s)
        first=capture(r);s.publish('a','Corrected final','completed');last=capture(r)
        assert first['items'][0]['text']=='Draft' and not first['terminal']
        assert len(last['items'])==1 and last['items'][0]['text']=='Corrected final'
        assert first['items'][0]['id']==last['items'][0]['id'] and last['items'][0]['publication_sequence']>first['items'][0]['publication_sequence']
    def test_real_source_small_pages_do_not_skip_b(self):
        s=Source();s.publish('a','Draft');s.publish('b','Other',position=2);s.publish('a','Final','completed')
        d=capture(build(s));assert [i['text'] for i in d['items']]==['Final','Other']
    def test_required_classifier(self):
        with pytest.raises(TypeError):build(Source(),classify=None)
    def test_withheld_text_never_serialized(self):
        s=Source();s.publish('a','synthetic private body')
        d=capture(build(s,classify=lambda i:ContentDecision('withheld',None,'WITHHELD')))
        assert d['items'][0]['text'] is None and 'synthetic private body' not in json.dumps(d)
    def test_filtered_text_marked(self):
        s=Source();s.publish('a','Original')
        d=capture(build(s,classify=lambda i:ContentDecision('visible-response','Filtered','FILTERED_VISIBLE_TEXT')))
        assert d['items'][0]['representation']=='FILTERED_VISIBLE_TEXT'
    def test_classifier_cannot_claim_verbatim_after_change(self):
        s=Source();s.publish('a','Original')
        with pytest.raises(WindowError):capture(build(s,classify=lambda i:ContentDecision('visible-response','Changed','VISIBLE_TEXT')))
    def test_wrong_full_scope_refused(self):
        s=Source();s.publish('a','Original')
        with pytest.raises(WindowError):capture(build(s,expected_scope=('other',KEY.native_turn_id)))
    def test_gap_is_disclosed_without_reset_loop(self):
        s=Source();s.owner.publish(KEY,method='item/updated',params={'item':{'type':'agentMessage','id':'bad'}},native_turn_id=KEY.native_turn_id)
        d=capture(build(s));assert d['gaps'] and d['coverage']=='GAP_PRESENT' and s.reads==1
    def test_page_limit_is_not_claimed_complete(self):
        s=Source();s.publish('a','One');s.publish('b','Two',position=2)
        d=capture(build(s,max_pages=1));assert d['coverage']=='READ_LIMIT_REACHED' and len(d['items'])==1
    def test_empty_window_not_fleet_zero(self):
        d=capture(build(Source()));assert d['scope']=='one-managed-turn-window' and d['history']=='NOT_PROVEN' and d['items']==[]
    def test_revoke_after_page_no_partial_response(self):
        s=Source();s.publish('a','One');s.publish('b','Two',position=2)
        async def read(cursor,limit):
            p=await s.read(cursor,limit)
            if s.reads==1:s.owner.revoke_grant(s.grant)
            return p
        with pytest.raises(WindowError):capture(build(s,read_page=read))
    def test_native_ids_and_reader_grant_not_in_public_output(self):
        s=Source();s.publish('a','One');d=capture(build(s));text=json.dumps(d)
        for forbidden in [s.grant,KEY.attempt_id,KEY.native_turn_id,KEY.process_generation_id]:assert forbidden not in text
    def test_public_projection_cannot_promote_acceptance(self):
        s=Source();s.publish('a','One');d=capture(build(s));d['acceptance']='ACCEPTED'
        with pytest.raises(WindowError):project_window(d)
    def test_terminal_is_not_acceptance(self):
        s=Source();s.publish('a','Final','completed');s.terminal();d=capture(build(s))
        assert d['terminal'] is True and d['acceptance']=='NOT_PROJECTED'
    @pytest.mark.parametrize('flag',[0,1,'false',True])
    def test_commands_stay_disabled(self,flag):
        d=capture(build(Source()));d['capabilities']['send']=flag
        with pytest.raises(WindowError):project_window(d)

@pytest.mark.skipif(not SPEC,reason='consumer not implemented yet')
class TestWindowBoundaries:
    def test_epoch_change_during_pages_discards_mixed_result(self):
        s=Source();s.publish('a','One');s.publish('b','Two',position=2)
        async def read(cursor,limit):
            p=await s.read(cursor,limit)
            return dataclasses.replace(p,publication_epoch='different-epoch') if s.reads==2 else p
        with pytest.raises(WindowError,match='EPOCH_CHANGED'):capture(build(s,read_page=read))
    def test_stalled_cursor_is_not_retried(self):
        s=Source();s.publish('a','One');s.publish('b','Two',position=2)
        async def read(cursor,limit):
            p=await s.read(cursor,limit)
            return dataclasses.replace(p,next_cursor=cursor) if cursor else p
        with pytest.raises(WindowError,match='CURSOR_STALLED'):capture(build(s,read_page=read))
        assert s.reads==2
    def test_missing_history_is_not_reclassified_as_empty_complete(self):
        s=Source();d=capture(build(s));d['history']='COMPLETE'
        with pytest.raises(WindowError):project_window(d)
    def test_unknown_classification_cannot_emit_reasoning(self):
        s=Source();s.publish('a','Body')
        with pytest.raises(WindowError):capture(build(s,classify=lambda i:ContentDecision('hidden-reasoning',i.text,'VISIBLE_TEXT')))
    def test_unknown_upstream_state_refuses_whole_read(self):
        s=Source();s.publish('a','Body')
        async def read(cursor,limit):
            p=await s.read(cursor,limit)
            if p.items:p=dataclasses.replace(p,items=(dataclasses.replace(p.items[0],state='action-approved'),))
            return p
        with pytest.raises(WindowError):capture(build(s,read_page=read))
    def test_duplicate_publication_conflict_refused(self):
        s=Source();s.publish('a','One');s.publish('b','Two',position=2);original=None
        async def read(cursor,limit):
            nonlocal original
            p=await s.read(cursor,limit)
            if original is None:original=p.items[0]
            elif p.items:p=dataclasses.replace(p,items=(dataclasses.replace(original,text='Bad',byte_length=3),))
            return p
        with pytest.raises(WindowError,match='ITEM_CONFLICT'):capture(build(s,read_page=read))
    @pytest.mark.parametrize('field',['source_sequence','publication_sequence'])
    def test_cross_language_unsafe_integer_refused(self,field):
        s=Source();s.publish('a','One');d=capture(build(s));d['items'][0][field]=2**53
        with pytest.raises(WindowError):project_window(d)
    def test_withheld_body_cannot_leak_via_extra_fields(self):
        s=Source();s.publish('a','One');d=capture(build(s));d['items'][0]['private_notes']='Private'
        with pytest.raises(WindowError):project_window(d)
    def test_observation_requires_timezone(self):
        with pytest.raises(WindowError):capture(build(Source(),now=lambda:'2026-09-16T20:00:00'))
    def test_native_grant_is_not_minted_or_released_by_consumer(self):
        s=Source();s.publish('a','One');before=dict(s.owner._grants)
        capture(build(s));assert s.owner._grants==before
