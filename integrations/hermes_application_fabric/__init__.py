"""Hermes primary inference adapter; no credential, routing or account owner."""

from integrations.hermes_application_fabric.client import ApplicationBinding, HermesApplicationClient, NativeCall, call_scope
from integrations.hermes_application_fabric.errors import HermesFabricError

__all__ = ["ApplicationBinding", "HermesApplicationClient", "NativeCall",
           "HermesFabricError", "call_scope"]


def register(ctx):
    """Native directory aliases delegate to the single installed implementation."""
    from integrations.hermes_application_fabric.gateway_plugin import register as install
    return install(ctx)
