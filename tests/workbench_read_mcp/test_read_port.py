"""Real-filesystem port tests. Constructed callers are fixtures, not real logins."""
from __future__ import annotations
import asyncio, dataclasses, hashlib, os, pathlib, tempfile, unittest
from integrations.workbench_read_mcp.app import ReadCaller, ProjectReadRefused
from integrations.workbench_read_mcp.observer import ReadScope
from integrations.workbench_read_mcp.read_port import ProjectReadBinding, create_descriptor_read_port

class DescriptorPortTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='mmx-descriptor-port-')
        self.root=pathlib.Path(self.temp.name); self.clock=100000; self.io_calls=0; self.bind_calls=0
        self.active=True;self.mode='normal';self.fds=[];self.bindings={}
        self.return_transform=lambda result:result
        self.caller_a=ReadCaller('a'*64,'client-a','https://workbench.example/mcp',('workbench.read',),200)
        self.caller_b=ReadCaller('b'*64,'client-b','https://workbench.example/mcp',('workbench.read',),200)
        for project,caller in [('alpha',self.caller_a),('beta',self.caller_b)]:
            path=self.root/project;path.mkdir();(path/'CLAUDE.md').write_bytes((project+' instructions\nsecond line\r\n').encode())
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(fd);s=os.fstat(fd)
            scope=ReadScope(fd,s.st_dev,s.st_ino,'context-'+project,'owner-'+project,'generation-1',('CLAUDE.md',),190000,'1'*40)
            self.bindings[(caller.subject_digest,project)]=ProjectReadBinding(caller,project,scope)
        def resolve(caller,project):
            self.bind_calls+=1
            if not self.active:raise ProjectReadRefused()
            return self.bindings.get((caller.subject_digest,project))
        async def io(operation):
            self.io_calls+=1
            if self.mode=='revoke-before-io':self.active=False
            if self.mode=='change-before-io':
                b=self.bindings[('a'*64,'alpha')]
                self.bindings[('a'*64,'alpha')]=dataclasses.replace(b,scope=dataclasses.replace(b.scope,generation='generation-2'))
            result = await asyncio.to_thread(operation)
            if self.mode == 'revoke-after-io':self.active=False
            if self.mode == 'change-after-io':
                b=self.bindings[('a'*64,'alpha')]
                self.bindings[('a'*64,'alpha')]=dataclasses.replace(b,scope=dataclasses.replace(b.scope,generation='generation-2'))
            return self.return_transform(result)
        self.resolve=resolve
        self.port=create_descriptor_read_port(resolve_binding=resolve,clock_ms=lambda:self.clock,run_io=io)

    async def asyncTearDown(self):
        for fd in self.fds:os.close(fd)
        self.temp.cleanup()

    async def read(self,caller=None,**kwargs):
        request={'project_ref':'alpha','relative_path':'CLAUDE.md'};request.update(kwargs)
        return await self.port(caller or self.caller_a,request)

    async def test_real_descriptor_content_and_project_identity(self):
        r=await self.read();self.assertEqual(r['content'],'alpha instructions\nsecond line\r\n')
        self.assertEqual(r['project_ref'],'alpha');self.assertEqual(r['context_ref'],'context-alpha')
        self.assertEqual(r['file_sha256'],hashlib.sha256((self.root/'alpha/CLAUDE.md').read_bytes()).hexdigest())
        self.assertEqual(r['index_status'],'NOT_OBSERVED');self.assertFalse(r['atomic_workspace_snapshot'])

    async def test_two_concurrent_callers_keep_actual_roots(self):
        a,b=await asyncio.gather(self.read(),self.read(self.caller_b,project_ref='beta'))
        self.assertTrue(a['content'].startswith('alpha'));self.assertTrue(b['content'].startswith('beta'))
        self.assertNotEqual(a['file_identity_digest'],b['file_identity_digest'])

    async def test_cross_project_refused_before_io(self):
        with self.assertRaises(ProjectReadRefused):await self.read(project_ref='beta')
        self.assertEqual(self.io_calls,0)

    async def test_binding_for_another_caller_is_refused_before_io(self):
        a=self.bindings[('a'*64,'alpha')];self.bindings[('a'*64,'alpha')]=dataclasses.replace(a,caller=self.caller_b)
        with self.assertRaises(ProjectReadRefused):await self.read()
        self.assertEqual(self.io_calls,0)

    async def test_binding_for_another_project_is_refused_before_io(self):
        a=self.bindings[('a'*64,'alpha')];self.bindings[('a'*64,'alpha')]=dataclasses.replace(a,project_ref='beta')
        with self.assertRaises(ProjectReadRefused):await self.read()
        self.assertEqual(self.io_calls,0)

    async def test_binding_wrong_client_is_refused_before_io(self):
        a=self.bindings[('a'*64,'alpha')];self.bindings[('a'*64,'alpha')]=dataclasses.replace(a,caller=dataclasses.replace(self.caller_a,client_ref='other'))
        with self.assertRaises(ProjectReadRefused):await self.read()
        self.assertEqual(self.io_calls,0)

    async def test_read_grant_cannot_outlive_request_token(self):
        self.clock=200000
        with self.assertRaises(ProjectReadRefused):await self.read()
        self.assertEqual(self.io_calls,0)

    async def test_revocation_between_admission_and_io_withholds_content(self):
        self.mode='revoke-before-io'
        with self.assertRaises(ProjectReadRefused):await self.read()

    async def test_binding_generation_change_before_io_refuses(self):
        self.mode='change-before-io'
        with self.assertRaises(ProjectReadRefused):await self.read()

    async def test_actual_edit_is_visible_with_unchanged_commit(self):
        old=await self.read();(self.root/'alpha/CLAUDE.md').write_text('changed\n')
        new=await self.read();self.assertNotEqual(old['file_sha256'],new['file_sha256'])
        self.assertEqual(new['committed_head'],old['committed_head']);self.assertEqual(new['content'],'changed\n')

    async def test_old_hash_returns_specific_refusal(self):
        old=await self.read();(self.root/'alpha/CLAUDE.md').write_text('changed\n')
        with self.assertRaises(ProjectReadRefused) as caught:await self.read(expected_sha256=old['file_sha256'])
        self.assertEqual(caught.exception.code,'READ_PREIMAGE_MISMATCH')

    async def test_line_range_maps_without_changing_full_hash(self):
        full=await self.read();r=await self.read(line_start=1,line_count=1)
        self.assertEqual(r['content'],'second line\r\n');self.assertEqual(r['file_sha256'],full['file_sha256'])
        self.assertEqual(r['line_start'],1)

    async def test_pagination_is_not_silent_truncation(self):
        r=await self.read(line_count=1);self.assertTrue(r['truncated']);self.assertEqual(r['next_line'],1)

    async def test_absolute_path_refused(self):
        with self.assertRaises(ProjectReadRefused):await self.read(relative_path='/etc/passwd')

    async def test_symlink_to_other_project_refused(self):
        p=self.root/'alpha/CLAUDE.md';p.unlink();p.symlink_to(self.root/'beta/CLAUDE.md')
        with self.assertRaises(ProjectReadRefused):await self.read()

    async def test_undeclared_file_refused(self):
        (self.root/'alpha/secret.txt').write_text('fixture only')
        with self.assertRaises(ProjectReadRefused):await self.read(relative_path='secret.txt')

    async def test_root_identity_replacement_refused(self):
        a=self.bindings[('a'*64,'alpha')];self.bindings[('a'*64,'alpha')]=dataclasses.replace(a,scope=dataclasses.replace(a.scope,root_inode=a.scope.root_inode+1))
        with self.assertRaises(ProjectReadRefused):await self.read()

    async def test_forbidden_fields_refuse_before_io(self):
        with self.assertRaises(ProjectReadRefused):await self.read(root='/',subject_digest='b'*64)
        self.assertEqual(self.io_calls,0)

    async def test_missing_io_integration_has_no_inline_fallback(self):
        with self.assertRaises(TypeError):create_descriptor_read_port(resolve_binding=self.resolve,clock_ms=lambda:0,run_io=None)

    async def test_resolver_exception_is_sanitized(self):
        def broken(c,p):raise RuntimeError('PRIVATE_SERVER_LOCATION')
        port=create_descriptor_read_port(resolve_binding=broken,clock_ms=lambda:0,run_io=lambda f:f())
        with self.assertRaises(ProjectReadRefused) as caught:await port(self.caller_a,{'project_ref':'alpha','relative_path':'CLAUDE.md'})
        self.assertNotIn('PRIVATE_SERVER_LOCATION',str(caught.exception))


    async def test_revocation_after_io_withholds_completed_read(self):
        self.mode='revoke-after-io'
        with self.assertRaises(ProjectReadRefused):await self.read()
        self.assertEqual(self.io_calls,1)

    async def test_generation_change_after_io_withholds_completed_read(self):
        self.mode='change-after-io'
        with self.assertRaises(ProjectReadRefused):await self.read()
        self.assertEqual(self.io_calls,1)


    async def reject_return(self, transform, **kwargs):
        self.return_transform=transform
        with self.assertRaises(ProjectReadRefused) as caught:
            await self.read(**kwargs)
        self.assertEqual(caught.exception.code,'PROJECT_READ_REFUSED')
        self.assertNotIn('instructions',str(caught.exception))

    async def test_return_from_real_other_project_is_not_relabelled(self):
        beta=await self.read(self.caller_b,project_ref='beta')
        await self.reject_return(lambda actual:beta)

    async def test_return_context_matches_selected_scope(self):
        await self.reject_return(lambda r:{**r,'context_ref':'context-beta'})

    async def test_return_owner_matches_selected_scope(self):
        await self.reject_return(lambda r:{**r,'owner_ref':'owner-beta'})

    async def test_return_generation_matches_selected_scope(self):
        await self.reject_return(lambda r:{**r,'generation':'generation-2'})

    async def test_return_baseline_matches_selected_scope(self):
        await self.reject_return(lambda r:{**r,'committed_head':'2'*40})

    async def test_return_relative_path_matches_requested_file(self):
        await self.reject_return(lambda r:{**r,'relative_path':'OTHER.md'})

    async def test_return_missing_identity_is_not_inferred(self):
        for key in ('context_ref','owner_ref','generation','committed_head','relative_path'):
            with self.subTest(key=key):
                await self.reject_return(lambda r,k=key:{n:v for n,v in r.items() if n!=k})

    async def test_return_conflicting_project_ref_is_not_overwritten(self):
        await self.reject_return(lambda r:{**r,'project_ref':'beta'})

    async def test_return_matching_project_ref_remains_valid(self):
        self.return_transform=lambda r:{**r,'project_ref':'alpha'}
        self.assertEqual((await self.read())['project_ref'],'alpha')

    async def test_return_line_start_matches_requested_range(self):
        other_page=await self.read(line_start=1,line_count=1)
        await self.reject_return(lambda r:other_page,line_start=0,line_count=1)

    async def test_return_does_not_exceed_requested_line_count(self):
        full=await self.read()
        await self.reject_return(lambda r:full,line_count=1)

    async def test_return_range_does_not_exceed_total_lines(self):
        await self.reject_return(lambda r:{**r,'total_lines':1})

    async def test_return_range_fields_require_exact_integers(self):
        for key in ('line_start','line_end','total_lines','content_bytes'):
            with self.subTest(key=key):
                await self.reject_return(lambda r,k=key:{**r,k:False})

    async def test_return_truncation_and_cursor_are_consistent(self):
        for patch in ({'truncated':False},{'truncated':1},{'next_line':0},{'next_line':None}):
            with self.subTest(patch=patch):
                await self.reject_return(lambda r,p=patch:{**r,**p},line_count=1)

    async def test_return_completed_range_has_no_continuation(self):
        await self.reject_return(lambda r:{**r,'next_line':r['line_end']})

    async def test_return_expected_hash_is_checked_at_port(self):
        expected=hashlib.sha256((self.root/'alpha/CLAUDE.md').read_bytes()).hexdigest()
        await self.reject_return(lambda r:{**r,'file_sha256':'0'*64},expected_sha256=expected)

    async def test_return_content_bytes_and_range_match(self):
        for patch in ({'content_bytes':1},{'content':'different\n'},{'content':'\ud800'}):
            with self.subTest(patch=repr(patch)):
                await self.reject_return(lambda r,p=patch:{**r,**p})

    async def test_return_declared_unknown_baseline_stays_unknown(self):
        b=self.bindings[('a'*64,'alpha')]
        self.bindings[('a'*64,'alpha')]=dataclasses.replace(b,scope=dataclasses.replace(b.scope,committed_head=None))
        self.assertIsNone((await self.read())['committed_head'])
        await self.reject_return(lambda r:{k:v for k,v in r.items() if k!='committed_head'})

    async def test_return_empty_file_and_eof_are_valid(self):
        self.assertEqual((await self.read(line_start=2))['content'],'')
        (self.root/'alpha/CLAUDE.md').write_bytes(b'')
        r=await self.read();self.assertEqual(r['line_end'],0);self.assertFalse(r['truncated'])

    async def test_return_byte_limited_page_is_valid(self):
        (self.root/'alpha/CLAUDE.md').write_bytes((b'a'*20000+b'\n')*2)
        r=await self.read(line_count=2)
        self.assertEqual(r['line_end'],1);self.assertTrue(r['truncated']);self.assertEqual(r['next_line'],1)

if __name__=='__main__':unittest.main(verbosity=2)
