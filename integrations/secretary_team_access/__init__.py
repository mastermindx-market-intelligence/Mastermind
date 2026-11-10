"""Source-only Secretary shared-team consumer. Host ownership stays incumbent."""

from integrations.secretary_team_access.client import SecretaryAccessClient
from integrations.secretary_team_access.mission import summarize_mission
from integrations.secretary_team_access.projection import (
    summarize_native_catalog, summarize_native_status,
)

__all__ = (
    "SecretaryAccessClient", "summarize_mission", "summarize_native_catalog",
    "summarize_native_status",
)
