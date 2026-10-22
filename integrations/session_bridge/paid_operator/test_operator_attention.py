import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fabric_operator_stop import decide,read_summaries,persist_attention
from fabric_operator_client import prepare_claude_hook,grok_hook_toml
from test_operator_admission_boundary import AdmissionBoundary

class Attention(unittest.TestCase):
 def test_receipt_directory_synced_before_attention_is_allowed(self):
  with tempfile.TemporaryDirectory() as temp:
   import os,stat
   calls=[];real=os.fsync
   def sync(fd):calls.append(stat.S_ISDIR(os.fstat(fd).st_mode));real(fd)
   with patch('fabric_operator_stop.os.fsync',side_effect=sync):
    self.assertTrue(persist_attention(Path(temp),'op','a'*64,{'root':'root'}))
   self.assertEqual(calls,[False,True])
   self.assertFalse(persist_attention(Path(temp),'op','a'*64,{'root':'root'}))
 def test_directory_sync_failure_keeps_receipt_and_does_not_allow_attention(self):
  with tempfile.TemporaryDirectory() as temp:
   import os,stat
   real=os.fsync
   def sync(fd):
    if stat.S_ISDIR(os.fstat(fd).st_mode):raise OSError('injected directory sync failure')
    real(fd)
   with patch('fabric_operator_stop.os.fsync',side_effect=sync):
    with self.assertRaises(OSError):persist_attention(Path(temp),'op','a'*64,{'root':'root'})
   self.assertEqual(len(list(Path(temp).glob('*.json'))),1)
   self.assertFalse(persist_attention(Path(temp),'op','a'*64,{'root':'root'}))
 def test_fixed_stable_lanes_symlink_remains_usable(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp);(path/'stable').mkdir();(path/'lanes').symlink_to(path/'stable')
   self.assertTrue(persist_attention(path/'lanes','op','a'*64,{'root':'root'}))

 def test_ready_exact_ids_and_digest_only(self):
  signature,result=decide({'root':'root','parent':'op','children':[{'run_id':'leaf','result_available':True,'sha256':'a'*64,'bytes':10}]},'root','op')
  self.assertEqual(len(signature),64);self.assertEqual(result['decision'],'block');self.assertIn('leaf',result['reason']);self.assertNotIn('token',result['reason'])
 def test_wrong_parent_or_missing_digest_refuses(self):
  for doc in [{'root':'root','parent':'other','children':[]},{'root':'root','parent':'op','children':[{'run_id':'leaf','result_available':True}]}]:
   with self.assertRaises(ValueError):decide(doc,'root','op')
 def test_no_children_means_no_continuation(self):
  self.assertEqual(decide({'root':'root','parent':'op','children':[]},'root','op'),(None,None))
 def test_pending_is_not_ready_or_retry(self):
  _,value=decide({'root':'root','parent':'op','children':[{'run_id':'leaf','result_available':False,'state':'ACTIVE_OR_WAITING'}]},'root','op')
  self.assertIn('"ready":false',value['reason']);self.assertIn('Do not relaunch',value['reason'])
 def test_new_plugin_adds_hook_without_replacing_profile(self):
  with tempfile.TemporaryDirectory() as temp:
   here=Path(temp);(here/'lanes').mkdir();env={'FABRIC_OPERATOR_CAPABILITY':'a'*64,'REMOTE_SUB_RUN_ID':'operator'}
   args=prepare_claude_hook(here,env);self.assertEqual(args[0],'--plugin-dir')
   config=json.loads((Path(args[1])/'hooks/hooks.json').read_text());self.assertIn('Stop',config['hooks']);self.assertNotIn('a'*64,json.dumps(config))
   self.assertIn('[[hooks.Stop]]',grok_hook_toml(here,env));self.assertEqual(prepare_claude_hook(here,{}),[])
 def test_http_reader_uses_only_exact_endpoint_and_closed_tool(self):
  class Response:
   def __init__(self,body,headers=None):self.body=body;self.headers=headers or {}
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def read(self,n):return self.body[:n]
  class Opener:
   def __init__(self):self.requests=[]
   def open(self,req,timeout):
    self.requests.append(req);assert req.full_url=='https://m2studio.taila6eca1.ts.net/studio-fabric';assert req.get_header('X-mastermind-fabric-operator')=='a'*64
    if req.method=='DELETE':return Response(b'')
    body=json.loads(req.data)
    if body['method']=='initialize':return Response(b'{"result":{}}',{'Mcp-Session-Id':'bound'})
    if body['method']=='notifications/initialized':return Response(b'')
    assert body['params']=={'name':'fabric_operator_returns','arguments':{}}
    return Response(json.dumps({'result':{'content':[{'type':'text','text':'{"root":"root","parent":"op","children":[]}'}]}}).encode())
  op=Opener();self.assertEqual(read_summaries('a'*64,opener=op)['parent'],'op');self.assertEqual(len(op.requests),4)

class Consumption(AdmissionBoundary):
 def test_ack_exact_digest_closes_attention_without_acceptance(self):
  state=dict(run_id='leaf',state='TERMINAL',result_available=True,root_id='root',parent_run_id='operator',rc=0)
  fake=type('Fake',(),{'inspect_run':staticmethod(lambda _:state),'read_result':staticmethod(lambda *a,**k:b'ok')})
  with patch.dict('sys.modules',{'fabric_task':fake}):
   before=self.o.returns(self.cap['token']);self.assertEqual(len(before['children']),1)
   with self.assertRaises(ValueError):self.o.acknowledge(self.cap['token'],'leaf','0'*64)
   receipt=self.o.acknowledge(self.cap['token'],'leaf',before['children'][0]['sha256']);self.assertFalse(receipt['acceptance_recorded'])
   self.assertEqual(self.o.returns(self.cap['token'])['children'],[])
if __name__=='__main__':unittest.main()
