"""Validate and prepare settings for the existing Hermes Adaptive Effort owner.

No profile writes, network requests, credentials, model selection or admission.
The CLI prints only the non-secret HAE settings fragment, never a user's config.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

PLUGIN = "hermes-adaptive-effort"
UPSTREAM_COMMIT = "c84f1389670cdd5ec4607b13bd32c4809878c415"
MANIFEST_BLOB = "4c989330a925086955a55e5bdd4eff838ed76ed2"
RETIRED_KEYS = frozenset({"respect_manual_effort", "effort_floor", "effort_ceiling"})


class ConfigurationError(ValueError):
    """A non-secret, deterministic configuration-contract error."""


def load_schema(path: Path) -> dict[str, Any]:
    """Read the exact reviewed manifest without importing or executing its plugin.

    BaseLoader keeps YAML 1.1's unquoted 'off' as a string. Only schema type names
    and enum strings are consumed; its scalar defaults are deliberately unused.
    """
    import yaml

    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ConfigurationError("MANIFEST_TOO_LARGE")
    digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if digest != MANIFEST_BLOB:
        raise ConfigurationError("MANIFEST_REVISION_MISMATCH")
    value = yaml.load(raw, Loader=yaml.BaseLoader)
    if not isinstance(value, dict) or value.get("id") != PLUGIN:
        raise ConfigurationError("MANIFEST_ID_MISMATCH")
    schema = value.get("config_schema")
    if not isinstance(schema, dict):
        raise ConfigurationError("MANIFEST_SCHEMA_MISSING")
    return schema


def validate_settings(settings: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    """Reject unknown and wrongly typed settings, including old package mistakes.

    Errors contain codes only, not arbitrary field names or setting values that
    could contain secrets. This validates configuration, not runtime readiness.
    """
    if type(settings) is not dict or type(schema) is not dict:
        raise ConfigurationError("SETTINGS_OBJECT_REQUIRED")
    if set(settings) & RETIRED_KEYS:
        raise ConfigurationError("UNSUPPORTED_LEGACY_SETTING")
    if set(settings) - set(schema):
        raise ConfigurationError("UNKNOWN_SETTING")
    for key, value in settings.items():
        spec = schema[key]
        if not isinstance(spec, dict):
            raise ConfigurationError("INVALID_SCHEMA")
        kind = spec.get("type")
        valid = ((kind == "str" and type(value) is str)
                 or (kind == "bool" and type(value) is bool)
                 or (kind == "int" and type(value) is int)
                 or (kind == "float" and type(value) in (int, float)
                     and math.isfinite(value)))
        if not valid:
            raise ConfigurationError("SETTING_TYPE_MISMATCH")
        choices = spec.get("choices")
        if choices is not None and value not in choices:
            raise ConfigurationError("SETTING_CHOICE_MISMATCH")
    if settings.get("subagent_mode", "off") != "off":
        raise ConfigurationError("CHILD_EFFORT_OUTSIDE_THIS_SLICE")
    if settings.get("effort_models", ""):
        raise ConfigurationError("UNQUALIFIED_MODEL_ASSERTION")
    if settings.get("dialogue_context_messages", 0) != 0:
        raise ConfigurationError("DIALOGUE_SHARING_OUTSIDE_THIS_SLICE")
    if settings.get("use_target_model_context", False) is not False:
        raise ConfigurationError("TARGET_SHARING_OUTSIDE_THIS_SLICE")
    if settings.get("continuation_downgrade_votes", 0) != 0:
        raise ConfigurationError("EXTRA_SCORER_CALL_OUTSIDE_THIS_SLICE")


def candidate_settings(schema: Mapping[str, Any], mode: str = "off") -> dict[str, Any]:
    """A staging or qualification candidate, not permission to activate it.

    'always' is deliberately distinct from 'auto': direct-zai is not upstream's
    exact dynamic registry, so retained auto decisions do not meet per-prompt
    acceptance. Keep live mode off until scorer and route evidence exist.
    """
    if mode not in ("off", "always"):
        raise ConfigurationError("MODE_OUTSIDE_THIS_SLICE")
    settings = {
        "mode": mode, "subagent_mode": "off", "scorer_provider": "jev",
        "jev_model": "jev-latest", "timeout_s": 2.0, "prompt_chars": 4000,
        "dialogue_context_messages": 0, "use_target_model_context": False,
        "continuation_downgrade_votes": 0, "dynamic_trial": False,
        "tool_error_escalation": False, "scorer_pause_failures": 3,
        "scorer_pause_s": 60.0, "max_turns": 64,
        "classification_instructions": (
            "Choose among the supplied legal levels for the actual task. "
            "Simple factual or mechanical tasks need the lowest level. "
            "Ambiguous engineering and substantive debugging need higher effort; "
            "reserve the highest level for difficult architecture or analysis. "
            "A short continuation does not by itself imply an easy task."
        ),
    }
    validate_settings(settings, schema)
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mode", choices=("off", "always"), default="off")
    args = parser.parse_args(argv)
    try:
        schema = load_schema(args.manifest)
        settings = candidate_settings(schema, args.mode)
    except (ConfigurationError, OSError, UnicodeError, ImportError):
        print(json.dumps({"state": "INVALID_CONFIGURATION_INPUT", "applied": False}))
        return 2
    print(json.dumps({
        "state": "SETTINGS_CANDIDATE_ONLY", "applied": False,
        "upstream_commit": UPSTREAM_COMMIT, "manifest_blob": MANIFEST_BLOB,
        "plugin": PLUGIN, "settings": settings,
        "manual_control": "/hae off here; then /reasoning <supported-level>",
        "proof": "CONFIGURATION_ONLY_NOT_SCORER_OR_PROVIDER_ACCEPTANCE",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
