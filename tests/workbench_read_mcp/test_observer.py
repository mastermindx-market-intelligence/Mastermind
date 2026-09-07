import concurrent.futures
import dataclasses
import gc
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from integrations.workbench_read_mcp.observer import ReadScope, ReadRefusal, observe_file

NOW=100000
class FileObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.project=self.root/'project'; self.project.mkdir()
        self.fd=os.open(self.project,os.O_RDONLY|os.O_DIRECTORY)
        s=os.fstat(self.fd)
        self.scope=ReadScope(self.fd,s.st_dev,s.st_ino,'context-a','owner-a','generation-a',('CLAUDE.md','nested/source.py','large.txt'),NOW+1000,'a'*40)
        (self.project/'CLAUDE.md').write_bytes(b'# Project A\nUse exact files.\n')
        (self.project/'nested').mkdir()
        (self.project/'nested/source.py').write_text('value = 1\n',encoding='utf-8')
        self.lookups=0
    def tearDown(self):
        os.close(self.fd); self.tmp.cleanup()
    def resolve(self):
        self.lookups+=1
        return self.scope
    def read(self, **kw):
        return observe_file({'relative_path':'CLAUDE.md',**kw},self.resolve,clock_ms=lambda:NOW)
    def refusal(self,args,code=None,**hooks):
        with self.assertRaises(ReadRefusal) as caught:
            observe_file(args,self.resolve,clock_ms=lambda:NOW,**hooks)
        if code:self.assertEqual(caught.exception.code,code)
        self.assertNotIn(self.tmp.name,str(caught.exception))
        return caught.exception.code
    def test_real_read_hash_and_content(self):
        r=self.read(); raw=(self.project/'CLAUDE.md').read_bytes()
        self.assertEqual(r['content'].encode(),raw)
        self.assertEqual(r['file_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(r['committed_head'],'a'*40)
        self.assertEqual(r['view_kind'],'WORKING_TREE')
        self.assertEqual(r['context_ref'],'context-a')
        self.assertEqual(r['line_start'],0);self.assertEqual(r['line_end'],2)
        self.assertFalse(r['truncated']);self.assertEqual(self.lookups,2)
        self.assertNotIn(self.tmp.name,json.dumps(r))
    def test_line_range_is_exact_and_paged(self):
        r=self.read(start_line=1,max_lines=1)
        self.assertEqual(r['content'],'Use exact files.\n');self.assertIsNone(r['next_line'])
        r=self.read(max_lines=1);self.assertTrue(r['truncated']);self.assertEqual(r['next_line'],1)
    def test_empty_file_success(self):
        (self.project/'CLAUDE.md').write_bytes(b'')
        r=self.read();self.assertEqual(r['content'],'');self.assertEqual(r['total_lines'],0)
    def test_crlf_and_unicode_preserved(self):
        raw='市场\r\n😀 last'.encode();(self.project/'CLAUDE.md').write_bytes(raw)
        r=self.read();self.assertEqual(r['content'].encode(),raw);self.assertEqual(r['total_lines'],2)
    def test_out_of_range_is_explicit(self):
        self.refusal({'relative_path':'CLAUDE.md','start_line':3},'RANGE_OUT_OF_BOUNDS')
    def test_stale_expected_hash_refuses(self):
        self.refusal({'relative_path':'CLAUDE.md','expected_sha256':'0'*64},'PREIMAGE_MISMATCH')
    def test_matching_hash_then_changed_live_bytes(self):
        a=self.read();(self.project/'CLAUDE.md').write_text('changed\n')
        self.assertEqual(self.read()['committed_head'],a['committed_head'])
        self.assertNotEqual(self.read()['file_sha256'],a['file_sha256'])
        self.refusal({'relative_path':'CLAUDE.md','expected_sha256':a['file_sha256']},'PREIMAGE_MISMATCH')
    def test_no_fake_current_index(self):
        r=self.read();self.assertEqual(r['index_status'],'NOT_OBSERVED');self.assertFalse(r['atomic_workspace_snapshot'])
    def test_identity_digest_changes_for_same_bytes_replacement(self):
        a=self.read();p=self.project/'CLAUDE.md';q=self.project/'replacement';q.write_bytes(p.read_bytes());os.replace(q,p)
        b=self.read();self.assertEqual(a['file_sha256'],b['file_sha256']);self.assertNotEqual(a['file_identity_digest'],b['file_identity_digest'])
    def test_missing_is_not_empty_content(self):
        (self.project/'CLAUDE.md').unlink();self.refusal({'relative_path':'CLAUDE.md'},'FILE_UNAVAILABLE')
    def test_unknown_scope_refuses(self):
        self.scope=None;self.refusal({'relative_path':'CLAUDE.md'},'SCOPE_UNAVAILABLE')
    def test_expired_scope_refuses(self):
        self.scope=dataclasses.replace(self.scope,expires_at_ms=NOW)
        self.refusal({'relative_path':'CLAUDE.md'},'SCOPE_EXPIRED')
    def test_wrong_root_identity_refuses(self):
        self.scope=dataclasses.replace(self.scope,root_inode=self.scope.root_inode+1)
        self.refusal({'relative_path':'CLAUDE.md'},'ROOT_IDENTITY_CHANGED')
    def test_undeclared_path_refuses(self):
        self.refusal({'relative_path':'private.txt'},'PATH_NOT_ALLOWED')
    def test_request_authority_fields_rejected_before_lookup(self):
        for key in ['root_fd','root','owner_ref','allowed_paths','scope','host','context_ref']:
            self.refusal({'relative_path':'CLAUDE.md',key:'forged'},'INVALID_REQUEST')
        self.assertEqual(self.lookups,0)
    def test_path_shape_refuses_before_lookup(self):
        for p in ['', '../x','/etc/passwd','nested/../CLAUDE.md','nested//source.py','./CLAUDE.md','C:/x','~/.ssh/key','a\\b','x\0y','x\ny','\ud800']:
            self.refusal({'relative_path':p},'INVALID_REQUEST')
        self.assertEqual(self.lookups,0)
    def test_bounds_have_exact_types(self):
        for key,v in [('start_line',True),('start_line',-1),('max_lines',True),('max_lines',0),('max_lines',513),('max_content_bytes',1.2),('max_content_bytes',32769),('expected_sha256','A'*64)]:
            self.refusal({'relative_path':'CLAUDE.md',key:v},'INVALID_REQUEST')
    def test_path_symlink_refuses(self):
        p=self.project/'CLAUDE.md';p.unlink();p.symlink_to(self.root/'outside')
        (self.root/'outside').write_text('PRIVATE')
        self.refusal({'relative_path':'CLAUDE.md'},'UNSAFE_FILE_TYPE')
    def test_parent_symlink_refuses(self):
        p=self.project/'nested';(p/'source.py').unlink();p.rmdir()
        out=self.root/'other';out.mkdir();(out/'source.py').write_text('PRIVATE');p.symlink_to(out)
        self.refusal({'relative_path':'nested/source.py'},'UNSAFE_DIRECTORY')
    def test_fifo_refuses_without_blocking(self):
        p=self.project/'CLAUDE.md';p.unlink();os.mkfifo(p)
        self.refusal({'relative_path':'CLAUDE.md'},'UNSAFE_FILE_TYPE')
    def test_directory_refuses(self):
        p=self.project/'CLAUDE.md';p.unlink();p.mkdir()
        self.refusal({'relative_path':'CLAUDE.md'},'UNSAFE_FILE_TYPE')
    def test_hardlink_refuses(self):
        os.link(self.project/'CLAUDE.md',self.root/'hardlink')
        self.refusal({'relative_path':'CLAUDE.md'},'UNSAFE_FILE_TYPE')
    def test_invalid_utf8_refuses(self):
        (self.project/'CLAUDE.md').write_bytes(b'\xffSECRET')
        self.refusal({'relative_path':'CLAUDE.md'},'TEXT_UNREPRESENTABLE')
    def test_embedded_nul_refuses(self):
        (self.project/'CLAUDE.md').write_bytes(b'abc\x00data')
        self.refusal({'relative_path':'CLAUDE.md'},'TEXT_UNREPRESENTABLE')
    def test_file_size_bounded(self):
        (self.project/'large.txt').write_bytes(b'x'*(1024*1024+1))
        self.refusal({'relative_path':'large.txt'},'FILE_TOO_LARGE')
    def test_long_line_refuses_not_false_empty_or_partial_line(self):
        (self.project/'CLAUDE.md').write_text('x'*100+'\n')
        self.refusal({'relative_path':'CLAUDE.md','max_content_bytes':20},'LINE_TOO_LARGE')
    def test_multibyte_output_budget_counts_bytes(self):
        (self.project/'CLAUDE.md').write_text('界\n界\n')
        r=self.read(max_content_bytes=4);self.assertEqual(r['content'],'界\n');self.assertTrue(r['truncated']);self.assertEqual(r['next_line'],1)
    def test_regular_swap_before_open_detected(self):
        def swap():
            p=self.project/'CLAUDE.md';q=self.project/'replacement';q.write_bytes(p.read_bytes());os.replace(q,p)
        self.refusal({'relative_path':'CLAUDE.md'},'FILE_IDENTITY_CHANGED',_before_file_open=swap)
    def test_symlink_swap_before_open_refuses(self):
        def swap():
            p=self.project/'CLAUDE.md';p.unlink();p.symlink_to('/etc/passwd')
        self.refusal({'relative_path':'CLAUDE.md'},_before_file_open=swap)
    def test_fifo_swap_before_open_refuses_without_blocking(self):
        def swap():
            p=self.project/'CLAUDE.md';p.unlink();os.mkfifo(p)
        self.refusal({'relative_path':'CLAUDE.md'},_before_file_open=swap)
    def test_parent_rename_detected_before_exposing_bytes(self):
        def swap():
            os.rename(self.project/'nested',self.project/'moved')
            (self.project/'nested').mkdir();(self.project/'nested/source.py').write_text('other')
        self.refusal({'relative_path':'nested/source.py'},'ANCESTRY_CHANGED',_before_final=swap)
    def test_file_change_after_read_detected(self):
        self.refusal({'relative_path':'CLAUDE.md'},'FILE_CHANGED',_before_final=lambda:(self.project/'CLAUDE.md').write_text('changed'))
    def test_growing_file_stops_at_limit(self):
        p=self.project/'large.txt';p.write_bytes(b'x'*65536);calls=[]
        def grow(n):
            calls.append(n)
            if len(calls)==1:
                with p.open('ab') as f:f.write(b'x'*(1024*1024))
        self.refusal({'relative_path':'large.txt'},_between_chunks=grow)
        self.assertLessEqual(len(calls),18)
    def test_scope_revoked_after_read_suppresses_content(self):
        self.refusal({'relative_path':'CLAUDE.md'},'SCOPE_UNAVAILABLE',_before_final=lambda:setattr(self,'scope',None))
    def test_scope_generation_change_suppresses_content(self):
        self.refusal({'relative_path':'CLAUDE.md'},'SCOPE_CHANGED',_before_final=lambda:setattr(self,'scope',dataclasses.replace(self.scope,generation='new')))
    def test_unrelated_directory_changes_do_not_invalidate_file(self):
        r=observe_file({'relative_path':'CLAUDE.md'},self.resolve,clock_ms=lambda:NOW,_before_final=lambda:(self.project/'unrelated').write_text('x'))
        self.assertIn('# Project A',r['content'])
    def test_scope_callback_error_sanitized(self):
        def bad():raise RuntimeError('secret/root/path')
        with self.assertRaises(ReadRefusal) as e:observe_file({'relative_path':'CLAUDE.md'},bad,clock_ms=lambda:NOW)
        self.assertEqual(str(e.exception),'SCOPE_UNAVAILABLE')
    def test_two_concurrent_scopes_never_share_current_root(self):
        other=self.root/'project-b';other.mkdir();(other/'CLAUDE.md').write_text('# Project B\n')
        fd=os.open(other,os.O_RDONLY|os.O_DIRECTORY);s=os.fstat(fd)
        b=dataclasses.replace(self.scope,root_fd=fd,root_inode=s.st_ino,root_device=s.st_dev,context_ref='context-b')
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(observe_file,{'relative_path':'CLAUDE.md'},lambda s=s:s,clock_ms=lambda:NOW) for s in (self.scope,b)*10]
                results=[f.result(timeout=2) for f in futures]
            for i,r in enumerate(results):self.assertEqual(r['context_ref'],'context-a' if i%2==0 else 'context-b');self.assertIn('Project A' if i%2==0 else 'Project B',r['content'])
        finally:os.close(fd)
    def test_no_descriptor_leak_on_success_or_refusal(self):
        opened=[];closed=[];orig_open=os.open;orig_close=os.close;orig_dup=os.dup
        def op(*a,**kw):fd=orig_open(*a,**kw);opened.append(fd);return fd
        def dup(*a,**kw):fd=orig_dup(*a,**kw);opened.append(fd);return fd
        def cl(fd):closed.append(fd);return orig_close(fd)
        with patch('integrations.workbench_read_mcp.observer.os.open',side_effect=op),patch('integrations.workbench_read_mcp.observer.os.close',side_effect=cl),patch('integrations.workbench_read_mcp.observer.os.dup',side_effect=dup):
            self.read();self.refusal({'relative_path':'CLAUDE.md','expected_sha256':'0'*64})
        self.assertEqual(sorted(opened),sorted(closed))
        os.fstat(self.fd)
    def test_platform_without_required_flags_refuses(self):
        with patch('integrations.workbench_read_mcp.observer.os.O_NOFOLLOW',0):self.refusal({'relative_path':'CLAUDE.md'},'PLATFORM_UNQUALIFIED')

    def test_many_short_lines_do_not_materialize_line_array(self):
        # A 1MiB file of newlines must not create a million-element line list.
        import tracemalloc
        (self.project/'large.txt').write_bytes(b'\n'*(1024*1024))
        tracemalloc.start()
        try:
            r=observe_file({'relative_path':'large.txt','start_line':999999,'max_lines':2},self.resolve,clock_ms=lambda:NOW)
            _current,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        self.assertEqual(r['content'],'\n\n');self.assertEqual(r['total_lines'],1024*1024)
        self.assertLess(peak,8*1024*1024)
    def test_truncated_file_during_read_is_refused(self):
        p=self.project/'large.txt';p.write_bytes(b'x'*100000)
        self.refusal({'relative_path':'large.txt'},'FILE_CHANGED',_between_chunks=lambda n:p.write_bytes(b'short') if n==65536 else None)
    def test_expiry_during_read_is_refused(self):
        times=iter([NOW,NOW+2000])
        with self.assertRaises(ReadRefusal) as e:observe_file({'relative_path':'CLAUDE.md'},self.resolve,clock_ms=lambda:next(times))
        self.assertEqual(e.exception.code,'SCOPE_EXPIRED')
    def test_scope_extra_access_change_refuses_publication(self):
        self.refusal({'relative_path':'CLAUDE.md'},'SCOPE_CHANGED',_before_final=lambda:setattr(self,'scope',dataclasses.replace(self.scope,allowed_paths=self.scope.allowed_paths+('extra',))))
    def test_whole_digest_is_not_just_slice_digest(self):
        r=self.read(max_lines=1)
        self.assertNotEqual(r['file_sha256'],hashlib.sha256(r['content'].encode()).hexdigest())
    def test_filename_percent_encoding_is_literal_not_decoded(self):
        name='encoded%2f..%2ftext';(self.project/name).write_text('literal')
        self.scope=dataclasses.replace(self.scope,allowed_paths=(name,))
        r=observe_file({'relative_path':name},self.resolve,clock_ms=lambda:NOW)
        self.assertEqual(r['content'],'literal')
    def test_socket_refuses_without_connecting(self):
        p=self.project/'CLAUDE.md';p.unlink()
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(p));self.refusal({'relative_path':'CLAUDE.md'},'UNSAFE_FILE_TYPE')

if __name__=='__main__':unittest.main()
