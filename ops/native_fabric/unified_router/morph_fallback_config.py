"""Pure, idempotent amendment of the existing M2 route document.

No credentials, provider calls, entitlement creation or cooldown clearing. The
installer separately fences the actual source/config preimage and drains8313.
"""
from __future__ import annotations

import copy


def upgrade(document):
    result = copy.deepcopy(document)
    routes = {r["route_id"]: r for r in result["routes"]}
    policy = result["model_routing"]
    resources = policy["resources"]
    kimi = ["morph_kimi", "morph_kimi_2"]
    morph_ds = ["morph_ds", "morph_ds_2"]
    deepseek = morph_ds + ["labs_pool", "opencode_go_1", "opencode_go_2",
                           "byteplus_coding", "byteplus_coding_2"]
    qwen = [f"bailian_{i}" for i in range(1, 9)]
    glm = [f"glm_chairman_{i}" for i in range(1, 7)]
    needed = set(kimi + deepseek + qwen + glm + ["claude_pool"])
    if needed - routes.keys():
        raise ValueError("expected existing route identities are missing")
    for rid in morph_ds:
        resources[rid].update(input_tpm=400000, output_tpm=70000, headroom=0.95,
            max_inflight=6, input_basis="uncached", allow_one_oversize=False,
            strict_output_reservation=True, alias_max_output_tokens=16384,
            require_observed_cache=True, provider_headers=True)
        routes[rid]["session_header"] = "x-session-id"
        routes[rid]["notes"] = ("Morph Ultra DeepSeek: existing subscription resource, shared Flash aliases. "
            "400000 uncached input/70000 output TPM;95% sustained budget;full output reservation; "
            "six local concurrent requests at most;16K output ceiling for flexible aliases. "
            "Observed cache/header constraints and durable uncertain-send holds apply. No assumed burst.")
    for rid in kimi:
        resources[rid].update(headroom=0.9, max_inflight=1, strict_output_reservation=True,
            alias_max_output_tokens=4096, require_observed_cache=True, allow_one_oversize=False,
            provider_headers=True)
    for rid in qwen:
        resources.setdefault(rid, {}).update(key="direct-" + rid, max_inflight=4,
            input_basis="uncached", cap_basis="local_safety_cap_not_provider_entitlement")
    for i in (1, 2):
        for rid in (f"opencode_go_{i}", f"opencode_go_beam_{i}"):
            if rid in routes:
                routes[rid].update(concurrency_group=f"opencode-go-credential-{i}", group_max_in_flight=2)
        routes[f"opencode_go_{i}"]["max_in_flight"] = 2
    for rid in ("byteplus_coding", "byteplus_coding_2"):
        # A family safety ceiling does not assert independent account entitlement.
        routes[rid].update(concurrency_group="byteplus-coding-safety", group_max_in_flight=2,
                           max_in_flight=2)
    for rid in ("labs_pool", "labs_fable_free"):
        routes[rid].update(concurrency_group="experiential-local-gateway", group_max_in_flight=2)
    allowed = policy.setdefault("exact_route_allowlists", {})
    allowed["deepseek-v4.1-flash"] = deepseek
    allowed["deepseek-v4.1-flash-1017"] = morph_ds + ["labs_pool"]
    allowed["qwen3.8-max"] = qwen
    allowed["qwen4-max-preview"] = qwen
    # The incumbent gateway reports this funding hold. Do not route around it
    # through its separately exposed Anthropic compatibility surface.
    policy.setdefault("route_model_holds", {}).setdefault("labs_pool", {}).update({
        "deepseek-v4.1-flash": "PLAN_INCLUDED_FUNDING_UNVERIFIED",
        "deepseek-v4.1-flash-1017": "PLAN_INCLUDED_FUNDING_UNVERIFIED"})
    maps = {"deepseek-v4.1-flash": deepseek, "kimi-k3.1-pro": kimi,
            "qwen4-max-preview": qwen, "glm-5.3": glm, "claude-opus-5-5": ["claude_pool"]}
    specs = {
        "auto": (["deepseek-v4.1-flash", "kimi-k3.1-pro", "glm-5.3", "qwen4-max-preview"], [6, 3, 1, 1], "balanced"),
        "fabric/fast": (["deepseek-v4.1-flash", "glm-5.3", "qwen4-max-preview"], [1000, 1, 1], "ordered"),
        "fabric/balanced": (["glm-5.3", "kimi-k3.1-pro", "qwen4-max-preview"], [4, 4, 2], "balanced"),
        "fabric/kimi-preferred": (["kimi-k3.1-pro", "qwen4-max-preview", "claude-opus-5-5"], [1000, 1, 1], "ordered"),
        "fabric/deepseek-preferred": (["deepseek-v4.1-flash", "qwen4-max-preview", "claude-opus-5-5"], [1000, 1, 1], "ordered"),
    }
    for name, (models, weights, strategy) in specs.items():
        result["aliases"][name] = models
        group = policy["groups"].setdefault(name, {})
        group.update(routes={m: maps[m] for m in models}, weights=dict(zip(models, weights)),
                     strategy=strategy, capacity_aware=True, cohort="qualified_text_and_custom_tools")
        if name.endswith("-preferred"):
            group["fallback_models"] = models[1:]
    families = policy["overflow"]["families"]
    for family, matches in (("kimi", ["kimi-k3.1-pro"]),
                            ("deepseek", ["deepseek-v4.1-flash"])):
        fam = families[family]
        fam.pop("target", None)
        fam.update(match=matches, targets=["qwen4-max-preview", "claude-opus-5-5"],
            cap_fallback="wait", request_boundary_fallback=True,
            preference_wait_s=1.5, return_to_primary_after_s=300)
    labels = result.setdefault("model_labels", {})
    labels.update({
        "fabric/kimi-preferred": "Kimi preferred (4K alias output); Qwen4 / Opus5.5 fallback",
        "fabric/deepseek-preferred": "DeepSeek preferred (16K alias output); eligible providers, Qwen4 / Opus5.5",
        "fabric/balanced": "Balanced - Kimi / GLM / Qwen4 with eligible capacity",
        "auto": "Auto - capacity-aware included models and eligible DeepSeek providers",
    })
    policy["constraints"] = [
        "exact models change only under the explicit configured fallback families",
        "no inferred task-quality equivalence outside the configured cohort",
        "no unauthorized paid overflow or funding-hold bypass",
        "no replay after possible upstream acceptance or a permission refusal",
        "local reservations are estimates, never authoritative quota balances",
    ]
    return result
