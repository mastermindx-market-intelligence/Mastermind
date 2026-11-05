"""Verified in-process ingress for the existing Go service and broker.

The release launcher supplies its already verified immutable descriptor. This
module does not select a generation, enroll a service, mint a key, or own a
server. Import and inspect are read-only. Only main enters the original B.main.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    "quota_circuit", "model_tier", "pool_status", "lease_broker",
    "go_lease_capability", "go_lease_gateway", "paid_yaml_runtime", "go_application_handler",
    "fabric_policy_snapshot",
)
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
    for name in MODULES:
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
    for name in MODULES[1:]:
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
    return Startup(handler, broker, paths, root.name, yaml_runtime,
                   yaml_bytes[0], yaml_bytes[1], yaml_check, sys.modules["fabric_policy_snapshot"])


SERVICE_SCHEMA = "mastermind.native_go_application_service.v1"
SERVICE_ENROLLMENT_SCHEMA = "native-go-service-enrollment.v1"
SERVICE_RECEIPT_SCHEMA = "native-go-service-enrollment-completed.v1"
SERVICE_CREDENTIAL_REF = "MACRO_FABRIC_APPLICATION_TOKEN"
SERVICE_SCOPE_FIELDS = frozenset({"principal_id", "caller_host", "native_host", "workload",
    "credential_ref", "capability_lane", "workload_profile", "account_profile"})
SERVICE_IDENTITY_FIELDS = frozenset({"dev", "ino", "uid", "gid", "mode", "nlink", "size",
    "mtime_ns", "ctime_ns"})


def application_enrollment_paths(startup):
    """Fixed names in the original Go and finite installer owners."""
    store = Path(__file__).absolute().parent.parent.parent
    return {"binding": startup.paths["go"] / "application-service.json",
            "intent": store / "bootstrap/.go-service-enrollment-v1.json",
            "receipt": store / "bootstrap/go-service-enrollment-v1.json"}


def application_service_owners(startup):
    return {key: str(startup.paths[key]) for key in
            ("go", "db_path", "lock_path", "accounts_path")}


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


def validate_application_service_document(startup, document):
    """Parse only stable authentication/profile projection; no grant lookup."""
    fields = {"schema", "operation_id", "plan_digest", "source_generation", "ingress_digest",
              "scope", "owners", "credential"}
    if (type(document) is not dict or set(document) != fields
            or document["schema"] != SERVICE_SCHEMA
            or document["owners"] != application_service_owners(startup)):
        raise ValueError("native application service projection refused")
    for key in ("plan_digest", "source_generation", "ingress_digest"):
        if type(document[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", document[key]) is None:
            raise ValueError("native application service commitment refused")
    if type(document["operation_id"]) is not str or IDENTITY.fullmatch(document["operation_id"]) is None:
        raise ValueError("native application service operation refused")
    scope = document["scope"]
    if type(scope) is not dict or set(scope) != SERVICE_SCOPE_FIELDS:
        raise ValueError("native application service scope refused")
    for key in ("principal_id", "caller_host", "native_host", "workload", "credential_ref"):
        if type(scope[key]) is not str or IDENTITY.fullmatch(scope[key]) is None:
            raise ValueError("native application service identity refused")
    if (scope["capability_lane"] != "admin-orchestrator"
            or scope["workload_profile"] != "site_interactive"
            or scope["credential_ref"] != SERVICE_CREDENTIAL_REF
            or type(scope["account_profile"]) is not str):
        raise ValueError("native application service mapping refused")
    profile = Path(scope["account_profile"])
    if not profile.is_absolute() or ".." in profile.parts:
        raise ValueError("native application service profile refused")
    binding = startup.handler.ApplicationServiceBinding(scope["principal_id"], scope["caller_host"],
        scope["workload"], scope["credential_ref"], document["credential"])
    return (binding,), scope["native_host"], profile


def load_completed_application_startup(startup):
    """Actual-main-only reader of the original finite enrollment receipt.

    The accounts hash is a publication receipt, not perpetual authentication
    authority. Grant expiry or later accounts updates cannot erase recovery.
    """
    paths = application_enrollment_paths(startup)
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
    document, intent, receipt = map(_service_json, (raw, intent_raw, receipt_raw))
    result = validate_application_service_document(startup, document)
    intent_fields = {"schema", "operation_id", "plan_digest", "source_generation", "ingress_digest", "bundle"}
    receipt_fields = {"schema", "operation_id", "plan_digest", "source_generation", "ingress_digest",
                      "scope", "binding_sha256", "binding_identity", "accounts_sha256", "accounts_identity"}
    if (set(intent) != intent_fields or intent["schema"] != SERVICE_ENROLLMENT_SCHEMA
            or set(receipt) != receipt_fields or receipt["schema"] != SERVICE_RECEIPT_SCHEMA
            or any(intent[key] != document[key] or receipt[key] != document[key]
                   for key in ("operation_id", "plan_digest", "source_generation", "ingress_digest"))
            or receipt["scope"] != document["scope"]
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
    if (application_file_identity(paths["binding"]) != binding_identity
            or application_file_identity(paths["intent"]) != intent_identity
            or application_file_identity(paths["receipt"]) != receipt_identity):
        raise ValueError("native application enrollment changed during startup")
    return result


def main(*, verified_root, verified_metadata, application_services=(), application_host=None,
         application_account_path=None):
    if type(application_services) is not tuple:
        raise ValueError("native Go application startup incomplete")
    startup = inspect(verified_root=verified_root, verified_metadata=verified_metadata)
    state_override = os.environ.get("GO_STATE_DIR")
    if state_override and Path(state_override).absolute() != startup.paths["go"]:
        raise ValueError("native Go state override conflicts with original owner")
    completed = load_completed_application_startup(startup)
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
    for key in ("lock_path",):
        if os.path.lexists(startup.paths[key]):
            _regular(startup.paths[key])
    with startup.yaml_runtime.held_yaml(startup.yaml_archive, startup.yaml_provenance, startup.yaml_check):
        broker = startup.broker_module.Broker(**{key: str(startup.paths[key]) for key in
            ("db_path", "lock_path", "accounts_path", "status_json", "hosts_path", "grok_marker")},
            this_host=application_host)
        if before != _existing_database(startup.paths["db_path"]):
            raise ValueError("native Go original database changed during startup")
        return startup.handler.main(application_broker=broker, application_services=application_services)


if __name__ == "__main__":
    raise SystemExit("native Go entry requires the verified original ingress")
