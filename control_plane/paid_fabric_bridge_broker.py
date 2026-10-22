"""Closed paid profile on the existing authenticated Fabric Unix protocol.

No new public listener or authority. The inherited connection handler resolves
actual kernel peers before reading requests. Finite/legacy broker code and
schemas retain their own validators and refuse this profile.
"""
import json

from control_plane.executive_fabric_bridge_broker import (
    FabricBridgeBroker, BridgeProtocolError, _object, _binding, _digest,
    _identifier, _canonical, _strict_json, start_request_sha256,
    BROKER_REQUEST_SCHEMA_VERSION, BROKER_RESPONSE_SCHEMA_VERSION,
)
from control_plane.fabric_control_start import authorize_control_command
from control_plane.paid_model_execution_contract import ADAPTER_ID, compile_request
from control_plane.paid_fabric_wire import require_paid_physical


class PaidFabricBridgeBroker(FabricBridgeBroker):
    adapter_id=ADAPTER_ID
    async def handle_connection(self,reader,writer):
        # Root administration has a distinct ancillary handshake. Control's
        # ordinary framed JSON path can never mint a stop authority.
        from control_plane.executive_worker_broker import get_peer_credentials
        sock=writer.get_extra_info('socket')
        try:
            if sock is None:raise OSError('missing socket')
            root_peer=get_peer_credentials(sock).uid==0
        except Exception:
            writer.close()
            return
        if root_peer:
            from control_plane.paid_quiesce_transport import handle_root_quiesce
            await handle_root_quiesce(self,reader,writer)
            return
        await super().handle_connection(reader,writer)

    async def execute(self, request, *, peer):
        self._authorize_peer(peer)  # same actual accepted Control kernel peer
        self.require_service_identity()
        if self.config.adapter_id != ADAPTER_ID:
            raise BridgeProtocolError('ConfigTrustError')
        _object(request, {'schema_version','request_id','operation','payload'})
        if request['schema_version'] != BROKER_REQUEST_SCHEMA_VERSION:
            raise BridgeProtocolError('BrokerProtocolError')
        _identifier(request['request_id'])
        if len(_canonical(request))+1 > self.config.max_request_bytes:
            raise BridgeProtocolError('BrokerProtocolError')
        operation = request['operation']
        if operation not in {'start','status','collect','service-readiness','native-capacity-observation'}:
            raise BridgeProtocolError('BackendRefusedError', 'Operation is outside the paid sealed-input profile')
        payload = _strict_json(_canonical(request['payload']))
        if operation=='service-readiness':
            _object(payload,{'nonce'})
            import re
            if type(payload['nonce']) is not str or re.fullmatch(r'[0-9a-f]{32}',payload['nonce']) is None:
                raise BridgeProtocolError('BrokerProtocolError')
            result=self.backend.service_readiness()
            response=dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,request_id=request['request_id'],
                operation=operation,ok=True,result=dict(result,nonce=payload['nonce']))
            if len(_canonical(response))+1>self.config.max_response_bytes:
                raise BridgeProtocolError('BrokerProtocolError')
            return response
        if operation=='native-capacity-observation':
            _object(payload,{'nonce','worker_id','quota_class','mode'} | ({'operation_id'} if payload.get('mode') in {'bootstrap','reconcile'} else set()))
            import re
            if (type(payload['nonce']) is not str or re.fullmatch(r'[0-9a-f]{32}',payload['nonce']) is None
                    or payload['mode'] not in {'observe','bootstrap','reconcile'}):
                raise BridgeProtocolError('BrokerProtocolError')
            _identifier(payload['worker_id']);_identifier(payload['quota_class'])
            result=await self.backend.capacity_observation(payload['worker_id'],payload['quota_class'],mode=payload['mode'],operation_id=payload.get('operation_id'))
            _object(result,{'observation','bootstrap','physical_binding_sha256','worker_source_config_digest',
                            'worker_id','quota_class','account_label'})
            if (result['worker_id']!=payload['worker_id'] or result['quota_class']!=payload['quota_class']):
                raise BridgeProtocolError('BackendRefusedError')
            from control_plane.paid_fabric_capacity import validate_paid_capacity_observation
            validate_paid_capacity_observation(result['observation'])
            response=dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,request_id=request['request_id'],
                operation=operation,ok=True,result=dict(result,nonce=payload['nonce']))
            if len(_canonical(response))+1>self.config.max_response_bytes:
                raise BridgeProtocolError('BrokerProtocolError')
            return response
        binding = _binding(payload.get('binding'))
        _digest(payload.get('physical_binding_sha256'))
        if operation == 'start':
            if 'control_start' not in payload:
                raise BridgeProtocolError('EFFECT_UNKNOWN', 'Fresh START requires original Control authority')
            compile_request(payload)
            require_paid_physical(payload)
            authority = authorize_control_command(payload, peer=peer)
            digest = start_request_sha256(payload)
            query = dict(binding=binding,run_id=binding['attempt_id'],
                physical_binding_sha256=payload['physical_binding_sha256'],start_request_sha256=digest)
            observed = await self.backend.execute('status',query)
            self._check_result(observed,query,'status')
            if observed.get('start_state') != 'NO_RETAINED_START':
                raise BridgeProtocolError('EFFECT_UNKNOWN', 'Original operation is recovery only')
            forwarded = {k:v for k,v in payload.items() if k != 'control_start'}
            forwarded['start_request_sha256'] = digest
            result = await self.backend.start_owned(forwarded,authority=authority)
            self._check_start(result,payload,digest)
        else:
            fields = {'binding','run_id','physical_binding_sha256'}
            if operation == 'status' and 'start_request_sha256' in payload:
                fields.add('start_request_sha256')
                _digest(payload['start_request_sha256'])
            _object(payload,fields)
            if payload['run_id'] != binding['attempt_id']:
                raise BridgeProtocolError('BrokerProtocolError')
            result = await self.backend.execute(operation,payload)
            self._check_result(result,payload,operation)
        response=dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,
            request_id=request['request_id'],operation=operation,ok=True,result=result)
        if len(_canonical(response))+1 > self.config.max_response_bytes:
            raise BridgeProtocolError('EFFECT_UNKNOWN','Bound response exceeds transport ceiling')
        return response

    @staticmethod
    def _common(result,payload,extras):
        _object(result,{'adapter_id','binding','physical_binding_sha256'}|set(extras))
        if (result['adapter_id'] != ADAPTER_ID or result['binding'] != payload['binding']
                or result['physical_binding_sha256'] != payload['physical_binding_sha256']):
            raise BridgeProtocolError('EFFECT_UNKNOWN','Paid original route differs')

    @classmethod
    def _check_start(cls,result,payload,digest):
        cls._common(result,payload,{'request_sha256','process_ref','launch_attestation'})
        if result['request_sha256'] != digest:
            raise BridgeProtocolError('EFFECT_UNKNOWN')
        from control_plane.paid_fabric_wire import validate_paid_start_wire
        validate_paid_start_wire(result,payload)

    @classmethod
    def _check_result(cls,result,payload,operation):
        if operation=='status' and 'start_request_sha256' in payload:
            state=result.get('start_state')
            extras={'request_sha256','start_state'}
            if state=='EXISTS':
                extras.add('start_result')
                retained=result['start_result']
                # Full expected payload is available at Control's recovery
                # owner; here retain exact original attribution without mint.
                if (type(retained) is not dict or retained.get('adapter_id')!=ADAPTER_ID
                        or retained.get('binding')!=payload['binding']
                        or retained.get('physical_binding_sha256')!=payload['physical_binding_sha256']
                        or retained.get('request_sha256')!=payload['start_request_sha256']):
                    raise BridgeProtocolError('EFFECT_UNKNOWN')
            elif state!='NO_RETAINED_START':
                raise BridgeProtocolError('EFFECT_UNKNOWN')
            cls._common(result,payload,extras)
            if result['request_sha256']!=payload['start_request_sha256']:
                raise BridgeProtocolError('EFFECT_UNKNOWN')
        elif operation=='status':
            cls._common(result,payload,{'run'})
            _object(result['run'],{'run_id','status','process_ref'})
            if (result['run']['run_id']!=payload['run_id']
                    or result['run']['status'] not in {'RUNNING','SUCCEEDED'}
                    or result['run']['process_ref'].get('schema_version')!='mastermind.paid_model_process_ref/v1'):
                raise BridgeProtocolError('EFFECT_UNKNOWN')
        elif operation=='collect':
            cls._common(result,payload,{'collection','paid_observation'})
            from control_plane.worker_execution_contract import CollectionReceipt
            import dataclasses
            _object(result['collection'],{f.name for f in dataclasses.fields(CollectionReceipt)})
            _object(result['paid_observation'],{'owned_launch','owned_terminal','capture'})
        else:
            raise BridgeProtocolError('BackendRefusedError')
