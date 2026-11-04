"""Closed exact-attempt direct-native correction DATA; no authority issuance."""
from common import direct_native_result_contract as result
SCHEMA = 'mastermind.direct_native_correction.v1'
PATH = '/os/executive/direct-native/correction'

def validate_request(value):
    if type(value) is not dict or set(value) != result.SELECTION_KEYS | {'fence_generation','operation_key'}:
        raise result.DirectResultContractError('direct correction request refused')
    selection = result.validate_selection({key:value[key] for key in result.SELECTION_KEYS})
    if type(value['fence_generation']) is not int or value['fence_generation'] < 1:
        raise result.DirectResultContractError('direct correction fence refused')
    selection.update(fence_generation=value['fence_generation'],operation_key=result.identifier(value['operation_key']))
    if len(result.canonical_bytes(selection)) > result.MAX_REQUEST_BYTES:
        raise result.DirectResultContractError('direct correction request over budget')
    return selection

def receipt(request,status):
    request=validate_request(request)
    if status not in {'CANCEL_REQUESTED','CANCELLED','COMPLETED','FAILED','LOST','RATE_LIMITED'}:
        raise result.DirectResultContractError('direct correction outcome refused')
    return dict(schema=SCHEMA,selection={key:request[key] for key in result.SELECTION_KEYS},
        fence_generation=request['fence_generation'],operation_key=request['operation_key'],status=status,
        parent_consumed=False)


def validate_response(value):
    if type(value) is not dict or set(value)!={'schema','selection','fence_generation','operation_key','status','parent_consumed'} or value['schema']!=SCHEMA or value['parent_consumed'] is not False:
        raise result.DirectResultContractError('direct correction response refused')
    selected=result.validate_selection(value['selection'])
    fence=value['fence_generation']
    if type(fence) is not int or fence<1 or value['status'] not in {'RUNNING','CHECKPOINTED','CANCEL_REQUESTED','CANCELLED','COMPLETED','FAILED','LOST','RATE_LIMITED'}:
        raise result.DirectResultContractError('direct correction response refused')
    key=None if value['operation_key'] is None else result.identifier(value['operation_key'])
    return dict(schema=SCHEMA,selection=selected,fence_generation=fence,operation_key=key,status=value['status'],parent_consumed=False)
