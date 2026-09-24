"""The six existing Steward reads transported over installed CeoIngress."""
from integrations.executive_content_contract import STEWARD_SCHEMA
from integrations.mastermind_secretary_mcp.adapter import (
    StewardGrounding, GroundingFact, GroundingSource, GroundingRefusedError,
)
from integrations.mastermind_secretary_mcp.schemas import (
    RESULT_SCHEMA, SERVER_VERSION, validate_result_data, validate_tool_arguments, result_envelope,
)


class CeoIngressStewardReadPort:
    def __init__(self, client):
        self.client=client

    async def _read(self, tool, arguments):
        try:
            args=validate_tool_arguments(tool,arguments)
            response=await self.client.request({'schema':STEWARD_SCHEMA,'tool':tool,'arguments':args})
            envelope=response['result']
            if (set(envelope)!={'schema','tool','ok','server_version','data','error'}
                    or envelope['schema']!=RESULT_SCHEMA or envelope['server_version']!=SERVER_VERSION
                    or envelope['tool']!=tool or envelope['ok'] is not True or envelope['error'] is not None):
                raise ValueError('RESPONSE_REFUSED')
            data=validate_result_data(envelope['data'])
            flat=[dict(fact,subject_ref=subject['subject_ref']) for subject in data['subjects'] for fact in subject['facts']]
            checked=result_envelope(tool,data={'state':data['state'],'facts':flat,'reason_codes':data['reason_codes']},expected_subject_ref=args.get('responsibility_ref'))
            if checked!=envelope:
                raise ValueError('RESPONSE_REFUSED')
            facts=tuple(GroundingFact(f['subject_ref'],f['predicate'],f['value'],f['freshness'],
                tuple(GroundingSource(**s) for s in f['sources'])) for f in flat)
            return StewardGrounding(data['state'],facts,tuple(data['reason_codes']))
        except Exception:
            raise GroundingRefusedError('RESPONSE_REFUSED') from None

    async def list_responsibilities(self):
        return await self._read('list_responsibilities',{})

    async def get_responsibility(self,responsibility_ref):
        return await self._read('get_responsibility',{'responsibility_ref':responsibility_ref})

    async def get_attention(self):
        return await self._read('get_attention',{})

    async def get_current_runtime(self,responsibility_ref):
        return await self._read('get_current_runtime',{'responsibility_ref':responsibility_ref})

    async def explain_blocker(self,responsibility_ref):
        return await self._read('explain_blocker',{'responsibility_ref':responsibility_ref})

    async def resolve_surface(self,responsibility_ref):
        return await self._read('resolve_surface',{'responsibility_ref':responsibility_ref})
