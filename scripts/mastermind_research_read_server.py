#!/usr/bin/env python3
"""Pinned Research HTTP launcher candidate. Import and --describe are inert.

--qualify verifies source/configuration/dependencies without building a store,
opening audit, starting a listener or contacting OAuth/tunnel providers.
Only the explicit serving invocation owns those actual startup effects.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

REQUIRED_DISTRIBUTIONS = ('mcp','uvicorn','starlette','httpx','PyJWT','cryptography','PyYAML','boto3','botocore')


def describe():
    versions = {}
    for name in REQUIRED_DISTRIBUTIONS:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"state":"BUILT_NOT_PROVEN", "transport":"authenticated_loopback_http",
            "required_distributions":versions, "source_config_runtime_client_acceptance":False}


def qualify(config_path, archive_owner_path):
    import os
    from integrations.research_read_mcp.runtime import load_deployment,read_secure_json,RuntimeRefused,_json
    from integrations.research_read_mcp.release_identity import load_archive_verifier
    from integrations.business_mcp_auth.contracts import load_resource_policy
    uid = os.geteuid()
    deployment = load_deployment(config_path, expected_owner_uid=uid)
    verifier = load_archive_verifier(archive_owner_path, deployment, owner_uid=uid)
    for project in ('mastermind','macro'):
        verifier(getattr(deployment,project+'_release'),getattr(deployment,project+'_commit'),getattr(deployment,project+'_tree'))
    root = Path(__file__).resolve().parents[1]
    if root != Path(deployment.mastermind_release):
        raise RuntimeRefused('LAUNCHER_IDENTITY_REFUSED')
    policy = load_resource_policy(_json(read_secure_json(deployment.policy_path,expected_owner_uid=uid),65536))
    if policy.policy_id != deployment.policy_id:
        raise RuntimeRefused('POLICY_REFUSED')
    # Examples are never enrollment evidence or a serving authorization.
    from urllib.parse import urlsplit
    if any(urlsplit(url).hostname.endswith('.invalid') for url in (policy.resource,policy.issuer,policy.jwks_uri)):
        raise RuntimeRefused('POLICY_REFUSED')
    if any(version is None for version in describe()['required_distributions'].values()):
        raise RuntimeRefused('RUNTIME_DEPENDENCIES_UNAVAILABLE')
    return deployment,verifier,policy


def create_runtime(deployment, verifier, policy, *, audit_sink, selected_options=None):
    """Actual factories; callable alone does not start HTTP or tunnel."""
    import os
    import time
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.business_mcp_auth.jwks import BoundedJwksCache,HttpxJwksFetcher
    from integrations.research_read_mcp.runtime import compose_runtime
    from integrations.research_read_mcp.port_adapter import (
        compose_macro_service, compose_selected_macro_service, ResearchPortAdapter)
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from integrations.research_read_mcp.citation_transport import RuntimeBindings
    owned = {}
    clock = lambda:int(time.time())
    def read_factory(_deployment):
        if selected_options is None:
            service,context_type,receipt = compose_macro_service(deployment.macro_release,deployment.macro_commit,
                                                                deployment.macro_tree,release_verifier=verifier)
        else:
            selected = compose_selected_macro_service(deployment.macro_release,deployment.macro_commit,
                deployment.macro_tree,release_verifier=verifier,options=selected_options,clock=clock)
            service,context_type,receipt = selected.service,selected.context_type,selected.receipt
            owned['selection'] = selected
        owned.update(service=service,context_type=context_type,factory_receipt=receipt)
        return service
    def adapter_factory(service,quote_limit,_deployment):
        adapter = ResearchPortAdapter(service,quote_limit,deployment.mastermind_commit,
            context_type=owned['context_type'],
            operation_runner=owned['selection'].run if 'selection' in owned else None)
        owned['adapter'] = adapter
        return adapter
    def authenticator_factory(selected):
        authenticator = JwtAuthenticator(policy=selected,jwks_cache=BoundedJwksCache(
            policy=selected,fetcher=HttpxJwksFetcher(selected),monotonic=time.monotonic))
        owned["authenticator"] = authenticator
        return authenticator
    def readiness(service):
        # Only the explicitly prepared owner can qualify a generation. The default
        # launcher still has no admitted writer/selection owner and remains false.
        return owned['selection'].ready() if 'selection' in owned else False
    def mount_health(app,health,ready):
        import asyncio
        async def live(request):
            body,status = health()
            return JSONResponse(body,status_code=status,headers={'Cache-Control':'no-store'})
        async def ready_route(request):
            body,status = await asyncio.to_thread(ready)
            return JSONResponse(body,status_code=status,headers={'Cache-Control':'no-store'})
        app.routes.extend([Route('/healthz',live),Route('/readyz',ready_route)])
    app = compose_runtime(deployment,release_verifier=verifier,policy_loader=lambda _:policy,
                          authenticator_factory=authenticator_factory,read_service_factory=read_factory,
                          adapter_factory=adapter_factory,context_factory=lambda ent:owned['adapter'].context_builder(ent),
                          readiness=readiness,mount_health_routes=mount_health,audit_sink=audit_sink,
                          clock=clock,owner_uid=os.geteuid())
    owned['app'] = app
    app.state.research_factory_receipt = owned['factory_receipt']
    app.state.research_release_receipts = verifier.receipts
    if 'selection' in owned:
        app.state.research_selection_owner = owned['selection']
        from integrations.research_read_mcp.selected_refresh import SelectedRefreshLifecycle
        refresh = SelectedRefreshLifecycle(owned['selection'],
            interval_seconds=min(selected_options.refresh_interval_seconds, selected_options.max_reuse_seconds))
        refresh.install(app)
        app.state.research_refresh_owner = refresh
    app.state.research_bindings = RuntimeBindings(owned["service"],owned["adapter"],
        owned["authenticator"],app.state.research_grant_owner,clock,audit_sink)
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--describe',action='store_true')
    parser.add_argument('--qualify',action='store_true')
    parser.add_argument('--config')
    parser.add_argument('--archive-owner',default='/etc/mastermind/research-read-archive-owner.json')
    parser.add_argument('--audit-directory',default='/var/lib/mastermind-research/audit')
    parser.add_argument('--citation-unix',action='store_true')
    parser.add_argument('--citation-socket-user',type=int)
    parser.add_argument('--citation-socket-group',type=int)
    args = parser.parse_args(argv)
    if args.describe:
        print(json.dumps(describe(),sort_keys=True));return 0
    if not args.config:
        parser.error('--config is required')
    # The protected entry point's own release is the sole Mastermind import root.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from integrations.research_read_mcp.runtime import RuntimeRefused
    try:
        deployment,verifier,policy = qualify(args.config,args.archive_owner)
        if args.qualify:
            print(json.dumps({'state':'SOURCE_CONFIG_DEPENDENCIES_QUALIFIED','receipts':verifier.receipts,
                              'production_readiness':False,'client_acceptance':False}));return 0
        import os
        import stat
        from integrations.business_mcp_auth.audit import DurableAuthAuditSink
        target = Path(args.audit_directory)
        if (not target.is_absolute() or any(p.is_symlink() for p in (target,*target.parents))):
            raise RuntimeRefused('AUDIT_DIRECTORY_REFUSED')
        info = target.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise RuntimeRefused('AUDIT_DIRECTORY_REFUSED')
        descriptor = os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_DIRECTORY)
        try:
            audit = DurableAuthAuditSink.open(descriptor,policy_id=policy.policy_id)
        finally:
            os.close(descriptor)
        try:
            # Only an explicitly admitted v2 archive owner reaches the selected
            # composition here, after qualify and before any listener exists.
            # A v1 owner (selected_options None) keeps the exact legacy call, and
            # a failed selected preparation refuses without legacy fallback.
            selected = verifier.selected_options
            if selected is None:
                app = create_runtime(deployment,verifier,policy,audit_sink=audit)
            else:
                app = create_runtime(deployment,verifier,policy,audit_sink=audit,
                    selected_options=selected)
            if args.citation_unix:
                from integrations.research_read_mcp.citation_transport import (
                    UnixSocketPolicy, acquire_listeners, build_citation_consumer, run_dual_server, MCP_ADDRESS)
                if (deployment.bind_host,deployment.bind_port) != MCP_ADDRESS:
                    raise RuntimeRefused('CITATION_TRANSPORT_REFUSED')
                # Refuse before listener acquisition until the incumbent service/
                # adapter has its reviewed exact-item seam and limiter discipline.
                citation = build_citation_consumer(policy,app.state.research_bindings)
                socket_policy = UnixSocketPolicy.production(args.citation_socket_user,args.citation_socket_group)
                listeners = acquire_listeners(socket_policy)
                run_dual_server(mcp_app=app,citation_app=citation,listeners=listeners)
            else:
                from integrations.research_read_mcp.citation_transport import run_mcp_server
                run_mcp_server(app=app,host=deployment.bind_host,port=deployment.bind_port)
        finally:
            audit.close()
        return 0
    except Exception:
        # Provider/configuration/source values never enter launcher diagnostics.
        print('RESEARCH_RUNTIME_REFUSED',file=sys.stderr);return 1


if __name__ == '__main__':
    raise SystemExit(main())
