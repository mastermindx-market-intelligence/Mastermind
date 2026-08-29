"""Read-only ABA-safe projection of the accepted current OHF writer."""
from __future__ import annotations

import hashlib
import sqlite3

from control_plane.executive_runtime import (
    ActiveOperatorBindingFacts,
    Runtime,
    StateConflict,
)
from control_plane.session_targets import RuntimeBinding, SessionTarget


_PROVIDER_TO_REASONING_SURFACE = {"openai-codex": "codex"}


def active_operator_binding_facts(
    runtime: Runtime,
    attempt_id: str,
    target: SessionTarget,
    *,
    connection: sqlite3.Connection | None = None,
) -> ActiveOperatorBindingFacts:
    """Return only the accepted source facts for a logical Wake target.

    ``connection=None`` owns one ``RuntimeStore.read()`` snapshot through the
    Runtime seam.  A caller that already owns a read or transaction connection
    passes it through unchanged, preventing a torn second read.
    """

    facts = runtime.current_harness_binding_source(
        attempt_id, connection=connection
    )
    surface = _PROVIDER_TO_REASONING_SURFACE.get(facts.provider)
    if (
        facts.owner_seat != target.target_seat
        or surface is None
        or target.reasoning_surface != surface
    ):
        raise StateConflict("runtime binding target/provider surface is not accepted")
    return facts


def project_runtime_binding(
    runtime: Runtime, attempt_id: str, target: SessionTarget
) -> RuntimeBinding:
    """Project one runtime-only binding; this function persists nothing."""

    facts = active_operator_binding_facts(runtime, attempt_id, target)
    binding_id = "bind-" + hashlib.sha256(
        f"{facts.attempt_id}:{facts.session_epoch_id}".encode("utf-8")
    ).hexdigest()[:40]
    return RuntimeBinding(
        session_alias=target.session_alias,
        binding_id=binding_id,
        binding_generation=facts.generation_number,
        native_handle=facts.provider_session_id,
        account_label=facts.account_label,
        reasoning_surface=target.reasoning_surface,
    )


__all__ = ["active_operator_binding_facts", "project_runtime_binding"]
