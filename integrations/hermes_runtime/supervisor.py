"""Supervise the pinned Hermes child and restart it after a crash.

systemd --user is the outer supervisor (Restart=on-failure in the unit).
This loop is the inner one the acceptance test can kill without a host bus.
"""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import threading
import time

from .constants import (HEALTH_SCHEMA, LOOPBACK_HOST, PINNED_UPSTREAM_SHA,
                        conversation_contract)
from .egress import ROLE_PROXY_HOST
from .hermes_config import render_hermes_config
from .errors import RuntimeRefusal
from .gateway import Gateway, reserve_loopback_port
from .memory import HighWaterLog, read_rss_kib
from .profile import RuntimeProfile
from .registry import assert_registered_tools_exact, extension_tools_for
from .secrets import Secrets, child_env, assert_no_supervisor_notification_env
from .role_status_publisher import PUBLICATION_INTERVAL_SECONDS, RoleStatusPublisher

_UNSAFE = set(" \n\r\t\"'`$")


def _backend_health_ready(port: int, host: str = LOOPBACK_HOST) -> bool:
    """Check native Hermes health identity, not only a local HTTP status.

    Pinned Hermes /api/health includes ok and its booted Git commit. A
    different/unstamped executable or another loopback server returning 200
    must never be promoted to healthy, even if the child PID is still alive.
    No credential, redirect, public interface or model call is used.
    """
    if (isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535
            or host not in (LOOPBACK_HOST, *ROLE_PROXY_HOST.values())):
        return False
    conn = http.client.HTTPConnection(host, port, timeout=0.25)
    try:
        conn.request("GET", "/api/health")
        response = conn.getresponse()
        if response.status != 200:
            return False
        body = response.read(4097)
        if len(body) > 4096:
            return False
        identity = json.loads(body.decode("utf-8", errors="strict"))
        return (
            type(identity) is dict
            and identity.get("ok") is True
            and identity.get("commit") == PINNED_UPSTREAM_SHA
        )
    except (OSError, http.client.HTTPException, ValueError):
        return False
    finally:
        conn.close()


def _safe_path(path: Path) -> str:
    text = str(path)
    if any(ch in text for ch in _UNSAFE):
        raise RuntimeRefusal("UNSAFE_PATH")
    return text


def build_tools_argv(hermes_bin: Path, role: str) -> list[str]:
    return [_safe_path(hermes_bin), "-p", role, "tools", "list", "--platform", "cli"]


def build_serve_argv(hermes_bin: Path, role: str, backend_port: int, host: str = LOOPBACK_HOST) -> list[str]:
    if isinstance(backend_port, bool) or not isinstance(backend_port, int):
        raise RuntimeRefusal("INVALID_BACKEND_PORT")
    if not 1024 <= backend_port <= 65535:
        raise RuntimeRefusal("INVALID_BACKEND_PORT")
    if host not in (LOOPBACK_HOST, ROLE_PROXY_HOST.get(role)):
        raise RuntimeRefusal("NON_LOOPBACK_BIND_REFUSED")
    argv = [
        _safe_path(hermes_bin),
        "-p",
        role,
        "serve",
        "--host",
        host,
        "--port",
        str(backend_port),
        "--skip-build",
        "--isolated",
    ]
    if "0.0.0.0" in argv or "--insecure" in argv:
        raise RuntimeRefusal("NON_LOOPBACK_BIND_REFUSED")
    return argv


def expected_disabled_mcp(
    profile: RuntimeProfile, consumer=None, primary_application=None, *, evaluation_inputs=None,
) -> dict[str, tuple[str, ...]] | None:
    """Require exact on-disk native config before trusting any CLI summary.

    A displayed MCP summary is not a connection or admission receipt.
    The only accepted additional config is the reviewed, *disabled*
    Steward source, plus - for a qualified optional consumer - the exact
    reviewed Executive entry whose tool filter is empty. No unknown or
    enabled MCP/server plugin is allowed.
    """
    if evaluation_inputs is not None and (primary_application is not None or profile.model_provider == "mastermind-fabric"):
        raise RuntimeRefusal("NATIVE_EVAL_INPUTS_UNQUALIFIED")
    path = profile.hermes_home / "profiles" / profile.role / "config.yaml"
    if not path.exists() and not path.is_symlink():
        if evaluation_inputs is not None or (profile.state_dir / "install-manifest.json").exists():
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_MISSING")
        # Uninstalled stub-runtime tests use a temporary profile without
        # a native config. Real installs must carry that config.
        return None
    if path.is_symlink():
        raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_SYMLINK")
    try:
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid() or info.st_nlink != 1):
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_UNSAFE")
        if info.st_size > 64 * 1024:
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_TOO_LARGE")
        raw = path.read_bytes()
    except OSError:
        raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_UNAVAILABLE") from None
    if (primary_application is None and evaluation_inputs is None
            and profile.model_provider != "mastermind-fabric" and profile.native_provider_id is None
            and raw == render_hermes_config(profile).encode("utf-8")):
        return None
    # The built-in WP1 package remains independent for non-integrated
    # installs; this optional consumer is loaded only for the specific
    # reviewed disabled native config.
    from integrations.hermes_harness.native_mcp import render_disarmed_native_config
    from integrations.hermes_steward.client import ALLOWED_TOOLS

    if profile.extension_allowlist:
        raise RuntimeRefusal("NATIVE_EXTENSION_NOT_INSTALLED")
    from integrations.hermes_harness.native_byok import (
        expected_native_config,
        render_disarmed_native_byok,
    )
    if primary_application is not None:
        from integrations.hermes_application_fabric.publication import expected_native_config as application_config
        allowed_native = {application_config(profile, primary_application, consumer).encode("utf-8")}
    elif profile.model_provider == "mastermind-fabric":
        raise RuntimeRefusal("NATIVE_PRIMARY_APPLICATION_UNQUALIFIED")
    else:
        allowed_native = ({render_disarmed_native_byok(profile).encode("utf-8")}
                          if evaluation_inputs is None else set())
    # Explicit primary or evaluation context cannot downgrade to a legacy
    # or model-less config. Only selector-free historical profiles retain
    # the earlier source-compatible config forms.
    if primary_application is None and evaluation_inputs is None and profile.native_provider_id is None:
        allowed_native.add(render_disarmed_native_config(profile).encode("utf-8"))
    expected_mcp: dict[str, tuple[str, ...]] = {"mastermind_steward": tuple(ALLOWED_TOOLS)}
    if consumer is not None:
        from integrations.hermes_harness.native_executive_consumer import (
            publication_from_document,
        )
        publication = publication_from_document(consumer)
        if primary_application is None:
            allowed_native.add(expected_native_config(
                profile, consumer, evaluation_inputs=evaluation_inputs).encode("utf-8"))
        # The upstream census renders an empty include list as "(none)". The
        # Executive entry registers no model-facing tool at all, so the
        # summary must show exactly that.
        expected_mcp[publication.mcp.server] = ("(none)",)
    if raw not in allowed_native:
        raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_DRIFT")
    return expected_mcp


class ServiceRuntime:
    def __init__(
        self,
        profile: RuntimeProfile,
        secrets: Secrets,
        hermes_bin: Path,
        *,
        extra_child_env: dict[str, str] | None = None,
        role_status_publisher: RoleStatusPublisher | None = None,
        native_launch=None,
    ):
        self.profile = profile
        self.secrets = secrets
        self.hermes_bin = Path(hermes_bin)
        self.extra_child_env = extra_child_env or {}
        self.restart_count = 0
        self.child_starts = 0
        self.child_pid: int | None = None
        self._backend_ready = False
        self.failed = False
        self.refusal_code = ""
        self.gateway: Gateway | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._child: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self.memory: HighWaterLog | None = None
        self._role_status_publisher = role_status_publisher
        self._next_role_status_publication = 0.0
        self._native_launch = native_launch
        self._native_home: Path | None = None
        self._extension_observed: dict | None = None
        self._extension_proved = False
        self._context_observed: dict | None = None

    def start(self) -> None:
        # Check native BYOK/alias policy before *any* Hermes subprocess,
        # including the tools-list census. A failed preflight starts nothing.
        self._model_child_env()
        if self._role_status_publisher is not None:
            self._publish_role_status_if_due(time.monotonic())
        self._check_registry()
        self.profile.hermes_home.mkdir(parents=True, exist_ok=True)
        os.chmod(self.profile.hermes_home, 0o700)
        self.memory = HighWaterLog(self.profile.state_dir / "memory" / "high-water.log")
        gateway_options = {}
        if self.profile.gateway_backend == "native-session-authority":
            from .secrets import role_conversation_token
            conversation_token = role_conversation_token(self.secrets, role=self.profile.role)
            if conversation_token is not None:
                gateway_options = {"conversation_token": conversation_token,
                                   "conversation_handler": self._native_conversation}
        self.gateway = Gateway(
            self.profile.gateway_host,
            self.profile.gateway_port,
            self.secrets.token,
            self.health_snapshot,
            role=self.profile.role,
            **gateway_options,
        )
        if (gateway_options and self._role_status_publisher is not None
                and self._role_status_publisher.custody_observer is not None):
            from dataclasses import replace
            self._role_status_publisher = replace(
                self._role_status_publisher, listener_observer=self.gateway.listener_custody,
            )
            self._next_role_status_publication = 0.0
            self._publish_role_status_if_due(time.monotonic())
        self._thread = threading.Thread(target=self._loop_guarded, name="hermes-runtime-supervisor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            child = self._child
        if child is not None:
            _terminate(child)
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self.gateway is not None:
            self.gateway.close()
            self.gateway = None

    def health_snapshot(self) -> tuple[int, dict]:
        with self._lock:
            original = self._child
            ready = self._backend_ready
        # Refresh at the existing requested health/status boundary, outside
        # the supervisor lock. No new watcher or automatic registration.
        if (original is not None and ready and original.poll() is None
                and self.profile.gateway_backend == "native-session-authority"
                and self._consumer_publication() is not None):
            self._consume_consumer_extension(original.pid)
        with self._lock:
            child = self._child
            running = child is not None and child.poll() is None
            backend_ready = running and self._backend_ready
            context = self._context_observed if backend_ready else None
            if self.failed:
                status = "failed"
            elif backend_ready:
                status = "ok"
            elif running:
                status = "starting"
            else:
                status = "restarting"
            payload = {
                "schema": HEALTH_SCHEMA,
                "status": status,
                "pinned_sha": self.profile.sha,
                "role": self.profile.role,
                "restart_count": self.restart_count,
                "child_starts": self.child_starts,
                "child_running": running,
                "backend_ready": backend_ready,
                # A verified pinned local HTTP health response is NOT a
                # provider-authenticated text turn or a Slack role delivery.
                # Until an authorized host attaches canonical proof, expose
                # those capabilities explicitly as unverified at all times.
                "provider_authenticated": False,
                "native_model_turn_verified": False,
                "network_egress_policy_verified": False,
                "slack_roundtrip_verified": False,
                "child_pid": self.child_pid,
                "memory_high_water_kib": 0 if self.memory is None else self.memory.high_water,
                # The serving-process extension proof is a read-back of the
                # actual scoped entry in the running child. It is separate
                # from the static no-credential built-in census and it never
                # clears the extension hold by itself.
                "native_extension_proved": self._extension_proved and backend_ready,
                "native_context_factory_registered": bool(context and context["factory_registered"]),
                "native_context_provider_installed": bool(context and context["provider_installed"]),
                "native_context_ready": bool(context and context["readiness"]
                                             and context["readiness"]["state"] == "READY"),
                "native_context_delivery_observed": bool(context and context["last_delivery"]),
                "native_context_prompt_observed": bool(context and context["last_delivery"]
                                                       and context["last_delivery"]["prompt"]),
                "loopback": True,
                "gateway_host": self.profile.gateway_host,
                "allowlist": sorted(self.profile.tool_allowlist),
                "upstream_attested": False,
            }
        return (200 if status == "ok" else 503), payload

    def _native_conversation(self, request: dict) -> dict:
        """Existing role gateway -> actual selected native private owner."""
        from .native_session_control import NativeSecretaryClient
        contract = conversation_contract(self.profile.role)
        response_schema = contract.response_schema
        implementation = self._native_launch.owner.root.name
        def reply(status, **fields):
            return {"schema": response_schema, "implementation_sha": implementation,
                    "result": {"schema": contract.native_schema, "status": status, **fields}}
        if (type(request) is not dict or set(request) != {"schema", "implementation_sha", "request"}
                or request["schema"] != contract.request_schema
                or request["implementation_sha"] != implementation or type(request["request"]) is not dict):
            return reply("REFUSED", reason="SOURCE_OR_REQUEST_MISMATCH")
        with self._lock:
            child, home, launch = self._child, self._native_home, self._native_launch

        def same_owner():
            with self._lock:
                if (self._stop.is_set() or self.failed or child is None
                        or self._child is not child or child.poll() is not None
                        or not self._backend_ready or home is None
                        or self._native_home != home or self._native_launch is not launch):
                    return False
            launch.check()
            launch.observe_child(child.pid)
            return (self.profile.hermes_home / "profiles" / self.profile.role).resolve(strict=True) == home

        try:
            if not same_owner():
                return reply("UNAVAILABLE")
        except Exception:
            return reply("UNAVAILABLE")
        # dispatch validates its closed request before the actual native call.
        # After this boundary, unexpected failure is conservative uncertainty.
        uncertain = "EFFECT_UNKNOWN" if request["request"].get("operation") == "submit" else "UNAVAILABLE"
        try:
            result = NativeSecretaryClient(
                home, expected_pid=child.pid, role=contract.role).dispatch(request["request"])
        except RuntimeRefusal:
            return reply("REFUSED", reason="REQUEST_REFUSED")
        except Exception:
            return reply(uncertain)
        try:
            if not same_owner():
                return reply(uncertain)
        except Exception:
            return reply(uncertain)
        return {"schema": response_schema, "implementation_sha": implementation, "result": result}

    def _observe_consumer_extension(self, child_pid: int):
        """Join one serving proof to its original child and enrolled session."""
        home, launch = self._native_home, self._native_launch
        if home is None or launch is None:
            return None
        try:
            from .native_session_control import NativeSecretaryClient, validate_enrollment_result
            from integrations.hermes_harness.native_executive_consumer import (
                ExecutiveContextConsumerPublication, publication_from_document)
            publication = publication_from_document(self._consumer_publication())
            implementation = launch.owner.root.name
            launch.observe_child(child_pid)
            client = NativeSecretaryClient(home, expected_pid=child_pid, role=self.profile.role)
            contextual = type(publication) is ExecutiveContextConsumerPublication
            result = client.consumer_capabilities() if contextual else client.consumer_extension()
            enrollment = validate_enrollment_result(
                client.inspect_enrollment(implementation, publication.session.request_id),
                implementation_sha=implementation, request_id=publication.session.request_id,
                profile_id=str(home), principal_id=publication.session.principal_id, role=self.profile.role)
            launch.observe_child(child_pid)
            if (not isinstance(result, dict) or result.get("status") != "OBSERVED"
                    or enrollment["status"] != "ENROLLED"
                    or type(result.get("consumer" if contextual else "extension")) is not dict):
                return None
            return result["consumer" if contextual else "extension"], enrollment["target"]
        except Exception:
            return None


    def _consume_consumer_extension(self, child_pid: int) -> None:
        """Refresh the conclusion for the same held child at a read boundary."""
        from .registry import assert_extension_proof_exact
        from .native_session_control import CONSUMER_EXTENSION_TOOL
        from integrations.hermes_harness.native_executive_consumer import (
            ExecutiveContextConsumerPublication, _canonical,
            publication_from_document, schema_digest, selected_child_publication,
            validate_consumer_publication)
        from integrations.hermes_harness.native_tool_registration import NATIVE_TOOL_SCHEMA
        with self._lock:
            original_child = self._child
            if original_child is None or original_child.pid != child_pid:
                return
        observation = self._observe_consumer_extension(child_pid)
        extension = None
        context = None
        proved = False
        try:
            if observation is not None:
                extension, target = observation
                document = validate_consumer_publication(self._consumer_publication())
                publication = publication_from_document(document)
                common = {
                    "implementation_sha": self._native_launch.owner.root.name,
                    "profile_id": str(self._native_home),
                    "instance_id": target["instance_id"], "authority_epoch": target["authority_epoch"],
                    "enrollment_request_id": publication.session.request_id,
                    "principal_id": publication.session.principal_id, "session_id": target["session_id"],
                }
                if type(publication) is ExecutiveContextConsumerPublication:
                    from .native_agentos_memory import validate_consumer_readback
                    import hashlib
                    checked = validate_consumer_readback(extension, publication=publication,
                        expected_binding={**common, "publication_sha256": hashlib.sha256(_canonical(document)).hexdigest()})
                    context, extension = checked["context"], checked["selected_child"]
                child = selected_child_publication(publication)
                expected = {**common,
                    "command_id": None if child is None else child.command,
                    "job_id": None if child is None else child.job_id,
                    "target_digest": None if child is None else child.target_digest,
                    "principal_binding_digest": publication.principal_binding_digest,
                    "authority_generation_digest": publication.authority_generation_digest,
                    "capability_profile_digest": publication.capability_profile_digest,
                    "plugin_sha256": publication.plugin.digest,
                    "mcp_tools_schema_sha256": publication.tools_schema_digest,
                }
                if child is not None:
                    verdict = assert_extension_proof_exact(
                        extension, expected_tool=CONSUMER_EXTENSION_TOOL,
                        expected_schema_sha256=schema_digest(NATIVE_TOOL_SCHEMA),
                        expected_scope=str(self._native_home), expected_binding=expected)
                    proved = verdict["installed"] is True
        except (RuntimeRefusal, ValueError, TypeError, KeyError, AttributeError):
            proved = False
        with self._lock:
            if self._child is original_child:
                self._extension_observed = extension
                self._extension_proved = proved and original_child.poll() is None
                self._context_observed = context if original_child.poll() is None else None


    def _env(self) -> dict[str, str]:
        # CLI/tool census receives no model provider credential.
        return child_env(self.secrets, home=self.profile.hermes_home, extra=self.extra_child_env)

    def _registry_env(self) -> dict[str, str]:
        """Tool discovery receives no dashboard, Slack or provider bearer.

        Keep the existing child-env validation for synthetic stub inputs, but
        pass only paths, locale and approved stub metadata to the census.
        """
        source = self._env()
        required = {"PATH", "HOME", "HERMES_HOME", "LANG"}
        result = {
            key: value for key, value in source.items()
            if key in required or key.startswith("HERMES_STUB_")
        }
        if self.profile.gateway_backend == "native-session-authority":
            from .native_gateway_entry import native_git_environment
            result.update(native_git_environment(Path(self._native_launch.recipe["vendor_root"])))
        return result

    def _model_child_env(self) -> dict[str, str]:
        """Forward only the reviewed primary credential to a pinned BYOK child.

        The receiving native config must be exact, owner-private, and have
        its Steward MCP disabled before any key is retrieved or forwarded.
        Legacy WP1 and plain disabled-MCP profiles receive no model key.
        """
        if self.profile.gateway_backend == "native-session-authority":
            if self._native_launch is None:
                raise RuntimeRefusal("NATIVE_STARTUP_CUSTODY_REQUIRED")
            try:
                self._native_launch.qualify(self.profile, self.hermes_bin)
            except RuntimeRefusal:
                raise
            except Exception:
                raise RuntimeRefusal("NATIVE_STARTUP_CUSTODY_UNQUALIFIED") from None
        from .secrets import role_conversation_token
        conversation_token = role_conversation_token(self.secrets, role=self.profile.role)
        if conversation_token is not None and self.profile.gateway_backend != "native-session-authority":
            raise RuntimeRefusal("SECRETARY_CONVERSATION_ROLE_UNQUALIFIED")
        if self.profile.gateway_backend == "native-session-authority":
            current_home = (self.profile.hermes_home / "profiles" / self.profile.role).resolve(strict=True)
            if self._native_home is None:
                self._native_home = current_home
            elif self._native_home != current_home:
                raise RuntimeRefusal("NATIVE_PROFILE_HOME_CHANGED")
        self._expected_disabled_mcp_native()
        native = self.profile.hermes_home / "profiles" / self.profile.role / "config.yaml"
        from integrations.hermes_harness.native_byok import expected_native_config
        env = self._env()
        if self.profile.gateway_backend == "native-session-authority":
            from .native_gateway_entry import native_git_environment
            env.update(native_git_environment(Path(self._native_launch.recipe["vendor_root"])))
        primary = self._native_launch.recipe.get("primary_application") if self._native_launch is not None else None
        if primary is not None:
            from integrations.hermes_application_fabric.publication import (
                expected_native_config as application_config, primary_child_env)
            from .secrets import child_secret_env_names
            from .constants import DEFAULT_CHILD_SECRET_ENV
            expected = application_config(self.profile, primary, self._consumer_publication()).encode("utf-8")
            if not native.is_file() or native.read_bytes() != expected:
                raise RuntimeRefusal("NATIVE_GATEWAY_CONFIG_MISMATCH")
            if self.secrets.dashboard_password == self.secrets.token:
                raise RuntimeRefusal("NATIVE_GATEWAY_PASSWORD_ALIAS_REFUSED")
            for name in child_secret_env_names() - DEFAULT_CHILD_SECRET_ENV:
                env.pop(name, None)
            env.update(primary_child_env(self.profile, primary, self.secrets))
            if self._consumer_publication() is not None:
                from .egress import native_egress_child_env
                env.update(native_egress_child_env(self.profile.role, self.secrets.values))
            assert_no_supervisor_notification_env(env)
            return env
        expected_config = None
        if native.is_file():
            expected_config = expected_native_config(
                self.profile, self._consumer_publication(), evaluation_inputs=(
                    self._native_launch.recipe.get("evaluation_inputs") if self._native_launch is not None else None))
        if expected_config is not None and native.read_bytes() == expected_config.encode("utf-8"):
            # load_secrets historically defaults dashboard Basic-Auth password
            # to the gateway token. The model child receives that password;
            # refusing this alias prevents disclosure under a *different*
            # environment name. The operator must provision two real,
            # independently revocable credentials, not rely on the fallback.
            if self.secrets.dashboard_password == self.secrets.token:
                raise RuntimeRefusal("NATIVE_GATEWAY_PASSWORD_ALIAS_REFUSED")
            from integrations.hermes_harness.native_model_credential import primary_model_env
            model_keys = primary_model_env(self.profile, self.secrets.values,
                                           self._consumer_publication())
            # Slack bot authority must not travel to the model-serving child
            # under a different credential name, including dashboard Basic Auth
            # (which the native Hermes child necessarily receives).
            protected_values = {self.secrets.token, self.secrets.dashboard_password}
            slack_bot_token = self.secrets.values.get("HERMES_SLACK_BOT_TOKEN", "")
            if slack_bot_token:
                if slack_bot_token in protected_values:
                    raise RuntimeRefusal("NATIVE_SLACK_BOT_AUTH_ALIAS_REFUSED")
                protected_values.add(slack_bot_token)
            if any(value in protected_values for value in model_keys.values()):
                raise RuntimeRefusal("NATIVE_MODEL_KEY_REUSE_REFUSED")
            env.update(model_keys)
            # The model child may reach external HTTPS only through an
            # operator-enrolled role-private localhost CONNECT proxy. A
            # missing or malformed proxy refuses startup before subprocess.
            # Never copy an ambient shell HTTPS_PROXY to the child.
            from .egress import native_egress_child_env
            env.update(native_egress_child_env(self.profile.role, self.secrets.values))
        assert_no_supervisor_notification_env(env)
        return env

    def _consumer_publication(self):
        """The optional qualified consumer input this runtime was installed with.

        It is absent by default. A malformed or absent member leaves the
        runtime disarmed; it never invents an extension.
        """
        launch = self._native_launch
        if launch is None:
            return None
        recipe = getattr(launch, "recipe", None)
        if not isinstance(recipe, dict):
            return None
        return recipe.get("executive_consumer")

    def _expected_disabled_mcp(self) -> dict[str, tuple[str, ...]] | None:
        primary = self._native_launch.recipe.get("primary_application") if self._native_launch is not None else None
        evaluation_inputs = self._native_launch.recipe.get("evaluation_inputs") if self._native_launch is not None else None
        if primary is not None:
            return expected_disabled_mcp(
                self.profile, self._consumer_publication(), primary,
                evaluation_inputs=evaluation_inputs)
        return expected_disabled_mcp(
            self.profile, self._consumer_publication(), evaluation_inputs=evaluation_inputs)

    def _check_registry(self) -> None:
        expected_disabled_mcp = self._expected_disabled_mcp_native()
        try:
            proc = subprocess.run(
                (self._native_launch.argv(self.profile, self.hermes_bin, tools=True)
                 if self.profile.gateway_backend == "native-session-authority"
                 else build_tools_argv(self.hermes_bin, self.profile.role)),
                capture_output=True,
                env=self._registry_env(),
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeRefusal("TOOLS_LIST_TIMEOUT") from None
        try:
            text = proc.stdout.decode("utf-8", errors="strict")
        except UnicodeError:
            raise RuntimeRefusal("TOOLS_LIST_NOT_UTF8") from None
        assert_registered_tools_exact(
            text,
            proc.stderr,
            self.profile.tool_allowlist,
            extension_tools_for(self.profile),
            expected_disabled_mcp=expected_disabled_mcp,
        )
        if proc.returncode != 0:
            raise RuntimeRefusal("TOOLS_LIST_FAILED")

    def _loop_guarded(self) -> None:
        """Convert unexpected inner-loop exceptions into observable failure.

        Otherwise a daemon thread can die silently while the foreground
        supervisor stays alive indefinitely and systemd sees no failure.
        """
        try:
            self._loop()
            return
        except RuntimeRefusal as exc:
            code = exc.code
        except Exception:
            # Never log exception text: third-party exceptions can contain
            # credential material or full environment values.
            code = "RUNTIME_SUPERVISOR_EXCEPTION"
        with self._lock:
            child = self._child
            self.refusal_code = code
            self.failed = True
        if child is not None:
            try:
                _terminate(child)
            except (OSError, subprocess.SubprocessError):
                pass
        with self._lock:
            self._child = None
            self.child_pid = None
            self._backend_ready = False

    def _publish_role_status_if_due(self, now: float) -> None:
        # One due-time check in the incumbent loop, independent of the profile's
        # 0.01–300 second memory cadence. No timer, thread or cached document.
        if self._role_status_publisher is None or now < self._next_role_status_publication:
            return
        self._next_role_status_publication = now + PUBLICATION_INTERVAL_SECONDS
        try:
            self._role_status_publisher.publish()
        except Exception:
            # Optional status failure must not enter the child-failure path.
            pass

    def _loop(self) -> None:
        assert self.memory is not None
        while not self._stop.is_set():
            if self.child_starts >= self.profile.start_limit_burst:
                self.failed = True
                return
            if self.child_starts > 0:
                try:
                    self._check_registry()
                except RuntimeRefusal as exc:
                    self.refusal_code = exc.code
                    self.failed = True
                    return
            self.child_starts += 1
            port = self.profile.backend_port or reserve_loopback_port(self.profile.gateway_host)
            try:
                argv = (self._native_launch.argv(self.profile, self.hermes_bin)
                        if self.profile.gateway_backend == "native-session-authority"
                        else build_serve_argv(self.hermes_bin, self.profile.role, port, self.profile.gateway_host))
            except RuntimeRefusal as exc:
                self.refusal_code = exc.code
                self.failed = True
                return
            try:
                model_child_env = self._model_child_env()
            except RuntimeRefusal as exc:
                self.refusal_code = exc.code
                self.failed = True
                return
            if self._stop.is_set():
                return
            proc = subprocess.Popen(
                argv,
                env=model_child_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            with self._lock:
                self._child = proc
                self.child_pid = proc.pid
                self._backend_ready = False
                self._extension_observed = None
                self._extension_proved = False
                self._context_observed = None
            next_memory_sample = 0.0
            poll_sec = min(0.25, self.profile.memory_sample_interval_sec)
            while not self._stop.is_set() and proc.poll() is None:
                if self.profile.gateway_backend == "native-session-authority":
                    try:
                        self._native_launch.observe_child(proc.pid)
                        from .native_gateway_entry import native_ready
                        backend_ready = native_ready(
                            vendor=Path(self._native_launch.recipe["vendor_root"]),
                            home=self._native_home,
                            host=self.profile.gateway_host, port=port, pid=proc.pid)
                    except Exception:
                        backend_ready = False
                else:
                    backend_ready = _backend_health_ready(port, self.profile.gateway_host)
                with self._lock:
                    if self._child is proc:
                        self._backend_ready = backend_ready
                now = time.monotonic()
                if now >= next_memory_sample:
                    rss = read_rss_kib(proc.pid)
                    if rss is not None:
                        self.memory.record(proc.pid, rss)
                    next_memory_sample = now + self.profile.memory_sample_interval_sec
                self._publish_role_status_if_due(now)
                self._stop.wait(poll_sec)
            if self._stop.is_set():
                _terminate(proc)
                with self._lock:
                    self._child = None
                    self.child_pid = None
                    self._backend_ready = False
                    self._extension_observed = None
                    self._extension_proved = False
                    self._context_observed = None
                return
            _reap(proc)
            with self._lock:
                self._child = None
                self.child_pid = None
                self._backend_ready = False
                self._extension_observed = None
                self._extension_proved = False
                self._context_observed = None
                self.restart_count += 1
            if self.child_starts >= self.profile.start_limit_burst:
                self.failed = True
                return
            if self._stop.wait(self.profile.restart_sec):
                return
    def _expected_disabled_mcp_native(self) -> dict[str, tuple[str, ...]] | None:
        primary = self._native_launch.recipe.get("primary_application") if self._native_launch is not None else None
        if primary is not None:
            return expected_disabled_mcp_with_application(self.profile, self._consumer_publication(), primary_application=primary)
        return self._expected_disabled_mcp()




def expected_disabled_mcp_with_application(profile: RuntimeProfile, consumer=None, primary_application=None,
                                              *, evaluation_inputs=None) -> dict[str, tuple[str, ...]] | None:
    """Require exact on-disk native config before trusting any CLI summary.

    A displayed MCP summary is not a connection or admission receipt.
    The only accepted additional config is the reviewed, *disabled*
    Steward source, plus - for a qualified optional consumer - the exact
    reviewed Executive entry whose tool filter is empty. No unknown or
    enabled MCP/server plugin is allowed.
    """

    if primary_application is None:
        return expected_disabled_mcp(profile, consumer, evaluation_inputs=evaluation_inputs)
    if evaluation_inputs is not None and profile.model_provider == "mastermind-fabric":
        raise RuntimeRefusal("NATIVE_EVAL_INPUTS_UNQUALIFIED")
    path = profile.hermes_home / "profiles" / profile.role / "config.yaml"
    if not path.exists() and not path.is_symlink():
        if evaluation_inputs is not None or (profile.state_dir / "install-manifest.json").exists():
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_MISSING")
        # Uninstalled stub-runtime tests use a temporary profile without
        # a native config. Real installs must carry that config.
        return None
    if path.is_symlink():
        raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_SYMLINK")
    try:
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid() or info.st_nlink != 1):
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_UNSAFE")
        if info.st_size > 64 * 1024:
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_TOO_LARGE")
        raw = path.read_bytes()
    except OSError:
        raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_UNAVAILABLE") from None
    if (evaluation_inputs is None and profile.native_provider_id is None
            and raw == render_hermes_config(profile).encode("utf-8")):
        return None
    # The built-in WP1 package remains independent for non-integrated
    # installs; this optional consumer is loaded only for the specific
    # reviewed disabled native config.
    from integrations.hermes_harness.native_mcp import render_disarmed_native_config
    from integrations.hermes_steward.client import ALLOWED_TOOLS

    if profile.extension_allowlist:
        raise RuntimeRefusal("NATIVE_EXTENSION_NOT_INSTALLED")
    from integrations.hermes_harness.native_byok import (
        expected_native_config,
        render_disarmed_native_byok,
    )
    if primary_application is not None:
        from integrations.hermes_application_fabric.publication import expected_native_config as application_config
        allowed_native = {application_config(profile, primary_application, consumer).encode("utf-8")}
    elif evaluation_inputs is not None:
        allowed_native = set()
    elif profile.model_provider == "mastermind-fabric":
        raise RuntimeRefusal("NATIVE_PRIMARY_APPLICATION_UNQUALIFIED")
    else:
        allowed_native = {render_disarmed_native_byok(profile).encode("utf-8")}
    # An explicit persisted selection cannot downgrade to a legacy or
    # model-less config. Only selector-free historical profiles retain
    # the earlier source-compatible config forms.
    if primary_application is None and evaluation_inputs is None and profile.native_provider_id is None:
        allowed_native.add(render_disarmed_native_config(profile).encode("utf-8"))
    expected_mcp: dict[str, tuple[str, ...]] = {"mastermind_steward": tuple(ALLOWED_TOOLS)}
    if consumer is not None:
        from integrations.hermes_harness.native_executive_consumer import (
            publication_from_document,
        )
        publication = publication_from_document(consumer)
        if primary_application is None:
            allowed_native.add(expected_native_config(
                profile, consumer, evaluation_inputs=evaluation_inputs).encode("utf-8"))
        # The upstream census renders an empty include list as "(none)". The
        # Executive entry registers no model-facing tool at all, so the
        # summary must show exactly that.
        expected_mcp[publication.mcp.server] = ("(none)",)
    if raw not in allowed_native:
        raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_DRIFT")
    return expected_mcp


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)



def _reap(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        return
    proc.wait(timeout=1)

