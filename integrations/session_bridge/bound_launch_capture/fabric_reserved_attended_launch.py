"""Compile the original reserved request, never launch from correlation alone.

This component prepares the actual existing lane-runtime invocation. It owns
no admission, credentials, lease, process or result lifecycle. The installed
executor keeps its pre-effect refusal until an authenticated physical owner
supplies the real authority, filesystem/isolation/canary proofs and full START.
"""
from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Mapping

from control_plane.executive_fabric_bridge_broker import start_request_sha256
from control_plane.executive_worker_broker import BrokerPolicy, BrokerProtocolError, _launch_spec_from_wire
from control_plane.fabric_attended_claude import prepare_attended_claude_launch
from integrations.session_bridge.bound_launch_capture import fabric_launch_reservation as reservation


class ReservedLaunchRefused(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class ReservedAttendedLaunch:
    request_sha256: str
    descriptor: object
    timeout_seconds: float
    cancel_grace_seconds: float
    validation_commands: tuple[tuple[str, ...], ...]

    def lane_runtime_arguments(self):
        """Non-secret arguments for the incumbent owner, NOT start permission.

        The owner must independently check admission at the process boundary,
        add only its exact realm credential and retain its existing lease,
        receipt, collection and cancellation ownership. No environment is
        inherited and no shell/sub.sh fallback is represented here.
        """
        return dict(command=self.descriptor.argv,
                    cwd=self.descriptor.workspace_path,
                    input_text=self.descriptor.stdin_text,
                    shell=False, env=dict(self.descriptor.environment),
                    timeout=self.timeout_seconds,
                    terminate_grace=self.cancel_grace_seconds)


def prepare_reserved_attended_launch(payload, *, correlation, run_id,
                                     routing_root_id, routing_parent_run_id,
                                     policy: BrokerPolicy, binary, binding, profile,
                                     model_class, max_turns, result_schema,
                                     allowed_validation_commands=()):
    """Recheck every original request byte before the existing spec compiler.

    Caller supplies correlation already read from the original reservation,
    not a newly self-signed request. This comparison does not authenticate that
    caller or authorize an effect. Owner policy/catalogue/binary/schema are
    independent inputs, never fields copied from the request.
    """
    try:
        correlation = reservation.validate_correlation(
            correlation, run_id=run_id, routing_root_id=routing_root_id,
            routing_parent_run_id=routing_parent_run_id)
        if type(payload) is not dict or not {
                'binding', 'physical_binding_sha256', 'launch_spec',
                'validation_commands'} <= set(payload) <= {
                'binding', 'physical_binding_sha256', 'launch_spec',
                'validation_commands', 'control_recovery', 'start_request_sha256'}:
            raise ReservedLaunchRefused('reserved_request_shape')
        # Copy the input before checking/decoding it so concurrent caller edits
        # cannot rewrite the object after its original digest was verified.
        payload = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        expected = reservation.backend_start_context(correlation)
        digest = start_request_sha256(payload)
        if (digest != expected['start_request_sha256']
                or payload['binding'] != expected['binding']
                or payload['physical_binding_sha256'] != expected['physical_binding_sha256']
                or ('start_request_sha256' in payload
                    and payload['start_request_sha256'] != digest)):
            raise ReservedLaunchRefused('reserved_request_changed')
        raw_spec = payload['launch_spec']
        if (type(raw_spec) is not dict or raw_spec.get('run_id') != run_id
                or raw_spec.get('job_id') != expected['binding']['job_id']
                or raw_spec.get('effective_grant_digest') != expected['binding']['effective_grant_digest']):
            raise ReservedLaunchRefused('reserved_spec_identity_changed')
        if type(policy) is not BrokerPolicy:
            raise ReservedLaunchRefused('fixed_worker_policy_required')
        commands = payload['validation_commands']
        if (type(commands) is not list or len(commands) > 32
                or any(type(argv) is not list or not argv
                       or any(type(arg) is not str or not arg or '\x00' in arg for arg in argv)
                       or tuple(argv) not in allowed_validation_commands for argv in commands)):
            raise ReservedLaunchRefused('reserved_validation_not_allowed')
        spec = _launch_spec_from_wire(raw_spec, policy)
        for label, value in [('timeout', spec.timeout_seconds),
                             ('cancel_grace', spec.cancel_grace_seconds)]:
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or value < 0 or (label == 'timeout' and value == 0)):
                raise ReservedLaunchRefused('reserved_' + label + '_invalid')
        descriptor = prepare_attended_claude_launch(
            spec, binary=binary, binding=binding, profile=profile,
            model_class=model_class, max_turns=max_turns, result_schema=result_schema)
        return ReservedAttendedLaunch(digest, descriptor,
                                      spec.timeout_seconds, spec.cancel_grace_seconds,
                                      tuple(tuple(argv) for argv in commands))
    except ReservedLaunchRefused:
        raise
    except (BrokerProtocolError, ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
        # Never leak a prompt, schema or credential-shaped hostile input.
        raise ReservedLaunchRefused('reserved_launch_preparation_refused') from exc
