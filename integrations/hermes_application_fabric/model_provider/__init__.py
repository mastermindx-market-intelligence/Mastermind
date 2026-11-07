"""Hermes model-provider entrypoint; contains no role enrollment or keys."""
from integrations.hermes_application_fabric.native import register_native_provider

register_native_provider()
