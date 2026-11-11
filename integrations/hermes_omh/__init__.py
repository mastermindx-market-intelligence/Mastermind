"""Selective source-only Oh My Hermes integration; no plugin registration."""
from .adapter import ProposalError, prepare_execution_plan

__all__ = ["ProposalError", "prepare_execution_plan"]
