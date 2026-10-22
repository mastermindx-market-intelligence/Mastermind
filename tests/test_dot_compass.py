"""Dot R0 deterministic owner/authorization/negative cases."""
import asyncio
import dataclasses
import json
import unittest
from datetime import datetime, timezone

from integrations.dot_compass.contracts import PROFILES, TOOL_SPECS, DotRefusal, schema_digest, validate_tool_arguments
from integrations.dot_compass.gateway import DotReadGateway, OwnerEvidence, PrincipalBinding
from integrations.dot_compass.owner_adapters import executive_read_port
from integrations.dot_compass.mcp_tools import build_handlers, build_mcp_server

NOW = datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)
SHA = 'a' * 40


def grant(scope='mastermind.executive.read', *, generation='gen.1'):
    return PrincipalBinding('subject.1', 'client.1', 'resource.1', generation, (scope,), True)


def company(data=None):
    return OwnerEvidence('executive','2026-10-09T02:59:00Z', ('mastermind@'+SHA,), 'BUILT_NOT_PROVEN', data if data is not None else {'company':'Mastermind'})


class DotTest(unittest.IsolatedAsyncioTestCase):
    def make(self, port=None, auth=None):
        async def authorize(_principal, scope): return await auth(_principal, scope) if auth else grant(scope)
        return DotReadGateway(profile='compass', ports={'dot_company_snapshot':port or (lambda _args: company())}, reauthorize=authorize, now=lambda: NOW)

    async def test_company_happy_path_exact_sources(self):
        g=self.make(); res=await g.call('dot_company_snapshot', {}, principal=object())
        self.assertTrue(res['ok']); self.assertEqual(res['data']['source_refs'],['mastermind@'+SHA]); self.assertEqual(res['data']['owner'],'executive')
        self.assertEqual(res['schema_digest'], schema_digest('compass',g.tool_names))

    async def test_stale_source_refused(self):
        g=self.make(port=lambda _:dataclasses.replace(company(),observed_at='2026-10-08T00:00:00Z'))
        res=await g.call('dot_company_snapshot',{},principal=object())
        self.assertEqual(res['error']['code'],'stale_owner_evidence')

    async def test_local_path_refused(self):
        g=self.make(port=lambda _: company({'root':'/private/var/db/company'}))
        res=await g.call('dot_company_snapshot',{},principal=object())
        self.assertEqual(res['error']['code'],'unsafe_owner_evidence')

    async def test_embedded_host_paths_and_windows_paths_refused(self):
        values = (
            'Diagnostic captured at /private/var/db/company in a failed read',
            'The host file was C:\\Users\\Operator\\secrets.txt',
            'Inspect (/Volumes/Mastermind/private) for errors',
        )
        for value in values:
            with self.subTest(value=value):
                res = await self.make(port=lambda _, msg=value: company({'message': msg})).call(
                    'dot_company_snapshot', {}, principal=object())
                self.assertFalse(res['ok'])
                self.assertEqual(res['error']['code'], 'unsafe_owner_evidence')

    async def test_source_and_issue_references_cannot_carry_secrets(self):
        for packet in (
            dataclasses.replace(company(), source_refs=('github_pat_1234567890',)),
            dataclasses.replace(company(), issues=('ghp_ABC123TOKEN',)),
        ):
            res = await self.make(port=lambda _, p=packet: p).call(
                'dot_company_snapshot', {}, principal=object())
            self.assertFalse(res['ok'])
            self.assertEqual(res['error']['code'], 'unsafe_owner_evidence')

    async def test_market_company_name_is_not_mistaken_for_api_secret(self):
        g = DotReadGateway(
            profile='market',
            ports={'dot_signal_evidence': lambda _args: OwnerEvidence(
                'data_os', '2026-10-09T02:59:00Z', ('signal@'+SHA,),
                'BUILT_NOT_PROVEN', {'issuer': 'SK-Hynix', 'theme': 'memory'})},
            reauthorize=lambda p,s: grant(s), now=lambda: NOW)
        result = await g.call('dot_signal_evidence',
            {'signal_ref': 'memory.leader', 'asof': '2026-10-09T00:00:00Z'},
            principal=object())
        self.assertTrue(result['ok'], result['error'])
        self.assertEqual(result['data']['data']['issuer'], 'SK-Hynix')

    async def test_long_api_secret_still_refused(self):
        g = self.make(port=lambda _: company({'hint': 'sk-proj-' + 'x'*40}))
        result = await g.call('dot_company_snapshot', {}, principal=object())
        self.assertEqual(result['error']['code'], 'unsafe_owner_evidence')

    async def test_safe_references_and_plain_diagnostics_still_work(self):
        packet = dataclasses.replace(company(),
            issues=('DEGRADED_BACKEND',),
            data={'message': 'The public path /docs/guide is accessible'})
        res = await self.make(port=lambda _: packet).call('dot_company_snapshot', {}, principal=object())
        self.assertTrue(res['ok'])
        self.assertEqual(res['data']['issues'], ['DEGRADED_BACKEND'])

    async def test_no_extra_args_even_for_empty_tools(self):
        g=self.make(); res=await g.call('dot_company_snapshot', {'cmd':'whoami'}, principal=object())
        self.assertEqual(res['error']['code'],'invalid_input')

    async def test_all_profiles_closed_and_read_only(self):
        self.assertEqual(set(PROFILES), {'compass','code_ci','ops','product','market'})
        names=[s.name for s in TOOL_SPECS]; self.assertEqual(len(names),len(set(names)))
        for profile in PROFILES:
            one=next(s for s in TOOL_SPECS if s.profile==profile)
            scope=one.scope
            g=DotReadGateway(profile=profile,ports={one.name:lambda _: OwnerEvidence(one.owner,'2026-10-09T02:59:00Z',('x@y',),'BUILT_NOT_PROVEN',{})},reauthorize=lambda _,s:grant(scope), now=lambda:NOW)
            for item in g.tool_definitions():
                self.assertTrue(item['annotations']['readOnlyHint']); self.assertFalse(item['annotations']['destructiveHint']); self.assertFalse(item['annotations']['openWorldHint']); self.assertFalse(item['inputSchema']['additionalProperties'])
        self.assertRaises(ValueError,DotReadGateway, profile='ops', ports={'dot_company_snapshot':lambda a: company()},reauthorize=lambda p,s:grant())

    async def test_revocation_after_await_refuses_leaked_data(self):
        calls=0
        async def change(_p,s):
            nonlocal calls; calls+=1
            return grant(s,generation='gen.1' if calls==1 else 'gen.2')
        g=self.make(auth=change)
        res=await g.call('dot_company_snapshot',{},principal=object())
        self.assertFalse(res['ok']); self.assertIsNone(res['data']); self.assertEqual(res['error']['code'],'authority_refused');self.assertEqual(calls,2)

    async def test_pre_read_denial_runs_no_port(self):
        called=False
        async def port(_a):
            nonlocal called;called=True;return company()
        g=self.make(port=port,auth=lambda p,s:asyncio.sleep(0,result=None))
        res=await g.call('dot_company_snapshot',{},principal=object())
        self.assertEqual(res['error']['code'],'authority_refused');self.assertFalse(called)

    async def test_schema_rejects_relative_paths_and_unknown_args(self):
        for args in ({'operation_ref':'../etc/passwd'},{'operation_ref':'host:/private/secret'},{'operation_ref':'latest:worker'},{'operation_ref':'good','host':'m2'}):
            with self.assertRaises(DotRefusal):validate_tool_arguments('dot_operation_context',args)
        with self.assertRaises(DotRefusal):validate_tool_arguments('dot_changed_since',{'baseline_sha':SHA,'current_sha':'bad'})
        with self.assertRaises(DotRefusal):validate_tool_arguments('dot_signal_evidence',{'signal_ref':'ok','asof':'2026-10-09T00:00:00+02:00'})

    async def test_wrong_owner_mismatched_and_secret_evidence_refused(self):
        for packet in (dataclasses.replace(company(),owner='other'), company({'token':'sensitive'}),company({'note':'Bearer example'}),company({'items':[0]*97}),company({'number':float('nan')})):
            g=self.make(port=lambda _,p=packet:p)
            res=await g.call('dot_company_snapshot',{},principal=object())
            self.assertFalse(res['ok']); self.assertIsNone(res['data'])

    async def test_future_timestamp_and_missing_source_ref_refused(self):
        for pkt in (dataclasses.replace(company(),observed_at='2026-10-10T00:00:00Z'),dataclasses.replace(company(),source_refs=())):
            g=self.make(port=lambda _,p=pkt:p)
            res=await g.call('dot_company_snapshot',{},principal=object());self.assertEqual(res['error']['code'],'invalid_owner_evidence')

    async def test_oversized_output_refused_without_truncation(self):
        g=self.make(port=lambda _:company({'chunks':['x'*12000,'y'*12000]}))
        res=await g.call('dot_company_snapshot',{},principal=object());self.assertEqual(res['error']['code'],'output_too_large')

    async def test_port_exception_not_exposed(self):
        def broken(_):raise RuntimeError('secret-credential')
        res=await self.make(port=broken).call('dot_company_snapshot',{},principal=object())
        self.assertEqual(res['error']['code'],'backend_unavailable');self.assertNotIn('secret',str(res))

    async def test_cancel_propagates(self):
        async def cancelled(_):raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.make(port=cancelled).call('dot_company_snapshot',{},principal=object())

    async def test_mcp_host_missing_principal(self):
        g=self.make(); handler=build_handlers(g,principal=lambda:None)['dot_company_snapshot']; out=await handler({})
        self.assertFalse(out['ok']);self.assertEqual(out['error']['code'],'authority_refused')
        with self.assertRaises(RuntimeError):build_mcp_server(g)

    async def test_executive_owner_adapter_actual_read_contract(self):
        class Executive:
            calls=[]
            async def call(self,name,args):
                self.calls.append((name,args))
                return {'schema':'mastermind.executive_mcp_result.v1','tool':name,'mode':'readonly','ok':True,
                        'grounding':{'mastermind':{'sha':SHA}},'generated_at':'2026-10-09T02:59:00Z',
                        'degraded':[],'data':{'runtime_counts':{'attempts':2},'runtime_db':{'path':'/private/var/db/mastermind'}}}
        owner=Executive(); reader=executive_read_port(owner,'executive_state'); g=self.make(port=reader)
        res=await g.call('dot_company_snapshot',{},principal=object())
        self.assertTrue(res['ok']);self.assertEqual(res['data']['data']['runtime_counts']['attempts'],2);self.assertNotIn('runtime_db',res['data']['data']);self.assertEqual(owner.calls,[('executive_state',{})])
        with self.assertRaises(ValueError): executive_read_port(owner,'submit_ceo_intent')

    async def test_executive_inbox_projection_never_leaks_host_roots(self):
        class Executive:
            async def call(self,name,args):
                return {'schema':'mastermind.executive_mcp_result.v1','tool':name,'mode':'readonly','ok':True,
                        'grounding':{'mastermind':{'sha':SHA,'root':'/private/var/db/control'}},
                        'generated_at':'2026-10-09T02:59:00Z','degraded':[],
                        'data':{'attention':[{'attention_id':'a1','kind':'WORK','owner_seat':'coo',
                                             'reason':'sensitive operator text',
                                             'source':{'path':'/private/var/db/secret'}},
                                            {'attention_id':'a2','kind':'BLOCKED','owner_seat':'ceo'}],
                                 'grounding':{'root':'/private/var/db/control'}}}
        g=DotReadGateway(profile='compass',ports={'dot_attention_snapshot':executive_read_port(Executive(),'executive_inbox')},
                         reauthorize=lambda p,s:grant(s),now=lambda:NOW)
        res=await g.call('dot_attention_snapshot',{},principal=object())
        self.assertTrue(res['ok']);self.assertEqual(res['data']['data']['attention_count'],2)
        self.assertEqual([x['attention_id'] for x in res['data']['data']['attention']],['a1','a2'])
        self.assertNotIn('/private/',str(res));self.assertNotIn('sensitive operator',str(res))

    async def test_no_owner_adapter_writes_or_dynamic_profile_routing(self):
        g=self.make();self.assertEqual(g.tool_names,('dot_company_snapshot',))
        self.assertEqual((await g.call('dot_ci_diagnosis',{'run_id':'1'},principal=object()))['error']['code'],'not_found')


if __name__ == '__main__': unittest.main()
