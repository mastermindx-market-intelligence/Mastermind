"""Register Capacity Fabric serving gateways as native T3 Code providers.

T3 Code keeps model providers in ``~/.t3/userdata/settings.json`` under
``providerInstances``. This package discovers the fabric's local serving
endpoints, reads each gateway's authenticated catalogue, and registers the
endpoint as a ``claudeAgent`` provider whose ``ANTHROPIC_BASE_URL`` points at
the fabric gateway. The fabric keeps every routing, admission, pool rotation
and load-balancing decision; T3 only selects a model slug.

This module owns no routing, retry, credential store or provider client. It
never invents a catalogue entry: only ids returned by the gateway's
authenticated ``GET /v1/models`` are registered.
"""
from integrations.t3_capacity_fabric.endpoints import (
    FabricEndpoint,
    default_endpoints,
    fetch_catalog,
    gateway_health,
    load_proxy_token,
)
from integrations.t3_capacity_fabric.registration import (
    apply_registration,
    build_provider_instance,
    plan_registration,
    verify_registration,
)

__all__ = [
    "FabricEndpoint",
    "apply_registration",
    "build_provider_instance",
    "default_endpoints",
    "fetch_catalog",
    "gateway_health",
    "load_proxy_token",
    "plan_registration",
    "verify_registration",
]
