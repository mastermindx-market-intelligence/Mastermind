"""Read the existing ModelRouter catalog without granting admission.

PR #1824's commercial aliases are expected to be absent until that source
merges. A present alias whose served model disagrees with the contract is
drift. A routing decision is suitability, never Executive or Capacity authority.
"""

from __future__ import annotations

from typing import Any

from integrations.hermes_models.contract import MODELARK_CONTRACT, PROVIDERS


class ContractDrift(RuntimeError):
    """A loaded router alias disagrees with the consumed ModelArk contract."""


def bind_model_router(router: Any) -> dict[str, Any]:
    """Describe catalog overlap. Does not mutate the router or arm providers."""

    aliases = getattr(router, "model_aliases", None)
    providers = getattr(router, "providers", None)
    if not isinstance(aliases, dict) or not isinstance(providers, dict):
        raise ContractDrift("model router catalog is unreadable")

    rows: list[dict[str, Any]] = []
    for alias, served in MODELARK_CONTRACT["aliases"].items():
        profile = aliases.get(alias)
        if profile is None:
            rows.append(
                {
                    "alias": alias,
                    "status": "absent_until_pr_1824_merges",
                    "served_model": served,
                    "worker_eligible": False,
                }
            )
            continue
        observed = str(getattr(profile, "model", "") or "")
        if observed != served:
            raise ContractDrift("model router alias disagrees with the ModelArk contract")
        provider_alias = str(getattr(profile, "provider_alias", "") or "")
        if provider_alias != MODELARK_CONTRACT["provider_alias"]:
            raise ContractDrift("model router alias disagrees with the ModelArk contract")
        provider = providers.get(provider_alias)
        rows.append(
            {
                "alias": alias,
                "status": "present",
                "served_model": observed,
                "worker_eligible": bool(getattr(profile, "worker_eligible", False)),
                "provider_enabled": bool(getattr(provider, "enabled", False)),
            }
        )

    minimax = aliases.get("minimax.attended")
    minimax_model = str(getattr(minimax, "model", "") or "") if minimax is not None else None
    if minimax is not None and minimax_model != PROVIDERS["minimax.attended"].served_model:
        raise ContractDrift("minimax.attended model disagrees with MiniMax-M3")

    personal = aliases.get("byteplus.attended")
    personal_model = str(getattr(personal, "model", "") or "") if personal is not None else None

    return {
        "policy_version": str(getattr(router, "policy_version", "") or ""),
        "authority_granted": False,
        "production_armed": False,
        "capacity_claimed": False,
        "selection_is_commitment": False,
        "modelark_aliases": rows,
        "minimax_attended_model": minimax_model,
        "personal_coding_plan_alias": "byteplus.attended" if personal is not None else None,
        "personal_coding_plan_model": personal_model,
        "personal_coding_plan_used": False,
    }
