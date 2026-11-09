#!/usr/bin/env python3
"""DEV/PROOF launcher: the real Executive stack for the WO-12 Hermes host lane.

Stands up, in ONE user-space process the caller owns (no launchd, no daemon
changes, no production sockets):

1. the real ``ExecutiveControlService`` (real Runtime, real CEO-ingress Unix
   socket) with principal admission ARMED and a host-frozen
   ``child_request_material`` loaded (and hot-reloaded) from a freeze file —
   the trusted host freezes which ``ChildExecutionRequest.v1`` envelopes may
   be named, exactly like the WO-13 test composition;
2. the real COO App (``create_coo_app``) over the repo's documented
   dev/test issuance path — a LOCALLY GENERATED RSA key and LOCALLY SIGNED
   JWT (``tests/test_mastermind_executive_app_asgi.py``'s ``_token`` /
   ``_FakeJwksCache`` helpers); no production credential is read or copied;
3. the WO-12 host-lane MCP producer (``build_hermes_host_mcp_app``) served
   by uvicorn on 127.0.0.1 — the App-side forwarding of the private
   ``selected_child_admit`` frame over the real Unix ingress.

Usage:
    python3 scripts/dev_hermes_child_request_mcp.py \
        --home <workdir> --material <freeze.json> \
        --port 8731 --token-out <token.txt>

The freeze file shape (written by the host-side freeze operator — in the
lane proof, the proof script):
    {"commands": {"child-request:<64hex>": <ChildExecutionRequest.v1 envelope dict>}}

The file is hot-reloaded into the live binding dict (the host may re-freeze
the same command with drifted content to produce the precise CONFLICT
receipt, exactly like the WO-13 test does).
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# The repo's composition test modules import each other by bare module
# name (pytest's rootdir path setup), so the tests directory itself must
# be importable for the dev/test issuance fixtures to load.
if str(_REPO_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "tests"))

# The dev/test issuance path the repo's own composition tests use.
from tests import test_mastermind_executive_app_asgi as fixture  # noqa: E402
from tests import test_coo_principal_mandate as mandate_fixture  # noqa: E402
from tests import test_executive_coo_host as host_fixture  # noqa: E402
from tests import test_executive_service as service_fixture  # noqa: E402
from tests import test_hermes_selected_child_ingress as ingress  # noqa: E402

from control_plane.coo_principal_host import MISSION_AUTHORITY_VERSION  # noqa: E402
from control_plane.executive_service import (  # noqa: E402
    CeoIngressAppBinding, ExecutiveControlService)
from integrations.business_mcp_auth.contracts import (  # noqa: E402
    load_resource_policy, subject_digest)
from integrations.executive_mcp.hermes_host import build_hermes_host_mcp_app  # noqa: E402
from integrations.hermes_delegate.executive import (  # noqa: E402
    ExecutiveSelectedChildTarget)
from integrations.mastermind_executive_app.app import AppSettings  # noqa: E402
from integrations.mastermind_executive_app.coo import (  # noqa: E402
    CooAppSettings, create_coo_app)
from integrations.mastermind_executive_app.coo_binding import (  # noqa: E402
    BINDING_SCHEMA, COO_SCOPES, _digest, principal_frame)
from integrations.mastermind_executive_app.gateway import AppPolicies  # noqa: E402

WORK_REF = ingress.WORK_REF
CLIENT = ingress.CLIENT


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", required=True, help="persistent workdir for this dev stack")
    parser.add_argument("--material", required=True,
                        help="host-freeze JSON: {'commands': {command: envelope}}")
    parser.add_argument("--port", type=int, default=8731)
    parser.add_argument("--token-out", required=True,
                        help="where to write the dev-signed Bearer JWT")
    parser.add_argument("--facts-out", default=None,
                        help="where to write the endpoint facts JSON")
    return parser.parse_args()


def _load_material(path: Path) -> dict:
    raw = json.loads(path.read_text())
    commands = raw.get("commands") if isinstance(raw, dict) else None
    if not isinstance(commands, dict):
        raise SystemExit(f"material file {path} must carry a 'commands' mapping")
    return {str(k): dict(v) for k, v in commands.items()}


class _MaterialWatcher(threading.Thread):
    """Hot-reload the host-freeze file into the LIVE binding dict.

    The Control reads ``app_binding.child_request_material`` (a real dict)
    on every admit frame, so in-place mutation is the honest host-side
    re-freeze: the same dict object, new content, no protocol surface.
    """

    def __init__(self, path: Path, material: dict) -> None:
        super().__init__(daemon=True, name="host-freeze-watcher")
        self._path = path
        self._material = material
        self._stamp: float | None = None
        self.loads = 0

    def _poll(self) -> None:
        try:
            stamp = self._path.stat().st_mtime
        except OSError:
            return
        if stamp == self._stamp:
            return
        self._stamp = stamp
        try:
            loaded = _load_material(self._path)
        except Exception as exc:  # a broken re-freeze never tears down the host
            print(f"[host-freeze] reload refused ({exc}); keeping the prior freeze",
                  file=sys.stderr, flush=True)
            return
        self._material.clear()
        self._material.update(loaded)
        self.loads += 1
        print(f"[host-freeze] loaded {len(loaded)} frozen command(s) "
              f"(load #{self.loads})", flush=True)

    def prime(self) -> None:
        self._poll()

    def run(self) -> None:
        while True:
            self._poll()
            time.sleep(0.2)


async def _stand_up_control(home: Path, material: dict):
    """The real Control: service, Runtime, seeded root/work child, authority
    host, armed binding with the frozen selected-child target and the live
    child-request material dict."""

    socket_root = home / "run"
    socket_root.mkdir(parents=True, exist_ok=True)
    config = service_fixture._config(
        home, socket_root=socket_root, coo_autonomy_armed=True,
        coo_tick_interval_seconds=3600.0)
    holder = {"finish_gate": asyncio.Event()}

    def factory(runtime):
        supervisor = ingress._SealingSupervisor(runtime, finish_gate=holder["finish_gate"])
        holder["supervisor"] = supervisor
        return supervisor

    uid = os.geteuid()
    binding = CeoIngressAppBinding(
        peer_uid=uid, armed=False,
        grounding_provider=SimpleNamespace(observe=lambda: {}),
        principal_admission_armed=True,
        principal_admission_guard=lambda _value: None)
    service = ExecutiveControlService(
        config, supervisor_factory=factory, autonomy_guard=(lambda: None),
        terminal_return_projector=lambda candidate: service_fixture._capture_projection(
            [], candidate),
        ceo_ingress_socket_path=socket_root / "selected-child.sock",
        ceo_ingress_peer_uid=uid + 1,
        ceo_ingress_grounding_provider=SimpleNamespace(observe=lambda: {}),
        ceo_ingress_armed=False, ceo_ingress_app_binding=binding)
    await service.start()
    # Seed the Runtime exactly like the WO-13 composition: a root job and
    # one admitted work child the frozen selected-child target names.
    assert (await service_fixture._request(service, "register-worker"))["ok"] is True
    ingress._register_peer(service)
    intent = service_fixture._coo_intent(config, "hermes-lane-proof")
    receipt = service._submit_service_intent(intent)
    root = service.runtime.jobs.get_job(receipt["job_id"])
    work = ingress._admit_work_child(service, root)
    # The installed principal-facts host (missions/policy/binding).
    authority_dir = home / "selected-child-authority"
    authority_dir.mkdir(parents=True, exist_ok=True)
    host, authority_config, _principal, _path = host_fixture.setup(authority_dir)
    authority_config["missions"][0].update(
        authority_version=MISSION_AUTHORITY_VERSION,
        principal_actions=["bounded_intent", "governed_orchestration"])
    document = json.loads(json.dumps(mandate_fixture.mission_doc()).replace(
        '"JOB-100"', json.dumps(root.job_id)))
    host.workspace.read_mission_for_work_ref = lambda work_ref: document
    target = ExecutiveSelectedChildTarget(
        work_ref=WORK_REF,
        children=(ingress.ExecutiveSelectedChild(
            selection=ingress._frozen_selection(work), attempt_ordinal=1),),
        currentness_guard=lambda: None)
    service._ceo_ingress_app_binding = dataclasses.replace(
        service._ceo_ingress_app_binding,
        principal_facts_factory=lambda runtime: host,
        selected_child_target=target,
        child_request_material=material)
    socket_path = socket_root / "selected-child.sock"
    # The composition namespace, exactly like the WO-13 test's ``_control``.
    stack = SimpleNamespace(
        service=service, root=root, work=work, target=target, host=host,
        authority_config=authority_config, document=document,
        socket=socket_path, finish_gate=holder["finish_gate"])
    return stack, socket_path


async def _stand_up_app(stack, rsa_key, socket_path: Path):
    """The real COO App over the dev-issued principal (mirrors the repo's
    ``_installed_app`` composition test)."""

    from tests.test_executive_coo_install_binding import policy as install_policy

    subject = "c29-selected-child-subject"
    raw = install_policy("executive-coo", list(COO_SCOPES))
    digest = subject_digest(issuer=raw["issuer"], subject=subject)
    raw["allowed_subject_digests"] = [digest]
    read_raw = install_policy("executive-read", ["mastermind.executive.read"])
    read_raw["allowed_subject_digests"] = [digest]
    submit_raw = install_policy("executive-submit", [
        "mastermind.executive.intent.submit", "mastermind.executive.read"])
    submit_raw["allowed_subject_digests"] = [digest]
    cache = fixture._FakeJwksCache(rsa_key)
    token = fixture._token(rsa_key, scope=" ".join(COO_SCOPES), iss=raw["issuer"],
                           aud=raw["resource"], sub=subject, client_id=CLIENT)
    coo_policy = load_resource_policy(raw)
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    principal = await JwtAuthenticator(
        policy=coo_policy, jwks_cache=cache).verify_token(token, now=fixture.NOW)
    binding = {"schema": BINDING_SCHEMA, "enabled": True,
               "binding": {**principal_frame(principal), "permission_digest": "a" * 64}}
    stack.authority_config["policy"] = dict(raw)
    stack.authority_config["binding"] = binding
    stack.authority_config["missions"][0]["principal_binding_digest"] = \
        _digest(binding["binding"])
    base = AppSettings(
        policies=AppPolicies(load_resource_policy(read_raw),
                             load_resource_policy(submit_raw)),
        mastermind_root=Path(tempfile.mkdtemp(prefix="mmx-hermes-host-", dir="/tmp")),
        macro_root_flag=None, environ={}, ceo_ingress_socket_path=socket_path,
        read_from_ceo_ingress=True, jwks_cache=cache, clock=lambda: fixture.NOW)
    settings = CooAppSettings(
        executive=base, policy=coo_policy, load_binding=lambda: binding,
        authority_provider=lambda p, work: stack.host.source.snapshot(work)[2],
        mission_provider=lambda p, work: stack.host.workspace.read_mission_for_work_ref(work),
        selected_child_target=stack.target)
    return settings, token


async def main() -> int:
    args = _parse_args()
    home = Path(args.home).resolve()
    home.mkdir(parents=True, exist_ok=True)
    material_path = Path(args.material).resolve()
    material: dict = {}
    watcher = _MaterialWatcher(material_path, material)
    watcher.prime()
    if not material:
        raise SystemExit(f"no frozen commands in {material_path}; the host must freeze "
                         "at least one before the lane can admit anything")

    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
    rsa_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)

    stack, socket_path = await _stand_up_control(home, material)
    settings, token = await _stand_up_app(stack, rsa_key, socket_path)
    core = create_coo_app(settings, audit_sink=ingress.app_fixture.Sink())
    app = build_hermes_host_mcp_app(core)

    Path(args.token_out).write_text(token)
    facts = {"endpoint": f"http://127.0.0.1:{args.port}/mcp/hermes-host",
             "tool": "child_request_admit", "work_ref": WORK_REF,
             "material": str(material_path), "auth": "Bearer (dev-issued JWT)",
             "note": "dev/proof stack; repo dev/test issuance path; no production "
                     "credentials"}
    facts_path = Path(args.facts_out) if args.facts_out else \
        Path(args.token_out).with_suffix(".facts.json")
    facts_path.write_text(json.dumps(facts, indent=2))
    print(f"[hermes-host] serving {facts['endpoint']}", flush=True)
    print(f"[hermes-host] token written to {args.token_out}", flush=True)
    print(f"[hermes-host] facts written to {facts_path}", flush=True)

    import uvicorn
    watcher.start()
    config = uvicorn.Config(app._app, host="127.0.0.1", port=args.port,
                            log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        watcher.join(timeout=1.0)
        await stack.service.close()
        print("[hermes-host] control service closed; dev stack stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
