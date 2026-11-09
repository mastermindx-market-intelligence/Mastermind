"""Stateless ChatGPT Dot -> canonical Mastermind session bridge.

This package is transport only. It owns no Job/Attempt/Worker/session lifecycle,
placement, retry, queue, or provider state.
"""

from .gateway import SessionBridgeGateway
from .schemas import BridgeError, ToolSpec, tool_names, validate_tool_arguments

__all__ = [
    "BridgeError",
    "SessionBridgeGateway",
    "ToolSpec",
    "tool_names",
    "validate_tool_arguments",
]
