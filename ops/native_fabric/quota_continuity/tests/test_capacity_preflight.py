"""Real HTTP rejection through actual provider wrapper branches; no real keys."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'candidate'),str(ROOT/'source')]
import capacity_preflight as probe
import provider_outcome as outcome

class Preflight(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.ext=self.root/'ext';self.ext.mkdir()
        self.bin=self.root/'bin';self.bin.mkdir();self.serial=0;self.requests=[];self.reply_delay=0
        self.reply=(429,{'type':'error','error':{'type':'rate_limit_error','message':'fixture only'}},{'Retry-After':'17'})
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                owner.requests.append((self.path,json.loads(body)))
                status,value,headers=owner.reply
                raw=json.dumps(value).encode()
                self.send_response(status)
                for k,v in headers.items():self.send_header(k,v)
                self.send_header('Content-Length',str(len(raw)));self.end_headers()
                time.sleep(owner.reply_delay)
                try:self.wfile.write(raw)
                except BrokenPipeError:pass
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/anthropic'
        for n in ('capacity_preflight.py','provider_outcome.py','sub.sh','glm_bound_claude.py'):
            shutil.copyfile(ROOT/'candidate'/n,self.ext/n)
        shutil.copyfile(ROOT/'source'/'model_tier.py',self.ext/'model_tier.py')
        (self.ext/'hosts.json').write_text(json.dumps({'fixture':{'local':True,'hostnames':[]}}))
        (self.ext/'slot.py').write_text('import os,sys\na=sys.argv[sys.argv.index("--")+1:]\nos.execvp(a[0],a)\n')
        (self.ext/'glm_keys.py').write_text('def accounts():return []\ndef selected_account_key(*args):return "inert-fixture-key"\n')
        self.script(self.ext/'studio_mcp_projection.sh','#!/bin/sh\nprintf \'{"mcpServers":{}}\\n\'\n')
        # Intercept only the exact incumbent key/base-url file reader. No actual
        # credential file is read and the user's HOME is never replaced.
        self.script(self.bin/'python3',f'''#!{sys.executable}
import os,sys
if len(sys.argv)>3 and sys.argv[1]=='-c' and sys.argv[-1].endswith('/.minimax/config.json'):
 print(os.environ['FIXTURE_ENDPOINT'] if 'anthropic_base_url' in sys.argv[2] else 'inert-fixture-key');sys.exit(0)
os.execv({sys.executable!r},[{sys.executable!r}]+sys.argv[1:])
''')
        self.script(self.bin/'claude',f'''#!{sys.executable}
import os,json
from pathlib import Path
Path(os.environ['FIXTURE_CLI_STARTED']).write_text('started')
print(json.dumps({{'type':'result','subtype':'success','is_error':False,'result':'STATUS: COMPLETE\\n'}}))
''')

    def script(self,path,source):path.write_text(source);path.chmod(0o700)

    def env(self):
        self.serial+=1
        # Strip the ambient host-floor overrides the host may have exported.
        # The production admission code reads these four env vars on every
        # lane_runtime call; an inherited host setting turns this fixture's
        # commissioned lane into a designed host_*_unknown refusal regardless
        # of provider reply. The four are forced to neutral defaults below so
        # the fixture child environment is independent of the host.
        ambient_floors = (
            'LANE_MIN_FREE_DISK_GB',
            'LANE_MIN_FREE_MEM_GB',
            'LANE_MAX_CPU_TCTL_C',
            'LANE_NICE',
        )
        base = {key: value for key, value in os.environ.items()
                if key not in ambient_floors}
        value=dict(base,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],
            POOL_CAPACITY_PREFLIGHT='1',REMOTE_SUB_RUN_ID='fixture-'+str(self.serial),
            POOL_OUTCOME_FILE=str(self.root/('fixture-'+str(self.serial)+'.provider.json')),
            POOL_ORCHESTRATOR_ID='root',POOL_PARENT_RUN_ID='parent',POOL_LEASE_ID='lease',
            POOL_ACCOUNT='account',LANE_REMOTE_HOST='fixture',LANE_LEASED='1',
            POOL_TASK_CLASS='mechanical',SUPPORT_DIGEST='a'*64,
            ANTHROPIC_BASE_URL=self.url,ANTHROPIC_AUTH_TOKEN='inert-fixture-key',
            FIXTURE_ENDPOINT=self.url,FIXTURE_CLI_STARTED=str(self.root/'cli-started'),
            # Neutral admission floors so an ambient LANE_* host floor can
            # never cause host_disk_unknown / host_memory_below_floor /
            # host_temperature_at_or_above_limit inside this fixture.
            LANE_MIN_FREE_DISK_GB='0',
            LANE_MIN_FREE_MEM_GB='0',
            LANE_MAX_CPU_TCTL_C='0',
            LANE_NICE='10')
        return value

    def launch(self,provider):
        env=self.env()
        marker=Path(env['FIXTURE_CLI_STARTED']);marker.unlink(missing_ok=True)
        if provider=='minimax':
            argv=['/bin/bash',str(self.ext/'sub.sh'),'minimax','PRIVATE TASK MUST NEVER ENTER PROBE',str(self.root),'MiniMax-M3']
        else:
            argv=[sys.executable,str(self.ext/'glm_bound_claude.py'),str(self.root),'glm-5.3',
                  'PRIVATE TASK MUST NEVER ENTER PROBE','','{"mcpServers":{}}','2']
        result=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=30)
        return result,env,marker

    def test_both_actual_wrapper_branches_stop_before_task_cli_on_capacity(self):
        for provider in ('minimax','glm'):
            with self.subTest(provider=provider):
                result,env,marker=self.launch(provider)
                self.assertEqual(result.returncode,75,result.stderr)
                self.assertFalse(marker.exists())
                receipt=Path(env['POOL_OUTCOME_FILE']).with_suffix('.preflight.json')
                value=json.loads(receipt.read_text())
                self.assertFalse(value['pre_task_evidence']['task_cli_started'])
                self.assertEqual(value['account'],'account')
                self.assertNotIn('inert-fixture-key',receipt.read_text()+result.stderr+result.stdout)
                if provider=='minimax':
                    published=json.loads(Path(env['POOL_OUTCOME_FILE']).read_text())
                    self.assertEqual(published['kind'],'rate_limit')
                    self.assertEqual(published['pre_task_evidence'],value['pre_task_evidence'])
        self.assertEqual(len(self.requests),2)
        for path,body in self.requests:
            self.assertEqual(path,'/anthropic/v1/messages');self.assertEqual(body['max_tokens'],1)
            self.assertNotIn('PRIVATE TASK',json.dumps(body));self.assertNotIn('tools',body)

    def test_success_and_indeterminate_continue_original_cli_once(self):
        for status,value in [(200,{'type':'message'}),(503,{'error':{'type':'api_error'}}),
                             (429,{'error':{'type':'unknown'}}),(400,{'error':{'type':'invalid_request_error'}})]:
            self.reply=(status,value,{})
            before=len(self.requests)
            result,env,marker=self.launch('minimax')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(marker.exists());self.assertEqual(len(self.requests),before+1)
            self.assertFalse(Path(env['POOL_OUTCOME_FILE']).with_suffix('.preflight.json').exists())

    def test_definitive_auth_refusal_is_not_capacity_and_does_not_launch(self):
        self.reply=(401,{'error':{'type':'authentication_error'}},{})
        result,env,marker=self.launch('minimax')
        self.assertEqual(result.returncode,78,result.stderr);self.assertFalse(marker.exists())
        value=json.loads(Path(env['POOL_OUTCOME_FILE']).read_text())
        self.assertEqual(value['kind'],'authentication');self.assertFalse(value['initial_rejection'])

    def test_redirect_never_forwards_credential_and_probe_is_opt_in(self):
        self.reply=(307,{}, {'Location':self.url+'/redirected'})
        result,env,marker=self.launch('minimax')
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(len(self.requests),1)
        env.pop('POOL_CAPACITY_PREFLIGHT')
        self.assertIsNone(probe.check(env,'minimax','MiniMax-M3',self.ext/'sub.sh'))
        self.assertEqual(len(self.requests),1)

    def test_vendor_capacity_codes_and_restrictions_are_distinct(self):
        for provider,code,kind,rc in [('glm','1308','quota_exhausted',75),
                                     ('glm','1310','quota_exhausted',75),
                                     ('minimax','2056','quota_exhausted',75),
                                     ('glm','1313','permission',78),
                                     ('glm','1113','billing',78),
                                     ('glm','1318','budget_limit',78)]:
            with self.subTest(provider=provider,code=code):
                # Numeric restriction must override a generic compatibility type.
                self.reply=(429,{'error':{'type':'rate_limit_error','code':code}},{})
                result,env,marker=self.launch(provider)
                self.assertEqual(result.returncode,rc,result.stderr);self.assertFalse(marker.exists())
                value=json.loads(Path(env['POOL_OUTCOME_FILE']).with_suffix('.preflight.json').read_text())
                self.assertEqual(value['kind'],kind)
                self.assertEqual(value['initial_rejection'],rc==75)
        self.reply=(429,{'error':{'type':'rate_limit_error','code':'999999'}},{})
        result,env,marker=self.launch('glm')
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(marker.exists())

    def test_whole_response_deadline_proceeds_without_retry(self):
        self.reply_delay=0.25
        start=time.monotonic()
        with patch.object(probe,'TIMEOUT',0.05):
            self.assertIsNone(probe.check(self.env(),'minimax','MiniMax-M3',self.ext/'sub.sh'))
        self.assertLess(time.monotonic()-start,0.2)
        self.assertEqual(len(self.requests),1)

if __name__=='__main__':unittest.main()
