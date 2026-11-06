"""Bounded native text inference for an already-authenticated host consumer.

No Slack transport, target registry, admission, credential store, retry or
background loop. The parent uses the existing canonical reply writer; this
module never selects an actor, destination, operation, account or provider.
The fresh helper stays inside the original role cgroup/UID and runs the same
installed-source/identity/TCP gates as the operator canary before key access.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from integrations.hermes_models.contract import native_provider
from integrations.hermes_runtime.errors import NativeTurnEffectUnknown, RuntimeRefusal
from integrations.hermes_runtime.supervisor import ServiceRuntime
from .native_turn_evidence import (
    ObservationRefusal, _closed_mapping, _no_constants,
    native_one_shot_argv, read_native_text,
)
from .native_turn_runner import _capture_bounded_child, _private_child_environment

TEXT_SCHEMA = "mastermind.hermes_native_text.v1"
MAX_PROMPT_BYTES = 8192
HELPER_SECONDS = 40.0
MODEL_SECONDS = 30.0
_HELPER_KEYS = frozenset({"schema", "status", "text", "may_have_provider_effect"})


def canonical_text_prompt(value: object, *, role: str | None = None) -> tuple[str, str]:
    """Rebuild the EXISTING consumer's data prompt; input is never authority."""
    from integrations.hermes_secretary.native_dialogue_consumer import (
        ConsumerRefusal, ROLES, _message_prompt,
    )
    if type(value) is not str:
        raise RuntimeRefusal("NATIVE_TEXT_PROMPT_INVALID")
    try:
        encoded = value.encode("utf-8", "strict")
        if not encoded or len(encoded) > MAX_PROMPT_BYTES:
            raise ValueError
        body = json.loads(value, object_pairs_hook=_closed_mapping, parse_constant=_no_constants)
        if (type(body) is not dict
                or set(body) != {"role", "task", "summary", "body", "instructions"}
                or body.get("role") not in ROLES
                or (role is not None and body["role"] != role)):
            raise ValueError
        canonical = _message_prompt({"summary": body["summary"], "body": body["body"]}, role=body["role"])
        if body != json.loads(canonical) or value != canonical:
            raise ValueError
        return body["role"], canonical
    except (ConsumerRefusal, ValueError, TypeError, UnicodeError, RecursionError):
        raise RuntimeRefusal("NATIVE_TEXT_PROMPT_INVALID") from None


def text_result(status: str, *, text: str | None = None) -> dict:
    if status not in {"TEXT_READY", "REFUSED", "EFFECT_UNKNOWN"}:
        raise ValueError("invalid native text result")
    return {"schema": TEXT_SCHEMA, "status": status,
            "text": text if status == "TEXT_READY" else None,
            "may_have_provider_effect": status != "REFUSED"}


def _qualified_text(value: object) -> str:
    from integrations.hermes_secretary.native_dialogue_consumer import _ANSWER_SECRET
    if (type(value) is not str or not value.strip() or len(value) > 700
            or _ANSWER_SECRET.search(value)
            or any(ord(ch) < 32 and ch not in "\n\t" for ch in value)):
        raise ValueError("invalid native text output")
    value.encode("utf-8", "strict")
    return value


def execute_prepared_text(profile, *, hermes_bin: Path, model_env: dict, prompt: str) -> str:
    """Internal helper after existing installed-role qualification, once only.

    Environment is supplied by the existing role-private runtime owner. Any
    failure after the child call begins is returned as possible provider effect,
    never as permission to repeat a paid turn. Raw streams never escape here.
    """
    _role, prompt = canonical_text_prompt(prompt, role=profile.role)
    env = _private_child_environment(profile, model_env)
    spec = native_provider(profile.role, profile.native_provider_id)
    argv = native_one_shot_argv(hermes_bin, profile.role)
    try:
        rc, stdout, stderr = _capture_bounded_child(
            argv, prompt.encode("utf-8"), env=env, cwd=profile.hermes_home,
            timeout_seconds=MODEL_SECONDS, max_prompt_bytes=MAX_PROMPT_BYTES,
        )
        answer = _qualified_text(read_native_text(
            role=profile.role, expected_model=spec.served_model,
            stdout=stdout, stderr=stderr, process_exit_code=rc,
        ))
        # Check the exact privately selected key too, not only secret patterns.
        if env[spec.credential_env] in answer:
            raise ValueError("private output refused")
        return answer
    except (RuntimeRefusal, ObservationRefusal, ValueError, UnicodeError, OSError):
        raise NativeTurnEffectUnknown() from None


class NativeTextInference:
    """One sync callback for HermesCanonicalTurnConsumer's existing model port.

    Construction is inert. Invocation is a potential paid effect and requires
    the host's existing per-turn authority/budget. No autostart or retry exists.
    A source object cannot manufacture a Runtime native session or bot identity.
    """
    def __init__(self, runtime: ServiceRuntime):
        if type(runtime) is not ServiceRuntime:
            raise RuntimeRefusal("NATIVE_TEXT_RUNTIME_UNQUALIFIED")
        profile = runtime.profile
        if (runtime.hermes_bin != profile.state_dir / "current" / "bin" / "hermes"
                or profile.source_path != profile.state_dir / "current" / "profile.yaml"):
            raise RuntimeRefusal("NATIVE_TEXT_NOT_INSTALLED_ROLE")
        self._runtime = runtime
        self._profile = profile
        self._hermes_bin = runtime.hermes_bin

    def __repr__(self) -> str:
        return "NativeTextInference(role-bound, credentials-not-rendered)"

    def __call__(self, prompt: str) -> str:
        _role, prompt = canonical_text_prompt(prompt, role=self._profile.role)
        if self._runtime.profile != self._profile or self._runtime.hermes_bin != self._hermes_bin:
            raise RuntimeRefusal("NATIVE_TEXT_RUNTIME_CHANGED")
        from integrations.hermes_runtime.system_service import assert_root_service_cgroup
        # Do not even launch the helper from an unconfined operator shell.
        assert_root_service_cgroup(self._profile.role)
        argv = [sys.executable, "-P", "-m", "integrations.hermes_runtime", "text-turn",
                "--profile", str(self._profile.source_path), "--hermes-bin", str(self._hermes_bin)]
        env = {"PATH": os.defpath, "HOME": str(self._profile.hermes_home),
               "LANG": "C.UTF-8", "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
               "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            rc, stdout, stderr = _capture_bounded_child(
                argv, prompt.encode("utf-8"), env=env, cwd=self._profile.hermes_home,
                timeout_seconds=HELPER_SECONDS, max_prompt_bytes=MAX_PROMPT_BYTES,
            )
        except RuntimeRefusal:
            raise NativeTurnEffectUnknown() from None
        try:
            result = json.loads(stdout.decode("utf-8", "strict"),
                                object_pairs_hook=_closed_mapping, parse_constant=_no_constants)
            if (stderr or type(result) is not dict or set(result) != _HELPER_KEYS
                    or result["schema"] != TEXT_SCHEMA):
                raise ValueError
            if result == text_result("REFUSED") and rc == 2:
                raise RuntimeRefusal("NATIVE_TEXT_PRECONDITION_REFUSED")
            if result == text_result("EFFECT_UNKNOWN") and rc == 3:
                raise NativeTurnEffectUnknown()
            if (rc != 0 or result["status"] != "TEXT_READY"
                    or result["may_have_provider_effect"] is not True):
                raise ValueError
            answer = _qualified_text(result["text"])
            # Parent-local gateways/tokens never enter helper env or its model;
            # additionally refuse literal accidental reflection before reply.
            protected = [self._runtime.secrets.token, self._runtime.secrets.dashboard_password]
            protected += [v for k, v in self._runtime.secrets.values.items()
                          if k.endswith(("_TOKEN", "_KEY", "_PASSWORD")) and isinstance(v, str)]
            if any(value and value in answer for value in protected):
                raise ValueError
            return answer
        except RuntimeRefusal:
            raise
        except (ValueError, TypeError, UnicodeError, RecursionError, KeyError):
            raise NativeTurnEffectUnknown() from None
