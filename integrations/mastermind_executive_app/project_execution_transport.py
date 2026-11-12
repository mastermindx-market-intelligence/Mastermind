"""Fixed project execution routes over the incumbent two-resource carrier."""
from common import project_execution_private_contract as wire
from integrations.mastermind_executive_app.project_planning_transport import HEADER, dispatch_project_request

ROUTES={f'/os/executive/project-execution/{name}':name for name in ('preview','submit','status')}


async def dispatch(owner,scope,body,principal,*,operation,receive):
    return await dispatch_project_request(owner,scope,body,principal,operation=operation,receive=receive,
        contract=wire,send_method="send_project_execution_frame")
