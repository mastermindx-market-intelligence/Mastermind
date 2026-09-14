"""Pin ADAPTER_DESCRIPTORS implemented=True to the master-reviewed set.

Every implemented=True entry must be one of the adapters implemented on
origin/master today. A new True requires a real-turn receipt path documented
in this docstring (BUILT_NOT_PROVEN → PROVEN_LIVE). Updating only the
descriptor table, without expanding this pin and documenting that receipt
path here, must fail CI.

Master-implemented set (read from origin/master:control_plane/worker_adapter.py
ADAPTER_DESCRIPTORS on 2026-09-13):
    - codex-cli

Receipt path for a new True: attach the real-turn receipt ruling R5 requires
and move the corresponding catalog rows off SPEC_ONLY in the same change.
There is no such receipt for claude-compatible-subscription.
"""
from __future__ import annotations

from control_plane.worker_adapter import ADAPTER_DESCRIPTORS


# Named explicitly from origin/master's implemented=True rows. Do not add a
# name here unless this docstring records the receipt path that authorizes it.
MASTER_IMPLEMENTED_ADAPTER_IDS = frozenset({"codex-cli"})


def test_implemented_true_requires_master_set_or_documented_receipt_path() -> None:
    implemented = frozenset(
        adapter_id
        for adapter_id, descriptor in ADAPTER_DESCRIPTORS.items()
        if descriptor.implemented is True
    )
    assert implemented == MASTER_IMPLEMENTED_ADAPTER_IDS
