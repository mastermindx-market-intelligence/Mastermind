"""Qualify an existing committed ruling through its original retained identity.

No principal send gateway is constructed. The current host authority checks the
original principal generation; the existing COMMIT/Relay owners prove the reply.
This is recovery of a missing qualified receipt, never a replacement ruling.
"""
from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_host import CooHostProvider
from integrations.mastermind_company_mcp.adapter import CompanyDialogueGateway, DialogueBinding
from integrations.mastermind_company_mcp.principal_adapter import (
    PrincipalCompanyDialogueGateway, _PRINCIPAL_MESSAGES,
)
from integrations.mastermind_company_principal_runtime_fence import (
    PrincipalDialogueRuntimeCommitOwner, _require_binding_intent_match,
)
from integrations.product_acceptance_request_owner import (
    ProductAcceptanceRequestOwner, ProductAcceptanceRequestUnavailable,
)
from integrations.product_acceptance_ruling_owner import (
    ProductAcceptanceRulingOwner, ProductAcceptanceRulingReceiptReader,
)
from integrations.slack_agent_dialogue.service import call_service


class ProductAcceptanceQualificationRecovery:
    def __init__(self, *, requester: ProductAcceptanceRequestOwner,
                 authority: CooHostProvider, socket_path: Path):
        if type(requester) is not ProductAcceptanceRequestOwner or type(authority) is not CooHostProvider:
            raise TypeError('qualification recovery requires the exact existing owners')
        self.requester, self.authority = requester, authority
        self.socket_path = Path(socket_path)
        if not self.socket_path.is_absolute():
            raise ValueError('qualification recovery requires the installed Relay path')

    async def recover(self, *, binding: DialogueBinding, message_key: str,
                      receiving_request_guard, service_call=call_service):
        def guard():
            # The request host's synchronous guard rechecks kernel peer, source
            # and its distinct current grant; this is not a model callback.
            if not callable(receiving_request_guard):
                raise ProductAcceptanceRequestUnavailable('PRODUCT_PARENT_BINDING_CHANGED')
            result = receiving_request_guard()
            if result is not None:
                if inspect.iscoroutine(result):
                    result.close()
                raise ProductAcceptanceRequestUnavailable('PRODUCT_PARENT_BINDING_CHANGED')

        guard()
        raw, *_ = ProductAcceptanceRulingReceiptReader(self.requester)._current_request(
            binding=binding, message_key=message_key)
        # The existing key owner excludes body and principal generation. Only
        # the original worker context and exact predecessor identify this slot.
        reply_binding = dataclasses.replace(binding, reply_to_message_key=message_key)
        reply_key = PrincipalCompanyDialogueGateway._edge_message_key(
            reply_binding, CompanyDialogueGateway._binding_context(binding))
        commit_owner = None
        outer = self

        class OriginalBinding:
            def resolve(self):
                guard()
                stored = commit_owner._event_for_message_key(reply_key)
                if stored is None:
                    raise ProductAcceptanceRequestUnavailable('PRODUCT_RULING_COMMIT_UNCONFIRMED')
                event, intent = stored
                snapshot = event.payload['binding']
                _require_binding_intent_match(snapshot, intent)
                context = snapshot['context']
                actor = context['actor_ref']
                if (intent.message_type != 'RULING' or intent.reply_to_message_key != message_key
                        or actor.get('root_job_id') != raw['subject']['root_job_id']
                        or actor.get('kind') != 'executive_principal' or actor.get('seat') != 'coo'):
                    raise ProductAcceptanceRequestUnavailable('PRODUCT_PRINCIPAL_GENERATION_CHANGED')
                outer.authority.guard_dialogue(
                    context=PrincipalAdmissionContext(context['work_ref'], actor['principal_binding_digest'],
                        actor['mission_authority_ref'], actor['authority_generation_digest']),
                    root_job_id=actor['root_job_id'],
                    capability_profile_digest=actor['capability_profile_digest'])
                guard()
                return DialogueBinding(**context, thread_ts=snapshot['thread_ts'],
                    reply_to_message_key=snapshot['reply_to_message_key'],
                    # Preserve the incumbent principal context contract. These
                    # labels grant nothing: no gateway is built, writes are
                    # refused by read_only, and the COMMIT guard always refuses.
                    allowed_message_types=_PRINCIPAL_MESSAGES)

        async def read_only(path, request):
            guard()
            if request['operation'] not in {'read_thread', 'wait_for_reply'}:
                raise ProductAcceptanceRequestUnavailable('PRODUCT_RULING_UNAVAILABLE')
            result = await service_call(path, request)
            guard()
            return result

        def no_commit(_intent):
            raise ProductAcceptanceRequestUnavailable('PRODUCT_RULING_UNAVAILABLE')

        commit_owner = PrincipalDialogueRuntimeCommitOwner(self.requester.runtime,
            OriginalBinding(), socket_path=self.socket_path, service_call=read_only,
            principal_authority_guard=lambda **_: no_commit(None))
        # Qualify checks the current principal binding again before its existing
        # Runtime event append. The retained COMMIT is only observed, never used
        # to authorize another before_commit or a new send.
        return await ProductAcceptanceRulingOwner(self.requester, commit_owner).qualify(
            binding=binding, message_key=message_key)
