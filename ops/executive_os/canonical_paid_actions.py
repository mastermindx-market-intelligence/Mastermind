#!/usr/bin/env python3
"""Closed paid profile actions reached only from the existing service owner.

Arguments are expected identities, never authority. Each actual publication
owner qualifies the selected root release, stopped services, original Control
preimage, Runtime quiescence and CONFIG_ROOT lock itself. Nothing here starts
inference, changes credentials, selects an App release or arms Control.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

from ops.executive_os import canonical_paid_definition as definition
from ops.executive_os import autonomy_control as owner
from control_plane.paid_model_execution_contract import paid_host_reference, PAID_REGISTRY_NAMESPACE
from control_plane.executive_capacity_join import CapacityJoin, PROVIDER_CAPACITY_SCHEMA


def prepare_paid(release_sha,control_sha,*,transport_host,capacity_id):
    host=owner.ProductionCeoSubmitHost()
    host.require_exact_install(release_sha)
    host.require_transaction_absent()
    host.require_services_already_stopped()
    host.require_service_uids_quiescent()
    prior=host.load_unarmed_configs(release_sha)
    host.require_runtime_quiescent(prior)
    if prior.control_sha256!=control_sha:raise ValueError('paid Control preimage differs')
    root=definition._RELEASES_ROOT/release_sha
    external={name:owner._read_root_file(root/path,
        modes=definition._RELEASE_SOURCE_MODES,uid=0,gid=0)[0]
        for name,path in dict(definition.BOUND_SOURCE_PATHS,
            overlay='ops/native_fabric/paid_canonical_glm/external-preimages.json').items()}
    from ops.native_fabric.quota_continuity.candidate.paid_host_qualification import _read_owned
    registry_raw,_=_read_owned(Path(PAID_REGISTRY_NAMESPACE),owners={0,501},maximum=131072)
    registry=json.loads(registry_raw)
    entry=registry[transport_host]
    canonical_ref=paid_host_reference(transport_host,entry['ssh_alias'])
    artifacts=definition.render_definition(prior,release_sha,host_ref=canonical_ref,
        capacity_capability_id=capacity_id,external_sources=external)
    # Existing CapacityJoin is identity DATA only. Inert v1 has no admitted
    # remote image or bindings and remains explicitly disabled/unselected.
    join=CapacityJoin(canonical_ref,capacity_id,PROVIDER_CAPACITY_SCHEMA,
        hashlib.sha256(artifacts['profile.json']).hexdigest())
    return definition.publish_definition(release_sha,control_sha,artifacts,
        capacity_join=join,external_sources=external)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare-paid','qualify-paid','stage-paid','reconcile-paid','status-paid'))
    parser.add_argument('--expected-sha',required=True)
    parser.add_argument('--expected-definition-sha256')
    parser.add_argument('--control-sha256')
    parser.add_argument('--transport-host')
    parser.add_argument('--capacity-id')
    parser.add_argument('--python-path')
    parser.add_argument('--capture-root')
    parser.add_argument('--worker-id')
    parser.add_argument('--quota-class')
    parser.add_argument('--account-label')
    args=parser.parse_args(argv)
    try:
        if os.geteuid()!=0:raise ValueError()
        source=Path(__file__).resolve()
        expected=definition._RELEASES_ROOT/args.expected_sha/'ops/executive_os/canonical_paid_actions.py'
        if source!=expected:raise ValueError()
        if args.action=='prepare-paid':
            if not all((args.control_sha256,args.transport_host,args.capacity_id)):raise ValueError()
            result=prepare_paid(args.expected_sha,args.control_sha256,
                transport_host=args.transport_host,capacity_id=args.capacity_id)
        elif args.action=='qualify-paid':
            if not all((args.control_sha256,args.expected_definition_sha256,args.transport_host,
                        args.python_path,args.capture_root,args.worker_id,args.quota_class,args.account_label)):
                raise ValueError()
            from ops.executive_os.canonical_paid_qualification import qualify_and_publish
            result=qualify_and_publish(args.expected_sha,args.control_sha256,args.expected_definition_sha256,
                transport_host=args.transport_host,python_path=args.python_path,capture_root=args.capture_root,
                worker_id=args.worker_id,quota_class=args.quota_class,account_label=args.account_label)
        elif args.action in {'stage-paid','reconcile-paid'}:
            if not args.expected_definition_sha256:raise ValueError()
            if args.action=='stage-paid' and not args.control_sha256:raise ValueError()
            from types import SimpleNamespace
            from ops.executive_os.paid_control_staging import run_command
            return run_command(SimpleNamespace(command=('paid-control-stage' if args.action=='stage-paid'
                else 'paid-control-stage-reconcile'),expected_sha=args.expected_sha,
                expected_control_sha256=args.control_sha256,
                expected_definition_sha256=args.expected_definition_sha256))
        else:
            if not args.expected_definition_sha256:raise ValueError()
            from ops.executive_os.canonical_paid_lifecycle import run_paid_lifecycle
            result=run_paid_lifecycle(args.action.removesuffix('-paid'),args.expected_sha,args.expected_definition_sha256)
        print(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False))
        return 0
    except Exception:
        print('canonical_paid_action_unconfirmed',file=sys.stderr)
        return 76


if __name__=='__main__':raise SystemExit(main())
