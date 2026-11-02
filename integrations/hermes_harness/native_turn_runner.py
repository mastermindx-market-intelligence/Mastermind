"""One bounded native Hermes one-shot canary INSIDE an existing role systemd cgroup.

Not a daemon, readiness endpoint, credential reader, provider connection pool,
retry engine or Slack sender. The already-authorized host must invoke this
with ServiceRuntime._model_child_env() from its existing role-private credential
owner. The process must actually be in the pinned role's systemd service; an
operator shell invocation outside that cgroup refuses before network use.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Mapping

from integrations.hermes_models.contract import native_provider
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import RuntimeProfile
from .native_turn_evidence import (
    MAX_STREAM_BYTES, ObservationRefusal, canary_prompt,
    native_one_shot_argv, observe_native_turn,
)

MAX_STDERR_BYTES = 1024
MAX_CANARY_SECONDS = 45.0
_SERVICE = re.compile(r"^[a-z0-9_-]+\.service$")
_ALLOWED_ROLES = frozenset({"mmsecretary", "mmmeta"})


def assert_role_service_cgroup(role: str, *, raw: str | None = None) -> None:
    """Require the current Linux cgroup under the exact selected role unit.

    Pure raw injection exists for deterministic tests only. run_native_canary
    never accepts raw cgroup evidence: it always reads /proc/self/cgroup.
    This is a confinement identity guard, not proof of BPF IPAddressDeny
    enforcement or absence of an unrelated external process.
    """
    if role not in _ALLOWED_ROLES:
        raise RuntimeRefusal("NATIVE_CANARY_ROLE_INVALID")
    if raw is None:
        if not sys.platform.startswith("linux"):
            raise RuntimeRefusal("NATIVE_CANARY_LINUX_REQUIRED")
        try:
            raw = Path("/proc/self/cgroup").read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise RuntimeRefusal("NATIVE_CANARY_CGROUP_UNAVAILABLE") from None
    basename = f"hermes-runtime-{role}.service"
    if (not isinstance(raw, str) or len(raw) > 16384
            or not any(
                (line.split(":", 2)[-1].split("/")[-1] == basename
                 or f"/{basename}/" in line.split(":", 2)[-1])
                for line in raw.splitlines()
                if line.startswith("0::") or line.count(":") >= 2
            )):
        raise RuntimeRefusal("NATIVE_CANARY_CGROUP_UNQUALIFIED")


def _private_child_environment(profile: RuntimeProfile, env: Mapping[str, str]) -> dict[str, str]:
    """Reject ambient/gateway/Slack credential exposure; use provided child scope."""
    if not isinstance(env, Mapping) or profile.role not in _ALLOWED_ROLES:
        raise RuntimeRefusal("NATIVE_CANARY_ENV_UNQUALIFIED")
    try:
        spec = native_provider(profile.role, profile.native_provider_id)
    except (ValueError, KeyError):
        raise RuntimeRefusal("NATIVE_CANARY_MODEL_UNQUALIFIED") from None
    if not spec.enabled_in_profile or spec.provider_id == "cursor-pool":
        raise RuntimeRefusal("NATIVE_CANARY_MODEL_UNQUALIFIED")
    needed = (spec.credential_env, "HTTPS_PROXY", "NO_PROXY", "HERMES_HOME")
    other_role_key = "ZAI_API_KEY" if profile.role == "mmsecretary" else "BYTEPLUS_MODELARK_API_KEY"
    if (other_role_key in env
            or any(not isinstance(env.get(k), str) or not env[k] for k in needed)
            or env.get("HERMES_HOME") != str(profile.hermes_home)
            or "HERMES_GATEWAY_TOKEN" in env
            or "HERMES_SLACK_BOT_TOKEN" in env
            or "HTTP_PROXY" in env
            or "ALL_PROXY" in env):
        raise RuntimeRefusal("NATIVE_CANARY_ENV_UNQUALIFIED")
    # The proxy URL is a role-private, supervisor-validated value on the
    # accepted #1952 composition. Verify its essential shape here without
    # replacing the upstream egress contract or reading another key file.
    proxy = env["HTTPS_PROXY"]
    if not re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{3,4})", proxy):
        raise RuntimeRefusal("NATIVE_CANARY_PROXY_NOT_QUALIFIED")
    port = int(proxy.rpartition(":")[2])
    if not 1024 <= port <= 65535 or env["NO_PROXY"] != "127.0.0.1,localhost":
        raise RuntimeRefusal("NATIVE_CANARY_PROXY_NOT_QUALIFIED")
    return dict(env)


def _terminate_group(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            proc.kill()
    try:
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _capture_bounded_child(
    argv: list[str], prompt: bytes, *, env: Mapping[str, str],
    cwd: Path, timeout_seconds: float,
) -> tuple[int, bytes, bytes]:
    """Capture pipes with hard byte ceilings; never buffer unlimited child output."""
    if (not 1 <= timeout_seconds <= MAX_CANARY_SECONDS
            or len(prompt) > 512 or not prompt):
        raise RuntimeRefusal("NATIVE_CANARY_ARGUMENTS_INVALID")
    proc: subprocess.Popen[bytes] | None = None
    captured: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=str(cwd), env=dict(env),
            close_fds=True, start_new_session=True,
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        # The canary prompt is always <512 bytes (well within a pipe's
        # atomic write size); no shell and no argv secret/prompt.
        proc.stdin.write(prompt)
        proc.stdin.close()
        deadline = time.monotonic() + timeout_seconds
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
            selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeRefusal("NATIVE_CANARY_TIMEOUT")
                for key, _ in selector.select(timeout=min(remaining, 0.2)):
                    label = key.data
                    chunk = os.read(key.fileobj.fileno(), 4096)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buf = captured[label]
                    buf.extend(chunk)
                    limit = MAX_STREAM_BYTES if label == "stdout" else MAX_STDERR_BYTES
                    if len(buf) > limit:
                        raise RuntimeRefusal("NATIVE_CANARY_OUTPUT_TOO_LARGE")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeRefusal("NATIVE_CANARY_TIMEOUT")
            exit_code = proc.wait(timeout=remaining)
        return exit_code, bytes(captured["stdout"]), bytes(captured["stderr"])
    except RuntimeRefusal:
        raise
    except (OSError, ValueError, BrokenPipeError, subprocess.SubprocessError):
        raise RuntimeRefusal("NATIVE_CANARY_PROCESS_UNAVAILABLE") from None
    finally:
        if proc is not None:
            _terminate_group(proc)
            for handle in (proc.stdin, proc.stdout, proc.stderr):
                if handle is not None:
                    try:
                        handle.close()
                    except OSError:
                        pass


def run_native_canary(
    profile: RuntimeProfile, *, hermes_bin: Path,
    model_child_env: Mapping[str, str],
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    """Execute a single challenge inside the already-running role service.

    No credential material, model output or prompt is returned. Never retry
    an ambiguous model call or infer remote provider reachability from this
    source-only parser. The receiving owner separately verifies proxy policy,
    TLS, provider auth, host install and role Slack roundtrip.
    """
    if (type(profile) is not RuntimeProfile
            or profile.sha != PINNED_UPSTREAM_SHA
            or profile.role not in _ALLOWED_ROLES
            or not profile.hermes_home.is_absolute()
            or not profile.hermes_home.is_dir()
            or not isinstance(hermes_bin, Path)
            or not hermes_bin.is_absolute()
            or not hermes_bin.is_file()):
        raise RuntimeRefusal("NATIVE_CANARY_PROFILE_UNQUALIFIED")
    assert_role_service_cgroup(profile.role)
    env = _private_child_environment(profile, model_child_env)
    try:
        spec = native_provider(profile.role, profile.native_provider_id)
        argv = native_one_shot_argv(hermes_bin, profile.role)
        marker = "MMX-CANARY-" + secrets.token_hex(16).upper()
        prompt = canary_prompt(marker).encode("utf-8")
    except (ObservationRefusal, ValueError, KeyError):
        raise RuntimeRefusal("NATIVE_CANARY_MODEL_UNQUALIFIED") from None
    rc, stdout, stderr = _capture_bounded_child(
        argv, prompt, env=env, cwd=profile.hermes_home, timeout_seconds=timeout_seconds,
    )
    observation = observe_native_turn(
        role=profile.role, expected_model=spec.served_model,
        challenge_marker=marker, stdout=stdout, stderr=stderr,
        process_exit_code=rc,
    )
    # True here means the calling process's Linux cgroup membership was
    # observed, NOT that systemd's eBPF network denial or proxy allowlist
    # was independently tested.
    return {
        **observation,
        "host_service_cgroup_membership_observed": True,
        "bpf_network_deny_verified": False,
        "provider_tls_verified": False,
        "attempted_once": True,
    }
