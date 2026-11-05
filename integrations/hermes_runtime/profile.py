"""Load the runtime profile. The profile names a secrets path; it never holds a secret."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from .constants import (
    ADMITTED_HERMES_TOOLSETS,
    LOOPBACK_HOST,
    PINNED_UPSTREAM_SHA,
    PROFILE_SCHEMA,
    QUALIFIED_MODEL_ROUTES,
    QUALIFIED_VISION_ROUTE,
    REFUSED_HERMES_TOOLSETS,
    UPSTREAM_REPOSITORY,
)
from .errors import RuntimeRefusal, refusal

_SHA = re.compile(r"^[0-9a-f]{40}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_TOP = frozenset({
    "schema", "upstream", "role", "tool_allowlist", "model",
    "secrets_file", "gateway", "service", "memory", "state_dir",
})
_SECRET_KEY = re.compile(
    r"(^|_)(api_key|access_token|refresh_token|client_secret|password|private_key|bearer|secret|token)($|_)",
    re.IGNORECASE,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RuntimeProfile:
    schema: str
    role: str
    sha: str
    repository: str
    tool_allowlist: frozenset[str]
    secrets_file: Path
    gateway_host: str
    gateway_port: int
    backend_port: int
    auth_required: bool
    state_dir: Path
    hermes_home: Path
    restart: str
    restart_sec: float
    start_limit_burst: int
    start_limit_interval_sec: int
    memory_sample_interval_sec: float
    model_provider: str
    model_default: str
    source_path: Path
    service_name: str
    native_provider_id: str | None = None

    @property
    def hermes_allowlist(self) -> frozenset[str]:
        return frozenset(name for name in self.tool_allowlist if name in ADMITTED_HERMES_TOOLSETS)

    @property
    def extension_allowlist(self) -> frozenset[str]:
        return self.tool_allowlist - self.hermes_allowlist


def load_profile(
    path: Path,
    *,
    state_dir: Path | None = None,
    secrets_file: Path | None = None,
    hermes_home: Path | None = None,
) -> RuntimeProfile:
    path = Path(path)
    if path.is_symlink():
        raise RuntimeRefusal("PROFILE_SYMLINK_REFUSED")
    data = path.read_bytes()
    if len(data) > 64 * 1024:
        raise RuntimeRefusal("PROFILE_TOO_LARGE")
    parsed = _load_unique_yaml(data)
    if not isinstance(parsed, dict):
        raise RuntimeRefusal("PROFILE_ROOT_NOT_MAPPING")
    if state_dir is not None:
        parsed["state_dir"] = str(state_dir)
    if secrets_file is not None:
        parsed["secrets_file"] = str(secrets_file)
    return _validate(parsed, source_path=path, hermes_home=hermes_home)


def dump_profile(profile: RuntimeProfile) -> str:
    allow = _ordered_allowlist(profile.tool_allowlist)
    lines = [
        f"schema: {profile.schema}",
        "upstream:",
        f"  repository: {profile.repository}",
        f"  sha: {profile.sha}",
        f"role: {profile.role}",
        "tool_allowlist:",
        *[f"  - {name}" for name in allow],
        "model:",
        f"  provider: {profile.model_provider}",
        f"  default: {profile.model_default}",
        *([f"  native_provider_id: {profile.native_provider_id}"]
          if profile.native_provider_id is not None else []),
        f"secrets_file: {profile.secrets_file}",
        "gateway:",
        f"  host: {profile.gateway_host}",
        f"  port: {profile.gateway_port}",
        f"  backend_port: {profile.backend_port}",
        "  auth: required",
        "service:",
        f"  restart: {profile.restart}",
        f"  restart_sec: {profile.restart_sec}",
        f"  start_limit_burst: {profile.start_limit_burst}",
        f"  start_limit_interval_sec: {profile.start_limit_interval_sec}",
        "memory:",
        f"  sample_interval_sec: {profile.memory_sample_interval_sec}",
        f"state_dir: {profile.state_dir}",
        "",
    ]
    return "\n".join(lines)


def profile_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_outside_repository(path: Path, *, label: str) -> None:
    resolved = path.expanduser().resolve()
    root = repo_root().resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return
    raise RuntimeRefusal(f"{label}_INSIDE_REPOSITORY")


def _ordered_allowlist(names: frozenset[str]) -> list[str]:
    rest = sorted(names - {"clarify"})
    if "clarify" in names:
        return ["clarify", *rest]
    return rest


def _validate(config: dict[str, Any], *, source_path: Path, hermes_home: Path | None) -> RuntimeProfile:
    issues: set[str] = set()
    if set(config) - _TOP:
        issues.add("UNQUALIFIED_PROFILE_KEY")
    if config.get("schema") != PROFILE_SCHEMA:
        issues.add("PROFILE_SCHEMA_MISMATCH")
    _reject_secret_fields(config, issues)

    upstream = config.get("upstream")
    sha = ""
    repository = ""
    if not isinstance(upstream, dict) or set(upstream) - {"repository", "sha"}:
        issues.add("UPSTREAM_PIN_REQUIRED")
    else:
        sha = upstream.get("sha")
        repository = upstream.get("repository")
        if not isinstance(sha, str) or not _SHA.fullmatch(sha) or sha != PINNED_UPSTREAM_SHA:
            issues.add("UNPINNED_SHA")
            sha = sha if isinstance(sha, str) else ""
        if repository != UPSTREAM_REPOSITORY:
            issues.add("UPSTREAM_REPOSITORY_UNPINNED")
            repository = repository if isinstance(repository, str) else ""

    role = config.get("role")
    route = QUALIFIED_MODEL_ROUTES.get(role) if isinstance(role, str) else None
    if route is None:
        issues.add("ROLE_UNQUALIFIED")
        role = ""
        route = {"provider": "", "default": ""}
    model = config.get("model")
    provider = ""
    default = ""
    native_id = None
    if not isinstance(model, dict) or set(model) - {"provider", "default", "native_provider_id"}:
        issues.add("UNQUALIFIED_MODEL_ROUTE")
    else:
        provider = model.get("provider")
        default = model.get("default")
        if provider != route["provider"] or default != route["default"]:
            issues.add("UNQUALIFIED_MODEL_ROUTE")
        if not isinstance(provider, str):
            provider = ""
        if not isinstance(default, str):
            default = ""
        if "native_provider_id" in model:
            native_id = model["native_provider_id"]
            from integrations.hermes_models.contract import native_provider
            try:
                if not isinstance(native_id, str):
                    raise ValueError("invalid native selector")
                native_provider(role, native_id)
            except (ValueError, KeyError):
                issues.add("UNQUALIFIED_NATIVE_MODEL_SELECTION")

    allow, allow_issues = _allowlist(config.get("tool_allowlist"))
    issues.update(allow_issues)

    secrets_file = _absolute_path(config.get("secrets_file"), issues, "SECRETS_PATH_INVALID")
    state_dir = _absolute_path(config.get("state_dir"), issues, "STATE_DIR_INVALID")
    if secrets_file is not None:
        try:
            assert_outside_repository(secrets_file, label="SECRETS_FILE")
        except RuntimeRefusal as exc:
            issues.add(exc.code)
    if state_dir is not None:
        try:
            assert_outside_repository(state_dir, label="STATE_DIR")
        except RuntimeRefusal as exc:
            issues.add(exc.code)
        _assert_dedicated(state_dir, issues)

    gateway = config.get("gateway")
    host = ""
    gateway_port = 0
    backend_port = 0
    if not isinstance(gateway, dict) or set(gateway) - {"host", "port", "backend_port", "auth"}:
        issues.add("GATEWAY_INVALID")
    else:
        host = gateway.get("host")
        if host != LOOPBACK_HOST:
            issues.add("NON_LOOPBACK_BIND_REFUSED")
            host = ""
        if gateway.get("auth") != "required":
            issues.add("AUTH_REQUIRED")
        gateway_port = _port(gateway.get("port"), issues, allow_zero=True)
        backend_port = _port(gateway.get("backend_port"), issues, allow_zero=True)

    service = config.get("service")
    restart = "on-failure"
    restart_sec = 2.0
    burst = 5
    interval = 60
    if not isinstance(service, dict) or set(service) - {
        "restart", "restart_sec", "start_limit_burst", "start_limit_interval_sec",
    }:
        issues.add("SERVICE_INVALID")
    else:
        if service.get("restart") != "on-failure":
            issues.add("RESTART_POLICY_UNQUALIFIED")
        restart_sec = _nonnegative_number(service.get("restart_sec"), issues, "RESTART_SEC_INVALID", upper=60)
        burst_value = service.get("start_limit_burst")
        if not isinstance(burst_value, int) or isinstance(burst_value, bool) or not 1 <= burst_value <= 10:
            issues.add("START_LIMIT_BURST_INVALID")
        else:
            burst = burst_value
        interval_value = service.get("start_limit_interval_sec")
        if (
            not isinstance(interval_value, int)
            or isinstance(interval_value, bool)
            or not 1 <= interval_value <= 3600
        ):
            issues.add("START_LIMIT_INTERVAL_INVALID")
        else:
            interval = interval_value

    memory = config.get("memory")
    sample = 5.0
    if not isinstance(memory, dict) or set(memory) - {"sample_interval_sec"}:
        issues.add("MEMORY_INVALID")
    else:
        sample = _nonnegative_number(
            memory.get("sample_interval_sec"), issues, "MEMORY_SAMPLE_INVALID", upper=300, lower=0.01,
        )

    if issues:
        raise refusal(issues)
    assert secrets_file is not None and state_dir is not None
    home = hermes_home.expanduser().resolve() if hermes_home is not None else (
        state_dir / "current" / "hermes-home"
    )
    return RuntimeProfile(
        schema=PROFILE_SCHEMA,
        role=role,
        sha=sha,
        repository=repository,
        tool_allowlist=allow,
        secrets_file=secrets_file,
        gateway_host=host,
        gateway_port=gateway_port,
        backend_port=backend_port,
        auth_required=True,
        state_dir=state_dir,
        hermes_home=home,
        restart=restart,
        restart_sec=restart_sec,
        start_limit_burst=burst,
        start_limit_interval_sec=interval,
        memory_sample_interval_sec=sample,
        model_provider=provider,
        model_default=default,
        source_path=source_path,
        service_name=f"hermes-runtime-{role}",
        native_provider_id=native_id,
    )


def _allowlist(value: Any) -> tuple[frozenset[str], set[str]]:
    issues: set[str] = set()
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        return frozenset(), {"ALLOWLIST_INVALID"}
    if len(value) != len(set(value)):
        issues.add("DUPLICATE_ALLOWLIST_ENTRY")
    names = set(value)
    if not names <= set(names):
        issues.add("ALLOWLIST_INVALID")
    if "clarify" not in names:
        issues.add("CLARIFY_REQUIRED")
    refused = names & REFUSED_HERMES_TOOLSETS
    if refused:
        issues.add("REFUSED_TOOLSET")
    unknown = {
        name for name in names
        if name not in ADMITTED_HERMES_TOOLSETS and not _TOOL.fullmatch(name)
    }
    if unknown:
        issues.add("INVALID_TOOL_NAME")
    hermes_extra = names & (REFUSED_HERMES_TOOLSETS | ADMITTED_HERMES_TOOLSETS) - ADMITTED_HERMES_TOOLSETS
    if hermes_extra:
        issues.add("REFUSED_TOOLSET")
    return frozenset(names), issues


def _reject_secret_fields(node: Any, issues: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and _SECRET_KEY.search(key) and value not in (None, ""):
                issues.add("INLINE_SECRET_FIELD")
            else:
                _reject_secret_fields(value, issues)
    elif isinstance(node, list):
        for value in node:
            _reject_secret_fields(value, issues)


def _absolute_path(value: Any, issues: set[str], code: str) -> Path | None:
    if not isinstance(value, str) or not value or any(ch in value for ch in "\n\r\t"):
        issues.add(code)
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        issues.add(code)
        return None
    return path


def _assert_dedicated(path: Path, issues: set[str]) -> None:
    resolved = path.expanduser().resolve() if path.exists() else path.expanduser()
    banned = {
        Path("/"), Path("/tmp"), Path("/var"), Path("/home"), Path("/etc"),
        Path.home(), Path.home() / ".config",
    }
    if resolved in banned or len(resolved.parts) < 3:
        issues.add("STATE_DIR_NOT_DEDICATED")


def _port(value: Any, issues: set[str], *, allow_zero: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        issues.add("GATEWAY_PORT_INVALID")
        return 0
    if value == 0 and allow_zero:
        return 0
    if 1024 <= value <= 65535:
        return value
    issues.add("GATEWAY_PORT_INVALID")
    return 0


def _nonnegative_number(
    value: Any, issues: set[str], code: str, *, upper: float, lower: float = 0,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        issues.add(code)
        return lower
    number = float(value)
    if number < lower or number > upper:
        issues.add(code)
        return lower
    return number


def _load_unique_yaml(data: bytes) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeRefusal("PYYAML_NOT_INSTALLED") from exc
    try:
        for token in yaml.scan(data):
            if isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken, yaml.tokens.TagToken)):
                raise RuntimeRefusal("YAML_ALIAS_ANCHOR_OR_TAG_NOT_ADMITTED")
    except yaml.YAMLError as exc:
        raise RuntimeRefusal("INVALID_YAML") from exc
    except RuntimeRefusal:
        raise

    class UniqueKeySafeLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):  # type: ignore[override]
            if not isinstance(node, yaml.MappingNode):
                raise yaml.constructor.ConstructorError(None, None, "expected mapping", node.start_mark)
            result = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str):
                    raise yaml.constructor.ConstructorError(None, None, "non-string mapping key", key_node.start_mark)
                if key in result:
                    raise yaml.constructor.ConstructorError(None, None, "duplicate mapping key", key_node.start_mark)
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        parsed = yaml.load(data, Loader=UniqueKeySafeLoader)
    except (yaml.YAMLError, RecursionError) as exc:
        raise RuntimeRefusal("INVALID_UNIQUE_SAFE_YAML") from exc
    return parsed
