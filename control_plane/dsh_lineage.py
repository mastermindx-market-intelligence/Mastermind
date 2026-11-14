"""Rev 5 DSH lane: two-level root lineage through GLM → DS Flash delegation.

The Revision 5 descendant-policy section requires the Executive root to be
carried through BOTH delegation levels — the GLM director child (level 1)
and its DS Flash child (level 2, the root's grandchild) — and the Wave 3
change order repeats: "Carry the root through both GLM and DS Flash
delegation levels."

This module is the pure derivation/validation surface over the existing
``ChildExecutionRequest.v1`` / ``ExecutionBinding.v1`` contracts
(``control_plane/child_execution_contracts.py``, WO-02/WO-13/WO-14): it
derives each next-level request from the parent binding with the root
CONSERVED and the immediate parent advanced exactly one level, joins the
company identity chain to dsh's native session chain (the acp session and
the native subagent's persisted session, which dsh itself tags with
``parentSession`` origin metadata), and refuses any chain that breaks root
conservation, skips a level, or double-counts a child key.

Law reminders encoded here: the binding is issued by the sole placement
authority; caller-supplied IDs are references, not credentials; the same
idempotency triple with a different digest is a conflict, never new work.
"""
from __future__ import annotations

import dataclasses
import hashlib
from typing import Sequence

from control_plane.child_execution_contracts import (
    ChildExecutionRequest,
    ExecutionBinding,
)

__all__ = [
    "DshNativeRef",
    "LineageLevel",
    "LineageConservationError",
    "run_ref",
    "child_request_from_binding",
    "assert_lineage_conservation",
    "native_chain_matches",
    "two_level_glm_dsflash_chain",
]


class LineageConservationError(ValueError):
    """The root/parent chain broke a lineage invariant."""


@dataclasses.dataclass(frozen=True)
class DshNativeRef:
    """The native identity join for one delegation level.

    Company identities (root run, parent run, logical child key) stay
    DISTINCT from native identities (T3 thread, dsh ACP session, dsh native
    child session); they are joined by this mapping, never merged (Rev 5
    §5 "distinct identities joined by a durable mapping").  References
    only — no credentials ever ride here.
    """

    t3_thread_id: str = ""
    acp_session_id: str = ""
    native_child_session: str = ""
    #: dsh tags native children with parentSession origin metadata; this is
    #: the observed native parent for the child (the previous level's
    #: native session or child session).
    native_parent_session: str = ""


def run_ref(binding: ExecutionBinding) -> str:
    """A stable logical run reference for one admitted binding.

    Prefers the broker's own attempt/job references; falls back to a
    deterministic digest of the binding's child identity triple so a chain
    can be validated even with a bare test binding.
    """
    for value in (binding.attempt_ref, binding.job_ref):
        if value:
            return value
    material = "|".join((
        binding.root_run_ref,
        binding.immediate_parent_run_ref,
        binding.logical_child_key,
        binding.request_digest,
    ))
    return f"mmx-run:{hashlib.sha256(material.encode()).hexdigest()[:24]}"


def child_request_from_binding(
    binding: ExecutionBinding,
    logical_child_key: str,
    *,
    task_kind: str = "",
    requested_complexity: str = "",
    operation_key: str = "",
    harness_preference: str = "",
) -> ChildExecutionRequest:
    """Derive the next-level request from an admitted parent binding.

    The root is CONSERVED from the parent binding (never re-stated by the
    caller — a caller cannot re-root a descendant), and the immediate
    parent becomes the parent binding's own run reference, advancing the
    chain exactly one level.  The child's requested class defaults to the
    parent's ADMITTED class (the binding's ``effective_complexity``); the
    shared admission re-classifies per child as always.
    """
    if not logical_child_key.strip():
        raise LineageConservationError("logical_child_key is required")
    if requested_complexity and not binding.effective_complexity:
        raise LineageConservationError(
            "parent binding carries no admitted class to inherit")
    return ChildExecutionRequest(
        root_ref=binding.root_run_ref,
        immediate_parent_run_ref=run_ref(binding),
        logical_child_key=logical_child_key,
        task_kind=task_kind,
        requested_complexity=requested_complexity or binding.effective_complexity,
        operation_key=operation_key,
        harness_preference=harness_preference,
    )


@dataclasses.dataclass(frozen=True)
class LineageLevel:
    """One admitted delegation level: its request, binding and native join."""

    depth: int  # 1 = child of the root run, 2 = grandchild, ...
    request: ChildExecutionRequest
    binding: ExecutionBinding
    native: DshNativeRef | None = None

    def __post_init__(self) -> None:
        if self.depth < 1:
            raise LineageConservationError("depth starts at 1 (first child)")
        if self.request.root_ref != self.binding.root_run_ref:
            raise LineageConservationError(
                f"level {self.depth}: request root {self.request.root_ref!r} "
                f"!= binding root {self.binding.root_run_ref!r}")
        if not self.binding.binds_request(self.request):
            raise LineageConservationError(
                f"level {self.depth}: binding does not fence this request "
                "(identity triple or digest mismatch)")


def assert_lineage_conservation(
    root_ref: str, levels: Sequence[LineageLevel],
) -> None:
    """Validate a full chain: one root everywhere, parents advance exactly
    one level per hop, logical child keys never repeat.

    This is the two-level (GLM director → DS Flash child) check of Rev 5:
    the grandchild (level 2) must carry the SAME root as the director
    (level 1) while its immediate parent is the director's run.
    """
    if not levels:
        raise LineageConservationError("no delegation levels to validate")
    seen_keys: set[tuple[str, str, str]] = set()
    previous: LineageLevel | None = None
    expected_depth = 1
    for level in levels:
        if level.request.root_ref != root_ref:
            raise LineageConservationError(
                f"level {level.depth}: root {level.request.root_ref!r} is not "
                f"the original root {root_ref!r} — root conservation broken")
        if level.depth != expected_depth:
            raise LineageConservationError(
                f"level order broken: depth {level.depth} where "
                f"{expected_depth} was expected")
        key = level.request.idempotency_key()
        if key in seen_keys:
            raise LineageConservationError(
                f"level {level.depth}: duplicate child identity {key!r} — "
                "a child key cannot repeat in one chain")
        seen_keys.add(key)
        if previous is not None:
            if level.request.immediate_parent_run_ref != run_ref(previous.binding):
                raise LineageConservationError(
                    f"level {level.depth}: immediate parent "
                    f"{level.request.immediate_parent_run_ref!r} is not the "
                    f"previous level's run {run_ref(previous.binding)!r} — "
                    "the chain skipped or forged a level")
            if (previous.request.is_idempotency_conflict(level.request)
                    if previous.request.idempotency_key() == key else False):
                raise LineageConservationError(
                    f"level {level.depth}: same child key with a different "
                    "digest is a conflict, never new work")
        previous = level
        expected_depth += 1


def native_chain_matches(
    levels: Sequence[LineageLevel], root_native: DshNativeRef | None = None,
) -> bool:
    """True when the dsh-native parent chain mirrors the company chain.

    The first level's native parent must be the root ACP session (from
    ``root_native``); each later level's ``native_parent_session`` must be
    the previous level's native child session (dsh records parentSession
    origin metadata on native children).
    """
    if not levels:
        return False
    expected_parent: str | None = None
    if root_native is not None and root_native.acp_session_id:
        expected_parent = root_native.acp_session_id
    for level in levels:
        native = level.native
        if native is None or not native.native_parent_session:
            return False
        if expected_parent is not None:
            if native.native_parent_session != expected_parent:
                return False
        elif native.native_parent_session != native.acp_session_id:
            # Without an explicit root ref, level 1's native parent must at
            # least be its own session's root chain entry.
            return False
        expected_parent = native.native_child_session or native.acp_session_id
    return True


def two_level_glm_dsflash_chain(
    root_ref: str,
    *,
    glm_run_binding: ExecutionBinding,
    dsflash_run_binding: ExecutionBinding,
    glm_request: ChildExecutionRequest,
    dsflash_request: ChildExecutionRequest,
    root_native: DshNativeRef,
    glm_native: DshNativeRef,
    dsflash_native: DshNativeRef,
) -> tuple[LineageLevel, LineageLevel]:
    """Build and validate the canonical two-level chain.

    Level 1 is the GLM director child of ``root_ref``; level 2 is the DS
    Flash child of the director — the root's grandchild, carrying the SAME
    root.  Returns the two validated levels or raises
    ``LineageConservationError``.
    """
    level1 = LineageLevel(depth=1, request=glm_request,
                          binding=glm_run_binding, native=glm_native)
    level2 = LineageLevel(depth=2, request=dsflash_request,
                          binding=dsflash_run_binding, native=dsflash_native)
    assert_lineage_conservation(root_ref, (level1, level2))
    if not native_chain_matches((level1, level2), root_native=root_native):
        raise LineageConservationError(
            "native dsh parentSession chain does not mirror the company "
            "parent chain")
    return level1, level2
