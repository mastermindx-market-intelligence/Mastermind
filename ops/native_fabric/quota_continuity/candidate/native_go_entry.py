"""Verified in-process ingress for the existing Go service and broker.

The release launcher supplies its already verified immutable descriptor. This
module does not select a generation, enroll a service, mint a key, or own a
server. Import and inspect are read-only. Only main enters the original B.main.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys


GLM_HELPER_SHA256 = "020b9ef9c59260d07980a23f2ac277d4e4d7350ff81e010d071fd733cc05b1fc"
MODULES = (
    "native_runtime_bindings", "commission_deadline", "provider_outcome",
    "quota_remote", "glm_keys", "quota_circuit", "model_tier", "pool_status",
    "go_lease_capability", "lease_broker", "go_lease_gateway", "paid_yaml_runtime", "go_application_handler",
    "fabric_policy_snapshot", "pool_ledger", "pick",
)
HTTP_MEMBERS = frozenset({"ext/application_http_transports.py",
    "ext/application_http_realm_projection.py", "ext/application_http_realms.v1.json"})
HTTP_MODULES = ("application_http_realm_projection", "application_http_transports", "bailian_keys")
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_LOADED_MODULES = {}


def _regular(path, *, mode=None, expected=None):
    """Check the exact named file; never resolve a state-internal symlink."""
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_nlink != 1 or before.st_mode & 0o022
                or mode is not None and stat.S_IMODE(before.st_mode) != mode
                or not 0 <= before.st_size <= 16 * 1024 * 1024):
            raise ValueError("native Go source custody refused")
        with os.fdopen(os.dup(fd), "rb") as handle:
            raw = handle.read(16 * 1024 * 1024 + 1)
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                    value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if (len(raw) != before.st_size or identity(os.fstat(fd)) != identity(before)
                or identity(path.lstat()) != identity(before)
                or expected is not None and hashlib.sha256(raw).hexdigest() != expected):
            raise ValueError("native Go source identity refused")
        return raw
    finally:
        os.close(fd)


def _directory(path):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o022 or path.resolve(strict=True) != path):
        raise ValueError("native Go original owner custody refused")


def _existing_database(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        named = Path(path).lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o022
                or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
            raise ValueError("native Go original database custody refused")
        return info.st_dev, info.st_ino
    finally:
        os.close(fd)


def _module_identity(name, path, expected):
    loaded = sys.modules.get(name)
    if loaded is not None:
        if (getattr(loaded, "__file__", None) != str(path)
                or loaded is not _LOADED_MODULES.get(name)
                and not (name == "native_go_entry" and loaded is sys.modules.get(__name__))):
            raise ValueError("native Go module conflict: " + name)
        _regular(path, expected=expected)
    return loaded


def _load(name, path, raw, expected):
    loaded = _module_identity(name, path, expected)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("native Go module unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        # Execute the bytes just checked; __file__ remains the real filename.
        exec(compile(raw, str(path), "exec"), module.__dict__)
        _LOADED_MODULES[name] = module
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


@dataclass(frozen=True)
class Startup:
    handler: object
    broker_module: object
    paths: dict
    generation: str
    yaml_runtime: object
    yaml_archive: bytes
    yaml_provenance: bytes
    yaml_check: object
    policy_snapshot: object
    http_projection: bytes | None = None
    http_recipes: tuple = ()
    http_transports: object = None
    bailian_keys: object = None
    http_projection_sha256: str | None = None
    handler_sha256: str | None = None
    glm_adapter: object = None
    glm_keys: object = None
    glm_projection: bytes | None = None
    glm_projection_sha256: str | None = None


GLM_HTTP_MEMBERS = frozenset({"ext/glm_application_adapter.py", "ext/application_http_realms.v2.json"})


def inspect(*, verified_root, verified_metadata):
    """Validate/import exact code and owner paths without business effects."""
    root = Path(verified_root)
    here = Path(__file__).absolute().parent
    meta = verified_metadata
    if (root != here.parent or root.resolve(strict=True) != root
            or root.parent.name != "native-code-releases"
            or type(meta) is not dict or meta.get("digest") != root.name
            or meta.get("entrypoints", {}).get("go") != "ext/native_go_entry.py"):
        raise ValueError("native Go verified entry context refused")
    files = meta["files"]
    http_present = HTTP_MEMBERS & set(files)
    glm_present = set(files) & GLM_HTTP_MEMBERS
    if glm_present and (glm_present != GLM_HTTP_MEMBERS or not HTTP_MEMBERS.issubset(files) or "ext/glm_keys.py" not in files):
        raise ValueError("native GLM application HTTP closure incomplete")
    if http_present and http_present != HTTP_MEMBERS:
        raise ValueError("native application HTTP closure incomplete")
    modules = (MODULES + HTTP_MODULES if http_present else MODULES) + (("glm_application_adapter",) if glm_present else ())
    _regular(here / "native_go_entry.py", mode=0o555,
             expected=files["ext/native_go_entry.py"])
    sources = {}
    # Guard the complete declared native Python namespace, including lazy
    # broker/status imports, before importing any business module. A foreign
    # preloaded module cannot win merely because its import happens later.
    for relative, expected in files.items():
        if relative.startswith("ext/") and relative.endswith(".py"):
            name = Path(relative).stem
            _module_identity(name, root / relative, expected)
    for name in modules:
        path = here / (name + ".py")
        expected = files.get("ext/" + name + ".py")
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError("native Go dependency missing")
        sources[name] = (path, _regular(path, mode=0o555, expected=expected), expected)
        _module_identity(name, path, expected)
    binding = _load("native_runtime_bindings", *sources["native_runtime_bindings"])
    owner = lambda relative: binding.owner_path(here / relative, here)
    paths = {
        "go": owner("go_shim"), "state": owner("state"),
        "helper": owner("glm_shim") / "glm_shim.py",
        "db_path": owner("broker/leases.sqlite"), "lock_path": owner("broker/leases.lock"),
        "accounts_path": binding.owner_path(root / "orch/fabric/accounts.yaml", here),
        "policy_path": binding.owner_path(root / "orch/fabric/pools.yaml", here),
        "ledger_path": binding.owner_path(root / "orch/fabric/ledger.jsonl", here),
        "status_json": binding.owner_path(root / "orch/fabric/status.json", here),
        "hosts_path": owner("hosts.json"), "grok_marker": owner("GROK_EXHAUSTED"),
    }
    _directory(paths["go"])
    _directory(paths["helper"].parent)
    helper_raw = _regular(paths["helper"], expected=GLM_HELPER_SHA256)
    _module_identity("glm_shim", paths["helper"], GLM_HELPER_SHA256)
    _load("glm_shim", paths["helper"], helper_raw, GLM_HELPER_SHA256)
    # The authentic historical helper adds the flat ext directory. Put the
    # verified generation first again before any incumbent lazy import.
    sys.path[:] = [str(here)] + [p for p in sys.path if p != str(here)]
    for name in modules[1:]:
        _load(name, *sources[name])
    sys.path[:] = [str(here)] + [p for p in sys.path if p != str(here)]
    handler, broker = sys.modules["go_application_handler"], sys.modules["lease_broker"]
    if (Path(handler.HERE) != paths["go"] or Path(handler._EXT_DIR) != here
            or Path(handler._STATE_OWNER) != paths["state"]
            or Path(handler._BROKER_DB) != paths["db_path"]
            or Path(handler._HELPER_OWNER) != paths["helper"].parent):
        raise ValueError("native Go handler owner mapping differs")
    yaml_paths = (here / "paid_pyyaml_6_0_3.zip", here / "paid_pyyaml_provenance.json")
    yaml_bytes = tuple(_regular(path, mode=0o555,
        expected=files["ext/" + path.name]) for path in yaml_paths)
    def identity(path):
        value = path.lstat()
        return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    yaml_sources = (*yaml_paths, here / "paid_yaml_runtime.py")
    identities = tuple(identity(path) for path in yaml_sources)
    yaml_runtime = sys.modules["paid_yaml_runtime"]
    def yaml_check():
        binding.owner_path(here / "broker", here)
        if (sys.modules.get("paid_yaml_runtime") is not yaml_runtime
                or tuple(identity(path) for path in yaml_sources) != identities):
            raise ValueError("native Go held YAML owner changed")
    http_projection, http_digest, http_transports, bailian_keys, recipes = None, None, None, None, ()
    if http_present:
        http_digest = files["ext/application_http_realms.v1.json"]
        http_projection = _regular(here / "application_http_realms.v1.json", mode=0o555,
                                   expected=http_digest)
        sys.modules["application_http_realm_projection"].validate_projection(
            http_projection, expected_sha256=http_digest)
        http_transports, bailian_keys = sys.modules["application_http_transports"], sys.modules["bailian_keys"]
        # Construction is pure. Check BOTH fixed drivers against the sealed
        # metadata without importing control_plane or reading any credential.
        drivers = [kind(transport=handler.application_http_transport,
                        realm_projection=http_projection, projection_sha256=http_digest)
                   for kind in (http_transports.BailianResponsesDriver, http_transports.MiniMaxResponsesDriver)]
        driver_identity = drivers[0].identity
        rows = []
        for model in sorted(driver_identity.allowed_models):
            recipe = {"schema": "mastermind.application_http_recipe.v1", "pool": driver_identity.pool,
                "model": model, "driver_id": driver_identity.driver_id, "realm_id": driver_identity.realm_id,
                "provider": driver_identity.provider, "protocol": driver_identity.protocol, "endpoint": driver_identity.endpoint,
                "source_projection_sha256": http_digest, "credential_owner": "bailian_keys._codex_key_value"}
            encoded, _ = broker._application_http_recipe(recipe, pool="bailian", model=model)
            rows.append(encoded)
        recipes = tuple(rows)
    glm_adapter, glm_keys, glm_projection, glm_digest = None, None, None, None
    if glm_present:
        glm_digest = files["ext/application_http_realms.v2.json"]
        glm_projection = _regular(here / "application_http_realms.v2.json", mode=0o555, expected=glm_digest)
        reader = sys.modules["application_http_realm_projection"]
        reader.validate_projection(glm_projection, expected_sha256=glm_digest)
        if json.loads(glm_projection)["legacy_projection"] != json.loads(http_projection):
            raise ValueError("GLM application legacy projection differs")
        glm_adapter, glm_keys = sys.modules["glm_application_adapter"], sys.modules["glm_keys"]
        driver = glm_adapter.GlmChatCompletionsDriver(
            transport=handler.application_http_transport,
            realm_projection=glm_projection, projection_sha256=glm_digest)
        glm_driver_identity = driver.identity
        rows = list(recipes)
        for model in sorted(glm_driver_identity.allowed_models):
            recipe = {"schema": "mastermind.application_http_recipe.v1",
                      "pool": "glm", "model": model, "driver_id": glm_driver_identity.driver_id,
                      "realm_id": glm_driver_identity.realm_id, "provider": glm_driver_identity.provider,
                      "protocol": glm_driver_identity.protocol, "endpoint": glm_driver_identity.endpoint,
                      "source_projection_sha256": glm_digest,
                      "credential_owner": "glm_keys.selected_account_key"}
            encoded, _ = broker._application_http_recipe(recipe, pool="glm", model=model)
            rows.append(encoded)
        recipes = tuple(rows)
    return Startup(handler, broker, paths, root.name, yaml_runtime,
                   yaml_bytes[0], yaml_bytes[1], yaml_check, sys.modules["fabric_policy_snapshot"],
                   http_projection, recipes, http_transports, bailian_keys, http_digest,
                   files["ext/go_application_handler.py"], glm_adapter=glm_adapter, glm_keys=glm_keys, glm_projection=glm_projection, glm_projection_sha256=glm_digest)


SERVICE_SCHEMA = "mastermind.native_go_application_service.v1"
SERVICE_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v1"
SERVICE_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v1"
SERVICE_HTTP_SCHEMA = "mastermind.native_go_application_service.v2"
SERVICE_HTTP_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v2"
SERVICE_HTTP_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v2"
SERVICE_SELECTED_SCHEMA = "mastermind.native_go_application_service.v3"
SERVICE_SELECTED_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v3"
SERVICE_SELECTED_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v3"
SERVICE_ADMIN_SCHEMA = "mastermind.native_go_application_service.v4"
SERVICE_ADMIN_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v4"
SERVICE_ADMIN_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v4"
SERVICE_SET_SCHEMA = "mastermind.native_go_application_service.v5"
SERVICE_SET_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v5"
SERVICE_SET_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v5"
SERVICE_FAMILY_SCHEMA = "mastermind.native_go_application_service.v6"
SERVICE_FAMILY_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v6"
SERVICE_FAMILY_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v6"
SERVICE_ROUTED_SCHEMA = "mastermind.native_go_application_service.v7"
SERVICE_ROUTED_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v7"
SERVICE_ROUTED_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v7"
SERVICE_WORKLOAD_SCHEMA = "mastermind.native_go_application_service.v8"
SERVICE_WORKLOAD_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v8"
SERVICE_WORKLOAD_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v8"
SERVICE_CREDENTIAL_REF = "MACRO_FABRIC_APPLICATION_TOKEN"
SERVICE_TEXT_CREDENTIAL_REF = "MASTERMIND_FABRIC_APPLICATION_TOKEN"
SERVICE_FAMILY_ROLES = (
    ("admin", "admin-orchestrator", "site_interactive", SERVICE_CREDENTIAL_REF),
    ("text", "mastermind-text", "site_batch", SERVICE_TEXT_CREDENTIAL_REF),
    ("chat", "mastermind-chat", "site_interactive", "MASTERMIND_FABRIC_CHAT_TOKEN"),
    ("brain", "brain", "site_interactive", "MACRO_BRAIN_FABRIC_APPLICATION_TOKEN"),
    ("ask", "ask-brain", "site_interactive", "MACRO_ASK_FABRIC_APPLICATION_TOKEN"),
)
# Preserve the five-role v6/v7 grammar. Only v8 adds generic workload authorities.
SERVICE_WORKLOAD_ROLES = SERVICE_FAMILY_ROLES + (
    ("batch", None, "site_batch", "MACRO_BATCH_FABRIC_APPLICATION_TOKEN"),
    ("analysis", None, "lobe_analysis", "MACRO_ANALYSIS_FABRIC_APPLICATION_TOKEN"),
    ("portfolio", None, "portfolio_analysis", "MACRO_PORTFOLIO_FABRIC_APPLICATION_TOKEN"),
)
SERVICE_ROLE_SCHEMA = "mastermind.native_go_application_service.v9"
SERVICE_ROLE_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v9"
SERVICE_ROLE_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v9"
SERVICE_FRESH_FAMILY_SCHEMA = "mastermind.native_go_application_service.v10"
SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v10"
SERVICE_FRESH_FAMILY_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v10"
# Closed service projections owned by the existing APPLICATION installer. A
# role's interactive session or another consumer's bearer is not this grant.
SERVICE_ROLE_PROFILES = {
    "hermes-secretary": ("hermes-secretary", "HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN"),
    "hermes-meta-ceo": ("hermes-meta-ceo", "HERMES_META_FABRIC_APPLICATION_TOKEN"),
    "hermes-attended": ("hermes-attended", "HERMES_ATTENDED_FABRIC_APPLICATION_TOKEN"),
}
SERVICE_SCOPE_FIELDS = frozenset({"principal_id", "caller_host", "native_host", "workload",
    "credential_ref", "capability_lane", "workload_profile", "account_profile"})
SERVICE_IDENTITY_FIELDS = frozenset({"dev", "ino", "uid", "gid", "mode", "nlink", "size",
    "mtime_ns", "ctime_ns"})


def application_enrollment_paths(startup, service_profile=None):
    """Fixed names in the original Go and finite installer owners."""
    store = Path(__file__).absolute().parent.parent.parent
    if service_profile is not None:
        if type(service_profile) is not str or service_profile not in SERVICE_ROLE_PROFILES:
            raise ValueError("native application service profile refused")
        return {"binding": startup.paths["go"] / ("application-service-" + service_profile + ".json"),
                "intent": store / "bootstrap" / (".go-service-enrollment-" + service_profile + "-v9.json"),
                "receipt": store / "bootstrap" / ("go-service-enrollment-" + service_profile + "-v9.json")}
    return {"binding": startup.paths["go"] / "application-service.json",
            "intent": store / "bootstrap/.go-service-enrollment-v1.json",
            "receipt": store / "bootstrap/go-service-enrollment-v1.json"}


def validate_application_role_scope(scope):
    """A finite source mapping, never caller-authored authority or a path."""
    profile = scope.get("service_profile") if type(scope) is dict else None
    if type(profile) is not str or profile not in SERVICE_ROLE_PROFILES:
        raise ValueError("native application service profile refused")
    lane, credential_ref = SERVICE_ROLE_PROFILES[profile]
    # Ordinary native conversations have their own inference-only workload.
    # Preserve the historical secretary/meta-CEO mapping and original owners.
    workload = "hermes_attended" if profile == "hermes-attended" else "site_interactive"
    if (scope.get("capability_lane") != lane or scope.get("principal_id") != lane
            or scope.get("credential_ref") != credential_ref
            or scope.get("workload") != workload
            or scope.get("workload_profile") != workload
            or "admin_pool_view" in scope):
        raise ValueError("native application role mapping refused")
    return profile


def application_service_owners(startup, *, application_http=False, glm_provider_profile=None):
    owners = {key: str(startup.paths[key]) for key in
            ("go", "db_path", "lock_path", "accounts_path")}
    if application_http:
        owners["provider_profile"] = str(application_http_profile(startup))
    if glm_provider_profile is not None:
        owners["glm_provider_profile"] = str(glm_provider_profile)
    return owners


def application_http_profile(startup):
    """Derive the incumbent owner path, never accept a new key-store input."""
    if startup.bailian_keys is None:
        raise ValueError("native application HTTP credential owner unavailable")
    path = Path(startup.bailian_keys.CONFIG_PATH)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("native application HTTP credential owner refused")
    return path


def application_http_recipe(startup, model, *, pool="bailian"):
    """One immutable recipe derived from the verified generation's source."""
    if startup.http_projection is None or startup.http_transports is None:
        raise ValueError("native application HTTP source unavailable")
    matches = [json.loads(raw) for raw in startup.http_recipes if json.loads(raw).get("model") == model and json.loads(raw).get("pool") == pool]
    if len(matches) != 1:
        raise ValueError("native application HTTP model unavailable")
    recipe = matches[0]
    startup.broker_module._application_http_recipe(recipe, pool=pool, model=model)
    return recipe


@dataclass(frozen=True)
class HTTPServiceProjection:
    recipe_json: str
    accounts: tuple
    provider_profile: Path



def application_glm_http_profile(startup):
    """Return the original key-owner path without reading credentials."""
    if startup.glm_keys is None:
        raise ValueError("GLM application key owner unavailable")
    path = Path(startup.glm_keys._config_path())
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("GLM application provider profile invalid")
    return path


@dataclass(frozen=True)
class GLMHTTPServiceProjection:
    recipes_json: tuple
    accounts: tuple
    provider_profile: Path
    provider_profile_identity_json: str
    provider_profile_sha256: str


def _glm_application_http_binding(startup, projection):
    """Use the original selected-account owner only at fresh-send preflight."""
    if type(projection) is not GLMHTTPServiceProjection or startup.glm_adapter is None:
        raise ValueError("GLM application HTTP projection unavailable")
    module = startup.glm_keys
    profile = projection.provider_profile
    expected_identity = json.loads(projection.provider_profile_identity_json)

    def credential(account):
        if module is None or sys.modules.get("glm_keys") is not module:
            raise ValueError("GLM application key owner changed")
        if Path(module._config_path()) != profile:
            raise ValueError("GLM application provider profile changed")
        _directory(profile.parent)
        if stat.S_IMODE(profile.parent.lstat().st_mode) != stat.S_IRWXU:
            raise ValueError("GLM application provider directory mode changed")
        raw, before = _service_private(profile)
        if before != expected_identity or hashlib.sha256(raw).hexdigest() != projection.provider_profile_sha256:
            raise ValueError("GLM application provider profile custody changed")
        if not module.enabled() or module.openai_base_url() != "https://api.z.ai/api/coding/paas/v4":
            raise ValueError("GLM application coding-plan configuration unavailable")
        value = module.selected_account_key(account, module.accounts(quiet=True))
        if application_file_identity(profile) != before or Path(module._config_path()) != profile:
            raise ValueError("GLM application provider profile changed during key selection")
        return value

    driver = startup.glm_adapter.GlmChatCompletionsDriver(
        transport=startup.handler.application_http_transport,
        realm_projection=startup.glm_projection,
        projection_sha256=startup.glm_projection_sha256)
    binding = startup.handler.ApplicationHTTPBinding(
        driver=driver, accounts=frozenset(projection.accounts),
        source_projection_sha256=startup.glm_projection_sha256, credential_loader=credential)
    for raw in projection.recipes_json:
        model = json.loads(raw)["model"]
        if binding.recipe(model) != application_http_recipe(startup, model, pool="glm"):
            raise ValueError("GLM application HTTP binding differs from current source")
    return binding


def _http_service_projection_map(value):
    if value is None:
        return {}
    if type(value) is HTTPServiceProjection:
        return {"bailian": value}
    if type(value) is GLMHTTPServiceProjection:
        return {"glm": value}
    if type(value) is dict and set(value).issubset({"bailian", "glm"}):
        if any(type(item) is not (HTTPServiceProjection if pool == "bailian"
                                 else GLMHTTPServiceProjection)
               for pool, item in value.items()):
            raise ValueError("application HTTP projection pool differs")
        return dict(value)
    raise ValueError("application HTTP projection shape invalid")


def _merge_http_service_projections(existing, added):
    if added is None:
        return existing
    result = _http_service_projection_map(existing)
    for pool, incoming in _http_service_projection_map(added).items():
        prior = result.get(pool)
        if prior is None:
            result[pool] = incoming
            continue
        if pool == "bailian":
            if prior != incoming:
                raise ValueError("Bailian application projection differs between services")
            continue
        if (prior.provider_profile, prior.provider_profile_identity_json,
                prior.provider_profile_sha256) != (
                incoming.provider_profile, incoming.provider_profile_identity_json,
                incoming.provider_profile_sha256):
            raise ValueError("GLM application provider custody differs between services")
        recipes = {json.loads(raw)["model"]: raw for raw in prior.recipes_json}
        for raw in incoming.recipes_json:
            model = json.loads(raw)["model"]
            if model in recipes and recipes[model] != raw:
                raise ValueError("GLM application recipe differs between services")
            recipes[model] = raw
        result[pool] = GLMHTTPServiceProjection(
            tuple(recipes[model] for model in sorted(recipes)),
            tuple(sorted(set(prior.accounts) | set(incoming.accounts))),
            prior.provider_profile, prior.provider_profile_identity_json,
            prior.provider_profile_sha256)
    return result


def _application_http_bindings(startup, projection):
    if type(projection) is HTTPServiceProjection:
        return _application_http_binding(startup, projection)
    return {pool: _application_http_binding(startup, item)
            for pool, item in _http_service_projection_map(projection).items()}


def _application_http_binding(startup, projection):
    """Compose the real H driver with B's original I/O and exact key owner."""
    # The historical enrollment authenticates recovery. Fresh admissions use
    # only this generation's current recipe and A's current scoped grant.
    if type(projection) is GLMHTTPServiceProjection:
        return _glm_application_http_binding(startup, projection)
    profile, module = application_http_profile(startup), startup.bailian_keys
    if projection.provider_profile != profile:
        raise ValueError("native application HTTP credential owner changed")
    def credential(account):
        # Current secret custody is checked only after original recovery, then
        # rechecked by H at send. Rotating/revoking it cannot erase old effects.
        if module.CONFIG_PATH != str(profile) or sys.modules.get("bailian_keys") is not module:
            raise ValueError("native application HTTP credential owner changed")
        _directory(profile.parent)
        _existing_database(profile)
        before = application_file_identity(profile)
        if stat.S_IMODE(profile.parent.lstat().st_mode) != 0o700 or before["mode"] != 0o600:
            raise ValueError("native application HTTP private profile refused")
        value = module._codex_key_value(account)
        if application_file_identity(profile) != before or module.CONFIG_PATH != str(profile):
            raise ValueError("native application HTTP profile changed during load")
        return value
    driver = startup.http_transports.BailianResponsesDriver(
        transport=startup.handler.application_http_transport, realm_projection=startup.http_projection,
        projection_sha256=startup.http_projection_sha256)
    binding = startup.handler.ApplicationHTTPBinding(driver, frozenset(projection.accounts),
        startup.http_projection_sha256, credential)
    for model in driver.identity.allowed_models:
        if binding.recipe(model) != application_http_recipe(startup, model):
            raise ValueError("native application HTTP driver differs from source recipe")
    return binding


def application_file_identity(path):
    value = Path(path).lstat()
    return {"dev": value.st_dev, "ino": value.st_ino, "uid": value.st_uid,
            "gid": value.st_gid, "mode": stat.S_IMODE(value.st_mode),
            "nlink": value.st_nlink, "size": value.st_size,
            "mtime_ns": value.st_mtime_ns, "ctime_ns": value.st_ctime_ns}


def _service_json(raw):
    try:
        def unique(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result
        def constant(_):
            raise ValueError("nonfinite value")
        if not 0 < len(raw) <= 65536:
            raise ValueError("size")
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
        json.dumps(value, allow_nan=False)
        if type(value) is not dict:
            raise ValueError("shape")
        return value
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        raise ValueError("native application enrollment document refused") from None


def _service_private(path):
    before = application_file_identity(path)
    raw = _regular(path, mode=0o600)
    if application_file_identity(path) != before:
        raise ValueError("native application enrollment identity changed")
    return raw, before


def _service_scope_binding(startup, scope, credential, *, admin=False):
    """One explicitly mapped Go role in the common native owner."""
    selected = "selection_purpose" in scope
    expected = SERVICE_SCOPE_FIELDS | ({"selection_purpose"} if selected else set())
    if admin and "admin_pool_view" in scope:
        expected |= {"admin_pool_view"}
    if (type(scope) is not dict or set(scope) != expected
            or type(scope["account_profile"]) is not str):
        raise ValueError("native application service scope refused")
    for key in ("principal_id", "caller_host", "native_host", "workload", "credential_ref"):
        if type(scope[key]) is not str or IDENTITY.fullmatch(scope[key]) is None:
            raise ValueError("native application service identity refused")
    if (scope["capability_lane"] != ("admin-orchestrator" if admin else "mastermind-text")
            or scope["workload_profile"] != ("site_interactive" if admin else "site_batch")
            or scope["credential_ref"] != (SERVICE_CREDENTIAL_REF if admin else SERVICE_TEXT_CREDENTIAL_REF)
            or admin and "admin_pool_view" in scope and type(scope["admin_pool_view"]) is not bool):
        raise ValueError("native application service mapping refused")
    profile = Path(scope["account_profile"])
    if not profile.is_absolute() or ".." in profile.parts:
        raise ValueError("native application service profile refused")
    return startup.handler.ApplicationServiceBinding(scope["principal_id"], scope["caller_host"],
        scope["workload"], scope["credential_ref"], credential, pool="go",
        selection_purpose=startup.handler.ApplicationSelectionPurpose(scope["selection_purpose"]) if selected else None,
        **({"admin_pool_view": scope["admin_pool_view"]} if admin and "admin_pool_view" in scope else {}))


def _validate_service_set(startup, document):
    fields = {"schema", "operation_id", "plan_digest", "source_generation", "ingress_digest",
              "scopes", "owners", "credentials"}
    if (set(document) != fields or document["schema"] != SERVICE_SET_SCHEMA
            or document["owners"] != application_service_owners(startup)
            or type(document["scopes"]) is not list or len(document["scopes"]) != 2
            or type(document["credentials"]) is not list or len(document["credentials"]) != 2):
        raise ValueError("native application service-set projection refused")
    for key in ("plan_digest", "source_generation", "ingress_digest"):
        if type(document[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", document[key]) is None:
            raise ValueError("native application service commitment refused")
    if type(document["operation_id"]) is not str or IDENTITY.fullmatch(document["operation_id"]) is None:
        raise ValueError("native application service operation refused")
    bindings = tuple(_service_scope_binding(startup, scope, credential, admin=index == 0)
                     for index, (scope, credential) in enumerate(zip(document["scopes"], document["credentials"])))
    common = {key: document["scopes"][0][key] for key in ("native_host", "account_profile")}
    roles = {(scope["capability_lane"], scope["workload_profile"], scope["credential_ref"])
             for scope in document["scopes"]}
    if (any(scope["native_host"] != common["native_host"]
            or scope["account_profile"] != common["account_profile"] for scope in document["scopes"])
            or roles != {("admin-orchestrator", "site_interactive", SERVICE_CREDENTIAL_REF),
                         ("mastermind-text", "site_batch", SERVICE_TEXT_CREDENTIAL_REF)}
            or len({(s.principal_id, s.host, s.workload) for s in bindings}) != 2
            or len({s.credential for s in bindings}) != 2):
        raise ValueError("native application closed service-set differs")
    return bindings, common["native_host"], Path(common["account_profile"])



def _service_family_scope_binding(startup, scope, credential, role):
    """One of five source-defined roles; no caller-defined role or authority."""
    mapping = {row[0]: row[1:] for row in SERVICE_FAMILY_ROLES}
    if role not in mapping:
        raise ValueError("native application service family role refused")
    if type(scope) is not dict:
        raise ValueError("native application service family scope refused")
    if role in ("admin", "text"):
        return _service_scope_binding(startup, scope, credential, admin=role == "admin")
    selected = "selection_purpose" in scope
    expected = SERVICE_SCOPE_FIELDS | ({"selection_purpose"} if selected else set())
    if (set(scope) != expected or type(scope["account_profile"]) is not str
            or (scope["capability_lane"], scope["workload_profile"], scope["credential_ref"]) != mapping[role]):
        raise ValueError("native application service family mapping refused")
    for key in ("principal_id", "caller_host", "native_host", "workload", "credential_ref"):
        if type(scope[key]) is not str or IDENTITY.fullmatch(scope[key]) is None:
            raise ValueError("native application service family identity refused")
    profile = Path(scope["account_profile"])
    if not profile.is_absolute() or ".." in profile.parts:
        raise ValueError("native application service family profile refused")
    return startup.handler.ApplicationServiceBinding(scope["principal_id"], scope["caller_host"],
        scope["workload"], scope["credential_ref"], credential, pool="go",
        selection_purpose=startup.handler.ApplicationSelectionPurpose(scope["selection_purpose"]) if selected else None)


def _service_routed_scope_binding(startup, scope, credential, role):
    """The same five stable identities with an explicit restrictive pool scope."""
    if type(scope) is not dict or "route_scope" not in scope:
        raise ValueError("native routed service scope refused")
    route_scope = startup.handler.ApplicationRouteScope(scope["route_scope"])
    original = {key: value for key, value in scope.items() if key != "route_scope"}
    binding = _service_family_scope_binding(startup, original, credential, role)
    return replace(binding, route_scope=route_scope)


def _service_workload_scope_binding(startup, scope, credential, role):
    """The retained routed family plus three explicit non-Admin workloads."""
    if role in {row[0] for row in SERVICE_FAMILY_ROLES}:
        return _service_routed_scope_binding(startup, scope, credential, role)
    mapping = {row[0]: row[1:] for row in SERVICE_WORKLOAD_ROLES[5:]}
    if (role not in mapping or type(scope) is not dict
            or set(scope) != SERVICE_SCOPE_FIELDS | {"selection_purpose", "route_scope"}
            or type(scope["account_profile"]) is not str
            or (scope["capability_lane"], scope["workload_profile"], scope["credential_ref"]) != mapping[role]
            or scope["workload"] != mapping[role][1]):
        raise ValueError("native application workload mapping refused")
    for key in ("principal_id", "caller_host", "native_host", "workload", "credential_ref"):
        if type(scope[key]) is not str or IDENTITY.fullmatch(scope[key]) is None:
            raise ValueError("native application workload identity refused")
    profile = Path(scope["account_profile"])
    if not profile.is_absolute() or ".." in profile.parts:
        raise ValueError("native application workload profile refused")
    return startup.handler.ApplicationServiceBinding(scope["principal_id"], scope["caller_host"],
        scope["workload"], scope["credential_ref"], credential, pool="go",
        selection_purpose=startup.handler.ApplicationSelectionPurpose(scope["selection_purpose"]),
        route_scope=startup.handler.ApplicationRouteScope(scope["route_scope"]))


def _validate_service_family(startup, document, *, routed=False, workloads=False, fresh_family=False):
    fields = {"schema", "operation_id", "plan_digest", "source_generation", "ingress_digest",
              "scopes", "owners", "credentials"}
    roles = SERVICE_WORKLOAD_ROLES if workloads or fresh_family else SERVICE_FAMILY_ROLES
    if (set(document) != fields or document["schema"] != (SERVICE_FRESH_FAMILY_SCHEMA if fresh_family else SERVICE_WORKLOAD_SCHEMA if workloads else SERVICE_ROUTED_SCHEMA if routed else SERVICE_FAMILY_SCHEMA)
            or document["owners"] != application_service_owners(startup)
            or type(document["scopes"]) is not list or len(document["scopes"]) != len(roles)
            or type(document["credentials"]) is not list or len(document["credentials"]) != len(roles)):
        raise ValueError("native application service family projection refused")
    for key in ("plan_digest", "source_generation", "ingress_digest"):
        if type(document[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", document[key]) is None:
            raise ValueError("native application service commitment refused")
    if type(document["operation_id"]) is not str or IDENTITY.fullmatch(document["operation_id"]) is None:
        raise ValueError("native application service operation refused")
    scope_binding = _service_workload_scope_binding if workloads or fresh_family else _service_routed_scope_binding if routed else _service_family_scope_binding
    if fresh_family and any(type(scope) is not dict or "selection_purpose" not in scope
                            for scope in document["scopes"]):
        raise ValueError("fresh application family requires explicit selection purposes")
    bindings = tuple(scope_binding(startup, scope, credential, role[0])
        for role, scope, credential in zip(roles, document["scopes"], document["credentials"]))
    first = document["scopes"][0]
    if (any(scope["native_host"] != first["native_host"]
            or scope["account_profile"] != first["account_profile"] for scope in document["scopes"])
            or len({(binding.principal_id, binding.host, binding.workload) for binding in bindings}) != len(roles)
            or len({binding.credential for binding in bindings}) != len(roles)):
        raise ValueError("native application closed service family differs")
    return bindings, first["native_host"], Path(first["account_profile"])



GLM_SERVICE_PROJECTION_FIELDS = frozenset({
    "pool", "source_projection_sha256", "recipes", "accounts"})
GLM_SERVICE_CUSTODY_FIELDS = frozenset({
    "provider_profile", "provider_profile_identity", "provider_profile_sha256"})


def validate_glm_application_http_projection(startup, record, *, normalized):
    """Parse a recorded projection without consulting current provider custody."""
    fields = GLM_SERVICE_PROJECTION_FIELDS | (GLM_SERVICE_CUSTODY_FIELDS if normalized else frozenset())
    if type(record) is not dict or set(record) != fields or record["pool"] != "glm":
        raise ValueError("GLM application service projection shape invalid")
    digest = record["source_projection_sha256"]
    accounts, recipes = record["accounts"], record["recipes"]
    if (type(digest) is not str or re.fullmatch("[0-9a-f]{64}", digest) is None or
            type(accounts) is not list or not 1 <= len(accounts) <= 128 or
            any(type(account) is not str or IDENTITY.fullmatch(account) is None for account in accounts) or
            accounts != sorted(set(accounts)) or type(recipes) is not list or
            not 1 <= len(recipes) <= 128):
        raise ValueError("GLM application service projection inventory invalid")
    encoded, models = [], []
    for recipe in recipes:
        if type(recipe) is not dict or recipe.get("source_projection_sha256") != digest:
            raise ValueError("GLM application service recipe projection differs")
        model = recipe.get("model")
        raw, _ = startup.broker_module._application_http_recipe(recipe, pool="glm", model=model)
        encoded.append(raw)
        models.append(model)
    if models != sorted(set(models)):
        raise ValueError("GLM application service recipes must have unique ordered models")
    if not normalized:
        return None
    profile, identity, profile_digest = (
        record["provider_profile"], record["provider_profile_identity"], record["provider_profile_sha256"])
    if (type(profile) is not str or not Path(profile).is_absolute() or ".." in Path(profile).parts or
            type(identity) is not dict or set(identity) != SERVICE_IDENTITY_FIELDS or
            any(type(value) is not int or value < 0 for value in identity.values()) or
            identity["mode"] != 0o600 or identity["nlink"] != 1 or
            type(profile_digest) is not str or re.fullmatch("[0-9a-f]{64}", profile_digest) is None):
        raise ValueError("GLM application service provider custody invalid")
    return GLMHTTPServiceProjection(
        tuple(encoded), tuple(accounts), Path(profile),
        startup.broker_module._application_json(identity), profile_digest)


def validate_application_service_document(startup, document):
    if type(document) is dict and document.get("schema") == SERVICE_FRESH_FAMILY_SCHEMA:
        return _validate_service_family(startup, document, fresh_family=True)
    if type(document) is dict and document.get("schema") == SERVICE_WORKLOAD_SCHEMA:
        return _validate_service_family(startup, document, workloads=True)
    if type(document) is dict and document.get("schema") == SERVICE_ROUTED_SCHEMA:
        return _validate_service_family(startup, document, routed=True)
    if type(document) is dict and document.get("schema") == SERVICE_FAMILY_SCHEMA:
        return _validate_service_family(startup, document)
    if type(document) is dict and document.get("schema") == SERVICE_SET_SCHEMA:
        return _validate_service_set(startup, document)
    """Parse only stable authentication/profile projection; no grant lookup."""
    fields = {"schema", "operation_id", "plan_digest", "source_generation", "ingress_digest",
              "scope", "owners", "credential"}
    http = type(document) is dict and document.get("schema") == SERVICE_HTTP_SCHEMA
    admin = type(document) is dict and document.get("schema") == SERVICE_ADMIN_SCHEMA
    role = type(document) is dict and document.get("schema") == SERVICE_ROLE_SCHEMA
    selected = type(document) is dict and document.get("schema") in (SERVICE_SELECTED_SCHEMA, SERVICE_ADMIN_SCHEMA, SERVICE_ROLE_SCHEMA)
    glm_projection = None
    if role and "glm_application_http" in document:
        if type(document.get("scope")) is not dict or "route_scope" not in document["scope"]:
            raise ValueError("GLM HTTP projection requires routed v9 role")
        fields = fields | {"glm_application_http"}
        glm_projection = validate_glm_application_http_projection(
            startup, document["glm_application_http"], normalized=True)
    if http:
        fields |= {"application_recipe", "application_accounts"}
    if (type(document) is not dict or set(document) != fields
            or document["schema"] != (SERVICE_ROLE_SCHEMA if role else SERVICE_HTTP_SCHEMA if http else SERVICE_ADMIN_SCHEMA if admin else
                                      SERVICE_SELECTED_SCHEMA if selected else SERVICE_SCHEMA)
            or document["owners"] != application_service_owners(startup, application_http=http, glm_provider_profile=glm_projection.provider_profile if glm_projection is not None else None)):
        raise ValueError("native application service projection refused")
    for key in ("plan_digest", "source_generation", "ingress_digest"):
        if type(document[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", document[key]) is None:
            raise ValueError("native application service commitment refused")
    if type(document["operation_id"]) is not str or IDENTITY.fullmatch(document["operation_id"]) is None:
        raise ValueError("native application service operation refused")
    scope = document["scope"]
    expected_scope = SERVICE_SCOPE_FIELDS | {"selection_purpose"} if selected else SERVICE_SCOPE_FIELDS
    if admin:
        expected_scope |= {"admin_pool_view"}
    if role:
        expected_scope |= {"service_profile"}
        if type(scope) is dict and "route_scope" in scope:
            expected_scope |= {"route_scope"}
    if type(scope) is not dict or set(scope) != expected_scope:
        raise ValueError("native application service scope refused")
    if admin and type(scope["admin_pool_view"]) is not bool:
        raise ValueError("native application metadata permission refused")
    for key in ("principal_id", "caller_host", "native_host", "workload", "credential_ref"):
        if type(scope[key]) is not str or IDENTITY.fullmatch(scope[key]) is None:
            raise ValueError("native application service identity refused")
    if role:
        validate_application_role_scope(scope)
    if ((not role and (scope["capability_lane"] != "admin-orchestrator"
            or scope["workload_profile"] != "site_interactive"
            or scope["credential_ref"] != SERVICE_CREDENTIAL_REF))
            or type(scope["account_profile"]) is not str):
        raise ValueError("native application service mapping refused")
    profile = Path(scope["account_profile"])
    if not profile.is_absolute() or ".." in profile.parts:
        raise ValueError("native application service profile refused")
    binding = startup.handler.ApplicationServiceBinding(scope["principal_id"], scope["caller_host"],
        scope["workload"], scope["credential_ref"], document["credential"],
        **({"pool": "bailian"} if http else {}),
        **({"selection_purpose": startup.handler.ApplicationSelectionPurpose(scope["selection_purpose"])}
           if selected else {}),
        **({"route_scope": startup.handler.ApplicationRouteScope(scope["route_scope"])}
           if role and "route_scope" in scope else {}),
        **({"admin_pool_view": scope["admin_pool_view"]} if admin else {}))
    if http:
        recipe, accounts = document["application_recipe"], document["application_accounts"]
        if (type(recipe) is not dict or scope["workload"] != "site_interactive"
                or type(accounts) is not list or not 1 <= len(accounts) <= 128
                or any(type(account) is not str or IDENTITY.fullmatch(account) is None for account in accounts)
                or len(set(accounts)) != len(accounts)):
            raise ValueError("native application HTTP service projection refused")
        # Structural integrity of the ORIGINAL receipt is independent of a
        # later catalogue revision or the original model's current availability.
        startup.broker_module._application_http_recipe(recipe, pool="bailian", model=recipe.get("model"))
        return (binding,), scope["native_host"], profile, HTTPServiceProjection(
            startup.broker_module._application_json(recipe), tuple(accounts), application_http_profile(startup))
    if glm_projection is not None:
        return (binding,), scope["native_host"], profile, glm_projection
    return (binding,), scope["native_host"], profile


def validate_completed_application_records(startup, raw, binding_identity, intent_raw, receipt_raw):
    """Validate the same completed enrollment chain from retained private bytes."""
    document, intent, receipt = map(_service_json, (raw, intent_raw, receipt_raw))
    result = validate_application_service_document(startup, document)
    fresh_family = document["schema"] == SERVICE_FRESH_FAMILY_SCHEMA
    workloads = document["schema"] == SERVICE_WORKLOAD_SCHEMA
    routed = document["schema"] == SERVICE_ROUTED_SCHEMA
    family = document["schema"] in (SERVICE_FAMILY_SCHEMA, SERVICE_ROUTED_SCHEMA, SERVICE_WORKLOAD_SCHEMA, SERVICE_FRESH_FAMILY_SCHEMA)
    service_set = document["schema"] in (SERVICE_SET_SCHEMA, SERVICE_FAMILY_SCHEMA, SERVICE_ROUTED_SCHEMA, SERVICE_WORKLOAD_SCHEMA, SERVICE_FRESH_FAMILY_SCHEMA)
    http = document["schema"] == SERVICE_HTTP_SCHEMA
    admin = document["schema"] == SERVICE_ADMIN_SCHEMA
    role = document["schema"] == SERVICE_ROLE_SCHEMA
    selected = document["schema"] in (SERVICE_SELECTED_SCHEMA, SERVICE_ADMIN_SCHEMA, SERVICE_ROLE_SCHEMA)
    intent_fields = {"schema", "operation_id", "plan_digest", "source_generation", "ingress_digest", "bundle"}
    scope_field = "scopes" if service_set else "scope"
    receipt_fields = {"schema", "operation_id", "plan_digest", "source_generation", "ingress_digest",
                      scope_field, "binding_sha256", "binding_identity", "accounts_sha256", "accounts_identity"}
    if role and "glm_application_http" in document:
        receipt_fields = receipt_fields | {"glm_application_http"}
        if receipt.get("glm_application_http") != document["glm_application_http"]:
            raise ValueError("GLM completed service projection differs from receipt")
    if http:
        receipt_fields |= {"application_recipe_digest", "source_projection_sha256", "provider_profile_identity"}
    if (set(intent) != intent_fields or intent["schema"] != (SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA if fresh_family else SERVICE_ROLE_ENROLLMENT_SCHEMA if role else SERVICE_WORKLOAD_ENROLLMENT_SCHEMA if workloads else SERVICE_ROUTED_ENROLLMENT_SCHEMA if routed else SERVICE_FAMILY_ENROLLMENT_SCHEMA if family else SERVICE_SET_ENROLLMENT_SCHEMA if service_set else SERVICE_HTTP_ENROLLMENT_SCHEMA if http else
            SERVICE_ADMIN_ENROLLMENT_SCHEMA if admin else
            SERVICE_SELECTED_ENROLLMENT_SCHEMA if selected else SERVICE_ENROLLMENT_SCHEMA)
            or set(receipt) != receipt_fields or receipt["schema"] != (SERVICE_FRESH_FAMILY_RECEIPT_SCHEMA if fresh_family else SERVICE_ROLE_RECEIPT_SCHEMA if role else SERVICE_WORKLOAD_RECEIPT_SCHEMA if workloads else SERVICE_ROUTED_RECEIPT_SCHEMA if routed else SERVICE_FAMILY_RECEIPT_SCHEMA if family else SERVICE_SET_RECEIPT_SCHEMA if service_set else SERVICE_HTTP_RECEIPT_SCHEMA if http else
                SERVICE_ADMIN_RECEIPT_SCHEMA if admin else
                SERVICE_SELECTED_RECEIPT_SCHEMA if selected else SERVICE_RECEIPT_SCHEMA)
            or any(intent[key] != document[key] or receipt[key] != document[key]
                   for key in ("operation_id", "plan_digest", "source_generation", "ingress_digest"))
            or receipt[scope_field] != document[scope_field]
            or receipt["binding_sha256"] != hashlib.sha256(raw).hexdigest()
            or receipt["binding_identity"] != binding_identity
            or type(intent["bundle"]) is not str or not Path(intent["bundle"]).is_absolute()
            or ".." in Path(intent["bundle"]).parts
            or type(receipt["accounts_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", receipt["accounts_sha256"]) is None
            or type(receipt["accounts_identity"]) is not dict
            or set(receipt["accounts_identity"]) != SERVICE_IDENTITY_FIELDS
            or any(type(v) is not int or v < 0 for v in receipt["accounts_identity"].values())):
        raise ValueError("native application enrollment receipt refused")
    if http:
        recipe = document["application_recipe"]
        _, digest = startup.broker_module._application_http_recipe(recipe, pool="bailian", model=recipe["model"])
        identity = receipt["provider_profile_identity"]
        if (receipt["application_recipe_digest"] != digest
                or receipt["source_projection_sha256"] != recipe["source_projection_sha256"]
                or type(identity) is not dict or set(identity) != SERVICE_IDENTITY_FIELDS
                or any(type(value) is not int or value < 0 for value in identity.values())
                or identity["mode"] != 0o600 or identity["nlink"] != 1):
            raise ValueError("native application HTTP receipt refused")
    return result


def load_completed_application_startup(startup, service_profile=None):
    """Actual-main-only reader of the original finite enrollment receipt.

    The accounts hash is a publication receipt, not perpetual authentication
    authority. Grant expiry or later accounts updates cannot erase recovery.
    """
    paths = application_enrollment_paths(startup, service_profile)
    present = {name: os.path.lexists(path) for name, path in paths.items()}
    if not any(present.values()):
        return (), None, None
    if not all(present.values()):
        raise ValueError("native application enrollment is incomplete")
    for directory in (startup.paths["go"], paths["intent"].parent,
                      paths["intent"].parent.parent):
        _directory(directory)
        if stat.S_IMODE(directory.lstat().st_mode) != 0o700:
            raise ValueError("native application enrollment private owner refused")
    raw, binding_identity = _service_private(paths["binding"])
    intent_raw, intent_identity = _service_private(paths["intent"])
    receipt_raw, receipt_identity = _service_private(paths["receipt"])
    result = validate_completed_application_records(startup, raw, binding_identity, intent_raw, receipt_raw)
    document = _service_json(raw)
    if ((document["schema"] == SERVICE_ROLE_SCHEMA) != (service_profile is not None)
            or (service_profile is not None
                and document["scope"]["service_profile"] != service_profile)):
        raise ValueError("native application enrollment profile differs")
    if (application_file_identity(paths["binding"]) != binding_identity
            or application_file_identity(paths["intent"]) != intent_identity
            or application_file_identity(paths["receipt"]) != receipt_identity):
        raise ValueError("native application enrollment changed during startup")
    return result


def load_all_completed_application_startup(startup):
    """Join role receipts to the incumbent family, without changing its loader.

    Family upgrades retain the original legacy-only reader. Actual startup
    joins the same physical owners and refuses partial role publications.
    """
    paths = tuple(path for profile in (None, *SERVICE_ROLE_PROFILES)
                  for path in application_enrollment_paths(startup, profile).values())
    def snapshot():
        return tuple(application_file_identity(path) if os.path.lexists(path) else None
                     for path in paths)
    before = snapshot()
    legacy = load_completed_application_startup(startup)
    services, host, account_profile = legacy[:3]
    http_projection = legacy[3] if len(legacy) == 4 else None
    for profile in SERVICE_ROLE_PROFILES:
        result = load_completed_application_startup(startup, profile)
        if not result[0]:
            continue
        if len(result) > 3:
            http_projection = _merge_http_service_projections(http_projection, result[3])
        if services and (result[1], result[2]) != (host, account_profile):
            raise ValueError("native application services have different physical owners")
        for candidate in result[0]:
            if any(candidate.principal_id == existing.principal_id
                   or candidate.credential_ref == existing.credential_ref
                   or candidate.credential == existing.credential for existing in services):
                raise ValueError("native application service identity collision")
            services += (candidate,)
        host, account_profile = result[1:3]
    if snapshot() != before:
        raise ValueError("native application enrollments changed during composition")
    result = (services, host, account_profile)
    return (*result, http_projection) if http_projection is not None else result


def main(*, verified_root, verified_metadata, application_services=(), application_host=None,
         application_account_path=None):
    if type(application_services) is not tuple:
        raise ValueError("native Go application startup incomplete")
    startup = inspect(verified_root=verified_root, verified_metadata=verified_metadata)
    state_override = os.environ.get("GO_STATE_DIR")
    if state_override and Path(state_override).absolute() != startup.paths["go"]:
        raise ValueError("native Go state override conflicts with original owner")
    completed = load_all_completed_application_startup(startup)
    http_projection = completed[3] if len(completed) == 4 else None
    completed = completed[:3]
    if completed[0]:
        if not application_services and application_host is None and application_account_path is None:
            application_services, application_host, application_account_path = completed
        elif (application_services, application_host, Path(application_account_path) if application_account_path is not None else None) != completed:
            raise ValueError("native Go explicit startup conflicts with completed enrollment")
    if not application_services:
        if application_host is not None or application_account_path is not None:
            raise ValueError("native Go application startup incomplete")
        # Missing enrollment remains disabled. Never invent a binding or open
        # the broker merely to keep its argument paired with an empty tuple.
        return startup.handler.main()
    if (not all(isinstance(s, startup.handler.ApplicationServiceBinding) for s in application_services)
            or not isinstance(application_host, str) or IDENTITY.fullmatch(application_host) is None
            or not isinstance(application_account_path, (str, Path))):
        raise ValueError("native Go application startup incomplete")
    # go_ctl supports an explicitly configured original account profile. Its
    # completed startup owner supplies that exact approved path; HOME or an
    # application request cannot nominate a replacement profile.
    account_path = Path(application_account_path)
    inherited_account = os.environ.get("GO_ACCOUNTS_PATH")
    if (not account_path.is_absolute() or ".." in account_path.parts
            or not inherited_account or Path(inherited_account).absolute() != account_path):
        raise ValueError("native Go account profile conflicts with verified startup")
    for key in ("GO_UPSTREAM_BASE", "GO_SHIM_PORT"):
        if os.environ.get(key, startup.handler.DEFAULTS[key]) != startup.handler.DEFAULTS[key]:
            raise ValueError("native Go transport conflicts with verified startup")
    for key in ("GO_WIRE_COMPAT_PATH", "GO_WIRE_MATRIX_PATH", "GO_MODEL_TIERS_PATH", "GO_WEIGHTS_PATH"):
        if Path(os.environ.get(key, startup.handler.DEFAULTS[key])).absolute() != Path(startup.handler.DEFAULTS[key]):
            raise ValueError("native Go data path conflicts with original owner")
    env_paths = {"POOL_BROKER_DB": "db_path", "POOL_BROKER_LOCK": "lock_path",
                 "POOL_ACCOUNTS_YAML": "accounts_path", "POOL_STATUS_JSON": "status_json",
                 "POOL_GROK_MARKER": "grok_marker"}
    for env, key in env_paths.items():
        value = os.environ.get(env)
        if value and Path(value).absolute() != startup.paths[key]:
            raise ValueError("native Go broker override conflicts with original owner")
    host_override = os.environ.get("POOL_BROKER_HOST")
    if host_override and host_override != application_host:
        raise ValueError("native Go host override conflicts with verified startup")
    # Broker.__init__ may initialize its existing schema, so qualify the actual
    # existing owner first. Missing DB is never permission to create a shadow.
    _directory(startup.paths["db_path"].parent)
    before = _existing_database(startup.paths["db_path"])
    # Read no grant or secret here. Check the ORIGINAL filesystem owners;
    # A still reads and authorizes its current grant inside each transaction.
    _directory(startup.paths["accounts_path"].parent.parent)
    _directory(startup.paths["accounts_path"].parent)
    _existing_database(startup.paths["accounts_path"])
    _directory(account_path.parent)
    _existing_database(account_path)
    if (stat.S_IMODE(account_path.parent.stat().st_mode) != 0o700
            or stat.S_IMODE(account_path.stat().st_mode) != 0o600):
        raise ValueError("native Go original account profile custody refused")
    selection_profile = None
    if any(service.selection_purpose is not None for service in application_services):
        # Compare only owner paths at startup. Original recovery must remain
        # available when current policy or quality data is missing/revoked.
        owner = sys.modules["native_runtime_bindings"].owner_path
        here = Path(__file__).absolute().parent
        configured_ledger = Path(os.path.abspath(sys.modules["pool_ledger"].LEDGER_PATH))
        configured_policy = Path(os.path.abspath(sys.modules["pick"].POOLS_YAML))
        if (owner(configured_ledger, here) != startup.paths["ledger_path"]
                or owner(configured_policy, here) != startup.paths["policy_path"]):
            raise ValueError("native application selection owner mapping differs")
        # Keep the exact qualified original paths. An unrelated symlink alias
        # is never adopted as another mutable route to the same data owner.
        sys.modules["pool_ledger"].LEDGER_PATH = str(startup.paths["ledger_path"])
        sys.modules["pick"].POOLS_YAML = str(startup.paths["policy_path"])
        selection_profile = sys.modules["go_lease_gateway"].ApplicationSelectionProfile(
            source_generation=startup.generation, ingress_digest=startup.handler_sha256,
            account_profile=str(account_path))
    for key in ("lock_path",):
        if os.path.lexists(startup.paths[key]):
            _regular(startup.paths[key])
    with startup.yaml_runtime.held_yaml(startup.yaml_archive, startup.yaml_provenance, startup.yaml_check):
        broker = startup.broker_module.Broker(**{key: str(startup.paths[key]) for key in
            ("db_path", "lock_path", "accounts_path", "status_json", "hosts_path", "grok_marker")},
            this_host=application_host)
        if before != _existing_database(startup.paths["db_path"]):
            raise ValueError("native Go original database changed during startup")
        return startup.handler.main(application_broker=broker, application_services=application_services,
            **({"application_selection_profile": selection_profile} if selection_profile is not None else {}),
            **({"application_http_binding": _application_http_bindings(startup, http_projection)}
               if http_projection is not None else {}))


if __name__ == "__main__":
    raise SystemExit("native Go entry requires the verified original ingress")
