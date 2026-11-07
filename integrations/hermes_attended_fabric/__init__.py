"""Hermes-native attended Fabric plugin; import alone has no effects."""


def register(ctx):
    """Compose only through the native PluginManager and enrolled MCP owner."""
    from .native_session import register as register_native_session
    register_native_session(ctx)
