"""Canonical Direction + Programs through signed READ/real temporary Unix owner.
No projected rows are edited. In-process physical child/host seals and enrollment
reuse the accepted installed-reader fixture premises; no live provider effects.
"""
import asyncio,json,os,subprocess
from pathlib import Path
import httpx
from tests.test_installed_project_direction_context import bound
from tests.test_agentos_project_direction_source import WORK
from tests.test_workspace_project_direction_http import rsa_key,short_socket_root
from tests.test_workspace_read_app import _authenticator,_workspace_token,NOW
from tests.test_workspace_result_socket import control
from tests.fresh_conversation_full_cache import CanonicalFixtureCache
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA,principal_frame,workspace_authorizers
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig,create_workspace_app
from control_plane.workspace_read_service import WorkspaceReadService

def test_whole_canonical_direction_and_programs_owner(tmp_path,monkeypatch,rsa_key,short_socket_root):
 async def run():
  auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
  principal=await auth.verify_authorization_header('Bearer '+token,now=NOW)
  slots={'schema':BINDINGS_SCHEMA,'profiles':{'web':{'enabled':True,'binding':dict(principal_frame(principal),permission_digest='a'*64)},'mac':{'enabled':False,'binding':None}}}
  app_auth,frame_auth=workspace_authorizers(policy=auth.policy,load_bindings=lambda:slots)
  (tmp_path/'source').mkdir();collector,seen=bound(tmp_path/'source',monkeypatch)
  # Remove only the earlier fixture's invalid, unused bootstrap input before
  # this NEW configured canonical fixture baseline is committed/composed.
  (seen['macro']/'agentos/workstreams/CHAIRMAN-CONTROL-ROOM.md').unlink()
  subprocess.run(['git','-C',str(seen['macro']),'add','.'],check=True,capture_output=True)
  subprocess.run(['git','-C',str(seen['macro']),'commit','-qm','Canonical whole Direction fixture'],check=True,capture_output=True)
  seen['sha']=subprocess.check_output(['git','-C',str(seen['macro']),'rev-parse','HEAD'],text=True).strip()
  cache=CanonicalFixtureCache(seen['macro'],tmp_path/'cache',mastermind_revision=collector._expected_source_sha)
  reader=collector.project_direction_reader(macro_root=seen['macro'])
  provider=lambda rt:WorkspaceReadService(cache=cache.cache,runtime=rt,authorize=frame_auth,armed={},runtime_identity={},project_direction_reader=reader)
  host=control(tmp_path/'host',short_socket_root,provider);await host.start()
  try:
   app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,authorize_principal=app_auth,client=CeoIngressWorkspaceClient(host.ceo_ingress_socket_path)))
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com',headers={'Authorization':'Bearer '+token}) as client:
    programs=await client.get('/workspace/programs/current');assert programs.status_code==200,programs.text
    direction=await client.get('/workspace/project-direction/current',params={'work_ref':WORK});assert direction.status_code==200,direction.text
    p,d=programs.json(),direction.json()
    assert [row['work_ref'] for row in p['control_room']['work']]==[WORK]
    assert d['source']['commit']==seen['sha'] and d['direction']['current']['decision_ref']=='DEC:CURRENT'
    assert len(d['direction']['history']['revisions'])==1
    assert 'PRIVATE_DEC_BODY' not in direction.text
    foreign=await client.get('/workspace/project-direction/current',params={'work_ref':'WS:FOREIGN'})
    assert foreign.status_code==404 and d['direction']['current']['answer'] not in foreign.text
    slots['profiles']['web']['enabled']=False
    denied=await client.get('/workspace/project-direction/current',params={'work_ref':WORK});assert denied.status_code==403
    output={'work_ref':WORK,'programs':p,'direction':d,'foreign':foreign.json(),'provenance':cache.provenance(),
      'premises':['accepted nominal installed collector; physical Direction child evaluated in-process over captured code','actual signed Workspace READ and temporary Unix service; inert enrolled bindings and source seal','no projected row mutation; no native session/provider/grant/write operation']}
    if os.environ.get('MMOS_DIRECTION_FIXTURE'):Path(os.environ['MMOS_DIRECTION_FIXTURE']).write_text(json.dumps(output,ensure_ascii=False,sort_keys=True))
  finally:await host.close()
 asyncio.run(run())
