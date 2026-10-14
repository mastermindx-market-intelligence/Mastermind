#!/usr/bin/env python3
"""Run one remote sub.sh task under the existing physical LaneLease.

This is not a scheduler. The Studio-side remote_sub.sh remains the placement and
provider-lease owner; this helper only closes the host-admission race between
telemetry selection and process start.
"""
from __future__ import annotations

import json
import asyncio
import hashlib
from contextlib import ExitStack
import os
import sys
from pathlib import Path
import time

from .lane_runtime import (
    LaneAdmissionRefused,
    LaneLease,
    LaneRuntimeConfigError,
    LaneRuntimeError,
    OwnedProcessStartError,
    cleanup_receipt_is_proven,
    install_signal_cleanup,
    load_runtime_config,
    parse_bounded_seconds,
    run_owned_process,
    begin_owned_process,
    abort_owned_process,
    start_owned_process_finisher,
    retain_owned_start_bytes,
    validate_owned_capture_live,
    owned_capture_paths,
    _launch_receipt_directory,
)


def _fail(message: str, code: int) -> int:
    print(message, file=sys.stderr, flush=True)
    return code


def grok_plaintext_and_usage(raw: str, run_id: str, model: str):
    """Normalize one Grok headless JSON response using observed usage only.

    Legacy inert/older plain responders keep the exact plaintext result with
    unknown usage. Malformed structured results expose no JSON thought fields.
    """
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        # Non-JSON legacy plaintext is okay. A malformed structured payload
        # must not expose possible private reasoning on an error path.
        return ("", None) if raw.lstrip().startswith(("{", "[")) else (raw, None)
    if not isinstance(parsed, dict):
        return "", None
    text = parsed.get("text")
    if not isinstance(text, str):
        return "", None
    usage = parsed.get("usage")
    sid = parsed.get("sessionId")
    if not isinstance(usage, dict) or not isinstance(sid, str) or not 0 < len(sid) <= 256:
        return text, None
    names = ("input_tokens", "cache_read_input_tokens", "output_tokens", "total_tokens")
    if not all(type(usage.get(k)) is int and 0 <= usage[k] <= 2**53 for k in names):
        return text, None
    extra = usage.get("cache_creation_input_tokens", 0)
    if type(extra) is not int or not 0 <= extra <= 2**53:
        return text, None
    noncached, cached, output, observed_total = (usage[k] for k in names)
    full_input = noncached + cached + extra
    if full_input > 2**53 or full_input + output != observed_total:
        return text, None
    return text, {
        "schema": "mastermind.grok_usage.v1",
        "status": "observed",
        "reason": "native_headless_final",
        "session_ids": [sid],
        "input_tokens": full_input,
        "cached_tokens": cached,
        "output_tokens": output,
        "total_tokens": observed_total,
        "source": "grok_native_headless",
        "served_model": model,
        "run_id": run_id,
    }



def grok_output_binding(receipt, contract, manifest, raw_stdout, display_stdout, env):
    """Original producer binds normalized output; never backfills an old run."""
    import native_remote  # legacy CLI only; never selected by the fixed finite entry
    import artifact_production
    if grok_plaintext_and_usage(raw_stdout, contract['run_id'], 'grok-4.6')[0] != display_stdout:
        raise ValueError('grok_output_transform_mismatch')
    row = json.loads(Path(receipt).read_text().splitlines()[-1])
    raw = raw_stdout.encode('utf-8');normalized = display_stdout.encode('utf-8')
    if (row.get('schema') != 'mastermind.local_owned_process_receipt.v1'
            or row.get('label') != contract['run_id']
            or row.get('returncode') != 0 or row.get('timed_out') is not False
            or row.get('stdout_truncated') is not False or row.get('stderr_truncated') is not False
            or not cleanup_receipt_is_proven(row.get('cleanup') or {})
            or row.get('stdout_bytes') != len(raw)
            or row.get('stdout_sha256') != hashlib.sha256(raw).hexdigest()):
        raise ValueError('grok_output_capture_unqualified')
    scope = {k:env.get(v,'') for k,v in {'root':'POOL_ORCHESTRATOR_ID',
        'parent':'POOL_PARENT_RUN_ID','run_id':'REMOTE_SUB_RUN_ID','host':'LANE_REMOTE_HOST',
        'lease_id':'POOL_LEASE_ID','account':'POOL_ACCOUNT','support_digest':'SUPPORT_DIGEST'}.items()}
    if any(scope[k] != contract[k] for k in ('root','parent','run_id','support_digest')):
        raise ValueError('grok_output_scope')
    if not all(native_remote.IDENT.fullmatch(scope[k]) for k in ('root','parent','run_id','host','lease_id','account')):
        raise ValueError('grok_output_scope')
    return dict(schema='mastermind.grok_normalized_output.v1', algorithm='grok_plaintext_and_usage_v1',
        **scope, mode='grok', model='grok-4.6', raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),
        normalized_bytes=len(normalized),normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        contract=contract,manifest=manifest)


def _run_lease_process(*, lease, state, key, receipt, arguments, at_boundary=None):
    """Shared incumbent process/capture/cleanup path. Never acquire a new lease.

    Called while the original controller owns its existing lease/context. This
    is execution mechanics, not an admission producer or separate lifecycle.
    """
    install_signal_cleanup(on_unproven=lease.hold_for_reconciliation)
    try:
        if at_boundary is not None:
            at_boundary()
        state["started"] = True
        return run_owned_process(label=key, receipt_path=receipt,
                                 timeout_returncode=124, **arguments)
    except OwnedProcessStartError:
        state["started"] = False
        raise
    finally:
        _retain_original_cleanup_hold(lease=lease, state=state, key=key, receipt=receipt)


def _verify_reserved_realm_observation(*, prepared, preparation,
                                     credential_loader, credential_realm_owner, credential_physical_binding,
                                     credential_bindings_document=None,
                                     credential_profiles_document=None):
    """Observe the existing fixed realm owner, never issue task authority.

    Ordinary Control/Runtime authority and the independently verified run-bound
    secret canary remain separate. An interactive canary is not a task grant.
    """
    from control_plane.fabric_control_start import ControlStartRefused
    from control_plane.codex_provider_realm import SubscriptionRealmOwner
    from control_plane.executive_fabric_adapter import FabricHostBinding
    if not callable(credential_loader):
        raise ControlStartRefused('realm_credential_loader_required')
    if type(credential_realm_owner) is not SubscriptionRealmOwner:
        raise ControlStartRefused('realm_owner_required')
    if type(credential_physical_binding) is not FabricHostBinding:
        raise ControlStartRefused('realm_physical_owner_required')
    from control_plane.claude_subscription_worker import _resolve_catalog_pair
    from control_plane.subscription_catalog import compose_catalog_digest
    verification_failed = False
    try:
        observed = credential_realm_owner.observe()
        fields = {'worker_id', 'control_uid', 'binding_id', 'profile_id', 'adapter_id',
                  'realm_config_sha256', 'realm_generation', 'catalog_digest'}
        if type(observed) is not dict or set(observed) != fields:
            raise ControlStartRefused('realm_observation_invalid')
        binding, profile, _ = _resolve_catalog_pair(observed['binding_id'],
            bindings_document=credential_bindings_document,
            profiles_document=credential_profiles_document)
        descriptor = prepared.descriptor
        physical = credential_physical_binding
        policy = preparation['policy']
        catalog_digest = compose_catalog_digest(
            bindings_document=credential_bindings_document,
            profiles_document=credential_profiles_document)
        if (physical.digest != preparation['correlation']['runtime_binding']['physical_binding_sha256']
                or observed['worker_id'] != descriptor.worker_id
                or type(observed['control_uid']) is not int
                or observed['control_uid'] != preparation['policy'].control_uid
                or observed['realm_config_sha256'] != physical.worker_source_config_digest
                or observed['worker_id'] != physical.worker_id
                or policy.worker_uid != physical.worker_uid or policy.worker_gid != physical.worker_gid
                or physical.bridge_uid != physical.worker_uid
                or os.getuid() != physical.worker_uid or os.geteuid() != physical.worker_uid
                or os.getgid() != physical.worker_gid or os.getegid() != physical.worker_gid
                or Path(policy.provider_home) != Path(physical.provider_home)
                or type(observed['realm_generation']) is not int
                or observed['realm_generation'] < 1
                or observed['catalog_digest'] != catalog_digest
                or binding != preparation['binding'] or profile != preparation['profile']
                or observed['binding_id'] != descriptor.binding_id
                or observed['profile_id'] != descriptor.profile_id
                or observed['adapter_id'] != descriptor.adapter_id
                or descriptor.model_class != preparation['model_class']
                or descriptor.model != binding.model_for(profile, preparation['model_class'])
                or descriptor.endpoint != binding.effective_base_url):
            raise ControlStartRefused('realm_credential_binding_changed')
    except Exception:
        verification_failed = True
    if verification_failed:
        # No opaque observer error or sensitive context crosses the boundary.
        raise ControlStartRefused('realm_observation_unqualified') from None
    return observed


def _prepare_reserved_attended_under_lease(*, payload, authority, preparation,
                                       lease, state, key, receipt, nice,
                                       check_original_owner, credential_loader=None,
                                       credential_realm_owner=None, credential_physical_binding=None,
                                       credential_bindings_document=None,
                                       credential_profiles_document=None):
    """Private composition seam, not exposed by CLI, RPC or environment.

    Only the existing authenticated owner may call this inside its original
    O_EXCL reservation and live lease. check_original_owner is a private
    composition/test seam: it must raise unless the actual current realm,
    canary, attendance, binary, schema and assignment isolation are qualified.
    A callable, boolean or this helper's result does NOT establish those facts.
    No production factory is enabled by adding this function. The public bound
    path remains refused until that concrete owner composition is reviewed.
    """
    from control_plane.fabric_control_start import ControlStartAuthority, ControlStartRefused
    from ..fabric_reserved_attended_launch import prepare_reserved_attended_launch
    if type(authority) is not ControlStartAuthority or not callable(check_original_owner):
        raise ControlStartRefused("authenticated_original_owner_required")
    original = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    authority.require(original)
    prepared = prepare_reserved_attended_launch(original, **preparation)
    if prepared.descriptor.run_id != key:
        raise ControlStartRefused("original_owner_run_mismatch")
    credential_inputs = dict(prepared=prepared, preparation=preparation,
        credential_loader=credential_loader, credential_realm_owner=credential_realm_owner,
        credential_physical_binding=credential_physical_binding,
        credential_bindings_document=credential_bindings_document,
        credential_profiles_document=credential_profiles_document)
    original_realm = _verify_reserved_realm_observation(**credential_inputs)
    arguments = prepared.lane_runtime_arguments()
    if arguments['env'] != dict(prepared.descriptor.environment):
        raise ControlStartRefused('realm_nonsecret_environment_changed')
    arguments['nice'] = nice
    credential_attempted = False

    def at_boundary():
        nonlocal credential_attempted
        if credential_attempted:
            raise ControlStartRefused('realm_credential_boundary_already_consumed')
        # The callback checks actual owner evidence; its return is never a seal.
        if check_original_owner(prepared) is not None:
            raise ControlStartRefused("owner_check_must_not_issue_authority")
        # A slow check or wait must not extend the existing Control command.
        authority.require(original)
        if _verify_reserved_realm_observation(**credential_inputs) != original_realm:
            raise ControlStartRefused('realm_observation_changed')
        from control_plane.claude_subscription_worker import _safe_credential
        if arguments['env'] != dict(prepared.descriptor.environment):
            raise ControlStartRefused('realm_nonsecret_environment_changed')
        credential_attempted = True
        load_failed = False
        try:
            credential = _safe_credential(credential_loader)
        except Exception:
            load_failed = True
        if load_failed:
            # Raise outside the handler so a hostile exception is not retained
            # as __context__ even when an outer owner records the refusal.
            raise ControlStartRefused('realm_credential_unavailable') from None
        try:
            # Loading can be slow; re-read original filesystem/binary owners too.
            if check_original_owner(prepared) is not None:
                raise ControlStartRefused('owner_check_must_not_issue_authority')
            authority.require(original)
            if _verify_reserved_realm_observation(**credential_inputs) != original_realm:
                raise ControlStartRefused('realm_observation_changed')
            arguments['env']['ANTHROPIC_AUTH_TOKEN'] = credential
        finally:
            credential = None

    return prepared, arguments, at_boundary


def _run_reserved_attended_under_lease(**kwargs):
    prepared, arguments, at_boundary = _prepare_reserved_attended_under_lease(**kwargs)
    try:
        result = _run_lease_process(lease=kwargs['lease'], state=kwargs['state'],
            key=kwargs['key'], receipt=kwargs['receipt'], arguments=arguments, at_boundary=at_boundary)
        return result, prepared.validation_commands
    finally:
        arguments['env'].pop('ANTHROPIC_AUTH_TOKEN', None)


def _retain_original_cleanup_hold(*, lease, state, key, receipt):
    if state.get("started"):
        proven = False
        try:
            row = json.loads(receipt.read_text().splitlines()[-1])
            proven = row.get("label") == key and cleanup_receipt_is_proven(row.get("cleanup", {}))
        except (OSError, ValueError, IndexError):
            pass
        if not proven:
            lease.hold_for_reconciliation("worker_cleanup_unproven")


def _begin_lease_process(*, lease, state, key, receipt, arguments, at_boundary):
    """Original main-thread controller keeps its lease after START mechanics.

    The caller must already own the reservation and lease for this entire
    controller lifetime. This helper never enters/exits/releases that context.
    The same runtime finisher retains capture/cleanup; the done callback merely
    applies this original controller's existing terminal hold check.
    """
    asyncio.get_running_loop()  # Refuse missing event-loop owner before effects.
    install_signal_cleanup(on_unproven=lease.hold_for_reconciliation)
    owner = None
    try:
        at_boundary()
        state['started'] = True
        owner = begin_owned_process(label=key, receipt_path=receipt,
                                    timeout_returncode=124, **arguments)
        finisher = start_owned_process_finisher(owner)
        # The resources stay strongly retained even if the successful START
        # handler returns. This is the original lease, never a new acquisition.
        owner._original_lease = lease
        def settled(task):
            try:
                if not task.cancelled():
                    task.exception()  # Retained on owner; suppress unobserved-task log.
            finally:
                _retain_original_cleanup_hold(lease=lease, state=state, key=key, receipt=receipt)
        finisher.add_done_callback(settled)
        return owner
    except OwnedProcessStartError:
        state['started'] = False
        raise
    except BaseException as exc:
        if owner is not None and owner.result is None and owner.failure is None:
            try:
                abort_owned_process(owner, exc)
            finally:
                _retain_original_cleanup_hold(lease=lease, state=state, key=key, receipt=receipt)
        else:
            _retain_original_cleanup_hold(lease=lease, state=state, key=key, receipt=receipt)
        raise


def _begin_reserved_attended_under_lease(*, owned_capture=False, **kwargs):
    """Source-only private composition, not a CLI/RPC/public admission bypass.

    The returned resource is NOT a full START. The qualified original Backend
    must separately observe the independently pinned executed image and retain
    complete launch/assignment evidence before exposing native START.

    With owned_capture=True the reserved-attended begin opts into the fixed
    private file capture: run_dir and the result schema come only from this
    exact real prepared descriptor, the three pinned files are reserved before
    Popen, and their actual identities are bound on the original handle. The
    integrated assembler must still require the live pinned files through
    lane_runtime.validate_owned_capture_live(owner) before START; binding
    claims live bound output ownership, never a completed result.
    """
    from control_plane.executive_fabric_bridge_broker import start_request_sha256
    original = json.loads(json.dumps(kwargs['payload'], ensure_ascii=False, allow_nan=False))
    prepared, arguments, at_boundary = _prepare_reserved_attended_under_lease(**kwargs)
    if start_request_sha256(original) != prepared.request_sha256:
        raise LaneRuntimeError('owned_start_original_request_changed')
    # The original controller selects the carrier before any spawn. Existing
    # bytes are unknown prior publication, never positive first-use proof.
    start_path = Path(kwargs['receipt']).with_suffix('.start.json')
    if not start_path.is_absolute():
        raise LaneRuntimeError('owned_start_original_carrier_required')
    _launch_receipt_directory(start_path)
    if os.path.lexists(start_path):
        raise LaneRuntimeError('owned_start_original_carrier_exists')
    if type(owned_capture) is not bool:
        raise LaneRuntimeError('owned_capture_option_invalid')
    capture_opt_in = owned_capture
    if capture_opt_in:
        # The finite executor takes run_dir and the result schema only from
        # this exact real prepared descriptor, never from caller arguments.
        descriptor = prepared.descriptor
        if (type(descriptor.run_dir) is not str or not descriptor.run_dir
                or type(descriptor.result_schema_json) is not str
                or not descriptor.result_schema_json):
            raise LaneRuntimeError('owned_capture_descriptor_unqualified')
        arguments = dict(arguments)
        arguments['owned_capture_run_dir'] = descriptor.run_dir
        arguments['owned_capture_result_schema_json'] = descriptor.result_schema_json
        # This is the exact request's admitted filesystem observation, not a
        # serialized Control authority. The original at_boundary check remains.
        manifest = original['launch_spec']['isolation_manifest']
        run_entries = [entry['identity'] for entry in manifest['entries']
                       if entry['disposition'] == 'CURRENT_RUN']
        stores = [entry for entry in manifest['roots']
                  if entry['path'] == str(kwargs['preparation']['policy'].run_root)]
        if len(run_entries) != 1 or len(stores) != 1:
            raise LaneRuntimeError('owned_capture_assignment_invalid')
        arguments['owned_capture_assignment'] = dict(run=run_entries[0], store=stores[0],
            control_uid=kwargs['preparation']['policy'].control_uid, worker_gid=kwargs['preparation']['policy'].worker_gid)
    try:
        owner = _begin_lease_process(lease=kwargs['lease'], state=kwargs['state'],
            key=kwargs['key'], receipt=kwargs['receipt'], arguments=arguments, at_boundary=at_boundary)
    finally:
        # The original generator shares this mapping. Popen copied it for the
        # child; remove the parent copy before returning the original handle.
        arguments['env'].pop('ANTHROPIC_AUTH_TOKEN', None)
    owner._original_preparation = prepared.descriptor
    owner._original_start_receipt_path = start_path
    owner._original_start_context = dict(binding=original['binding'],
        physical_binding_sha256=original['physical_binding_sha256'],
        request_sha256=prepared.request_sha256)
    if capture_opt_in:
        # Bind the actual pinned reservation created inside begin_owned_process;
        # caller path strings never establish capture ownership for START.
        try:
            owner._capture_reservation.expected_identity = {
                key: original['launch_spec'][key] for key in ('run_id', 'job_id', 'worker_id')}
            owner._original_capture_paths = owned_capture_paths(owner)
            validate_owned_capture_live(owner)
        except BaseException:
            kwargs['lease'].hold_for_reconciliation('owned_capture_binding_unconfirmed')
            raise
    return owner, prepared.validation_commands




def _execute(argv: list[str], state: dict) -> int:
    import native_remote  # legacy CLI only; never selected by the fixed finite entry
    if len(argv) != 6:
        return _fail(
            "usage: remote_sub_exec.py <key> <mode> <packet> <cwd> <model>", 2
        )
    _, key, mode, packet, cwd, model = argv
    here = Path(__file__).resolve().parent
    packet_path = Path(packet)
    if not packet_path.is_file():
        return _fail("REMOTE_SUB_PACKET_MISSING", 2)
    try:
        prompt = packet_path.read_text(encoding="utf-8")
    except OSError:
        return _fail("REMOTE_SUB_PACKET_UNREADABLE", 2)

    artifact_contract = None
    if prompt.startswith("FABRIC_ARTIFACT_REQUEST_V1 "):
        try:
            import artifact_production
            artifact_contract = artifact_production.parse_packet(prompt)
            artifact_production.bind(artifact_contract, key, mode, os.environ, here)
        except (ImportError, ValueError, TypeError, KeyError, RecursionError):
            return _fail("ARTIFACT_DELIVERY_CONTRACT_REFUSED", 65)
    artifact_failure = False

    # Optional correlation is read outside the prompt, before physical admission.
    # It does not change Runtime, provider or host admission requirements.
    try:
        from ..fabric_launch_transport import remote_launch_arguments
        launch_arguments = remote_launch_arguments(Path.home(), key, os.environ)
    except (OSError, ValueError, TypeError):
        return _fail("BOUND_LAUNCH_CONTEXT_REFUSED before_spawn=1", 78)

    # V2 carries correlation only. The legacy sub.sh command below cannot
    # enforce the original WorkerLaunchSpec or attest its isolated provider.
    # Refuse before physical admission, handler changes or provider effects;
    # an early gate receipt must never make that legacy path a native START.
    if launch_arguments or "FABRIC_LAUNCH_SNAPSHOT_SHA256" in os.environ:
        return _fail("BOUND_ATTENDED_EXECUTOR_UNAVAILABLE before_admission=1 before_spawn=1", 78)

    # Tilde belongs to this host, not to the controller that selected it.
    if cwd.startswith("~") and cwd != "~" and not cwd.startswith("~/"):
        return _fail("REMOTE_SUB_CWD_REFUSED", 2)
    try:
        cwd = str(Path(cwd).expanduser())
        if not Path(cwd).is_dir():
            return _fail("REMOTE_SUB_CWD_MISSING", 2)
    except (OSError, RuntimeError):
        return _fail("REMOTE_SUB_CWD_UNREADABLE", 2)

    if mode in native_remote.MODES:
        try:
            native_remote.scope(key, mode, model, here, os.environ, timing=state.get("timing"))
        except (ValueError, OSError) as exc:
            return _fail(str(exc), 78)

    try:
        timeout = parse_bounded_seconds(
            os.environ.get("REMOTE_SUB_CHILD_TIMEOUT"),
            default=7000.0,
            minimum=0.05,
            maximum=7200.0,
            key="REMOTE_SUB_CHILD_TIMEOUT",
        )
    except LaneRuntimeConfigError as exc:
        return _fail("REMOTE_SUB_PREFLIGHT_REFUSED " + str(exc), 78)

    config = load_runtime_config(os.environ, cpu_count=os.cpu_count() or 1)
    install_signal_cleanup()
    active_dir = here / "active"
    try:
        lease = LaneLease.acquire(
            active_dir,
            key=key,
            label=key,
            env=os.environ,
            reconcile_unreleased=True,
        )
    except LaneAdmissionRefused as exc:
        payload = json.dumps(
            exc.snapshot.public_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        return _fail("REMOTE_SUB_ADMISSION_REFUSED " + payload, 75)
    except LaneRuntimeError as exc:
        return _fail("REMOTE_SUB_ADMISSION_ERROR " + type(exc).__name__, 78)

    # Prompt bytes must not consume the operating system's per-argument limit.
    # The already-delivered file stays inside the existing per-run transport.
    if mode in ("glm", "minimax", "qwen"):
        command = ["bash", str(here / "sub.sh"), "--prompt-file", mode, str(packet_path.resolve()), cwd]
    else:
        command = ["bash", str(here / "sub.sh"), mode, prompt, cwd]
    if model:
        command.append(model)
    if mode in native_remote.MODES:
        command = native_remote.command(mode, model, prompt, cwd, packet_path=packet_path.resolve())
    lanes_dir = here / "lanes"
    child_env = dict(os.environ)
    child_env.pop('FABRIC_OPERATOR_CAPABILITY', None)
    if child_env.get('FABRIC_OPERATOR_CAPSULE'):
        from fabric_operator_client import load_operator_environment
        try:
            child_env = load_operator_environment(child_env, key, mode, model, packet_path.read_bytes())
        except (OSError, ValueError, TypeError):
            lease.release()
            return _fail("OPERATOR_CAPSULE_REFUSED", 78)
    child_env["POOL_USAGE_FILE"] = str(lanes_dir / f"{key}.usage.json")
    child_env["POOL_USAGE_RUN_ID"] = key
    if mode in native_remote.MODES:
        timeout = min(timeout, float(os.environ["NATIVE_LEASE_DEADLINE"])-time.time())
        if timeout <= 0:
            lease.release()
            return _fail("native_remote_lease_expired", 78)
    receipt = here / "lanes" / f"{key}.process.jsonl"
    diagnostic_reader = None
    if child_env.get('FABRIC_OPERATOR_CAPABILITY'):
        from fabric_operator_diagnostics import collect
        diagnostic_reader = lambda: collect(here, key)
    try:
        with lease, ExitStack() as artifact_stack:
            artifact_owner = (artifact_stack.enter_context(artifact_production.NewDirectory(artifact_contract))
                              if artifact_contract is not None else None)
            if mode in native_remote.MODES:
                child_env = native_remote.environment(mode, model, key, here, child_env)
            # Worker-spawned shell tools inherit PATH. The immutable, reviewed
            # "yes" shim bounds CPU-stealer lifetime even when an agent leaves
            # an unbounded background "taskset ... yes" shell running.
            if sys.platform.startswith("linux"):
                guard = here / "yes"
                if (not guard.is_file() or guard.is_symlink()
                        or not os.access(guard, os.X_OK)):
                    return _fail("FABRIC_CPU_STRESS_GUARD_UNAVAILABLE", 78)
                child_env["PATH"] = str(here) + os.pathsep + child_env.get("PATH", "/usr/bin:/bin")
            result = _run_lease_process(
                lease=lease, state=state, key=key, receipt=receipt,
                arguments=dict(command=command, cwd=cwd, timeout=timeout,
                               env=child_env, nice=config.nice,
                               receipt_diagnostics=diagnostic_reader,
                               **launch_arguments))

            display_stdout = result.stdout
            if mode == "grok":
                # Normalize even when the provider rc is nonzero. Never
                # echo structured JSON including its private thought field.
                display_stdout, usage_record = grok_plaintext_and_usage(result.stdout, key, model)
                if (usage_record is not None and result.returncode == 0
                        and result.cleanup_proven
                        and not result.stdout_truncated and not result.stderr_truncated):
                    usage_file = Path(child_env["POOL_USAGE_FILE"])
                    try:
                        fd = os.open(usage_file,
                                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                        with os.fdopen(fd, "w") as output:
                            json.dump(usage_record, output, sort_keys=True)
                            output.write("\n")
                            output.flush()
                            os.fsync(output.fileno())
                    except OSError:
                        # Metering failure is unknown usage, never invented spend
                        # and never a reason to replay a completed provider call.
                        pass
            if (artifact_contract is not None and result.returncode == 0
                    and result.cleanup_proven and not result.stdout_truncated and not result.stderr_truncated):
                try:
                    manifest = artifact_production.verify_completion(
                        artifact_contract, artifact_owner, display_stdout, child_env["LANE_REMOTE_HOST"])
                    if mode == "grok":
                        state['output_binding'] = grok_output_binding(
                            receipt, artifact_contract, manifest, result.stdout, display_stdout, child_env)
                    if mode in artifact_production.ORDINARY_MODES:
                        artifact_production.record_ordinary_completion(
                            receipt, artifact_contract, manifest, result.stdout, mode=mode)
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    artifact_failure = True

    except OwnedProcessStartError as exc:
        number = str(exc.error_number) if exc.error_number is not None else "unknown"
        return _fail("REMOTE_SUB_EXEC_NOT_STARTED errno=" + number, 78)
    except (LaneRuntimeError, OSError, ValueError) as exc:
        if state.get("started"):
            return _fail("REMOTE_CLEANUP_UNPROVEN " + type(exc).__name__, 76)
        return _fail("REMOTE_SUB_RUNTIME_ERROR " + type(exc).__name__, 78)

    if display_stdout:
        sys.stdout.write(display_stdout)
        sys.stdout.flush()
    # A successful worker's stderr is transport/diagnostic chatter, not its
    # return value. Keep it out of the parent result. On any worker/result/
    # cleanup failure, preserve the bounded stderr so diagnosis remains visible.
    result_failed = (
        int(result.returncode) != 0
        or not result.cleanup_proven
        or result.stdout_truncated
        or result.stderr_truncated
    )
    if result.stderr and result_failed:
        sys.stderr.write(result.stderr)
        sys.stderr.flush()
    if not result.cleanup_proven:
        return _fail("REMOTE_CLEANUP_UNPROVEN", 76)
    if result.stdout_truncated or result.stderr_truncated:
        marker = "NATIVE_CAPTURE_TRUNCATED" if mode in native_remote.MODES else "REMOTE_CAPTURE_TRUNCATED"
        return _fail(marker, 76)
    if artifact_failure:
        return _fail("ARTIFACT_DELIVERY_CONTRACT_FAILED", 65)
    return int(result.returncode)


def main(argv: list[str]) -> int:
    import native_remote  # legacy CLI only; never selected by the fixed finite entry
    state = {"started": False}
    if len(argv) == 6 and argv[2] in native_remote.MODES:
        state["timing"] = {"remote_exec_entered_at": time.time()}
    is_go = len(argv) == 6 and argv[2] == "go-codex"
    rc = 78
    try:
        rc = _execute(argv, state)
        return rc
    except BaseException as exc:
        if isinstance(exc, SystemExit) and isinstance(exc.code, int):
            rc = exc.code
        raise
    finally:
        if len(argv) == 6 and argv[2] in native_remote.MODES:
            native_remote.terminal(Path(__file__).resolve().parent, argv[1], argv[2], argv[5], os.environ, state["started"], rc, timing=state.get("timing"), output_binding=state.get("output_binding"))
        if is_go:
            from lane_runtime import cleanup_receipt_is_proven
            from go_remote_capsule import IDENT
            key = argv[1]
            if not IDENT.fullmatch(key):
                raise ValueError("invalid run key")
            names = {"root":"POOL_ORCHESTRATOR_ID", "lease_id":"POOL_LEASE_ID",
                     "account":"POOL_ACCOUNT", "run_id":"REMOTE_SUB_RUN_ID",
                     "host":"LANE_REMOTE_HOST"}
            scope = {k:os.environ.get(v, "") for k,v in names.items()}
            scope["model"] = argv[5]
            if scope["run_id"] != key or not all(IDENT.fullmatch(v) for v in scope.values()):
                raise ValueError("invalid worker scope")
            folder = Path(__file__).resolve().parent / "lanes"
            folder.mkdir(exist_ok=True)
            cleanup = None
            if state["started"]:
                try:
                    rows = (folder / (key+".process.jsonl")).read_text().splitlines()
                    record = json.loads(rows[-1])
                    if record.get("schema") == "mastermind.local_owned_process_receipt.v1" and record.get("label") == key:
                        cleanup = record.get("cleanup")
                except (OSError, ValueError, IndexError):
                    pass
            value = {"schema":"mastermind.go.worker-terminal.v1", **scope,
                     "started":state["started"], "returncode":rc, "cleanup":cleanup,
                     "cleanup_proven":(not state["started"] or cleanup_receipt_is_proven(cleanup or {}))}
            fd = os.open(folder / (key+".go-terminal.json"), os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(value, output); output.write("\n"); output.flush(); os.fsync(output.fileno())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
