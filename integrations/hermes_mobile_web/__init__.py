"""Mobile UI package: deliberately registers no agent capabilities."""


def register(ctx):
    """Hermes mounts the separately allowlisted dashboard API; no tools or hooks."""
    return None
