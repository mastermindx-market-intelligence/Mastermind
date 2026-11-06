"""Read-only historical proof for the original News packet-retention refusal.

This is a fixed-case diagnostic, not a reconciliation or lifecycle owner. It
neither writes receipts nor changes status, retry, acceptance or admission.
The historical native-owner evidence is trusted only within the incumbent
same-OS-principal model. It does not prove absence of all telemetry transport.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import stat

from artifact_delivery import DirectoryChain
from native_runtime_bindings import owner_path

HERE = Path(__file__).resolve().parent
RUN = "news-9612-exact-3a663-release-review-20261021"
ROOT = "news-cockpit-rebuild-20261018-astra-01"
SUBJECT = "3a663ae70ecbd8a4130de9c95dbb6d940d181e04"
SCHEMA = "mastermind.fabric_plain_packet_historical_check.v1"
RECONCILIATION_SUFFIX = ".plain-packet-reconciliation.json"
ARTIFACTS = {
    "request.json": "b5bb695de6933a6bc93cc85d4f0e05d542796b839f15c4118f4ec4c5c27736ab",
    "request-launch.json": "cb921d63a414d918d495edbd7645eb3cf570a3edf08199f40c97895d0ee5d78d",
    "request-return.json": "e4d74823bca187ba9f799348247f223d9d535e539e1e4ce22d65f27eebe1f0b6",
    "continuation-request.json": "fac0a8886027ac68d0b15ab1da881355e49c479d14d6396bde4ab7fd463f0769",
    "continuation-finished.json": "ab7f106d6d5c4d36b2c0ebd0baae153610ba79e1eaf912ee7efb9f19c0a8ba3c",
    "log": "d8e1fdc7abd879e1b703d66e49e3a82e5d9295235afbec286e6232210792b3fb",
    "request.packet": "a2b5dfdadbc61e5f6bcc5ad8d7eea05535b5f35976e62dc5d699ffc4715d89c4",
    "routing-process.jsonl": "29fe01552c731ac69f693ed78ab2cd2b5b8fccb078dac0289f28685ac587b445",
}
GENERATIONS = (
    "4cf603706381969f2a784adb38ed9e6ace2b14188444e5bbb8085d2c31c472ec",
    "bb80e3793f116f43ef73d56f60d71edde7b1773d70dc5444973d019c3e66132c",
)
SOURCES = {
    "remote_sub.sh": "f6ae11dc1e320506efc950fc4bc7a352af34e52b67887d901b35274034dcf48b",
    "fabric_task.py": "f559e7d9b4186a013335082defe549a2ff11a4fe6689aad2e1b0f6ae328392e4",
    "lease_broker.py": "58916ce301ad588238ef0c848321114f4ecdc52d7bb59b612285822f8ae211d0",
    "quota_circuit.py": "9890eb620e3ee859c759aa072d2f354eee1f82acdad804b643176de97005b84d",
    "pick.py": "74bd656884739d61e7a1892735fdcf7844e030fa55b2dc51ecaad1b4c8560286",
    "remote_sub_helpers.py": "2840d0bf548f80aed8e8b02db011dc2a38e402d26342545075d785b5cfed84ba",
    "commission_deadline.py": "7b82d2824e9a2004b2a482f0b49ec3965729436fcd9a2a6568e8e8583bd381dc",
    "lane_runtime.py": "966869a4137545203faa2269faeed15cd0a096b5611161d242e2fb13b7c27937",
    "fabric_continuation.py": "9fea1e7fcf6b7bb524067abaf8d74c3113aa55d122183659e14d1e4319274562",
}


class Unqualified(ValueError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Unqualified("duplicate_json_key")
            result[key] = value
        return result
    def invalid_constant(_):
        raise Unqualified("nonfinite_json_number")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class EvidenceReadSet:
    """Keep file descriptors and every directory edge until final revalidation."""
    def __init__(self):
        self.stack = ExitStack()
        self.files = []
        self.chains = {}
        self.directory_requirements = {}
        self.absent_paths = []

    def chain(self, path):
        path = Path(path)
        if path not in self.chains:
            self.chains[path] = self.stack.enter_context(DirectoryChain(path))
        return self.chains[path]

    def require_absent(self, path):
        path = Path(path)
        chain = self.chain(path.parent)
        self.absent_paths.append((chain, path.name))
        self.verify()

    def require_directory(self, path, *, mode):
        chain = self.chain(path)
        info = os.fstat(chain.fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != mode:
            raise Unqualified("native_generation_directory_custody")
        self.directory_requirements[chain.fd] = (info.st_dev, info.st_ino, info.st_uid, mode)
        self.verify()

    def read(self, path, *, mode, limit):
        path = Path(path)
        chain = self.chain(path.parent)
        chain.verify()
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=chain.fd)
        self.stack.callback(os.close, fd)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != mode or before.st_nlink != 1
                or not 0 < before.st_size <= limit):
            raise Unqualified("file_custody_or_size")
        data = b""
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        expected = identity(before)
        self.files.append((chain, path.name, fd, expected))
        if len(data) != before.st_size or len(data) > limit:
            raise Unqualified("file_size_changed")
        self.verify()
        return data

    def verify(self):
        for chain in self.chains.values():
            chain.verify()
        for chain, name in self.absent_paths:
            try:
                os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise Unqualified("contradictory_original_result")
        for fd, expected in self.directory_requirements.items():
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) != expected:
                raise Unqualified("native_generation_directory_changed")
        for chain, name, fd, expected in self.files:
            visible = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
            if identity(os.fstat(fd)) != expected or identity(visible) != expected:
                raise Unqualified("evidence_changed")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stack.close()


def exact_inventory(chain, *, allow_reconciliation=False):
    # Absence of other artifacts is only a contradiction check. Positive proof
    # comes from the retained hash chain and the reviewed historical control flow.
    names = set()
    with os.scandir(chain.fd) as entries:
        for entry in entries:
            if entry.name.startswith(RUN):
                names.add(entry.name)
                if len(names) > len(ARTIFACTS) + int(allow_reconciliation):
                    raise Unqualified("contradictory_run_artifact")
    wanted = {RUN + "." + suffix for suffix in ARTIFACTS}
    receipt = RUN + RECONCILIATION_SUFFIX
    if names != wanted and not (allow_reconciliation and names == wanted | {receipt}):
        raise Unqualified("run_inventory_mismatch")
    chain.verify()
    return names


def validate_chain(raw):
    request = strict_json(raw["request.json"])
    launch = strict_json(raw["request-launch.json"])
    returned = strict_json(raw["request-return.json"])
    continuation = strict_json(raw["continuation-request.json"])
    finished = strict_json(raw["continuation-finished.json"])
    routing = strict_json(raw["routing-process.jsonl"])
    for value in (request, launch, returned, continuation, finished, routing):
        if type(value) is not dict:
            raise Unqualified("record_not_object")
    for value in (request, launch, returned, continuation, finished):
        if value.get("root_id") != ROOT or value.get("parent_run_id") != ROOT:
            raise Unqualified("lineage_mismatch")
    for value in (request, launch, returned):
        if value.get("run_id") != RUN:
            raise Unqualified("run_mismatch")
    packet = raw["request.packet"]
    if (request.get("schema") != "mastermind.fabric_request_artifact.v1"
            or request.get("task_class") != "review"
            or request.get("cwd") != "~"
            or request.get("automatic_background_execution") is not False
            or request.get("packet") != RUN + ".request.packet"
            or type(request.get("packet_bytes")) is not int
            or request["packet_bytes"] != len(packet)
            or request.get("packet_sha256") != digest(packet)
            or SUBJECT.encode() not in packet or ROOT.encode() not in packet):
        raise Unqualified("request_binding")
    route = {"HOST": "ubuntu0", "KEY": "Chris", "MODE": "qwen",
             "MODEL": "qwen3.8-max", "POOL": "bailian",
             "REASON": "execute_order_bailian"}
    if (launch.get("schema") != "mastermind.fabric_request_launch.v1"
            or launch.get("state") != "LAUNCH_ATTEMPT_RESERVED"
            or launch.get("capacity_handoff") is not True
            or launch.get("route") != route
            or launch.get("request_sha256") != digest(raw["request.json"])
            or launch.get("packet_sha256") != digest(packet)
            or launch.get("native_sources") != {
                name: SOURCES[name]
                for name in ("remote_sub.sh", "lease_broker.py", "quota_circuit.py")}):
        raise Unqualified("launch_binding")
    if (returned.get("schema") != "mastermind.fabric_request_return.v1"
            or returned.get("state") != "NATIVE_CONTROLLER_RETURNED"
            or type(returned.get("controller_rc")) is not int
            or returned["controller_rc"] != 78
            or returned.get("request_sha256") != digest(raw["request.json"])
            or returned.get("launch_sha256") != digest(raw["request-launch.json"])
            or returned.get("log_sha256") != digest(raw["log"])
            or "prelease_sha256" not in returned or returned["prelease_sha256"] is not None):
        raise Unqualified("controller_return_binding")
    prefix = "2026-10-21T04:42Z [remote_sub id=" + RUN + " host=ubuntu0] "
    expected_log = (prefix + "RUN_RESERVED explicit=1\n" + prefix
                    + "PLAIN_PACKET_RETENTION_REFUSED rc=78 before_lease=1\n").encode()
    if raw["log"] != expected_log:
        raise Unqualified("historical_failure_phase")
    if (continuation.get("schema") != "mastermind.fabric_continuation.v1"
            or continuation.get("origin_run_id") != RUN
            or continuation.get("background_execution") is not False
            or type(continuation.get("deadline_ns")) is not int
            or continuation["deadline_ns"] <= 0
            or type(continuation.get("max_attempts")) is not int
            or continuation["max_attempts"] != 3
            or type(continuation.get("wall_seconds")) is not int
            or continuation["wall_seconds"] != 7200
            or finished.get("schema") != "mastermind.fabric_continuation.v1"
            or finished.get("origin_run_id") != RUN
            or finished.get("effective_run_id") != RUN
            or finished.get("background_execution") is not False
            or type(finished.get("controller_rc")) is not int
            or finished["controller_rc"] != 78
            or finished.get("reason") != "continuation_evidence_unqualified"):
        raise Unqualified("continuation_binding")
    stdout = ("POOL=bailian KEY=Chris MODEL=qwen3.8-max "
              "REASON=execute_order_bailian HOST=ubuntu0 MODE=qwen\n").encode()
    cleanup = routing.get("cleanup")
    if (routing.get("schema") != "mastermind.local_owned_process_receipt.v1"
            or routing.get("label") != RUN + ".routing"
            or type(routing.get("returncode")) is not int or routing["returncode"] != 0
            or routing.get("timed_out") is not False
            or routing.get("stdout_truncated") is not False
            or routing.get("stderr_truncated") is not False
            or routing.get("runtime_failure_code", "missing") is not None
            or type(routing.get("pid")) is not int or routing["pid"] <= 0
            or type(routing.get("pgid")) is not int or routing["pgid"] != routing["pid"]
            or type(routing.get("stdout_bytes")) is not int
            or routing["stdout_bytes"] != len(stdout)
            or routing.get("stdout_sha256") != digest(stdout)
            or type(routing.get("stderr_bytes")) is not int or routing["stderr_bytes"] != 0
            or type(cleanup) is not dict
            or cleanup.get("identity_verified") is not True
            or cleanup.get("census_proven") is not True
            or type(cleanup.get("residual_count")) is not int or cleanup["residual_count"] != 0
            or cleanup.get("status") != "not_needed"
            or cleanup.get("reason") != "normal_completion"
            or cleanup.get("error_code", "missing") is not None
            or cleanup.get("stdout_capture_complete") is not True
            or cleanup.get("stderr_capture_complete") is not True
            or cleanup.get("stdin_delivery_complete") is not True
            or any(cleanup.get(key, "missing") is not None for key in (
                "stdout_capture_error", "stderr_capture_error", "stdin_delivery_error"))):
        raise Unqualified("routing_settlement_unqualified")


def _historical_proof(held, run_id, root_id, *, allow_reconciliation=False):
    if run_id != RUN or root_id != ROOT:
        raise Unqualified("unsupported_original_request")
    state = owner_path(HERE / "state/remote_sub", HERE)
    store = state.parents[2] / "native-code-releases"
    state_chain = held.chain(state)
    held.require_absent(owner_path(HERE / "lanes" / (RUN + ".remote.stdout"), HERE))
    inventory = exact_inventory(state_chain, allow_reconciliation=allow_reconciliation)
    raw = {}
    for suffix, expected in ARTIFACTS.items():
        data = held.read(state / (RUN + "." + suffix), mode=0o600, limit=32768)
        if digest(data) != expected:
            raise Unqualified("historical_artifact_digest:" + suffix)
        raw[suffix] = data
    validate_chain(raw)
    manifests = {}
    for generation in GENERATIONS:
        root = store / generation
        for directory, mode in ((store, 0o700), (root, 0o555), (root / "ext", 0o555)):
            held.require_directory(directory, mode=mode)
        manifest_raw = held.read(root / "RELEASE.json", mode=0o444, limit=262144)
        manifest = strict_json(manifest_raw)
        if (type(manifest) is not dict or set(manifest) != {
                "digest", "schema", "files", "links", "entrypoints", "stable_ext"}
                or manifest["schema"] != "native-code-generation.v1"
                or manifest["digest"] != generation
                or manifest["stable_ext"] != str(state.parents[1])
                or type(manifest["files"]) is not dict
                or manifest["entrypoints"] != {
                    "pool": "pool", "remote": "ext/remote_sub.sh", "task": "ext/fabric_task.py"}):
            raise Unqualified("historical_generation_binding")
        material = {k: v for k, v in manifest.items() if k != "digest"}
        canonical = json.dumps(material, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode()
        if digest(canonical) != generation:
            raise Unqualified("historical_generation_digest")
        for name, expected in SOURCES.items():
            if manifest["files"].get("ext/" + name) != expected:
                raise Unqualified("historical_source_manifest")
            data = held.read(root / "ext" / name, mode=0o555, limit=2097152)
            if digest(data) != expected:
                raise Unqualified("historical_source_bytes")
        manifests[generation] = digest(manifest_raw)
    if exact_inventory(state_chain, allow_reconciliation=allow_reconciliation) != inventory:
        raise Unqualified("run_inventory_changed")
    held.verify()
    result = {
        "schema": SCHEMA, "run_id": RUN, "root_id": ROOT, "parent_run_id": ROOT,
        "review_subject_sha": SUBJECT, "predicate": "QUALIFIED_PRELEASE_WORKER_ABSENCE",
        "evidence_basis": "retained_native_owner_hash_chain_and_historical_control_flow",
        "artifact_sha256": dict(ARTIFACTS), "historical_source_sha256": dict(SOURCES),
        "compatible_generation_manifest_sha256": manifests,
        "original_local_result_absent": True,
        "original_selected_generation_recorded": False,
        "telemetry_transport_absence_claimed": False,
        "operator_continuation_environment_recorded": False,
        "canonical_state_changed": False, "reconciliation_performed": False,
        "retry_allowed": False, "acceptance_eligible": False,
        "review_result_available": False,
    }
    result["proof_sha256"] = digest(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    return result


def check_original(run_id, root_id):
    with EvidenceReadSet() as held:
        return _historical_proof(held, run_id, root_id)
