"""Development-unarmed Slack-facing Executive Relay surfaces.

B1 deliberately supplies only the outbound state renderer/publisher protocol.
There is no production Slack client, credential, channel configuration, Socket
Mode listener, or inbound CEO-request processing in this package.
"""

from integrations.slack_executive.sol_state import (
    HistoryPage,
    PublicationReceipt,
    SlackStateClient,
    SolStateError,
    SolStatePublisher,
    StateMessage,
    build_sol_state_document,
    render_sol_state,
)

__all__ = [
    "HistoryPage",
    "PublicationReceipt",
    "SlackStateClient",
    "SolStateError",
    "SolStatePublisher",
    "StateMessage",
    "build_sol_state_document",
    "render_sol_state",
]
