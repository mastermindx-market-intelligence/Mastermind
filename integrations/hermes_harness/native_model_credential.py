"""Resolve one primary BYOK model key through the existing WP2 credential owner.

Only the primary role's reviewed key name is materialized. This is *not*
an authorization for an Executive effect, global key export, model call,
provider fallback, or host computer tool.
"""
from __future__ import annotations

from collections.abc import Mapping

from integrations.hermes_models.contract import PROFILE_PRIMARY, native_provider
from integrations.hermes_models.credentials import CredentialUnavailable, load_credential
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import RuntimeProfile


def primary_model_env(
    profile: RuntimeProfile,
    secret_values: Mapping[str, str],
    consumer=None,
) -> dict[str, str]:
    """Resolve one primary BYOK model key through the existing WP2 credential owner.

    When a qualified optional consumer is installed, the Executive connection
    must keep its own OAuth client reference: it never borrows the model's
    provider, its credential name or its client.
    """
    if not isinstance(profile, RuntimeProfile) or profile.role not in PROFILE_PRIMARY:
        raise RuntimeRefusal("NATIVE_MODEL_ROLE_UNQUALIFIED")
    if profile.extension_allowlist:
        raise RuntimeRefusal("NATIVE_EXTENSION_NOT_INSTALLED")
    try:
        spec = native_provider(profile.role, profile.native_provider_id)
    except (ValueError, KeyError):
        raise RuntimeRefusal("NATIVE_MODEL_SELECTION_UNQUALIFIED") from None
    if spec.provider_id == "cursor-pool" or not spec.enabled_in_profile:
        raise RuntimeRefusal("NATIVE_MODEL_PROVIDER_UNQUALIFIED")
    if consumer is not None:
        _assert_consumer_credential_separate(spec, consumer)
    try:
        value = load_credential(spec, secret_values)
    except CredentialUnavailable:
        raise RuntimeRefusal("NATIVE_MODEL_CREDENTIAL_UNAVAILABLE") from None
    return {spec.credential_env: value}


def _assert_consumer_credential_separate(spec, consumer) -> None:
    """The consumer must never borrow the model's provider identity.

    The Executive connection is authenticated by its own OAuth client
    reference, held by the incumbent OAuth owner and its token storage. It is
    never the model's provider, its credential name, or its client.
    """
    from integrations.hermes_harness.native_executive_consumer import (
        publication_from_document,
    )

    publication = publication_from_document(consumer)
    client_id = publication.mcp.client_id
    forbidden = {
        spec.credential_env, spec.provider_id, spec.hermes_name, spec.display_name,
        spec.served_model,
    }
    if client_id in forbidden:
        raise RuntimeRefusal("NATIVE_CONSUMER_MODEL_CREDENTIAL_ALIAS_REFUSED")
