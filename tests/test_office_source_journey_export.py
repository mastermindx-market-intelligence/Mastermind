"""One canonical Office READ fixture, no Runtime/provider/modifying effects."""
import asyncio,json,os,subprocess,time
from pathlib import Path
import httpx
from tests.test_installed_project_direction_context import bound
from tests.test_agentos_project_direction_source import WORK
from tests.test_workspace_project_direction_http import rsa_key,short_socket_root
from tests.test_workspace_read_app import _authenticator,_workspace_token
from tests.test_workspace_result_socket import control
from tests.fresh_conversation_full_cache import CanonicalFixtureCache
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA,principal_frame,workspace_authorizers
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig,create_workspace_app
from integrations.mastermind_executive_app.os_transport import _context_payload
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane import agentos_project_plan as plan_source
from control_plane import agentos_project_direction as direction_source
from control_plane import agentos_project_journal as journal_source
from integrations.executive_mcp.installed import _default_packet_runner


def test_whole_office_canonical_owner(tmp_path,monkeypatch,rsa_key,short_socket_root):
 async def run():
  import tests.test_workspace_read_app as auth_suite
  now=int(time.time());monkeypatch.setattr(auth_suite,'NOW',now)
  auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
  principal=await auth.verify_authorization_header('Bearer '+token,now=now)
  slots={'schema':BINDINGS_SCHEMA,'profiles':{'web':{'enabled':True,'binding':dict(principal_frame(principal),permission_digest='a'*64)},'mac':{'enabled':False,'binding':None}}}
  app_auth,frame_auth=workspace_authorizers(policy=auth.policy,load_bindings=lambda:slots)
  (tmp_path/'source').mkdir();collector,seen=bound(tmp_path/'source',monkeypatch)
  (seen['macro']/'agentos/workstreams/CHAIRMAN-CONTROL-ROOM.md').unlink()
  subprocess.run(['git','-C',str(seen['macro']),'add','.'],check=True,capture_output=True)
  subprocess.run(['git','-C',str(seen['macro']),'commit','-qm','Canonical Office read fixture'],check=True,capture_output=True)
  seen['sha']=subprocess.check_output(['git','-C',str(seen['macro']),'rev-parse','HEAD'],text=True).strip()
  monkeypatch.setattr(plan_source,'_SOURCE_ROOT',seen['code'])
  monkeypatch.setattr(journal_source,'_SOURCE_ROOT',seen['code'])
  def same_child(argv,**limits):
   seen['calls'].append((list(argv),dict(limits)))
   if argv[0]=='git':return _default_packet_runner(argv,**limits)
   owner=direction_source if any(str(a).endswith('agentos_project_direction_entry.py') for a in argv) else journal_source if any(str(a).endswith('agentos_project_journal_entry.py') for a in argv) else plan_source
   child=Path(argv[argv.index('--macro-root')+1]);seen['child_macro']=child
   value=owner.read_from_macro_owner(macro_root=child,expected_macro_sha=argv[argv.index('--expected-macro-sha')+1],work_ref=argv[argv.index('--work-ref')+1],timeout=float(argv[-1]))
   return dict(code=0,stdout=json.dumps(value),timed_out=False,limit_exceeded=False,invalid_utf8=False)
  collector._runner=same_child
  cache=CanonicalFixtureCache(seen['macro'],tmp_path/'cache',mastermind_revision=collector._expected_source_sha)
  direction=collector.project_direction_reader(macro_root=seen['macro'])
  objective=collector.project_plan_reader(macro_root=seen['macro'])
  journal=collector.project_journal_reader(macro_root=seen['macro'])
  provider=lambda rt:WorkspaceReadService(cache=cache.cache,runtime=rt,authorize=frame_auth,armed={},runtime_identity={},project_direction_reader=direction,project_plan_reader=objective,project_journal_reader=journal)
  host=control(tmp_path/'host',short_socket_root,provider);await host.start()
  try:
   app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:now,authorize_principal=app_auth,client=CeoIngressWorkspaceClient(host.ceo_ingress_socket_path)))
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com',headers={'Authorization':'Bearer '+token}) as client:
    output={'schema':'mastermind.office_source_journey.v1','work_ref':WORK,'clock':{'verified_at':now,'verified_expiry':principal.expires_at},'read_context':_context_payload(principal),'provenance':cache.provenance(),'responses':{}}
    for name,route,params in [('programs','programs',None),('objective','project-plan',{'work_ref':WORK}),('direction','project-direction',{'work_ref':WORK}),('journal','project-journal',{'work_ref':WORK})]:
     response=await client.get('/workspace/'+route+'/current',params=params)
     output['responses'][name]={'status':response.status_code,'body':response.json()}
     assert response.status_code==200,response.text
    assert output['responses']['objective']['body']['availability']=='AVAILABLE',output['responses']['objective']
    assert output['responses']['objective']['body']['plan']['objective']=='An authored objective is not accepted Direction.'
    assert output['responses']['direction']['body']['direction']['current']['decision_ref']=='DEC:CURRENT'
    assert output['responses']['journal']['body']['availability']=='AVAILABLE'
    assert output['responses']['journal']['body']['selection']=={'work_ref':WORK}
    assert output['responses']['objective']['body']['source']['commit']==output['responses']['direction']['body']['source']['commit']==seen['sha']
    output['premises']=['ONE canonical temporary Git/Store/CCR source','actual signed Workspace READ/temporary Unix service and actual verifier context','accepted nominal collector with physical fixed child evaluated in-process against captured parser/helper; explicit synthetic source seal/enrollment/kernel','rootless project source; no Mission/native session/Executive send grant supplied; no Runtime Jobs/provider/command effects','no projected row or response rewrite/splice']
    output['export_completed']=True
    if os.environ.get('MMOS_OFFICE_FIXTURE'):Path(os.environ['MMOS_OFFICE_FIXTURE']).write_text(json.dumps(output,ensure_ascii=False,sort_keys=True,indent=2))
  finally:await host.close()
 asyncio.run(run())
