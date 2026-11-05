"""Root-profile entrypoint for the ONE incumbent paid GLM shim and Fabric FD.

Installed definition is disabled by default. No CLI-selected module/state/key,
new listener/controller or finite socket reuse. Qualification precedes all
existing credential reads; missing FD/profile/actual source refuses closed.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import sys
import threading

_ROOT=Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:sys.path.insert(0,str(_ROOT))

_CONFIG=Path('/Library/Application Support/MastermindExecutive/config/fabric-glm-paid-01/bridge.json')


def _load_fixed(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None or name in sys.modules:
        raise ValueError('paid owner module unavailable')
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    try:spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name,None)
        raise
    return module


def _qualify_socket(config,activated):
    info=config.socket_path.lstat()
    if (activated.family!=socket.AF_UNIX or activated.getsockname()!=str(config.socket_path)
            or activated.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)!=1
            or not stat.S_ISSOCK(info.st_mode) or info.st_uid!=0 or info.st_gid!=450
            or stat.S_IMODE(info.st_mode)!=0o660):
        raise ValueError('paid protected socket unavailable')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    args=parser.parse_args(argv)
    activated=None
    httpd=None
    thread=None
    try:
        if args.config!=_CONFIG:
            raise ValueError('paid config unavailable')
        from control_plane.executive_paid_fabric_composition import load_paid_config
        from control_plane.executive_worker_broker import activate_launchd_socket
        from control_plane.paid_fabric_backend import (
            CanonicalPaidBackend,qualify_paid_startup,_root_source)
        config=load_paid_config(args.config)
        if config.adapter_id!='canonical-paid-fabric':
            raise ValueError('paid profile unavailable')
        activated=activate_launchd_socket(config.launchd_socket_name)
        _qualify_socket(config,activated)
        startup=qualify_paid_startup(_ROOT,config=config)
        # qualify_paid_startup already joins the actual root-installed profile.
        native=startup.native_ext
        # Fixed qualified source closure only; never import mutable owner code.
        sys.path.insert(0,str(native))
        _load_fixed('paid_controller_channel',native/'paid_controller_channel.py')
        source=_ROOT/'ops/native_fabric/paid_canonical_glm/candidate'
        _load_fixed('glm_lease_capability',source/'glm_lease_capability.py')
        _load_fixed('glm_lease_gateway',source/'glm_lease_gateway.py')
        shim=_load_fixed('glm_shim',source/'glm_shim.py')
        incumbent=shim.build_canonical_incumbent_context(str(startup.owner_ext))
        context,gateway=shim.require_canonical_incumbent(incumbent)
        backend=CanonicalPaidBackend(startup,incumbent)
        backend.bind_activated_socket(activated)
        # Existing HTTP endpoint is owned by this same singleton/context/key.
        httpd=shim.serve(context,'127.0.0.1',4141,lease_gateway=gateway)
        thread=threading.Thread(target=httpd.serve_forever,daemon=True)
        thread.start()
        from scripts.executive_fabric_bridge import serve
        used=False
        def take(name):
            nonlocal used
            if used or name!=config.launchd_socket_name:
                raise ValueError('paid adopted socket unavailable')
            used=True
            return activated
        asyncio.run(serve(config,backend,activate_socket=take))
        return 0
    except Exception:
        print('CANONICAL_PAID_STARTUP_NOT_ADMITTED',file=sys.stderr)
        return 78
    finally:
        if httpd is not None:
            if thread is not None and thread.is_alive():httpd.shutdown()
            httpd.server_close()
        if activated is not None:activated.close()


if __name__=='__main__':
    raise SystemExit(main())
