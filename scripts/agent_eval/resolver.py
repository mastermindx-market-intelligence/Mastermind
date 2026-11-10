"""Read-only, direct-ID artifact resolver protocol for EVAL-R0.

Plan §5.6 (binding resolver-boundary ruling, adopted 2026-09-01): this
Protocol exposes ONLY the read-only direct-ID lookup. There is no write,
network, environment, provider, search, or fallback method — never here,
and never on any implementation.

The production implementation is :class:`scripts.agent_eval.store.ArtifactStore`.
The test-only ``MemoryArtifactResolver`` lives under
``tests/agent_eval_factories.py``, NOT in this module, per the same ruling.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class ArtifactResolver(Protocol):
    """Direct-ID lookup only. Each method resolves exactly one canonical
    artifact ID to its stored document, or ``None`` if it does not exist.
    No method here may add, update, delete, search, or fall back to a
    fuzzy/repository-wide lookup."""

    def resolve_scenario(self, scenario_id: str, scenario_version: int) -> Optional[dict]:
        ...

    def resolve_configuration(self, configuration_id: str) -> Optional[dict]:
        ...

    def resolve_experiment(self, experiment_id: str) -> Optional[dict]:
        ...

    def resolve_run(self, run_id: str) -> Optional[dict]:
        ...

    def resolve_scorer_pass(self, scorer_pass_id: str) -> Optional[dict]:
        ...

    def resolve_evidence_ref(self, evidence_ref_id: str) -> Optional[dict]:
        ...
