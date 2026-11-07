"""Real signed JWT to qualified source context; no Macro/Runtime/Git effects."""
import asyncio
import copy
import httpx
import pytest

from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from tests.test_workspace_project_authoring_grant import project_bindings
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW


@pytest.mark.parametrize("case", ["available", "read_only", "foreign_work", "after_read_revoke",
                                  "duplicate_query", "extra_query", "body", "unsigned"])
def test_signed_current_source_context_is_distinct_and_independent_of_source_refresh(rsa_key, case):
    async def run():
        auth = _authenticator(rsa_key)
        token = _workspace_token(rsa_key)
        who = await auth.verify_authorization_header("Bearer " + token, now=NOW)
        _, source = project_bindings(selected=None)
        for slot in source["profiles"].values():
            slot["enabled"], slot["binding"] = False, None
        slot = source["profiles"][source["primary_profile"]]
        slot["enabled"] = True
        slot["binding"] = dict(principal_frame(who), permission_digest="a" * 64)
        if case != "read_only":
            slot["plan_adoption"] = {"work_ref": "WS:TEST", "permission_digest": "b" * 64}
        raw_loader = lambda: source
        def legacy_loader():
            return legacy_workspace_document(source, auth.policy)
        gate, _ = workspace_authorizers(policy=auth.policy, load_bindings=legacy_loader)
        factory = WorkspaceSourceOperationContextFactory(policy=auth.policy, load_bindings=raw_loader, now=lambda: NOW)
        class UnusedClient:
            async def request(self, frame):
                pytest.fail("Context attempted a source/socket read")
        if case == "after_read_revoke":
            original = factory.bind
            def bind(*args, **kwargs):
                permission = original(*args, **kwargs)
                read = permission.public_context
                def revoke():
                    body = read()
                    slot["plan_adoption"] = None
                    return body
                permission.public_context = revoke
                return permission
            factory.bind = bind
        app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
            authorize_principal=gate, client=UnusedClient(), source_operation_context=factory))
        query = "action=ADOPT_PLAN&work_ref=WS%3ATEST"
        if case == "foreign_work": query = query.replace("TEST", "FOREIGN")
        if case == "duplicate_query": query += "&action=ADOPT_PLAN"
        if case == "extra_query": query += "&principal_scope=" + "c" * 64
        headers = {} if case == "unsigned" else {"Authorization": "Bearer " + token}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as client:
            response = await client.request("GET", "/workspace/source-operation/context?" + query,
                headers=headers, content=b"x" if case == "body" else b"")
        expected = {"available": 200, "read_only": 403, "foreign_work": 403, "after_read_revoke": 403,
                    "duplicate_query": 400, "extra_query": 400, "body": 400, "unsigned": 401}[case]
        assert response.status_code == expected, response.text
        assert response.headers["cache-control"] == "no-store"
        if case == "available":
            assert response.json()["can_inspect"] is True
            assert len(response.json()["owner_context"]["principal_scope"]) == 64
        else:
            assert "principal_scope" not in response.text
    asyncio.run(run())


def test_signed_nonfile_prepare_cannot_borrow_file_cap_with_whitespace(rsa_key):
    import json
    async def run():
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        _,source=project_bindings(selected=None)
        factory=WorkspaceSourceOperationContextFactory(policy=auth.policy,load_bindings=lambda:source,now=lambda:NOW)
        class Never:
            async def request(self,frame):pytest.fail('oversized nonfile request reached socket')
        app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,
            authorize_principal=lambda p:True,client=Never(),source_operation_context=factory))
        value={'action':'ADOPT_PLAN','request':{'request_id':'mmos-project-adopt-'+'a'*40,'work_ref':'WS:TEST'}}
        raw=json.dumps(value).encode()+b' '*32768
        assert 32768<len(raw)<98304
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com') as client:
            response=await client.post('/workspace/source-operation/prepare',content=raw,
                headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        assert response.status_code==400 and response.headers['cache-control']=='no-store'
    asyncio.run(run())
