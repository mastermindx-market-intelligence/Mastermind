"""Bounded Notion knowledge-surface integration.

This package is a presentation/bootstrap adapter only. It owns no Executive OS,
Agent OS, priority, identity, retry, publication, or other canonical state.
"""

from .bootstrap import (
    NOTION_VERSION,
    BootstrapError,
    NotionClient,
    apply_workspace,
    build_plan,
    load_manifest,
    validate_manifest,
)

__all__ = [
    "NOTION_VERSION",
    "BootstrapError",
    "NotionClient",
    "apply_workspace",
    "build_plan",
    "load_manifest",
    "validate_manifest",
]
