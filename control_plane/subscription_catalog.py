"""Read-only catalog helpers shared by provider realm and canary admission."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from control_plane.subscription_harness_bindings import HarnessBindingError


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def compose_catalog_digest(
    *,
    bindings_document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> str:
    from control_plane.subscription_harness_bindings import (
        load_bindings,
        validate_bindings,
    )
    from control_plane.subscription_provider_profiles import (
        load_profiles,
        validate_profiles,
    )

    profiles = (
        validate_profiles(profiles_document)
        if profiles_document is not None
        else load_profiles()
    )
    bindings = (
        validate_bindings(bindings_document, profiles_document=profiles)
        if bindings_document is not None
        else load_bindings(profiles_document=profiles)
    )
    return hashlib.sha256(
        _canonical_json({"bindings": bindings, "profiles": profiles}).encode("utf-8")
    ).hexdigest()


def get_binding(
    binding_id: str,
    *,
    document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> Any:
    from control_plane.subscription_harness_bindings import (
        load_bindings,
        validate_bindings,
    )
    from control_plane.subscription_provider_profiles import (
        load_profiles,
        validate_profiles,
    )

    if not isinstance(binding_id, str) or not binding_id:
        raise HarnessBindingError("binding_id is required")
    profiles = (
        validate_profiles(profiles_document)
        if profiles_document is not None
        else load_profiles()
    )
    bindings = (
        validate_bindings(document, profiles_document=profiles)
        if document is not None
        else load_bindings(profiles_document=profiles)
    )
    binding = bindings.get("bindings", {}).get(binding_id)
    if binding is None:
        raise HarnessBindingError(f"unknown harness binding {binding_id!r}")
    if binding.get("binding_id", binding_id) != binding_id:
        raise HarnessBindingError(f"binding {binding_id!r} does not match its catalog key")
    from control_plane.subscription_harness_bindings import get_binding as binding_lookup

    return binding_lookup(
        binding_id,
        document={**document, "bindings": {binding_id: binding}}
        if document is not None
        else None,
        profiles_document=profiles,
    )


__all__ = [
    "HarnessBindingError",
    "compose_catalog_digest",
    "get_binding",
]
