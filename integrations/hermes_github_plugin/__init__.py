"""Native directory-plugin entry point; unbound discovery is inert."""
from pathlib import Path


def register(ctx):
    from integrations.hermes_github_plugin_host import register_from_host

    return register_from_host(ctx, package_path=Path(__file__).resolve().parent)
