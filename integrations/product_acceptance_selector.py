"""Join one retained original Wake anchor to its canonical acceptance issuance.

This internal reader neither discovers a latest request nor authenticates an
App. The receiving owner must supply its exact original obligation and current
authenticated work/root scope inside the existing permission, source and owner
observation brackets. Browser publication remains that owner's responsibility.
"""
from __future__ import annotations

import inspect

from common.product_acceptance_read_contract import selection
from control_plane.agentos_product_acceptance_basis import AgentOsProductAcceptanceBasisReader
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import Runtime, _dialogue_source_from_root_creation
from control_plane.principal_dialogue_obligation import read_original_principal_dialogue_obligation
from integrations.product_acceptance_request_owner import ProductAcceptanceRequestOwner
from integrations.product_acceptance_ruling_owner import ProductAcceptanceRulingReceiptReader


class ProductAcceptanceSelectionUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("PRODUCT_ACCEPTANCE_SELECTION_UNAVAILABLE")


def read_original_acceptance_selection(
    runtime, basis_reader, *, original_obligation_id, expected_work_ref, expected_root_job_id,
    receiving_read_guard,
):
    """Return only the existing three-key selector, never acceptance or authority.

    Resolved obligations are intentionally supported for original-result reads.
    Neither the issuance owner nor a principal COMMIT owner is invoked. Current
    product/source/parent verification stays with ``read_acceptance``; obtaining
    a selector does not mean the request has been answered or consumed.
    """
    try:
        def guard():
            if not callable(receiving_read_guard):
                raise ProductAcceptanceSelectionUnavailable()
            value = receiving_read_guard()
            if value is not None:
                if inspect.iscoroutine(value):
                    value.close()
                raise ProductAcceptanceSelectionUnavailable()

        guard()
        if (type(runtime) is not Runtime or runtime.store.read_binding is None
                or type(basis_reader) is not AgentOsProductAcceptanceBasisReader):
            raise ProductAcceptanceSelectionUnavailable()
        args = dict(obligation_id=original_obligation_id,
            expected_work_ref=expected_work_ref, expected_root_job_id=expected_root_job_id)
        before = read_original_principal_dialogue_obligation(runtime, **args)
        physical = before.physical_source
        candidate = physical.candidate
        owner = ProductAcceptanceRulingReceiptReader(ProductAcceptanceRequestOwner(runtime, basis_reader))
        request = owner._request(physical.predecessor_message_key)
        context, message, subject = request["context"], request["message"], request["subject"]
        issuer = {name: subject["issuer_" + name] for name in ("job_id", "attempt_id", "worker_id")}
        child = runtime.jobs.get_job(issuer["job_id"])
        attempt = runtime.attempts.get_attempt(issuer["attempt_id"])
        if (child is None or child.root_job_id != expected_root_job_id
                or child.current_attempt_id != issuer["attempt_id"] or attempt is None
                or attempt.job_id != issuer["job_id"] or attempt.worker_id != issuer["worker_id"]):
            raise ProductAcceptanceSelectionUnavailable()
        identity = derive_delegation_identity(child)
        with runtime.store.read() as connection:
            source = _dialogue_source_from_root_creation(connection, root_job_id=expected_root_job_id)
        if (source is None or source.work_ref != expected_work_ref
                or context["commission_ref"] != source.commission_ref.to_dict()
                or context["watch_mode"] != source.watch_mode
                or context["work_ref"] != expected_work_ref or message["work_ref"] != expected_work_ref
                or subject["root_job_id"] != expected_root_job_id
                or message["fingerprint"] != physical.predecessor_message_fingerprint
                or request["thread_ts"] != physical.thread_ts
                or context["operation_key"] != physical.operation_key
                or context["operation_key"] != identity.operation_key
                or context["session_ref"] != identity.session_ref
                or message["commission_ref"] != context["commission_ref"]
                or message["session_ref"] != context["session_ref"]
                or context["actor_ref"] != {"kind": "worker_attempt", **issuer}
                or message["actor_ref"] != context["actor_ref"]
                or context["applies_to"] != {"kind": "executive_attempt", **issuer}
                or message["applies_to"] != context["applies_to"]
                or candidate.mode != "ACTIVE_CURRENT_WORKER"
                or any(getattr(candidate, name) != value for name, value in issuer.items())):
            raise ProductAcceptanceSelectionUnavailable()
        selected = selection({"work_ref": context["work_ref"], "root_job_id": subject["root_job_id"],
                              "request_message_key": message["message_key"]})
        if (read_original_principal_dialogue_obligation(runtime, **args) != before
                or owner._request(message["message_key"]) != request):
            raise ProductAcceptanceSelectionUnavailable()
        runtime.store.read_binding.validate_before_core_return()
        guard()
        return selected
    except Exception:
        # A foreign or malformed key must not become a source existence oracle.
        raise ProductAcceptanceSelectionUnavailable() from None


async def read_original_acceptance_observation(provider, frame, *, owner_target):
    """Compose the join with the actual existing selected Workspace read owner.

    ``frame`` is its already authenticated two-key mission_v3 frame, while the
    frozen ``owner_target`` is supplied by trusted host composition, never HTTP
    or model arguments. This function registers no route and changes no frame
    decoder. Production must explicitly publish the optional result through its
    selected App port; the current browser transport does not acquire it yet.
    """
    import asyncio
    import copy
    from common.executive_workspace_contract import permission_stamp, validate_v2_frame
    from common import product_acceptance_read_contract as contract
    from control_plane.principal_ruling_target import PrincipalRulingTarget
    from control_plane.workspace_read_service import (
        WorkspaceReadService, _join, _observation, _qualified, await_owned,
    )

    try:
        frame = copy.deepcopy(frame)
        validate_v2_frame(frame)
        if (type(provider) is not WorkspaceReadService or frame['operation'] != 'mission_v3'
                or type(owner_target) is not PrincipalRulingTarget
                or owner_target.work_ref != frame['selection']['work_ref']
                or not callable(provider._bounded_runtime)):
            raise ProductAcceptanceSelectionUnavailable()
        principal, scoped = frame['principal'], frame['selection']
        if provider.authorize(principal) is not True:
            raise ProductAcceptanceSelectionUnavailable()
        permission = permission_stamp(provider.authorize, principal)
        owner_fields = ('cache', 'runtime', 'authorize', '_bounded_runtime', '_product_acceptance_basis_reader',
                        '_product_acceptance_read', '_product_acceptance_observe')
        owner_values = tuple(getattr(provider, field) for field in owner_fields)

        def guard():
            if (any(getattr(provider, field) is not value for field, value in zip(owner_fields, owner_values))
                    or provider.authorize(principal) is not True
                    or permission_stamp(provider.authorize, principal) != permission):
                raise ProductAcceptanceSelectionUnavailable()

        def read():
            guard()
            before = provider.cache.snapshot()
            _join(before.document, scoped)
            if not _qualified(before, scoped):
                raise ProductAcceptanceSelectionUnavailable()
            runtime = provider._bounded_runtime(provider.runtime)
            args = dict(original_obligation_id=owner_target.obligation_id,
                expected_work_ref=scoped['work_ref'], expected_root_job_id=scoped['root_job_id'],
                receiving_read_guard=guard)
            selected = read_original_acceptance_selection(runtime,
                provider._product_acceptance_basis_reader, **args)
            response = provider._read_mission_v4({**frame, 'schema': contract.FRAME_SCHEMA,
                'operation': contract.OPERATION, 'selection': selected})
            if (response.get('ok') is not True or selected != read_original_acceptance_selection(
                    runtime, provider._product_acceptance_basis_reader, **args)):
                raise ProductAcceptanceSelectionUnavailable()
            after = provider.cache.snapshot()
            _join(after.document, scoped)
            body = response['result']
            observed = body['mission']['source']['owner_observation']
            if (not _qualified(after, scoped) or observed['state'] != 'SAME'
                    or _observation(before, after, scoped, observed['runtime'])['state'] != 'SAME'):
                raise ProductAcceptanceSelectionUnavailable()
            runtime.store.read_binding.validate_before_core_return()
            guard()
            return body, after, runtime

        result, observed_source, runtime = await await_owned(asyncio.create_task(asyncio.to_thread(read)))
        guard()
        current = provider.cache.snapshot()
        _join(current.document, scoped)
        generation = result['mission']['source']['owner_observation']['runtime']
        if (not _qualified(current, scoped)
                or _observation(observed_source, current, scoped, generation)['state'] != 'SAME'):
            raise ProductAcceptanceSelectionUnavailable()
        runtime.store.read_binding.validate_before_core_return()
        return result
    except Exception:
        raise ProductAcceptanceSelectionUnavailable() from None
