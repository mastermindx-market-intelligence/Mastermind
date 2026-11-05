"""Bounded attended Claude Code launch preparation.

Contract ``fabric.attended.claude.bounded.v1`` compiles exactly one finite
foreground READ or READ+WRITE_BRANCH Claude Code launch into an immutable
descriptor.  This is launch *preparation* only: it never admits a worker,
starts or supervises a process, canaries capacity, loads credentials, writes
the filesystem, creates an authority seal, or overrides reviewed policy.  A
``SPEC_ONLY`` binding state is source-catalog bookkeeping, not runtime
approval, so the descriptor always carries ``preparation_only=True`` and
``start_authorized=False`` and names the proofs the caller must already hold
before any full launch (realm enrollment, capacity, isolation, attendance,
and the full launch attestation owned elsewhere).

Guarantees compiled into the descriptor:

* the task prompt travels as stdin text and never appears in argv;
* ``--settings`` is the closed canonical JSON of scoped permission rules from
  the existing ``_tool_policy`` compiler, the actual protected file-tool
  denies, a ``dontAsk`` default, a disabled bypass mode, and the existing
  fail-closed ``_subprocess_sandbox_request`` object, so settings and
  attestation cannot drift;
* project MCP is an empty server map, hooks are disabled, and slash commands,
  chrome, and session persistence are off;
* the executable is the attested ``binary.real_path`` and the model is the
  exact reviewed profile model for one declared class -- every environment
  model alias is pinned to that model with no fallback, no moving alias, and
  no inherited environment values;
* descriptor values are non-secret only; the owner inserts the current realm
  credential at the real process boundary, never here.

All path handling is lexical.  Directory creation, privacy, attestation of the
binary, workspace, run directory, home, and tmp remain caller obligations and
are never claimed by this module.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from control_plane.claude_worker import (
    _protected_file_tool_denies,
    _subprocess_sandbox_request,
    _tool_policy,
    _compile_tool_policy,
)
from control_plane.subscription_harness_bindings import SubscriptionHarnessBinding
from control_plane.subscription_provider_profiles import SubscriptionProviderProfile
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    WorkerLaunchSpec,
)

CONTRACT_NAME = "fabric.attended.claude.bounded.v1"
DESCRIPTOR_SCHEMA = "mastermind.fabric_attended_claude_launch/v1"
# The reviewed Claude Code binding identity: the "claude-code" harness speaking
# the reviewed Anthropic "anthropic" protocol.  Nothing else prepares here.
SUPPORTED_HARNESS_ID = "claude-code"
SUPPORTED_PROTOCOL = "anthropic"
SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
SYSTEM_PROMPT = (
    "You are a bounded Executive worker. Work only in the current Git workspace. "
    "Do not access parent directories, user homes, credentials, network tools, "
    "MCP, subagents, or shells. "
    "Make only changes authorized by the provided task and allowed write paths. "
    "Return only the structured result required by the supplied JSON schema."
)
# Closed, non-secret environment.  No inherited values, no credential keys:
# the owner adds the current realm credential at the process boundary only.
ENVIRONMENT_KEYS = (
    "HOME",
    "TMPDIR",
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "CLAUDE_CODE_MAX_RETRIES",
    "MAX_STRUCTURED_OUTPUT_RETRIES",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "DISABLE_AUTOUPDATER",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)
REQUIRED_USAGE_POLICY_KEYS = (
    "supported_harness_required",
    "interactive_only",
    "unattended_background_allowed",
    "production_backend_allowed",
)
REQUIRED_LAUNCH_PROOFS = (
    "provider_realm_enrolled",
    "capacity_known",
    "isolation_verified",
    "attendance_confirmed",
    "full_launch_attestation",
)
CALLER_OBLIGATIONS = (
    "binary_reattestation_at_spawn",
    "home_and_tmp_private_directory_creation",
    "workspace_and_run_filesystem_attestation",
    "realm_credential_insertion_at_boundary",
    "capacity_and_attendance_proof_before_start",
)
MAX_TURNS_LIMIT = 64
MAX_PROMPT_BYTES = 1 * 1024 * 1024
MAX_RESULT_SCHEMA_BYTES = 1 * 1024 * 1024
# Selectors that can change the served model or even the model family.  A
# reviewed exact model is required; selectors never prepare here.
MOVING_MODEL_ALIASES = frozenset(
    {"best", "default", "fable", "haiku", "opus", "opusplan", "sonnet"}
)
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
# Preserve the conservative grammar; admit only the canonical macOS install
# directory's literal space. The compiler transports this as one argv element
# with shell=False, never a quoted shell command or a broader path selector.
_SAFE_BINARY_PATH_RE = re.compile(
    r"^(?:[A-Za-z0-9/._+-]+|/Library/Application Support/MastermindExecutive/bin/claude-[0-9][A-Za-z0-9._+-]*)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_NAME_RE = re.compile(
    r"(?:^|_)(?:api[-_]?key|authorization|credential|secret|token)(?:$|_)",
    re.IGNORECASE,
)
_FILE_TOOLS = frozenset({"Edit", "Glob", "Grep", "Read", "Write"})
_MCP_CLOSED_CONFIG = '{"mcpServers":{}}'
_MAX_URL_CHARS = 512
_FORBIDDEN_ARGV_FLAGS = (
    "--dangerously-skip-permissions",
    "bypassPermissions",
)


class AttendedClaudePreparationError(ValueError):
    """The requested attended launch cannot be prepared as bounded."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AttendedClaudePreparationError(
            "value is not canonically serializable"
        ) from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _frozen(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _frozen(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _lexical_absolute(value: Any, label: str) -> PurePosixPath:
    if isinstance(value, Path):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise AttendedClaudePreparationError(f"{label} must be a path")
    if not text or "\\" in text or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise AttendedClaudePreparationError(f"{label} is not a safe lexical path")
    path = PurePosixPath(text)
    if not path.is_absolute():
        raise AttendedClaudePreparationError(f"{label} must be lexically absolute")
    if ".." in path.parts:
        raise AttendedClaudePreparationError(f"{label} must not contain '..'")
    return path


def _lexical_within(child: PurePosixPath, parent: PurePosixPath) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _exact_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AttendedClaudePreparationError(f"{label} must be a non-empty string")
    return value


def _capability_set(spec: WorkerLaunchSpec) -> frozenset[str]:
    """Extract and bound the capability set: READ, or READ + WRITE_BRANCH."""
    raw = list(spec.authorities)
    if spec.authority is not None:
        raw.append(spec.authority)
    if not raw:
        raise AttendedClaudePreparationError(
            "attended preparation requires an explicit capability grant"
        )
    if any(not isinstance(value, str) or not value.strip() for value in raw):
        raise AttendedClaudePreparationError("capabilities must be non-empty strings")
    requested = frozenset(value.strip().upper() for value in raw)
    if "READ" not in requested or requested - {"READ", "WRITE_BRANCH"}:
        raise AttendedClaudePreparationError(
            "attended preparation supports only READ or READ+WRITE_BRANCH; "
            "unsupported capabilities: " + ", ".join(sorted(requested - {"READ", "WRITE_BRANCH"}))
        )
    return requested


def _protected_deny_rules(tools: tuple[str, ...]) -> tuple[str, ...]:
    # Use the real compiler's exact rule representation. Never reinterpret
    # Read(pattern) as a raw path and wrap it in a second permission rule.
    rules = _protected_file_tool_denies(tools)
    if (not isinstance(rules, tuple) or not rules
            or any(not isinstance(rule, str) or not rule for rule in rules)):
        raise AttendedClaudePreparationError("protected file-tool denies are unavailable")
    return rules


def _reviewed_binary(binary: Any) -> str:
    if not isinstance(binary, BinaryAttestation):
        raise AttendedClaudePreparationError(
            "attended preparation requires a BinaryAttestation"
        )
    for label in ("path", "real_path"):
        value = getattr(binary, label)
        if (
            not isinstance(value, str)
            or not value
            or not PurePosixPath(value).is_absolute()
            or str(PurePosixPath(value)) != value or '..' in PurePosixPath(value).parts
            or _SAFE_BINARY_PATH_RE.fullmatch(value) is None
        ):
            raise AttendedClaudePreparationError(
                f"binary {label} must be an absolute, shell-free path"
            )
    if (
        not isinstance(binary.sha256, str)
        or _SHA256_RE.fullmatch(binary.sha256) is None
    ):
        raise AttendedClaudePreparationError("binary sha256 attestation is invalid")
    if not isinstance(binary.version, str) or not binary.version.strip():
        raise AttendedClaudePreparationError("binary version attestation is invalid")
    if type(binary.size) is not int or binary.size <= 0:
        raise AttendedClaudePreparationError("binary size attestation is invalid")
    return binary.real_path


def _reviewed_binding_and_profile(
    binding: Any, profile: Any
) -> tuple[str, str, str, str]:
    if not isinstance(binding, SubscriptionHarnessBinding):
        raise AttendedClaudePreparationError(
            "attended preparation requires a SubscriptionHarnessBinding"
        )
    if not isinstance(profile, SubscriptionProviderProfile):
        raise AttendedClaudePreparationError(
            "attended preparation requires a SubscriptionProviderProfile"
        )
    if binding.profile_id != profile.profile_id:
        raise AttendedClaudePreparationError(
            "binding profile_id does not match the reviewed profile"
        )
    if binding.provider != profile.provider:
        raise AttendedClaudePreparationError(
            "binding provider does not match the reviewed profile"
        )
    if binding.harness_id != SUPPORTED_HARNESS_ID:
        raise AttendedClaudePreparationError(
            "binding harness is not the reviewed claude-code harness"
        )
    if binding.protocol != SUPPORTED_PROTOCOL or profile.protocol != SUPPORTED_PROTOCOL:
        raise AttendedClaudePreparationError(
            "binding and profile must agree on the reviewed anthropic protocol"
        )
    if binding.adapter_id != "claude-compatible-subscription":
        raise AttendedClaudePreparationError("binding adapter identity is unsupported")
    if type(binding.autonomous_allowed) is not bool:
        raise AttendedClaudePreparationError("binding autonomy flag must be a bool")
    if type(profile.autonomous_allowed) is not bool:
        raise AttendedClaudePreparationError("profile autonomy flag must be a bool")
    endpoint = binding.effective_base_url
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > _MAX_URL_CHARS:
        raise AttendedClaudePreparationError("binding endpoint is invalid")
    # Exact endpoint match: an attended preparation never relocates the
    # reviewed profile endpoint; reviewed overrides belong to binding review.
    if endpoint.rstrip("/") != str(profile.base_url).rstrip("/"):
        raise AttendedClaudePreparationError(
            "binding endpoint drifts from the reviewed profile endpoint"
        )
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise AttendedClaudePreparationError(
            "binding endpoint must be a plain HTTPS origin"
        )
    usage = profile.usage_policy
    if not isinstance(usage, Mapping) or not all(
        type(item) is bool for item in usage.values()
    ):
        raise AttendedClaudePreparationError(
            "profile usage policy must be a mapping of booleans"
        )
    missing = [key for key in REQUIRED_USAGE_POLICY_KEYS if key not in usage]
    if missing:
        raise AttendedClaudePreparationError(
            "profile usage policy is missing reviewed flags: " + ", ".join(missing)
        )
    return (
        endpoint.rstrip("/"),
        binding.adapter_id,
        dict(usage),
        bool(binding.autonomous_allowed),
    )


def _reviewed_model(
    binding: SubscriptionHarnessBinding,
    profile: SubscriptionProviderProfile,
    model_class: str,
) -> str:
    if not isinstance(model_class, str) or not model_class or model_class != model_class.strip():
        raise AttendedClaudePreparationError("model class must be a non-empty string")
    if model_class not in binding.model_classes:
        raise AttendedClaudePreparationError(
            "binding does not declare the requested model class"
        )
    try:
        selected = profile.model_for(model_class)
        bound = binding.model_for(profile, model_class)
    except (TypeError, ValueError) as exc:
        raise AttendedClaudePreparationError(
            "reviewed model resolution failed"
        ) from exc
    if bound != selected:
        raise AttendedClaudePreparationError(
            "binding and profile models drift for the requested class"
        )
    if (
        not isinstance(selected, str)
        or _MODEL_RE.fullmatch(selected) is None
        or selected.lower() in MOVING_MODEL_ALIASES
    ):
        raise AttendedClaudePreparationError(
            "reviewed model must be an exact non-selector model identifier"
        )
    return selected


def _reviewed_prompt(prompt: Any) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise AttendedClaudePreparationError("prompt is missing")
    try:
        payload = prompt.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AttendedClaudePreparationError(
            "prompt must be strict UTF-8"
        ) from exc
    if len(payload) > MAX_PROMPT_BYTES:
        raise AttendedClaudePreparationError("prompt exceeds one MiB")
    return prompt


def _reviewed_result_schema(result_schema: Any) -> str:
    if type(result_schema) is not bool and not isinstance(result_schema, Mapping):
        raise AttendedClaudePreparationError(
            "result schema must be a mapping or boolean"
        )
    encoded = _canonical_json(result_schema).encode("utf-8")
    if len(encoded) > MAX_RESULT_SCHEMA_BYTES:
        raise AttendedClaudePreparationError("result schema exceeds one MiB")
    return encoded.decode("utf-8")


def attended_profile_digest(profile: SubscriptionProviderProfile) -> str:
    """Digest the full non-secret reviewed profile for launch correlation."""
    if not isinstance(profile, SubscriptionProviderProfile):
        raise AttendedClaudePreparationError(
            "attended preparation requires a SubscriptionProviderProfile"
        )
    return _canonical_sha256(_plain(profile))


def _closed_settings(
    tools: tuple[str, ...],
    preapproved: tuple[str, ...],
    forbidden: tuple[str, ...],
) -> dict[str, Any]:
    allow = tuple(sorted(set(preapproved)))
    if not allow or any("(" not in rule for rule in allow):
        raise AttendedClaudePreparationError(
            "allowed permission rules must be scoped, never broad tool approval"
        )
    deny = tuple(sorted(set((*_protected_deny_rules(tools), *forbidden,
                             "SendMessage", "ListAgents"))))
    return {
        "permissions": {
            "allow": allow,
            "deny": deny,
            "defaultMode": "dontAsk",
            "disableBypassPermissionsMode": True,
        },
        "sandbox": _subprocess_sandbox_request(),
        "disableAllHooks": True,
        "enableAllProjectMcpServers": False,
        # One finite assignment returns through its existing parent; native
        # peer traffic must not inject unrelated work into this process.
        "crossSessionInbound": "refuse",
    }


def finite_read_permission_digest() -> str:
    """Expected finite READ settings; no fabricated spec, grant or admission."""
    return _canonical_sha256(_closed_settings(*_compile_tool_policy(frozenset({"READ"}))))


def compiled_permission_digest(descriptor) -> str:
    """Bind the permission receipt to the actual --settings launch operand."""
    argv = descriptor.argv
    try:
        if argv.count("--settings") != 1:
            raise ValueError("exact settings operand required")
        encoded = argv[argv.index("--settings") + 1]
        document = json.loads(encoded)
        if type(document) is not dict or encoded != _canonical_json(document):
            raise ValueError("canonical settings required")
        digest = _canonical_sha256(document)
        if digest != descriptor.settings_sha256:
            raise ValueError("compiled settings changed")
        return digest
    except (ValueError, TypeError, IndexError, AttributeError) as exc:
        raise AttendedClaudePreparationError("compiled permission settings changed") from exc


@dataclasses.dataclass(frozen=True)
class AttendedClaudeLaunchPreparation:
    """Immutable, secret-free compilation of one attended launch.

    Not an admission: ``preparation_only`` is pinned True and
    ``start_authorized`` is pinned False at construction.
    """

    schema: str
    contract_name: str
    run_id: str
    job_id: str
    worker_id: str
    capabilities: tuple[str, ...]
    model_class: str
    model: str
    endpoint: str
    binding_id: str
    adapter_id: str
    harness_id: str
    protocol: str
    implementation_state: str
    binary: BinaryAttestation
    argv: tuple[str, ...]
    stdin_text: str
    settings: Mapping[str, Any]
    settings_json: str
    settings_sha256: str
    environment: Mapping[str, str]
    max_turns: int
    profile_id: str
    profile_digest: str
    profile_usage_policy: Mapping[str, bool]
    binding_autonomous_allowed: bool
    result_schema_path: str
    result_schema_json: str
    workspace_path: str
    run_dir: str
    provider_home: str
    provider_tmp: str
    preparation_only: bool
    start_authorized: bool
    required_launch_proofs: tuple[str, ...]
    caller_obligations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "required_launch_proofs", tuple(self.required_launch_proofs))
        object.__setattr__(self, "caller_obligations", tuple(self.caller_obligations))
        object.__setattr__(self, "settings", _frozen(self.settings))
        object.__setattr__(self, "environment", _frozen(self.environment))
        object.__setattr__(self, "profile_usage_policy", _frozen(self.profile_usage_policy))
        if self.schema != DESCRIPTOR_SCHEMA or self.contract_name != CONTRACT_NAME:
            raise AttendedClaudePreparationError("descriptor identity is invalid")
        if self.preparation_only is not True or self.start_authorized is not False:
            raise AttendedClaudePreparationError(
                "an attended preparation is never an admission or start authority"
            )
        if type(self.max_turns) is not int or not 1 <= self.max_turns <= MAX_TURNS_LIMIT:
            raise AttendedClaudePreparationError("descriptor turn bound is invalid")
        if set(self.environment) != set(ENVIRONMENT_KEYS):
            raise AttendedClaudePreparationError(
                "descriptor environment is not the closed non-secret set"
            )
        if any(
            _SECRET_NAME_RE.search(key) for key in self.environment
        ):
            raise AttendedClaudePreparationError(
                "descriptor environment must never carry a credential key"
            )
        if self.model.lower() in MOVING_MODEL_ALIASES:
            raise AttendedClaudePreparationError(
                "descriptor model must be an exact reviewed model"
            )
        if (
            not self.argv
            or not isinstance(self.argv[0], str)
            or not PurePosixPath(self.argv[0]).is_absolute()
        ):
            raise AttendedClaudePreparationError("descriptor argv head is invalid")
        if "--settings" not in self.argv or "--json-schema" not in self.argv:
            raise AttendedClaudePreparationError(
                "descriptor argv must carry the closed settings and result schema"
            )
        if any(
            self.stdin_text and self.stdin_text == item for item in self.argv
        ):
            raise AttendedClaudePreparationError(
                "the task prompt must never travel as an argv operand"
            )
        if _plain(self.settings.get("sandbox", {})) != _subprocess_sandbox_request():
            raise AttendedClaudePreparationError(
                "descriptor sandbox request has drifted from the reviewed policy"
            )
        permissions = self.settings.get("permissions")
        if not isinstance(permissions, Mapping):
            raise AttendedClaudePreparationError("descriptor permissions are invalid")
        if permissions.get("defaultMode") != "dontAsk":
            raise AttendedClaudePreparationError("descriptor must default to dontAsk")
        if permissions.get("disableBypassPermissionsMode") is not True:
            raise AttendedClaudePreparationError("descriptor must disable the bypass")
        if self.settings.get("crossSessionInbound") != "refuse":
            raise AttendedClaudePreparationError("descriptor must refuse native peer messages")
        native_denies = permissions.get("deny")
        if (not isinstance(native_denies, (list, tuple))
                or not {"SendMessage", "ListAgents"}.issubset(native_denies)):
            raise AttendedClaudePreparationError("descriptor must deny native peer tools")
        if self.settings.get("disableAllHooks") is not True:
            raise AttendedClaudePreparationError("descriptor must disable hooks")
        if self.settings.get("enableAllProjectMcpServers") is not False:
            raise AttendedClaudePreparationError(
                "descriptor must leave project MCP servers disabled"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            field.name: _plain(getattr(self, field.name))
            for field in dataclasses.fields(self)
        }


def prepare_attended_claude_launch(
    spec: WorkerLaunchSpec,
    *,
    binary: BinaryAttestation,
    binding: SubscriptionHarnessBinding,
    profile: SubscriptionProviderProfile,
    model_class: str,
    max_turns: int,
    result_schema: Mapping[str, Any] | bool,
) -> AttendedClaudeLaunchPreparation:
    """Compile one bounded attended Claude Code launch descriptor.

    Pure, side-effect-free preparation: no subprocess, provider request,
    credential load, filesystem access, or seal creation.  The returned
    descriptor is not an admission and authorizes no start.
    """
    if not isinstance(spec, WorkerLaunchSpec):
        raise AttendedClaudePreparationError(
            "attended preparation requires a WorkerLaunchSpec"
        )
    run_id = _exact_str(spec.run_id, "run_id")
    job_id = _exact_str(spec.job_id, "job_id")
    worker_id = _exact_str(spec.worker_id, "worker_id")
    prompt = _reviewed_prompt(spec.prompt)
    capabilities = _capability_set(spec)
    if "WRITE_BRANCH" in capabilities and not spec.allowed_artifact_paths:
        raise AttendedClaudePreparationError(
            "WRITE_BRANCH requires declared allowed write paths"
        )
    try:
        tools, preapproved, forbidden = _tool_policy(spec)
    except AttendedClaudePreparationError:
        raise
    except Exception as exc:  # the existing compiler owns its error type
        raise AttendedClaudePreparationError(
            f"claude tool policy rejected the launch: {exc}"
        ) from exc
    executable = _reviewed_binary(binary)
    endpoint, adapter_id, usage_policy, binding_autonomous = (
        _reviewed_binding_and_profile(binding, profile)
    )
    selected_model = _reviewed_model(binding, profile, model_class)
    if spec.model != selected_model:
        raise AttendedClaudePreparationError("model differs from the exact Runtime launch spec")
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_TURNS_LIMIT:
        raise AttendedClaudePreparationError(
            "max_turns must be a canonical int within 1..64"
        )
    schema_json = _reviewed_result_schema(result_schema)

    workspace = _lexical_absolute(spec.workspace_path, "workspace_path")
    run_dir = _lexical_absolute(spec.run_dir, "run_dir")
    schema_path = _lexical_absolute(spec.result_schema_path, "result_schema_path")
    if _lexical_within(run_dir, workspace) or _lexical_within(workspace, run_dir):
        raise AttendedClaudePreparationError(
            "workspace and run_dir must be lexically disjoint"
        )
    if not _lexical_within(schema_path, run_dir / "input"):
        raise AttendedClaudePreparationError(
            "result schema path must stay inside the run input directory"
        )
    home = run_dir / "home"
    tmp = run_dir / "tmp"

    settings = _closed_settings(tools, preapproved, forbidden)
    tools_enabled = set(tools)
    protected_rules = _protected_deny_rules(tools)
    for tool in sorted(tools_enabled & _FILE_TOOLS):
        if not any(rule.startswith(f"{tool}(") for rule in protected_rules):
            raise AttendedClaudePreparationError(
                f"enabled file tool {tool} lacks its protected path denies"
            )
    settings_json = _canonical_json(settings)
    # Deny rules may name tools like Task/Skill but must never name secrets.
    if any(
        _SECRET_NAME_RE.search(rule.split("(", 1)[0])
        for rule in settings["permissions"]["deny"]
    ):
        raise AttendedClaudePreparationError("settings carry a secret-like rule")

    environment = {
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "PATH": SAFE_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "CLAUDE_CODE_MAX_RETRIES": "0",
        "MAX_STRUCTURED_OUTPUT_RETRIES": "0",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
        "ANTHROPIC_BASE_URL": endpoint,
        "ANTHROPIC_MODEL": selected_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": selected_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": selected_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": selected_model,
        "CLAUDE_CODE_SUBAGENT_MODEL": selected_model,
    }
    if set(environment) != set(ENVIRONMENT_KEYS):
        raise AttendedClaudePreparationError(
            "environment compilation drifted from the closed key set"
        )

    argv = (
        executable,
        "--safe-mode",
        "-p",
        "--output-format", "json",
        "--model", selected_model,
        "--max-turns", str(max_turns),
        "--permission-mode", "dontAsk",
        "--tools", *tools,
        "--allowedTools", *preapproved,
        "--disallowedTools", *forbidden,
        "--strict-mcp-config",
        "--mcp-config", _MCP_CLOSED_CONFIG,
        "--settings", settings_json,
        "--json-schema", schema_json,
        "--system-prompt", SYSTEM_PROMPT,
        "--disable-slash-commands",
        "--no-chrome",
        "--no-session-persistence",
    )
    for flag in _FORBIDDEN_ARGV_FLAGS:
        if flag in argv:
            raise AttendedClaudePreparationError(
                "argv must never request a permission bypass"
            )
    if prompt and prompt in argv:
        raise AttendedClaudePreparationError(
            "the task prompt must never travel as an argv operand"
        )

    return AttendedClaudeLaunchPreparation(
        schema=DESCRIPTOR_SCHEMA,
        contract_name=CONTRACT_NAME,
        run_id=run_id,
        job_id=job_id,
        worker_id=worker_id,
        capabilities=tuple(sorted(capabilities)),
        model_class=model_class,
        model=selected_model,
        endpoint=endpoint,
        binding_id=binding.binding_id,
        adapter_id=adapter_id,
        harness_id=binding.harness_id,
        protocol=binding.protocol,
        implementation_state=binding.implementation_state,
        binary=binary,
        argv=argv,
        stdin_text=prompt,
        settings=settings,
        settings_json=settings_json,
        settings_sha256=_canonical_sha256(settings),
        environment=environment,
        max_turns=max_turns,
        profile_id=profile.profile_id,
        profile_digest=attended_profile_digest(profile),
        profile_usage_policy=usage_policy,
        binding_autonomous_allowed=binding_autonomous,
        result_schema_path=str(schema_path),
        result_schema_json=schema_json,
        workspace_path=str(workspace),
        run_dir=str(run_dir),
        provider_home=str(home),
        provider_tmp=str(tmp),
        preparation_only=True,
        start_authorized=False,
        required_launch_proofs=REQUIRED_LAUNCH_PROOFS,
        caller_obligations=CALLER_OBLIGATIONS,
    )


__all__ = [
    "CALLER_OBLIGATIONS",
    "CONTRACT_NAME",
    "DESCRIPTOR_SCHEMA",
    "ENVIRONMENT_KEYS",
    "MAX_PROMPT_BYTES",
    "MAX_RESULT_SCHEMA_BYTES",
    "MAX_TURNS_LIMIT",
    "REQUIRED_LAUNCH_PROOFS",
    "SUPPORTED_HARNESS_ID",
    "SUPPORTED_PROTOCOL",
    "AttendedClaudeLaunchPreparation",
    "AttendedClaudePreparationError",
    "attended_profile_digest",
    "prepare_attended_claude_launch",
]
