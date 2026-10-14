"""Optional UID501 bridge entrypoint: no install, bind, chmod, credentials or sweep.

The production composition owner injects the reviewed backend factory into
main(), or calls serve(config, backend). No CLI option/environment/payload may
select a Python module, executable, host or account. Standalone serve deliberately
refuses until that composition exists; check-config is read-only. Packaging and
launchd installation/activation qualification remain separate owner work.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import sys
from typing import Callable

_ROOT=Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:sys.path.insert(0,str(_ROOT))

from control_plane.executive_fabric_bridge_broker import (
    Backend, BridgeConfig, BridgeProtocolError, FabricBridgeBroker, load_config,
)
from control_plane.executive_worker_broker import activate_launchd_socket


async def serve(config: BridgeConfig,backend: Backend,*,stop_event=None,
                activate_socket: Callable=activate_launchd_socket):
    """Claim the existing named launchd socket; never create a listener path.

    Stop closes only our server/FD. Runtime/Fabric owns unsettled operations;
    shutdown does not cancel, sweep, release leases or infer process absence.
    """
    broker=FabricBridgeBroker(config,backend)
    broker.require_service_identity()
    activated=None
    server=None
    registered=[]
    stopping=stop_event or asyncio.Event()
    loop=asyncio.get_running_loop()
    try:
        activated=activate_socket(config.launchd_socket_name)
        if (activated.family!=socket.AF_UNIX
                or activated.getsockname()!=str(config.socket_path)
                or activated.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)!=1):
            raise BridgeProtocolError('SocketBindingError','Activated socket differs from root-installed binding')
        kwargs={'sock':activated,'limit':config.max_request_bytes+1}
        # Python3.13+ otherwise unlinks an activated Unix socket on close.
        # Python3.11/12 never owned a path here, and accept no cleanup_socket arg.
        if sys.version_info>=(3,13):kwargs['cleanup_socket']=False
        server=await asyncio.start_unix_server(broker.handle_connection,**kwargs)
        if stop_event is None:
            for signum in (signal.SIGTERM,signal.SIGINT):
                loop.add_signal_handler(signum,stopping.set)
                registered.append(signum)
        await stopping.wait()
    finally:
        try:
            if server is not None:
                server.close()
                await server.wait_closed()
        finally:
            if activated is not None:activated.close()
            for signum in registered:loop.remove_signal_handler(signum)


def parser():
    value=argparse.ArgumentParser(description='Optional authenticated attended-Fabric bridge')
    value.add_argument('operation',choices=('check-config','serve'))
    value.add_argument('--config',required=True,type=Path,help='Existing root-installed closed JSON config')
    return value


def main(argv=None,*,backend_factory=None,activate_socket=activate_launchd_socket):
    args=parser().parse_args(argv)
    try:
        config=load_config(args.config)
        if args.operation=='check-config':
            print(json.dumps({'config_sha256':config.source_sha256,'adapter_id':config.adapter_id,'activated':False}))
            return 0
        if backend_factory is None:
            raise BridgeProtocolError('BackendNotConfiguredError','Reviewed backend composition must be injected by owner')
        backend=backend_factory(config)
        asyncio.run(serve(config,backend,activate_socket=activate_socket))
        return 0
    except BridgeProtocolError as exc:
        print(str(exc),file=sys.stderr)
        return 2
    except Exception:
        # Do not print arbitrary backend exception values, paths or secrets.
        print('BackendUnavailableError: bridge startup failed; no automatic retry',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
