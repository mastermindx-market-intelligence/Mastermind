"""Apply the model overlay for each harness role. Cursor stays last.

``mmsecretary`` serves ModelArk GLM-5.3-Flash first. ``mmmeta`` serves Z.AI
GLM-5.3 first. Vision and computer-use serve MiniMax-M3 first. None of these
renders put a credential value in the YAML.
"""

from __future__ import annotations

from integrations.hermes_models.contract import PROVIDERS, chain_for
from integrations.hermes_models.profile_config import render_profile

ROLE_CONTRACT = {
    "mmsecretary": "secretary",
    "mmmeta": "meta-ceo",
    "vision": "vision",
}
PRIMARY = {
    "mmsecretary": "byteplus-modelark.glm-5.3-flash",
    "mmmeta": "zai.glm-5.3",
    "vision": "minimax.attended",
}


class OverlayError(RuntimeError):
    """The role chain does not match the Chairman mapping."""


def overlay_chain(role_name: str) -> tuple[str, ...]:
    contract_role = ROLE_CONTRACT.get(role_name)
    if contract_role is None:
        raise OverlayError(f"unknown overlay role {role_name}")
    specs = chain_for(contract_role)
    ids = tuple(spec.provider_id for spec in specs)
    if not ids or ids[-1] != "cursor-pool":
        raise OverlayError("cursor pool is not last")
    if ids[0] != PRIMARY[role_name]:
        raise OverlayError(f"{role_name} primary provider drifted")
    if role_name == "mmmeta" and specs[0].served_model != "glm-5.3":
        raise OverlayError("mmmeta is not GLM-5.3")
    if role_name == "mmsecretary" and "flash" not in specs[0].provider_id:
        raise OverlayError("mmsecretary is not Flash")
    if role_name == "vision" and specs[0].served_model != "MiniMax-M3":
        raise OverlayError("vision is not MiniMax-M3")
    return ids


def render_vision_overlay() -> str:
    spec = PROVIDERS["minimax.attended"]
    cursor = PROVIDERS["cursor-pool"]
    lines = [
        "# mastermind.hermes_model_provider_overlay.v1",
        "# Vision and computer-use. MiniMax-M3, then the Cursor pool.",
        "# production_armed: false",
        "# executive_admission: false",
        "model:",
        "  provider: minimax-m3",
        "  default: \"MiniMax-M3\"",
        f"  base_url: \"{spec.base_url}\"",
        f"  key_env: {spec.credential_env}",
        "  api_mode: chat_completions",
        "providers:",
        "  minimax-m3:",
        "    name: \"MiniMax-M3\"",
        f"    api: \"{spec.base_url}\"",
        f"    key_env: {spec.credential_env}",
        "    api_mode: chat_completions",
        "    default_model: \"MiniMax-M3\"",
        "  cursor-pool:",
        "    name: \"Cursor pool\"",
        f"    api: \"{cursor.base_url}\"",
        f"    key_env: {cursor.credential_env}",
        "    api_mode: chat_completions",
        f"    default_model: \"{cursor.served_model}\"",
        "    enabled: false",
        "",
    ]
    text = "\n".join(lines)
    if "api_key:" in text.lower() or "sk-" in text.lower():
        raise OverlayError("vision overlay contains forbidden material")
    return text


def render_overlays() -> dict[str, str]:
    return {
        "mmsecretary": render_profile("mmsecretary"),
        "mmmeta": render_profile("mmmeta"),
        "vision": render_vision_overlay(),
    }
