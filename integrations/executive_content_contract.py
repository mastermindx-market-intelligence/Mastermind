"""Compatibility import for the canonical shared content contract.

Definitions live in common so control owners do not depend on integrations.
Re-export the same objects, preserving the installed App's existing imports.
"""
from common.executive_content_contract import *  # noqa: F401,F403
