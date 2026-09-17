"""Read-only conversation workspace projections over existing Mastermind owners."""

from integrations.mastermind_workspace_content.live_window import (
    ContentDecision,
    LiveWindowError,
    LiveWindowReader,
    validate_visible_window,
)
from integrations.mastermind_workspace_content.resource import WorkspaceContentResource
from integrations.mastermind_workspace_content.projection_source import ManagedTurnWindowSource
from integrations.mastermind_workspace_content.app import build_workspace_content_app
from integrations.mastermind_workspace_content.business import (
    CONTENT_SCOPE,
    build_business_workspace_content_resource,
)

__all__ = [
    "CONTENT_SCOPE",
    "ContentDecision",
    "LiveWindowError",
    "LiveWindowReader",
    "ManagedTurnWindowSource",
    "WorkspaceContentResource",
    "build_business_workspace_content_resource",
    "build_workspace_content_app",
    "validate_visible_window",
]
