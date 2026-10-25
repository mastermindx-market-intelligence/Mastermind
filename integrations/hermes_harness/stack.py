"""Boot one role against a local Hermes binary and the composed allowlist.

``boot_stack`` is the offline entry the end-to-end test uses with the runtime
stub. It does not fetch upstream and it does not construct a provider socket.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import time

from integrations.hermes_harness.extensions import boot_harness, extension_names_for
from integrations.hermes_harness.overlays import overlay_chain, render_overlays
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA, UPSTREAM_REPOSITORY
from integrations.hermes_runtime.profile import dump_profile, load_profile
from integrations.hermes_runtime.secrets import load_secrets
from integrations.hermes_runtime.supervisor import ServiceRuntime

PROFILES = Path(__file__).resolve().parents[1] / "hermes_runtime" / "profiles"
STUB = Path(__file__).resolve().parents[1] / "hermes_runtime" / "tests" / "fixtures" / "hermes_stub.py"
CENSUS = Path(__file__).resolve().parents[1] / "hermes_qualification" / "tests" / "fixture-cli-toolsets.txt"


@dataclass
class Stack:
    runtime: ServiceRuntime
    ready: dict
    overlays: dict[str, str]
    chains: dict[str, tuple[str, ...]]

    def close(self) -> None:
        self.runtime.stop()


def compose_profile(
    role: str,
    *,
    state_dir: Path,
    secrets_file: Path,
    hermes_home: Path | None = None,
    gateway_port: int | None = None,
    backend_port: int | None = None,
):
    shipped = PROFILES / f"{role}.yaml"
    profile = load_profile(
        shipped,
        state_dir=state_dir,
        secrets_file=secrets_file,
        hermes_home=hermes_home,
    )
    changes: dict = {"tool_allowlist": frozenset({"clarify"}) | extension_names_for(role)}
    if gateway_port is not None:
        changes["gateway_port"] = gateway_port
    if backend_port is not None:
        changes["backend_port"] = backend_port
    return replace(profile, **changes)


def boot_stack(
    *,
    root: Path,
    secrets_file: Path,
    role: str = "mmsecretary",
    hermes_bin: Path | None = None,
    tools_fixture: Path | None = None,
) -> Stack:
    boot_harness()
    binary = Path(hermes_bin or STUB)
    os.chmod(binary, 0o755)
    state = root / "state"
    state.mkdir(parents=True, exist_ok=True)
    home = root / "hermes-home"
    home.mkdir(parents=True, exist_ok=True)
    profile = compose_profile(
        role,
        state_dir=state,
        secrets_file=secrets_file,
        hermes_home=home,
        gateway_port=0,
        backend_port=0,
    )
    overlays = render_overlays()
    _write_private(home / "provider-overlay.yaml", overlays[role])
    _write_private(home / "vision-overlay.yaml", overlays["vision"])
    ready_path = root / "ready.json"
    runtime = ServiceRuntime(
        profile,
        load_secrets(secrets_file),
        binary,
        extra_child_env={
            "HERMES_STUB_TOOLS": str(tools_fixture or CENSUS),
            "HERMES_STUB_READY": str(ready_path),
        },
    )
    runtime.start()
    ready = _wait_ready(runtime, ready_path)
    chains = {name: overlay_chain(name) for name in ("mmsecretary", "mmmeta", "vision")}
    return Stack(runtime=runtime, ready=ready, overlays=overlays, chains=chains)


def write_composed_profile(role: str, *, state_dir: Path, secrets_file: Path, dest: Path) -> None:
    profile = compose_profile(role, state_dir=state_dir, secrets_file=secrets_file)
    _write_private(dest, dump_profile(profile))


def _wait_ready(runtime: ServiceRuntime, ready: Path, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        code, _payload = runtime.health_snapshot()
        if code == 200 and ready.is_file():
            return json.loads(ready.read_text(encoding="utf-8"))
        if runtime.failed:
            break
        time.sleep(0.02)
    runtime.stop()
    raise RuntimeError(runtime.refusal_code or "STACK_BOOT_FAILED")


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def pinned_identity() -> dict[str, str]:
    return {"sha": PINNED_UPSTREAM_SHA, "repository": UPSTREAM_REPOSITORY}
