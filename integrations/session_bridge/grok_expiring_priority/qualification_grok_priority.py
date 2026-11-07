import copy,importlib.util,os,sys
from pathlib import Path
from datetime import datetime,timezone
import pytest,yaml
BASE=Path(os.environ.get("GROK_EVIDENCE_DIR", str(Path(__file__).parent)))
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0,str(EXT))
@pytest.fixture
def p(monkeypatch):
 spec=importlib.util.spec_from_file_location('grok_candidate',os.environ.get('GROK_TEST_SOURCE',str(BASE/'candidate/pick.py')))
 p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
 p.HERE=str(EXT)
 doc=yaml.safe_load((BASE/'candidate/pools.yaml').read_text())
 monkeypatch.setattr(p,'load_pools',lambda:doc)
 monkeypatch.setattr(p,'_grok_exhausted',lambda:False)
 class Clock(datetime):
  @classmethod
  def now(cls,tz=None):return datetime(2026,10,12,2,0,tzinfo=timezone.utc)
 monkeypatch.setattr(p,'datetime',Clock)
 return p,doc

def test_reset_observed_not_guessed(p):
 m,d=p
 assert 3.8<m._hours_to_reset('grok')<4

@pytest.mark.parametrize('mutation',[{'reset_at':'2026-10-12T01:50:00Z'},{'observed_at':'2026-10-12T03:00:00Z'},{'observed_at':'2026-10-11T18:00:00Z'},{'remaining_pct':True},{'remaining_pct':float('nan')},{'source':'guess'},{'reset_at':'2026-10-12T05:54:00'}])
def test_untrusted_stale_expired_window_is_not_urgent(p,mutation):
 m,d=p;d['pools']['grok']['windows']['weekly'].update(mutation)
 assert not m._grok_priority_active(d,'mechanical')
 assert not m.burn_down_urgent('grok',d)

def test_leaf_exception_and_scope(p):
 m,d=p
 assert m.launch_policy('grok','mechanical','grok-4.6',doc=d,task_complexity='C0_MECHANICAL')['allowed']
 assert not m.launch_policy('grok','mechanical','unregistered',doc=d,task_complexity='C0_MECHANICAL')['allowed']
 assert not m.policy_allows('grok','orchestration',d)[0]
 assert not m.policy_allows('grok','invented',d)[0]
 assert m.policy_allows('grok','build',d)[0]
 d['pools']['grok']['windows']['weekly']['reset_at']='2026-10-12T02:00:00Z'
 assert not m.launch_policy('grok','mechanical','grok-4.6',doc=d,task_complexity='C0_MECHANICAL')['allowed']

def arrange(m,d,monkeypatch):
 monkeypatch.setattr(m,'_promo_balance_glm',lambda order,*a,**k:order)
 monkeypatch.setattr(m,'_bailian_routine_sample',lambda *a,**k:False)
 monkeypatch.setattr(m,'_promote_urgent',lambda order,*a,**k:order)
 monkeypatch.setattr(m,'floor_demotes',lambda *a,**k:False)
 monkeypatch.setattr(m,'hard_filter',lambda *a,**k:(True,'ok'))
 monkeypatch.setattr(m,'_bailian_keys_usable',lambda:[])
 monkeypatch.setattr(m,'_glm_meter_state',lambda:'OK')

def test_default_useful_labor_prefers_grok(p,monkeypatch):
 m,d=p;arrange(m,d,monkeypatch)
 line=m._format_pick('mechanical',host_modes={'grok':'grok','minimax':'minimax'},task_complexity='C0_MECHANICAL')
 assert line.startswith('POOL=grok '),line

@pytest.mark.parametrize('gate',['quality','capacity','exhaustion','host','review_independence'])
def test_priority_preserves_existing_gates(p,monkeypatch,gate):
 m,d=p;arrange(m,d,monkeypatch);modes={'grok':'grok','minimax':'minimax'};tc='mechanical';kw={}
 if gate=='quality':monkeypatch.setattr(m,'floor_demotes',lambda pool,*a,**k:pool=='grok')
 if gate=='capacity':monkeypatch.setattr(m,'hard_filter',lambda pool,*a,**k:(pool!='grok','cap'))
 if gate=='exhaustion':
  monkeypatch.setattr(m,'_grok_exhausted',lambda:True)
  monkeypatch.setattr(m,'hard_filter',lambda pool,*a,**k:(pool!='grok','exhausted'))
 if gate=='host':modes.pop('grok')
 if gate=='review_independence':tc='review';kw['subject_pool']='grok'
 line=m._format_pick(tc,host_modes=modes,task_complexity='C0_MECHANICAL',**kw)
 assert not line.startswith('POOL=grok '),line

def test_ubuntu_only_selection_filter(p,monkeypatch):
 m,d=p;import host_pick,placement_view
 registry={n:{'platform':'linux' if n.startswith('ubuntu') else 'darwin'} for n in ['ubuntu0','ubuntu1','ubuntu2','ubuntu3','m2','mb','unexpected']}
 monkeypatch.setattr(host_pick,'load_registry',lambda:registry)
 seen=[]
 def view(registry,state,mode,**kw):
  seen.append(kw['excluded']);return {'host_choice':'ubuntu2'}
 monkeypatch.setattr(placement_view,'build_placement_view',view)
 assert m._eligible_host_routes('auto',required_modes=['grok'])=={'grok':('ubuntu2','grok')}
 assert all(x=={'m2','mb','unexpected'} for x in seen)
 assert not m._eligible_host_routes('m2',required_modes=['grok'])
