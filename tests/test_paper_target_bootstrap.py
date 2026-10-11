"""Synthetic target-binding regression. Never contacts Paper or a live service."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('target_bootstrap_bridge', ROOT / 'integrations/paper_desktop/bridge.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
FILE = '01M2WGNCX9475G79JRKJTCM08P'
OTHER = '01M3NQQ5KHTEZ50AGPT3RAD4BN'
BINDING = {'schema':'mastermind.paper_execution_binding.v1','host_ref':'host-'+'1'*64,'service_ref':'2'*64,'runtime_revision':'3'*40,'bridge_sha256':'4'*64}

class Fake:
    def __init__(self):
        self.calls = []
        self.server = {'name':'fixture','version':'0'}
        self.revision = 1
        self.wrong_first = self.wrong_second = self.error = self.timeout = False
        self.reads = 0
    def initialize(self):
        return {}
    def catalog(self):
        return {n:{'name':n,'inputSchema':{'type':'object'}} for n in b.READ_TOOLS | b.EDIT_TOOLS}
    def call(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == 'get_basic_info':
            if not args.get('fileId'):
                return {'isError':True,'content':[{'type':'text','text':'Open a Paper file to use this tool.'}]}
            self.reads += 1
            if self.error:
                return {'isError':True,'content':[]}
            fid = OTHER if ((self.wrong_first and self.reads == 1) or (self.wrong_second and self.reads == 2)) else args['fileId']
            page = args.get('pageId','p-default')
            header = {'file':{'id':fid,'name':'MASTERMIND PAGES'},'contentHash':{'tokens':'fixture'}}
            detail = {'fileName':'MASTERMIND PAGES','pageName':page,'pageId':page,'nodeCount':self.revision,'artboards':[]}
            return {'content':[{'type':'text','text':json.dumps(header)},{'type':'text','text':json.dumps(detail)}]}
        if name in b.EDIT_TOOLS:
            self.revision += 1
            if self.timeout:
                raise TimeoutError('synthetic response loss after a possible effect')
        return {'content':[{'type':'text','text':'ok'}]}

class TargetBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = Fake()
    def tearDown(self):
        self.tmp.cleanup()
    def run_bridge(self, action='read', **kw):
        args = dict(tool='get_basic_info',arguments={'fileId':FILE},client=self.client,lock_root=Path(self.tmp.name),_server_pin=None,_catalog_pin=None)
        args.update(kw)
        return b.execute(action, **args)
    def edit(self, guard, **kw):
        return self.run_bridge('edit',tool='set_text_content',arguments={'fileId':FILE,'updates':[]},expected_snapshot=guard,operation_id='bootstrap-synthetic-1',allow_write=True,**kw)
    def test_default_context_failure_is_reproduced(self):
        with self.assertRaisesRegex(b.Refusal,'DOCUMENT_UNAVAILABLE'):
            self.run_bridge('status')
        self.assertEqual(self.client.calls,[('get_basic_info',{})])
    def test_explicit_read_bootstraps_without_active_lookup(self):
        result = self.run_bridge()
        self.assertEqual(result['state'],'OBSERVED')
        self.assertIn('document',result)
        self.assertEqual(result['document']['identity'],{'kind':'file-id','id':FILE})
        self.assertTrue(result['write_schema']['accepted_for_write'])
        self.assertTrue(all(args.get('fileId') == FILE for _,args in self.client.calls))
    def test_read_snapshot_supports_existing_guarded_edit(self):
        result = self.run_bridge()
        self.assertIn('document',result)
        receipt = self.edit(result['document']['snapshot_sha256'])
        self.assertEqual(receipt['state'],'APPLIED_RESPONSE_OBSERVED')
        self.assertEqual(sum(n == 'set_text_content' for n,_ in self.client.calls),1)
        self.assertFalse(any(n == 'open_file' or not a.get('fileId') for n,a in self.client.calls))
    def test_page_read_keeps_page_but_returns_file_guard(self):
        result = self.run_bridge(arguments={'fileId':FILE,'pageId':'p-S-1'})
        self.assertIn('document',result)
        self.assertEqual(json.loads(result['result']['content'][1]['text'])['pageId'],'p-S-1')
        self.assertEqual(result['document']['basic_info']['pageId'],'p-default')
        self.assertEqual(self.edit(result['document']['snapshot_sha256'])['state'],'APPLIED_RESPONSE_OBSERVED')
    def test_wrong_first_response_cannot_mint_guard(self):
        self.client.wrong_first = True
        with self.assertRaisesRegex(b.Refusal,'FILE_ID_MISMATCH'):
            self.run_bridge()
    def test_wrong_snapshot_response_cannot_mint_guard(self):
        self.client.wrong_second = True
        with self.assertRaisesRegex(b.Refusal,'FILE_ID_MISMATCH'):
            self.run_bridge()
    def test_error_read_returns_no_snapshot(self):
        self.client.error = True
        result = self.run_bridge()
        self.assertEqual(result['state'],'TOOL_ERROR')
        self.assertNotIn('document',result)
    def test_unbound_or_other_read_does_not_mint_guard(self):
        result = self.run_bridge(arguments={})
        self.assertNotIn('document',result)
        result = self.run_bridge(tool='get_children',arguments={'fileId':FILE,'nodeId':'example'})
        self.assertNotIn('document',result)
    def test_host_binding_survives_and_cross_host_edit_refuses(self):
        result = self.run_bridge(execution_binding=BINDING)
        self.assertIn('document',result)
        self.assertEqual(result['document']['execution_binding'],BINDING)
        other = dict(BINDING,host_ref='host-'+'9'*64)
        with self.assertRaisesRegex(b.Refusal,'DOCUMENT_CHANGED'):
            self.edit(result['document']['snapshot_sha256'],execution_binding=other)
        self.assertFalse(any(n == 'set_text_content' for n,_ in self.client.calls))
    def test_stale_target_snapshot_still_refuses_before_edit(self):
        result = self.run_bridge()
        self.assertIn('document',result)
        self.client.revision += 1
        with self.assertRaisesRegex(b.Refusal,'DOCUMENT_CHANGED'):
            self.edit(result['document']['snapshot_sha256'])
        self.assertFalse(any(n == 'set_text_content' for n,_ in self.client.calls))
    def test_unreviewed_schema_read_does_not_authorize_write(self):
        result = self.run_bridge(_catalog_pin='0'*64)
        self.assertIn('document',result)
        self.assertFalse(result['write_schema']['accepted_for_write'])
        with self.assertRaisesRegex(b.Refusal,'UPSTREAM_SCHEMA_UNREVIEWED'):
            self.edit(result['document']['snapshot_sha256'],_catalog_pin='0'*64)
        self.assertFalse(any(n == 'set_text_content' for n,_ in self.client.calls))
    def test_lost_edit_response_remains_unknown_without_retry(self):
        result = self.run_bridge()
        self.assertIn('document',result)
        self.client.timeout = True
        receipt = self.edit(result['document']['snapshot_sha256'])
        self.assertEqual(receipt['state'],'EFFECT_UNKNOWN')
        self.assertFalse(receipt['retry_allowed'])
        self.assertEqual(sum(n == 'set_text_content' for n,_ in self.client.calls),1)

if __name__ == '__main__':
    unittest.main()
