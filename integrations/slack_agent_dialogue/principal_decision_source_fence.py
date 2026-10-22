"""Fresh decision-source acquisition at the existing principal COMMIT seam.

Host composition supplies already authenticated scope and one original physical
source. These values create no authority. Runtime still owns the final current
attempt, enrolled authority and single-COMMIT transaction. Cross-service reads
are observations, not an atomic Slack/Runtime transaction or a reusable lease.
"""
from dataclasses import dataclass

from control_plane.dialogue_source_resolution import PhysicalDialogueSourceIdentity
from integrations.mastermind_company_principal_runtime_fence import (
    PrincipalDialogueRuntimeCommitOwner, PrincipalRuntimeFenceError, _validate_intent,
)
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import CooPrincipalDialogueCaller
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader
from integrations.slack_agent_dialogue.principal_current_reader import read_current_principal_source
from integrations.slack_agent_dialogue.principal_pending_decision import require_unanswered_principal_decision


@dataclass(frozen=True)
class PrincipalDecisionSource:
    caller: CooPrincipalDialogueCaller
    context: DialogueContextV2
    physical_source: PhysicalDialogueSourceIdentity
    observation_client: ExecutiveDialogueObservationClient | HostLocalDialogueObservationReader

    def __post_init__(self):
        if (type(self.caller) is not CooPrincipalDialogueCaller
                or type(self.context) is not DialogueContextV2
                or type(self.physical_source) is not PhysicalDialogueSourceIdentity
                or type(self.observation_client) not in (ExecutiveDialogueObservationClient, HostLocalDialogueObservationReader)):
            raise TypeError("exact principal source owners required")


class PrincipalDecisionSourceFence:
    def __init__(self, source: PrincipalDecisionSource,
                 owner: PrincipalDialogueRuntimeCommitOwner):
        if (type(source) is not PrincipalDecisionSource
                or type(owner) is not PrincipalDialogueRuntimeCommitOwner):
            raise TypeError("exact principal decision source and commit owner required")
        if (type(source.observation_client) is HostLocalDialogueObservationReader
                and source.observation_client.runtime is not owner.runtime):
            raise TypeError("host-local observation must use the COMMIT owner's Runtime")
        self.source, self.owner = source, owner

    async def before_commit(self, intent):
        try:
            intent = _validate_intent(intent)
            # This composition qualifies the decision-request family only.
            # No other command may silently skip fresh source acquisition.
            if intent.message_type != "RULING":
                raise PrincipalRuntimeFenceError("decision source requires a ruling")
            source = self.source
            current = await read_current_principal_source(
                caller=source.caller, context=source.context,
                physical_source=source.physical_source,
                socket_path=self.owner.socket_path,
                observation_client=source.observation_client,
                service_call=self.owner.service_call,
            )
            require_unanswered_principal_decision(current)
            # No await after the final source validation. The existing owner
            # checks the complete fresh binding, then authority/current attempt
            # and request uniqueness inside its original write transaction.
            return self.owner.before_commit(intent, expected_binding=current.binding)
        except Exception:
            raise PrincipalRuntimeFenceError("principal decision source unavailable") from None
