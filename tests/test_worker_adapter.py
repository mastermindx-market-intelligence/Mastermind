"""Pin ADAPTER_DESCRIPTORS implemented=True to the reviewed set.

Every implemented=True entry must be one of the adapters pinned in this file.
A new True requires expanding this pin and documenting, in this docstring,
the existing real-turn receipt path (BUILT_NOT_PROVEN -> PROVEN_LIVE).
The explicitly recorded source-only additions below do not
create a general substitute for other adapters' required receipt paths. Updating
only the descriptor table, without expanding this pin and documenting that
status here, must fail CI.

Master-implemented set (read from origin/master:control_plane/worker_adapter.py
ADAPTER_DESCRIPTORS on 2026-09-13):
    - codex-cli

PR1794 source-implementation addition (BUILT_NOT_PROVEN; this records a source
implementation only and is NOT a master merge, NOT runtime activation, and NOT
an R1/live receipt):
    - canonical-paid-fabric: exact class CanonicalPaidFabricWorkerAdapter
      exists in the source tree for sealed-input READ/RESEARCH subjects; no
      native/tools/write or absent physical qualification admission is
      implied.

PR2177 source-implementation addition (BUILT_NOT_PROVEN):
    - dsh-native-acp: existing NativeOperatorAdapter, exclusively the original
      claimed OperatorHarness v2 interface; cannot construct/bind as a sealed
      WorkerExecutionAdapter. Source/runtime tests are recorded in
      integrations/deepseek_harness/runtime_compat/evidence/native-runtime-port-20261107.json.
      Installed Worker/quota/host/account/source/confinement and actual signed-in
      native journey qualification remain separate; no new registration is made.

Receipt path for a PROVEN_LIVE entry: attach the real-turn receipt ruling R5
requires and move the corresponding catalog rows off SPEC_ONLY in the same
change. There is no such receipt for claude-compatible-subscription, and no
R1/live receipt exists for canonical-paid-fabric either.
"""
from __future__ import annotations

from control_plane.worker_adapter import ADAPTER_DESCRIPTORS


# "codex-cli" is named explicitly from origin/master's implemented=True rows.
# "canonical-paid-fabric" is the PR1794 source-implementation entry documented
# above (BUILT_NOT_PROVEN). Do not add a name here unless this docstring
# records the receipt path or source-implementation status that authorizes it.
MASTER_IMPLEMENTED_ADAPTER_IDS = frozenset({"codex-cli", "canonical-paid-fabric", "dsh-native-acp"})


def test_implemented_true_requires_master_set_or_documented_receipt_path() -> None:
    implemented = frozenset(
        adapter_id
        for adapter_id, descriptor in ADAPTER_DESCRIPTORS.items()
        if descriptor.implemented is True
    )
    assert implemented == MASTER_IMPLEMENTED_ADAPTER_IDS



def test_native_operator_descriptor_cannot_enter_sealed_worker_construction():
    import pytest
    from control_plane.worker_adapter import (
        ADAPTER_INTERFACE_VERSION, AdapterBindingError, adapter_descriptor,
        adapter_implementation, construct_reviewed_adapter, bind_reviewed_adapter,
    )
    from control_plane.operator_harness_contract import OPERATOR_HARNESS_INTERFACE_VERSION
    native = adapter_descriptor("dsh-native-acp")
    assert native.interface_version == OPERATOR_HARNESS_INTERFACE_VERSION
    assert native.interface_version != ADAPTER_INTERFACE_VERSION
    assert native.implementation == "integrations.deepseek_harness.operator_adapter.NativeOperatorAdapter"
    assert adapter_descriptor("acp").implemented is False
    for action in (
        lambda: adapter_implementation("dsh-native-acp"),
        lambda: construct_reviewed_adapter("dsh-native-acp"),
        lambda: bind_reviewed_adapter(object(), "dsh-native-acp"),
    ):
        with pytest.raises(AdapterBindingError, match="original claimed factory"):
            action()
